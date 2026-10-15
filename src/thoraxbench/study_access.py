# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Shared development-study access checks for the CLI and local web interface."""

import hashlib
from pathlib import Path

from thoraxbench.config import Settings
from thoraxbench.splits import CaseGuard, Phase, SealedAccessError
from thoraxbench.splits.split import SplitManifest


def guard_study_input(path: Path, settings: Settings) -> tuple[str, str]:
    """Check paths and header identities before any pixel data is loaded.

    Registered raw inputs require their frozen development split. Public patient hashes
    also block copied sealed patients in otherwise ad hoc folders; sealed IDs stay unread.
    """
    import pydicom  # noqa: PLC0415 - DICOM is needed only for analysis
    from pydicom.errors import InvalidDicomError  # noqa: PLC0415

    resolved = path.resolve()
    sealed = settings.data_path("sealed").resolve()
    raw = settings.data_path("raw").resolve()
    guards: dict[str, CaseGuard] = {}

    def check_path(candidate: Path) -> tuple[str, str] | None:
        target = candidate.resolve()
        if target.is_relative_to(sealed):
            raise SealedAccessError("sealed input is forbidden for analyze")
        if not target.is_relative_to(raw):
            return None
        parts = target.relative_to(raw).parts
        if len(parts) < 2:
            raise SealedAccessError("select a single development patient directory")
        dataset, patient = parts[:2]
        if dataset not in guards:
            guards[dataset] = CaseGuard.load(settings.data_dir, settings.manifests_dir, dataset)
        guards[dataset].check(patient, Phase.DEVELOPMENT)
        return dataset, patient

    identity = check_path(resolved)
    if not resolved.is_dir():
        raise ValueError(f"study directory does not exist: {path}")
    files = sorted(candidate for candidate in resolved.rglob("*") if candidate.is_file())
    for candidate in files:
        check_path(candidate)
    manifests = [
        SplitManifest.model_validate_json(candidate.read_text(encoding="utf-8"))
        for candidate in sorted((settings.manifests_dir / "splits").glob("*.json"))
    ]
    for candidate in files:
        try:
            header = pydicom.dcmread(
                candidate, stop_before_pixels=True, specific_tags=["PatientID"]
            )
        except InvalidDicomError, EOFError:
            continue
        patient = str(header.get("PatientID", ""))
        candidate_identity = check_path(candidate)
        if candidate_identity is not None and patient != candidate_identity[1]:
            raise SealedAccessError("DICOM patient identity does not match development folder")
        for manifest in manifests:
            digest = hashlib.sha256(f"{manifest.salt}:{patient}".encode()).hexdigest()
            if digest in manifest.patient_hashes.get(Phase.SEALED.value, []):
                raise SealedAccessError("DICOM patient belongs to sealed validation")
    return identity or ("adhoc", resolved.name)
