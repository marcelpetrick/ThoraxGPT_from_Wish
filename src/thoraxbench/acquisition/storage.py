# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Filesystem helpers for acquisition: usage, safe extraction and SHA-256 manifests.

Nothing here parses pixel data. Usage measurement only calls ``lstat``; it never opens files.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

from thoraxbench.acquisition.nbia import AcquisitionError, BudgetError

#: Dataset-root metadata files that the SHA-256 manifest does not list.
META_FILES = frozenset({"_sha256.txt", "_acquisition.json", "_api_log.jsonl"})
MD5_MEMBER = "md5hashes.csv"


def usage_bytes(root: Path) -> int:
    """Apparent size of every file below *root* (``lstat`` only, 0 if missing)."""
    total = 0
    for directory, _dirs, files in os.walk(root):
        for name in files:
            try:
                total += os.lstat(os.path.join(directory, name)).st_size
            except FileNotFoundError:  # pragma: no cover - file removed during the walk
                continue
    return total


def sha256_file(path: Path) -> str:
    """Hex SHA-256 of a file, read in 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def md5_file(path: Path) -> str:
    """Hex MD5 of a file (only to compare against NBIA-provided MD5 lists)."""
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        while block := handle.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def dicom_count(directory: Path) -> int:
    """Count ``*.dcm`` files directly inside *directory* (0 if missing)."""
    if not directory.is_dir():
        return 0
    return sum(1 for path in directory.iterdir() if path.suffix.lower() == ".dcm")


def series_complete(directory: Path, expected: int) -> bool:
    """Whether *directory* holds exactly *expected* DICOM files."""
    return directory.is_dir() and dicom_count(directory) == expected


def safe_extract(archive: Path, dest: Path, *, max_bytes: int) -> int:
    """Extract *archive* into *dest*, rejecting traversal, corruption and oversize content.

    If the archive ships an NBIA ``md5hashes.csv``, every listed member is checked.

    Returns:
        Number of extracted files.

    Raises:
        AcquisitionError: for corrupt archives, unsafe member paths or MD5 mismatches.
        BudgetError: if the uncompressed content exceeds *max_bytes*.
    """
    root = dest.resolve()
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = [m for m in bundle.infolist() if not m.is_dir()]
            if sum(m.file_size for m in members) > max_bytes:
                msg = f"{archive.name} expands beyond the remaining data budget"
                raise BudgetError(msg)
            bad = bundle.testzip()
            if bad is not None:
                msg = f"corrupt member {bad} in {archive.name}"
                raise AcquisitionError(msg)
            for member in members:
                target = (root / member.filename).resolve()
                if member.filename.startswith("/") or not target.is_relative_to(root):
                    msg = f"unsafe path in archive: {member.filename}"
                    raise AcquisitionError(msg)
            for member in members:
                target = root / member.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, target.open("wb") as out:
                    shutil.copyfileobj(source, out)
    except zipfile.BadZipFile as exc:
        msg = f"{archive.name} is not a valid ZIP archive"
        raise AcquisitionError(msg) from exc
    _check_md5_list(root)
    return len(members)


def _check_md5_list(root: Path) -> None:
    listing = next(iter(root.rglob(MD5_MEMBER)), None)
    if listing is None:
        return
    reader = csv.reader(io.StringIO(listing.read_text(encoding="utf-8")))
    for row in reader:
        if len(row) < 2 or row[0].strip().lower() in {"filename", "file name"}:
            continue
        name, expected = row[0].strip(), row[1].strip().lower()
        candidate = (listing.parent / name).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            msg = f"MD5 list names a missing file: {name}"
            raise AcquisitionError(msg)
        if md5_file(candidate) != expected:
            msg = f"MD5 mismatch for {name}"
            raise AcquisitionError(msg)


def read_sha256_manifest(path: Path) -> dict[str, str]:
    """Parse a ``sha256sum``-format manifest into ``{relative path: hex digest}``."""
    if not path.is_file():
        return {}
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, sep, rel = line.partition("  ")
        if sep and re.fullmatch(r"[0-9a-f]{64}", digest):
            entries[rel] = digest
    return entries


def write_sha256_manifest(path: Path, entries: dict[str, str]) -> None:
    """Write *entries* sorted by path in ``sha256sum -c`` format."""
    lines = [f"{entries[rel]}  {rel}" for rel in sorted(entries)]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def dataset_files(ds_dir: Path) -> list[Path]:
    """Every file of a dataset directory except metadata and in-flight downloads."""
    return sorted(
        path
        for path in ds_dir.rglob("*")
        if path.is_file()
        and ".partial" not in path.relative_to(ds_dir).parts
        and not (path.parent == ds_dir and path.name in META_FILES)
    )


def extract_lidc_xml(
    ds_dir: Path, archive_name: str, series_uids: set[str]
) -> tuple[set[str], list[Path]]:
    """Copy reader XML for the selected series out of the official LIDC XML archive.

    Files land in ``_labels/xml_selected/<SeriesInstanceUID>.xml`` (the archive stays
    untouched), matching what :mod:`thoraxbench.index` reads. Series that already have
    their XML are never rewritten, so existing checksums and reader choices stay stable.
    Archive members are visited in archive order, as in the pilot prototype.

    Returns:
        Series UIDs that have reader XML, and the files written by this call.
    """
    labels = ds_dir / "_labels"
    outdir = labels / "xml_selected"
    outdir.mkdir(parents=True, exist_ok=True)
    have = {uid for uid in series_uids if (outdir / f"{uid}.xml").exists()}
    wanted = series_uids - have
    found: dict[str, list[str]] = {}
    written: list[Path] = []
    pattern = re.compile(rb"<SeriesInstanceUid>\s*([0-9.]+)\s*</SeriesInstanceUid>", re.I)
    if wanted:
        with zipfile.ZipFile(labels / archive_name) as bundle:
            for name in bundle.namelist():
                if not name.endswith(".xml"):
                    continue
                raw = bundle.read(name)
                match = pattern.search(raw)
                if match is None or match.group(1).decode() not in wanted:
                    continue
                uid = match.group(1).decode()
                found.setdefault(uid, []).append(name)
                suffix = "" if len(found[uid]) == 1 else f".{len(found[uid])}"
                target = outdir / f"{uid}{suffix}.xml"
                target.write_bytes(raw)
                written.append(target)
    if written:
        index_path = labels / "xml_selected_index.json"
        previous = (
            json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}
        )
        matched = {**previous.get("matched", {}), **found}
        index = {
            "source": archive_name,
            "matched": matched,
            "missing": sorted(series_uids - have - set(found)),
        }
        index_path.write_text(json.dumps(index, indent=1), encoding="utf-8")
        written.append(index_path)
    return have | set(found), written
