# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Session-only local folder registrations; no uploads, copies or automatic inference."""

import hashlib
import os
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from thoraxbench.config import Settings
from thoraxbench.study import Study
from thoraxbench.study_access import StudyPathGuard, guard_study_input, guard_study_path


class SourceChangedError(ValueError):
    """The input did not remain stable while its pixels were loaded."""

    code = "source_changed"


MAX_FOLDERS = 200
MAX_SCANNED = 1000
MAX_LOCAL_STUDIES = 16


def absolute_folder(value: str) -> Path:
    """Require an explicit absolute server-side path; preserve aliases for later checks."""
    path = Path(value)
    if not path.is_absolute() or "\x00" in value:
        raise ValueError("Choose an absolute local folder")
    return Path(os.path.abspath(path))


def browse_folders(path: Path, settings: Settings) -> dict[str, Any]:
    """List a bounded directory level after path-only development checks."""
    access = StudyPathGuard(settings)
    access.check(path, allow_ancestors=True)
    folders: list[dict[str, str]] = []
    truncated = False
    with os.scandir(path) as entries:
        for scanned, entry in enumerate(entries):
            if scanned >= MAX_SCANNED or len(folders) >= MAX_FOLDERS:
                truncated = True
                break
            child = path / entry.name
            try:
                access.check(child, allow_ancestors=True)
                if not entry.is_dir():
                    continue
            except OSError, ValueError, RuntimeError:
                continue
            folders.append({"name": entry.name, "path": str(child)})
    parent: str | None = None
    if path.parent != path:
        try:
            access.check(path.parent, allow_ancestors=True)
            parent = str(path.parent)
        except OSError, ValueError, RuntimeError:
            pass
    return {
        "path": str(path),
        "parent": parent,
        "folders": sorted(folders, key=lambda item: item["name"].casefold()),
        "truncated": truncated,
    }


def source_signature(path: Path, settings: Settings | None = None) -> str:
    """Invalidate cached volumes after source replacement; access guard runs first."""
    access = StudyPathGuard(settings) if settings is not None else None
    if access is not None:
        access.check(path)
    digest = hashlib.sha256(str(path.resolve()).encode())
    pending = [path]
    while pending:
        directory = pending.pop()
        for candidate in sorted(directory.iterdir()):
            if access is not None:
                access.check(candidate)
            info = candidate.stat()
            digest.update(str(candidate.relative_to(path)).encode())
            digest.update(
                f"{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}:{info.st_ctime_ns}".encode()
            )
            if candidate.is_dir() and not candidate.is_symlink():
                pending.append(candidate)
    return digest.hexdigest()


def _guard_policy_signature(settings: Settings) -> str:
    # Public hash manifests and development assignments affect header eligibility.
    # Never inspect data/sealed or retain patient identifiers in the registry.
    digest = hashlib.sha256()
    for root in (settings.manifests_dir / "splits", settings.data_path("splits")):
        for file in sorted(root.glob("*.json")):
            digest.update(str(file).encode())
            digest.update(file.read_bytes())
    return digest.hexdigest()


@dataclass(frozen=True)
class LocalStudy:
    """Private source identity and public session summary."""

    path: Path
    signature: str
    identity: tuple[str, str]
    policy_signature: str
    summary: dict[str, Any]


class LocalStudies:
    """Bounded private path registry; summaries expose only opaque API identifiers."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.lock = RLock()
        self.items: OrderedDict[str, LocalStudy] = OrderedDict()

    def register(self, identifier: str, path: Path, study: Study, signature: str) -> None:
        """Retain a successfully checked source with its pre-load signature."""
        summary = {
            "dataset": "local",
            "case_id": identifier,
            "n_slices": study.volume.shape[0],
            "phase": "local",
            "qc_adequate": study.qc.adequate,
        }
        with self.lock:
            self.items[identifier] = LocalStudy(
                path,
                signature,
                guard_study_path(path, self.settings) or ("adhoc", path.resolve().name),
                _guard_policy_signature(self.settings),
                summary,
            )
            while len(self.items) > MAX_LOCAL_STUDIES:
                self.items.popitem(last=False)

    def checked(
        self, identifier: str, *, require_headers: bool = False
    ) -> tuple[LocalStudy, tuple[str, str], str]:
        """Reuse validated pixels only while path and source signature remain unchanged.

        A cache miss must set require_headers before loading any new pixels. Changed
        sources always repeat header identity validation, regardless of that flag.
        """
        with self.lock:
            entry = self.items[identifier]
        guard_study_path(entry.path, self.settings)
        signature = source_signature(entry.path, self.settings)
        identity = entry.identity
        if (
            require_headers
            or signature != entry.signature
            or _guard_policy_signature(self.settings) != entry.policy_signature
        ):
            identity = guard_study_input(entry.path, self.settings)
        return entry, identity, signature

    def summaries(self) -> list[dict[str, Any]]:
        """Expose session entries whose paths remain permitted."""
        with self.lock:
            items = list(self.items.values())
        summaries = []
        for entry in items:
            try:
                guard_study_path(entry.path, self.settings)
            except OSError, ValueError, RuntimeError:
                continue
            summaries.append(dict(entry.summary))
        return summaries


def local_identity(study: Study, identity: tuple[str, str], identifier: str) -> None:
    """Preserve registered scientific keys; keep ad hoc output keys opaque."""
    if identity[0] == "adhoc":
        study.identifiers = study.identifiers | {study.patient_id}
        study.dataset = "local"
        study.case_id = identifier
        study.patient_id = identifier
