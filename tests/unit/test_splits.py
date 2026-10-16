# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
import json
import os
import stat
from pathlib import Path

import pytest

from thoraxbench.splits import (
    CaseGuard,
    CaseRecord,
    Phase,
    SealedAccessError,
    freeze_experiment,
    load_split,
    make_split,
    save_split,
)
from thoraxbench.splits.guard import verify_freeze


def _cases(n: int = 50) -> list[CaseRecord]:
    out = []
    for i in range(n):
        stratum = "pos" if i % 3 == 0 else "neg"
        out.append(
            CaseRecord(dataset="ds", patient_id=f"P{i:03d}", case_id=f"P{i:03d}-a", stratum=stratum)
        )
        if i % 5 == 0:  # second study of the same patient
            out.append(
                CaseRecord(
                    dataset="ds", patient_id=f"P{i:03d}", case_id=f"P{i:03d}-b", stratum="neg"
                )
            )
    return out


def test_split_is_patient_level_stratified_and_deterministic() -> None:
    cases = _cases()
    a = make_split(cases, "ds")
    b = make_split(list(reversed(cases)), "ds")
    assert a.assignments == b.assignments
    m = a.manifest
    assert m.patients["sealed"] == 10  # 20 % of 50 patients
    assert m.patients["calibration"] + m.patients["internal_test"] == 40
    assert m.patients["calibration"] == 32
    for ph in ("sealed", "calibration", "internal_test"):
        assert sum(s[ph] for s in m.strata.values()) == m.patients[ph]
    assert m.strata["pos"]["sealed"] >= 1
    # a patient's studies never straddle phases
    phase_by_patient: dict[str, set[Phase]] = {}
    for case, ph in a.assignments.items():
        phase_by_patient.setdefault(a.patient_of[case], set()).add(ph)
    assert all(len(v) == 1 for v in phase_by_patient.values())
    assert set(a.cases(Phase.DEVELOPMENT)) == set(a.cases(Phase.CALIBRATION)) | set(
        a.cases(Phase.INTERNAL_TEST)
    )
    assert make_split(cases, "ds", salt="other").assignments != a.assignments


def test_split_validation() -> None:
    with pytest.raises(ValueError, match="empty"):
        make_split([], "ds")
    with pytest.raises(ValueError, match="belong"):
        make_split(_cases(3), "other")
    with pytest.raises(ValueError, match="fractions"):
        make_split(_cases(3), "ds", sealed_fraction=1.5)


def test_small_strata() -> None:
    single = [CaseRecord(dataset="ds", patient_id="A", case_id="A1")]
    assert make_split(single, "ds").manifest.patients["sealed"] == 0
    pair = [*single, CaseRecord(dataset="ds", patient_id="B", case_id="B1")]
    res = make_split(pair, "ds")
    assert res.manifest.patients == {"calibration": 1, "internal_test": 0, "sealed": 1}


def test_save_load_and_guard(tmp_path: Path) -> None:
    data, manifests = tmp_path / "data", tmp_path / "manifests"
    res = make_split(_cases(), "ds")
    paths = save_split(res, data, manifests)
    assert not os.stat(paths["sealed"]).st_mode & stat.S_IWUSR  # sealed file is read-only
    committed = paths["manifest"].read_text()
    assert "P0" not in committed  # no plaintext patient IDs in the committed manifest
    with pytest.raises(FileExistsError):
        save_split(res, data, manifests)
    save_split(res, data, manifests, overwrite=True)

    dev_only = load_split(data, manifests, "ds", include_sealed=False)
    assert not dev_only.cases(Phase.SEALED)
    guard = CaseGuard.load(data, manifests, "ds")
    assert guard.dataset == "ds"
    assert guard.summary()["patients"]["sealed"] == 10  # type: ignore[index]
    with pytest.raises(SealedAccessError):
        guard.cases(Phase.SEALED)
    sealed_case = res.cases(Phase.SEALED)[0]
    cal_case = res.cases(Phase.CALIBRATION)[0]
    it_case = res.cases(Phase.INTERNAL_TEST)[0]
    assert guard.phase_of(sealed_case) is None
    with pytest.raises(SealedAccessError, match="not in the development split"):
        guard.check(sealed_case, Phase.DEVELOPMENT)
    guard.check(cal_case, Phase.DEVELOPMENT)
    guard.check(cal_case, Phase.CALIBRATION)
    with pytest.raises(SealedAccessError, match="belongs to"):
        guard.check(it_case, Phase.CALIBRATION)

    config = tmp_path / "exp.yaml"
    config.write_text("model: x\n")
    with pytest.raises(SealedAccessError, match="not frozen; freezing is not yet exposed"):
        verify_freeze(config, "E1", data)
    record = freeze_experiment(config, "E1", data)
    assert freeze_experiment(config, "E1", data) == record
    unsealed = CaseGuard.load(data, manifests, "ds", freeze=verify_freeze(config, "E1", data))
    assert unsealed.cases(Phase.SEALED) == res.cases(Phase.SEALED)
    unsealed.check(sealed_case, Phase.SEALED)
    with pytest.raises(SealedAccessError, match="is sealed"):
        unsealed.check(sealed_case, Phase.CALIBRATION)
    config.write_text("model: y\n")  # tuning after freezing is detected
    with pytest.raises(SealedAccessError, match="changed"):
        verify_freeze(config, "E1", data)
    with pytest.raises(FileExistsError):
        freeze_experiment(config, "E1", data)


def test_tampering_detected(tmp_path: Path) -> None:
    data, manifests = tmp_path / "data", tmp_path / "manifests"
    paths = save_split(make_split(_cases(), "ds"), data, manifests)
    dev = json.loads(paths["development"].read_text())
    first = next(iter(dev["cases"]))
    dev["cases"][first]["patient_id"] = "INTRUDER"
    paths["development"].write_text(json.dumps(dev))
    with pytest.raises(ValueError, match="development split"):
        load_split(data, manifests, "ds", include_sealed=False)


def test_sealed_tampering_detected(tmp_path: Path) -> None:
    data, manifests = tmp_path / "data", tmp_path / "manifests"
    paths = save_split(make_split(_cases(), "ds"), data, manifests)
    os.chmod(paths["sealed"], stat.S_IRUSR | stat.S_IWUSR)
    sealed = json.loads(paths["sealed"].read_text())
    sealed["cases"].popitem()
    paths["sealed"].write_text(json.dumps(sealed))
    with pytest.raises(ValueError, match="sealed split"):
        load_split(data, manifests, "ds", include_sealed=True)


@pytest.mark.parametrize("dataset", ["../sealed/ds", "/tmp/ds", "..", "a/b", "", "../ds"])
def test_unsafe_split_identifiers_are_refused_before_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dataset: str
) -> None:
    def forbidden_read(*_args: object, **_kwargs: object) -> str:
        pytest.fail("An unsafe split identifier must be rejected before file reads")

    monkeypatch.setattr(Path, "read_text", forbidden_read)
    with pytest.raises(ValueError, match="safe split key"):
        CaseGuard.load(tmp_path / "data", tmp_path / "manifests", dataset)


@pytest.mark.parametrize("kind", ["development", "manifest", "directory"])
def test_split_symlink_escape_is_refused_before_reads(tmp_path: Path, kind: str) -> None:
    data, manifests = tmp_path / "data", tmp_path / "manifests"
    paths = save_split(make_split(_cases(), "ds"), data, manifests)
    if kind == "directory":
        paths["development"].unlink()
        (data / "splits").rmdir()
        (data / "splits").symlink_to(data / "sealed", target_is_directory=True)
    else:
        paths[kind].unlink()
        paths[kind].symlink_to(paths["sealed"])
    with pytest.raises(ValueError, match="escapes its designated directory"):
        load_split(data, manifests, "ds", include_sealed=False)


def test_split_manifest_identity_mismatch_stops_before_development_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data, manifests = tmp_path / "data", tmp_path / "manifests"
    paths = save_split(make_split(_cases(), "ds"), data, manifests)
    manifest = json.loads(paths["manifest"].read_text())
    manifest["dataset"] = "other"
    paths["manifest"].write_text(json.dumps(manifest))
    original = Path.read_text

    def read_manifest_only(path: Path, *args: object, **kwargs: object) -> str:
        assert path == paths["manifest"]
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_manifest_only)
    with pytest.raises(ValueError, match="requested identity"):
        load_split(data, manifests, "ds", include_sealed=False)


@pytest.mark.parametrize("experiment", ["../E1", "/tmp/E1", "..", ""])
def test_unsafe_freeze_identifiers_are_refused(tmp_path: Path, experiment: str) -> None:
    config = tmp_path / "experiment.yaml"
    config.write_text("model: synthetic")
    with pytest.raises(ValueError, match="safe freeze key"):
        freeze_experiment(config, experiment, tmp_path / "data")
    with pytest.raises(ValueError, match="safe freeze key"):
        verify_freeze(config, experiment, tmp_path / "data")


def test_freeze_symlink_escape_is_refused(tmp_path: Path) -> None:
    config = tmp_path / "experiment.yaml"
    config.write_text("model: synthetic")
    folder = tmp_path / "data" / "sealed" / "freeze"
    folder.mkdir(parents=True)
    (folder / "E1.json").symlink_to(config)
    with pytest.raises(ValueError, match="escapes its designated directory"):
        verify_freeze(config, "E1", tmp_path / "data")
