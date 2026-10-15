# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Pilot splitting uses patient folder names without opening medical data."""

import json
from pathlib import Path

import pytest

from thoraxbench.config import Settings
from thoraxbench.registry import PolicyError
from thoraxbench.splits import CaseGuard, CaseRecord, Phase, make_split
from thoraxbench.splits.pilot import create_pilot_split

ENTRY = """
id: pilot
name: Demo
provider: TCIA
license: CC-BY-3.0
access: public
redistribution: allowed_with_attribution
source_url: https://example.org
raw_format: DICOM
status: {status}
"""


def _settings(tmp_path: Path, status: str = "approved") -> Settings:
    configs = tmp_path / "configs" / "datasets"
    configs.mkdir(parents=True)
    (configs / "pilot.yaml").write_text(ENTRY.format(status=status))
    return Settings(repo_root=tmp_path, data_dir=tmp_path / "data")


def test_pilot_split_only_uses_immediate_patient_directories(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    root = settings.data_path("raw", "pilot")
    for i in range(60):
        series = root / f"patient-{i:03d}" / "series"
        series.mkdir(parents=True)
        (series / "not-a-valid-dicom.dcm").write_text("must never be opened")
    (root / "_labels").mkdir()
    (root / ".cache").mkdir()
    (root / "_sha256.txt").write_text("metadata")
    (root / "loose-file").touch()

    manifest = create_pilot_split("pilot", settings)
    assert manifest.patients == {"calibration": 38, "internal_test": 10, "sealed": 12}
    assert manifest.strata == {"all": manifest.patients}
    expected = make_split(
        [
            CaseRecord(dataset="pilot", patient_id=f"patient-{i:03d}", case_id=f"patient-{i:03d}")
            for i in range(60)
        ],
        "pilot",
    )
    assert manifest.patient_hashes == expected.manifest.patient_hashes
    committed = (settings.manifests_dir / "splits" / "pilot.json").read_text()
    assert "patient-" not in committed
    assert json.loads(committed)["sealed_fraction"] == 0.2
    guard = CaseGuard.load(settings.data_dir, settings.manifests_dir, "pilot")
    assert len(guard.cases(Phase.DEVELOPMENT)) == 48
    assert settings.data_path("sealed", "pilot.json").exists()


def test_pilot_split_refuses_existing_artifact_before_scanning_patients(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    sealed = settings.data_path("sealed", "pilot.json")
    sealed.parent.mkdir(parents=True)
    sealed.write_text("do not read me")
    # No raw directory exists, so iterating patients would fail with FileNotFoundError.
    with pytest.raises(FileExistsError, match="frozen"):
        create_pilot_split("pilot", settings)


def test_pilot_split_checks_license_before_scanning_patients(tmp_path: Path) -> None:
    settings = _settings(tmp_path, "pending_access")
    with pytest.raises(PolicyError, match="pending_access"):
        create_pilot_split("pilot", settings)


def test_pilot_split_rejects_empty_download(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.data_path("raw", "pilot", "_labels").mkdir(parents=True)
    with pytest.raises(ValueError, match="empty"):
        create_pilot_split("pilot", settings)
