# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Shared development-study access checks for the CLI and local web interface."""

import hashlib
import os
from collections.abc import Iterable
from pathlib import Path

from thoraxbench.config import Settings
from thoraxbench.dicom.headers import read_header
from thoraxbench.dicom.progress import Progress, emit_progress
from thoraxbench.splits import CaseGuard, Phase, SealedAccessError
from thoraxbench.splits.split import SplitManifest


class StudyPathGuard:
    """Path-only split checks, reusable before browsing or descending into a directory."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.guards: dict[str, CaseGuard] = {}

    def check(self, path: Path, *, allow_ancestors: bool = False) -> tuple[str, str] | None:
        """Check lexical identity before resolving symlink targets or entering folders."""
        # Inspect both spellings: a development-folder symlink cannot escape its identity.
        lexical = Path(os.path.abspath(path))
        data = Path(os.path.abspath(self.settings.data_dir))
        if lexical.is_relative_to(data / "sealed"):
            raise SealedAccessError("sealed input is forbidden for analyze")

        def raw_identity(target: Path, raw: Path) -> tuple[str, str] | None:
            if not target.is_relative_to(raw):
                return None
            parts = target.relative_to(raw).parts
            if not parts:
                if allow_ancestors:
                    return None
                raise SealedAccessError("select a single development patient directory")
            if len(parts) == 1 and not allow_ancestors:
                raise SealedAccessError("select a single development patient directory")
            dataset = parts[0]
            if dataset not in self.guards:
                self.guards[dataset] = CaseGuard.load(
                    self.settings.data_dir, self.settings.manifests_dir, dataset
                )
            if len(parts) == 1:
                if allow_ancestors:
                    return None
                raise SealedAccessError("select a single development patient directory")
            patient = parts[1]
            self.guards[dataset].check(patient, Phase.DEVELOPMENT)
            return dataset, patient

        direct = raw_identity(lexical, data / "raw")
        resolved = path.resolve()
        if resolved.is_relative_to(self.settings.data_path("sealed").resolve()):
            raise SealedAccessError("sealed input is forbidden for analyze")
        actual = raw_identity(resolved, self.settings.data_path("raw").resolve())
        if direct is not None and direct != actual:
            raise SealedAccessError("development input symlink changes study identity")
        return actual or direct


def guard_study_path(
    path: Path, settings: Settings, *, allow_ancestors: bool = False
) -> tuple[str, str] | None:
    """Refuse forbidden paths before directory traversal; no DICOM headers are read."""
    return StudyPathGuard(settings).check(path, allow_ancestors=allow_ancestors)


def guard_study_input(
    path: Path, settings: Settings, *, progress: Progress | None = None
) -> tuple[str, str]:
    """Check every path and header identity before any pixels are loaded.

    Check directories before descending, including aliases, so neither sealed folders
    nor unapproved raw-dataset branches are traversed while selecting ad hoc inputs.
    """
    emit_progress(progress, "path_check", 0, None)
    access = StudyPathGuard(settings)
    identity = access.check(path)
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValueError(f"study directory does not exist: {path}")
    files: list[Path] = []
    pending = [resolved]
    visited: set[Path] = set()
    checked = 0
    while pending:
        directory = pending.pop()
        access.check(directory)
        target = directory.resolve()
        if target in visited:
            continue
        visited.add(target)
        for candidate in directory.iterdir():
            access.check(candidate)
            checked += 1
            emit_progress(progress, "path_check", checked, None)
            if candidate.is_dir():
                pending.append(candidate)
            elif candidate.is_file():
                files.append(candidate)
    emit_progress(progress, "path_check", checked, checked)
    manifests = public_split_manifests(settings)
    emit_progress(progress, "header_check", 0, len(files))
    for completed, candidate in enumerate(sorted(files), 1):
        emit_progress(progress, "header_check", completed - 1, len(files))
        header = read_header(candidate)
        if header is None:
            continue
        patient = str(header.get("PatientID", ""))
        candidate_identity = access.check(candidate)
        guard_patient_identity(patient, candidate_identity, manifests)
    emit_progress(progress, "header_check", len(files), len(files))
    return identity or ("adhoc", resolved.name)


def public_split_manifests(settings: Settings) -> list[SplitManifest]:
    """Read public hash manifests only; never inspect sealed patient files."""
    return [
        SplitManifest.model_validate_json(candidate.read_text(encoding="utf-8"))
        for candidate in sorted((settings.manifests_dir / "splits").glob("*.json"))
    ]


def guard_patient_identity(
    patient: str, identity: tuple[str, str] | None, manifests: Iterable[SplitManifest]
) -> None:
    """Apply the shared copied-sealed/header identity policy to one already-read header."""
    if identity is not None and patient != identity[1]:
        raise SealedAccessError("DICOM patient identity does not match development folder")
    for manifest in manifests:
        digest = hashlib.sha256(f"{manifest.salt}:{patient}".encode()).hexdigest()
        if digest in manifest.patient_hashes.get(Phase.SEALED.value, []):
            raise SealedAccessError("DICOM patient belongs to sealed validation")
