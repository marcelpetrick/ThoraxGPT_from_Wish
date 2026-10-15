# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Pure acquisition helpers: selection, license matching, checksums, NBIA client."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from thoraxbench.acquisition import AcquisitionError, AcquisitionManifest, NbiaClient
from thoraxbench.acquisition.manifest import load_manifest
from thoraxbench.acquisition.nbia import SeriesRecord, default_client, nbia_url
from thoraxbench.acquisition.service import check_series_licenses, select_series
from thoraxbench.acquisition.storage import (
    read_sha256_manifest,
    usage_bytes,
    write_sha256_manifest,
)
from thoraxbench.config import get_settings
from thoraxbench.registry import PolicyError


def _record(patient: str, uid: str, size: int = 100, **extra: object) -> SeriesRecord:
    return SeriesRecord.model_validate(
        {
            "SeriesInstanceUID": uid,
            "PatientID": patient,
            "Modality": "CT",
            "ImageCount": 1,
            "FileSize": size,
            "LicenseURI": "http://creativecommons.org/licenses/by/3.0/",
            **extra,
        }
    )


def test_selection_is_deterministic_whole_patient_and_bounded() -> None:
    rows = [_record(f"P{n}", f"1.2.{n}.1") for n in range(10)]
    rows.append(_record("P3", "1.2.3.2"))
    first = select_series(rows, patients=3, seed=7, headroom=10_000)
    assert first == select_series(list(reversed(rows)), patients=3, seed=7, headroom=10_000)
    assert len({r.patient_id for r in first}) == 3
    if any(r.patient_id == "P3" for r in first):
        assert sum(r.patient_id == "P3" for r in first) == 2
    assert select_series(rows, patients=3, seed=8, headroom=10_000) != first
    assert select_series(rows, patients=5, seed=7, headroom=170) == select_series(
        rows, patients=1, seed=7, headroom=170
    )
    assert (
        len({r.patient_id for r in select_series(rows, patients=99, seed=1, headroom=10**6)}) == 10
    )


def test_license_uri_matching_ignores_scheme_and_slash() -> None:
    record = _record("P1", "1.2.3")
    check_series_licenses([record], "C", "https://www.creativecommons.org/licenses/by/3.0")
    with pytest.raises(PolicyError):
        check_series_licenses([record], "C", "https://creativecommons.org/licenses/by-nc/3.0/")


def test_series_record_rejects_path_tricks() -> None:
    with pytest.raises(ValueError, match="PatientID"):
        _record("../escape", "1.2.3")
    with pytest.raises(ValueError, match="SeriesInstanceUID"):
        _record("P1", "1.2/../3")


def test_sha256_manifest_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "_sha256.txt"
    assert read_sha256_manifest(path) == {}
    entries = {"b/x.dcm": "a" * 64, "a y.csv": "b" * 64}
    write_sha256_manifest(path, entries)
    path.write_text(path.read_text() + "garbage line\n")
    assert read_sha256_manifest(path) == entries
    write_sha256_manifest(path, {})
    assert path.read_text() == ""


def test_usage_counts_bytes_without_following_missing_dirs(tmp_path: Path) -> None:
    assert usage_bytes(tmp_path / "missing") == 0
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f").write_bytes(b"12345")
    (tmp_path / "g").write_bytes(b"1")
    assert usage_bytes(tmp_path) == 6


def test_nbia_client_handles_empty_and_invalid_bodies() -> None:
    bodies = iter([b"", b"{not json"])
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, content=next(bodies)))
    )
    nbia = NbiaClient(client, sleep=lambda _s: None)
    assert nbia.get_series("A B", "CT") == []
    with pytest.raises(AcquisitionError, match="invalid JSON"):
        nbia.get_series("A B", "CT")


def test_nbia_client_retries_with_backoff(tmp_path: Path) -> None:
    waits: list[float] = []
    client = httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(502)))
    nbia = NbiaClient(client, retries=3, sleep=waits.append)
    with pytest.raises(AcquisitionError, match="download failed after 3"):
        nbia.download("https://example.invalid/x", tmp_path / "x.zip", max_bytes=10)
    assert waits == [3.0, 6.0]
    assert not (tmp_path / "x.zip").exists()


def test_nbia_url_and_default_client() -> None:
    assert nbia_url("getSeries", Collection="NSCLC Radiogenomics").endswith(
        "getSeries?Collection=NSCLC%20Radiogenomics"
    )
    client = default_client()
    try:
        assert client.headers["User-Agent"].startswith("thoraxbench/")
    finally:
        client.close()


@pytest.mark.parametrize("dataset", ["lidc_idri", "nsclc_radiogenomics"])
def test_committed_pilot_manifests_match_the_format(dataset: str) -> None:
    path = get_settings().manifests_dir / "datasets" / f"{dataset}.json"
    manifest = load_manifest(path)
    assert isinstance(manifest, AcquisitionManifest)
    assert manifest.dataset == dataset
    assert manifest.series > 0
    assert load_manifest(path.with_name("missing.json")) is None


def test_safe_extract_refuses_oversize_and_corrupt_archives(tmp_path: Path) -> None:
    import zipfile

    from thoraxbench.acquisition import BudgetError
    from thoraxbench.acquisition.storage import dicom_count, safe_extract

    archive = tmp_path / "a.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("00000001.dcm", b"x" * 100)
    with pytest.raises(BudgetError):
        safe_extract(archive, tmp_path / "out", max_bytes=10)
    data = bytearray(archive.read_bytes())
    data[data.index(b"x" * 100)] = ord("y")  # flip one stored byte -> CRC mismatch
    archive.write_bytes(bytes(data))
    with pytest.raises(AcquisitionError, match="corrupt member"):
        safe_extract(archive, tmp_path / "out", max_bytes=1_000)
    assert dicom_count(tmp_path / "missing") == 0


def test_checksums_never_open_files_outside_the_development_scope(tmp_path: Path) -> None:
    from thoraxbench.acquisition.service import _update_checksums
    from thoraxbench.acquisition.storage import write_sha256_manifest

    for rel in ("DEV-1/s/1.dcm", "SEALED-1/s/1.dcm", "_labels/l.csv"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(b"x")
    write_sha256_manifest(tmp_path / "_sha256.txt", {"SEALED-1/s/1.dcm": "0" * 64})
    entries, failures = _update_checksums(tmp_path, {}, verify=True, scope=frozenset({"DEV-1"}))
    assert failures == []  # the stale sealed hash is not re-verified
    assert entries["SEALED-1/s/1.dcm"] == "0" * 64
    assert {"DEV-1/s/1.dcm", "_labels/l.csv"} <= set(entries)
