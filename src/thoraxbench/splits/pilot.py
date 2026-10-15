# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Seal downloaded pilot patients before development reads their images or labels."""

from thoraxbench.config import Settings
from thoraxbench.registry import load_registry, require_acquirable
from thoraxbench.splits.split import (
    CaseRecord,
    SplitManifest,
    make_split,
    save_split,
    split_paths,
)


def create_pilot_split(dataset: str, settings: Settings) -> SplitManifest:
    """Freeze a reproducible pseudorandom 80/20 patient split from directory names only.

    Immediate patient directories are cases; metadata directories beginning with ``_``
    or ``.`` are excluded. No DICOM, reference labels, or sealed file is read. A single
    stratum and the versioned default hash salt keep selection independent of findings.
    Development is subdivided into calibration/internal-test using the existing 80/20
    policy. Existing split artifacts cause refusal rather than reassignment.

    Returns counts and salted hashes only; plaintext sealed assignments stay on disk.
    """
    require_acquirable(load_registry(settings.configs_dir / "datasets")[dataset])
    if any(
        path.exists()
        for path in split_paths(settings.data_dir, settings.manifests_dir, dataset).values()
    ):
        raise FileExistsError(f"split for {dataset} already exists and is frozen")
    root = settings.data_path("raw", dataset)
    cases = [
        CaseRecord(dataset=dataset, patient_id=path.name, case_id=path.name)
        for path in sorted(root.iterdir())
        if not path.name.startswith(("_", ".")) and path.is_dir()
    ]
    result = make_split(cases, dataset)
    save_split(result, settings.data_dir, settings.manifests_dir)
    return result.manifest
