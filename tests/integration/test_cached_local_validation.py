# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Cached pixels avoid header rescans while changed/new sources remain guarded."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from thoraxbench.api import local_studies
from thoraxbench.api.local_studies import LocalStudies, source_signature
from thoraxbench.config import Settings
from thoraxbench.splits import CaseRecord, Phase, make_split, save_split
from thoraxbench.study import load_study_dir
from thoraxbench.study_access import guard_study_input
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series


def registered(tmp_path: Path) -> tuple[Settings, Path, LocalStudies]:
    """Load and validate one synthetic source before adding it to the session."""
    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    folder = tmp_path / "external"
    spec = PhantomSpec(shape=(32, 64, 64))
    write_dicom_series(make_phantom(spec), folder, spec.spacing_mm)
    guard_study_input(folder, settings)
    study = load_study_dir(folder)
    registry = LocalStudies(settings)
    registry.register("session", folder, study, source_signature(folder))
    return settings, folder, registry


def test_cached_access_reads_zero_headers_and_cache_miss_forces_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, registry = registered(tmp_path)
    guard = Mock(wraps=local_studies.guard_study_input)
    monkeypatch.setattr(local_studies, "guard_study_input", guard)
    for _ in range(5):
        entry, identity, signature = registry.checked("session")
        assert identity == ("adhoc", "external")
        assert signature == entry.signature
    guard.assert_not_called()
    registry.checked("session", require_headers=True)
    assert guard.call_count == 1


def test_changed_source_revalidates_and_copied_sealed_headers_stay_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, folder, registry = registered(tmp_path)
    guard = Mock(wraps=local_studies.guard_study_input)
    monkeypatch.setattr(local_studies, "guard_study_input", guard)
    (folder / "changed.txt").write_text("changed source")
    entry, _, signature = registry.checked("session")
    assert signature != entry.signature
    assert guard.call_count == 1
    split = make_split(
        [CaseRecord(dataset="toy", patient_id=f"P{i}", case_id=f"P{i}") for i in range(10)],
        "toy",
    )
    save_split(split, settings.data_dir, settings.manifests_dir)
    sealed = split.cases(Phase.SEALED)[0]
    import pydicom

    file = next(folder.glob("*.dcm"))
    dataset = pydicom.dcmread(file)
    dataset.PatientID = sealed
    dataset.save_as(file, enforce_file_format=True)
    with pytest.raises(PermissionError, match="sealed validation"):
        registry.checked("session")


def test_new_nested_sealed_alias_is_refused_before_signature_stat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, folder, registry = registered(tmp_path)
    sealed = settings.data_path("sealed", "forbidden")
    sealed.mkdir(parents=True)
    alias = folder / "nested-alias"
    alias.symlink_to(sealed, target_is_directory=True)
    original = Path.stat

    def stat(path: Path, **kwargs: object) -> object:
        assert path != alias  # guard must refuse before explicitly inspecting its target
        return original(path, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    with pytest.raises(PermissionError):
        registry.checked("session")


def test_new_split_policy_rechecks_unchanged_ad_hoc_patient(tmp_path: Path) -> None:
    settings, folder, registry = registered(tmp_path)
    before = source_signature(folder)
    patient = "PHANTOM-0001"
    records = [CaseRecord(dataset="toy", patient_id=patient, case_id=patient)]
    records.extend(
        CaseRecord(dataset="toy", patient_id=f"P{i}", case_id=f"P{i}") for i in range(10)
    )
    # Choose a salt that deterministically assigns the existing patient to sealed.
    split = make_split(records, "toy")
    for seed in range(100):
        split = make_split(records, "toy", salt=f"policy-test-{seed}")
        if patient in split.cases(Phase.SEALED):
            break
    assert patient in split.cases(Phase.SEALED)
    save_split(split, settings.data_dir, settings.manifests_dir)
    assert source_signature(folder) == before
    with pytest.raises(PermissionError, match="sealed validation"):
        registry.checked("session")
