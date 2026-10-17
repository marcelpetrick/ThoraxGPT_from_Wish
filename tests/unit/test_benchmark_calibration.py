# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Calibration fit/apply direction and training-overlap tagging in the benchmark."""

from pathlib import Path
from typing import Any

import pytest

from thoraxbench.benchmark import CalibrationSettings, fit_and_apply, training_overlap
from thoraxbench.benchmark.calibration import BASELINE_THRESHOLD
from thoraxbench.config import REPO_ROOT, Settings
from thoraxbench.scoring import CaseRecord, combine_overlaps, normalize_family
from thoraxbench.scoring import possible_training_overlap as overlap

LABEL = "pulmonary_nodule"


def _rec(i: int, truth: bool | None, score: float | None) -> CaseRecord:
    return CaseRecord(
        case_id=f"c{i}", patient_id=f"p{i}", y_true={LABEL: truth}, y_score={LABEL: score}
    )


def _phased(phase: str, pairs: list[tuple[bool | None, float | None]], start: int = 0) -> list[Any]:
    return [(phase, _rec(start + i, t, s)) for i, (t, s) in enumerate(pairs)]


FIT = [(True, 0.9), (True, 0.8), (False, 0.7), (False, 0.2), (False, 0.1), (True, 0.75)]
EVAL = [(True, 0.85), (False, 0.72), (False, 0.3), (True, 0.6)]


def _records() -> list[Any]:
    return _phased("calibration", FIT) + _phased("internal_test", EVAL, start=100)


@pytest.mark.parametrize("method", ["platt", "temperature", "isotonic", "none"])
def test_fit_on_calibration_apply_to_internal_test(method: str) -> None:
    out = fit_and_apply(_records(), [LABEL], CalibrationSettings(method=method), n_boot=20, seed=1)
    assert out["status"] == "applied"
    assert (out["n_fit_cases"], out["n_eval_cases"]) == (len(FIT), len(EVAL))
    fit = out["per_label"][LABEL]
    assert (fit["fit_n"], fit["fit_positives"]) == (6, 3)
    assert fit["fitted_threshold"] == pytest.approx(0.75)
    assert (fit["calibrator"] or {}).get("kind", "none") == method
    assert out["task_a_fixed"]["per_label"][LABEL]["threshold"] == BASELINE_THRESHOLD
    assert out["task_a_fitted"]["per_label"][LABEL]["threshold"] == pytest.approx(0.75)
    assert out["task_a_fixed"]["per_label"][LABEL]["n"] == len(EVAL)
    # Fixed 0.5 calls 0.72 positive (FP); the fitted 0.75 threshold rejects it but misses 0.6.
    assert out["task_a_fixed"]["per_label"][LABEL]["specificity"] == pytest.approx(0.5)
    assert out["task_a_fitted"]["per_label"][LABEL]["specificity"] == pytest.approx(1.0)
    assert out["task_b_raw"][LABEL]["n"] == len(EVAL)
    if method == "none":
        assert out["task_b_calibrated"] == out["task_b_raw"]
    else:
        assert out["task_b_calibrated"][LABEL]["brier"] != out["task_b_raw"][LABEL]["brier"]


def test_eval_scores_never_change_the_fit() -> None:
    first = fit_and_apply(_records(), [LABEL], CalibrationSettings(), n_boot=0)
    flipped = _phased("calibration", FIT) + _phased(
        "internal_test", [(not t, 1 - s) for t, s in EVAL], start=100
    )
    second = fit_and_apply(flipped, [LABEL], CalibrationSettings(), n_boot=0)
    assert first["per_label"] == second["per_label"]


@pytest.mark.parametrize("phase", ["sealed", "development", "unknown"])
def test_refuses_records_outside_calibration_and_internal_test(phase: str) -> None:
    with pytest.raises(ValueError, match=r"sealed|calibration/internal_test"):
        fit_and_apply([*_records(), (phase, _rec(9, True, 0.5))], [LABEL], CalibrationSettings())


def test_not_applicable_without_fit_or_eval_cases() -> None:
    no_fit = fit_and_apply(_phased("internal_test", EVAL), [LABEL], CalibrationSettings())
    assert no_fit["status"] == "not_applicable"
    assert "calibration-phase" in no_fit["reason"]
    no_eval = fit_and_apply(_phased("calibration", FIT), [LABEL], CalibrationSettings())
    assert no_eval["status"] == "not_applicable"
    assert "internal_test" in no_eval["reason"]
    assert no_eval["per_label"] == {}


def test_single_class_and_missing_label_keep_baseline() -> None:
    records = _phased("calibration", [(False, 0.2), (False, 0.6)]) + _phased(
        "internal_test", [(False, 0.4)], start=10
    )
    out = fit_and_apply(records, [LABEL, "pulmonary_mass"], CalibrationSettings(), n_boot=0)
    one = out["per_label"][LABEL]
    assert one["fitted_threshold"] == BASELINE_THRESHOLD
    assert one["calibrator"] is None
    assert any("one reference class" in n for n in one["notes"])
    missing = out["per_label"]["pulmonary_mass"]
    assert (missing["fit_n"], missing["calibrator"]) == (0, None)
    assert "0.5 kept" in missing["notes"][0]


def test_sensitivity_threshold_method() -> None:
    settings = CalibrationSettings(threshold_method="sensitivity", target_sensitivity=1.0)
    out = fit_and_apply(_records(), [LABEL], settings, n_boot=0)
    assert out["per_label"][LABEL]["fitted_threshold"] == pytest.approx(0.75)
    assert out["threshold_method"] == "sensitivity"


def test_calibration_settings_validate() -> None:
    with pytest.raises(ValueError, match="method"):
        CalibrationSettings.model_validate({"method": "magic"})
    with pytest.raises(ValueError, match="target_sensitivity"):
        CalibrationSettings.model_validate({"target_sensitivity": 0})


def test_overlap_helpers() -> None:
    assert normalize_family(" CT-CLIP ") == "ct_clip"
    assert overlap("ct-clip", "ct_rate") == "yes"
    assert overlap("rules", "lidc_idri") == "no"
    assert combine_overlaps([]) == "unknown"
    assert combine_overlaps(["no", "no"]) == "no"
    assert combine_overlaps(["no", "unknown"]) == "unknown"
    assert combine_overlaps(["unknown", "yes", "no"]) == "yes"


def test_training_overlap_from_repository_configs(tmp_path: Path) -> None:
    settings = Settings(repo_root=REPO_ROOT, data_dir=tmp_path)
    assert training_overlap("heuristic-hu", ["lidc_idri"], settings) == {"lidc_idri": "no"}
    assert training_overlap("ct-clip", ["ct_rate", "radgenome_chestct", "lidc_idri"], settings) == {
        "ct_rate": "yes",
        "radgenome_chestct": "yes",
        "lidc_idri": "no",
    }
    assert training_overlap("medgemma1.5-q4", ["lidc_idri"], settings) == {"lidc_idri": "unknown"}
    assert training_overlap("no-such-model", ["lidc_idri"], settings) == {"lidc_idri": "unknown"}


def test_training_overlap_without_registry(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "configs").mkdir(parents=True)
    (repo / "configs" / "models").symlink_to(REPO_ROOT / "configs" / "models")
    (repo / "configs" / "datasets").mkdir()
    (repo / "configs" / "datasets" / "bad.yaml").write_text("id: other\n", encoding="utf-8")
    settings = Settings(repo_root=repo, data_dir=tmp_path)
    assert training_overlap("ct-clip", ["ct_rate"], settings) == {"ct_rate": "yes"}
