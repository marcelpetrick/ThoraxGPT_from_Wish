# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Fit thresholds and calibrators on ``calibration`` cases; apply them to ``internal_test``.

Vision §14 and §20 allow threshold fitting and confidence mapping on development data only.
This module enforces the direction inside the development split: every fit sees
calibration-phase records only, and the fitted maps are scored on internal-test records only.
Any record from another phase (``sealed`` or unknown) is refused before anything is fitted.

The fixed 0.5 threshold on raw scores is always reported next to the fitted threshold, so a
reader can see what the fit changed. Neither is clinical accuracy.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from thoraxbench.benchmark.config import CalibrationSettings
from thoraxbench.calibration import (
    Calibrator,
    IsotonicCalibrator,
    PlattCalibrator,
    TemperatureScaler,
    check_phase,
    fit_thresholds,
)
from thoraxbench.scoring import CaseRecord, task_a, task_b
from thoraxbench.scoring.classification import label_arrays
from thoraxbench.splits import Phase

FIT_PHASE = Phase.CALIBRATION.value
EVAL_PHASE = Phase.INTERNAL_TEST.value
BASELINE_THRESHOLD = 0.5
ALLOWED_PHASES = frozenset({FIT_PHASE, EVAL_PHASE})

PhasedRecord = tuple[str, CaseRecord]


def _check_phases(records: Sequence[PhasedRecord]) -> None:
    for phase, _ in records:
        check_phase(phase)
        if phase not in ALLOWED_PHASES:
            msg = f"calibration accepts calibration/internal_test records only, got {phase!r}"
            raise ValueError(msg)


def _make_calibrator(method: str) -> Calibrator | None:
    if method == "isotonic":
        return IsotonicCalibrator()
    if method == "temperature":
        return TemperatureScaler()
    if method == "platt":
        return PlattCalibrator()
    return None


def _fit_label(
    fit: Sequence[CaseRecord], label: str, settings: CalibrationSettings
) -> tuple[float, Calibrator | None, dict[str, Any]]:
    y, p, _ = label_arrays(fit, label)
    notes: list[str] = []
    info: dict[str, Any] = {"fit_n": len(y), "fit_positives": int(y.sum()) if len(y) else 0}
    if len(y) == 0:
        notes.append("no calibration-phase case with reference and score; 0.5 kept")
        info |= {"fitted_threshold": BASELINE_THRESHOLD, "calibrator": None, "notes": notes}
        return BASELINE_THRESHOLD, None, info
    classes = len(set(y.tolist()))
    threshold = fit_thresholds(
        {label: y.tolist()},
        {label: p.tolist()},
        method=settings.threshold_method,
        target_sensitivity=settings.target_sensitivity,
        phase=FIT_PHASE,
        default=BASELINE_THRESHOLD,
    )[label]
    calibrator = _make_calibrator(settings.method)
    if classes < 2 and calibrator is not None:
        calibrator = None
        notes.append("calibrator not fitted: one reference class in calibration data")
    if classes < 2:
        notes.append("threshold kept at 0.5: one reference class in calibration data")
    if calibrator is not None:
        calibrator.fit(y.tolist(), p.tolist(), phase=FIT_PHASE)
    info |= {
        "fitted_threshold": threshold,
        "calibrator": calibrator.to_dict() if calibrator else None,
        "notes": notes,
    }
    return threshold, calibrator, info


def _calibrated(
    records: Sequence[CaseRecord], calibrators: dict[str, Calibrator | None]
) -> list[CaseRecord]:
    out: list[CaseRecord] = []
    for rec in records:
        scores = dict(rec.y_score)
        for label, cal in calibrators.items():
            raw = scores.get(label)
            if cal is not None and raw is not None:
                scores[label] = float(cal.transform([raw])[0])
        out.append(replace(rec, y_score=scores))
    return out


def not_applicable(reason: str, settings: CalibrationSettings) -> dict[str, Any]:
    """Return the result block used when no fit/apply cycle is possible."""
    return {
        "status": "not_applicable",
        "reason": reason,
        "fit_phase": FIT_PHASE,
        "eval_phase": EVAL_PHASE,
        "method": settings.method,
        "threshold_method": settings.threshold_method,
        "baseline_threshold": BASELINE_THRESHOLD,
        "per_label": {},
    }


def fit_and_apply(
    records: Sequence[PhasedRecord],
    labels: Sequence[str],
    settings: CalibrationSettings,
    *,
    n_boot: int = 1000,
    seed: int = 0,
) -> dict[str, Any]:
    """Fit per-label thresholds and calibrators on calibration records; score internal_test.

    Args:
        records: ``(phase, record)`` pairs of scored development cases.
        labels: Labels to fit and score.
        settings: Calibrator and threshold method.
        n_boot: Bootstrap replicates for the internal-test Task-A CIs.
        seed: Bootstrap seed.

    Raises:
        ValueError: if any record is not from ``calibration`` or ``internal_test``.
    """
    _check_phases(records)
    fit = [rec for phase, rec in records if phase == FIT_PHASE]
    held = [rec for phase, rec in records if phase == EVAL_PHASE]
    if not fit:
        return not_applicable("no scored calibration-phase cases to fit on", settings)
    if not held:
        return not_applicable("no scored internal_test cases to apply the fit to", settings)
    thresholds: dict[str, float] = {}
    calibrators: dict[str, Calibrator | None] = {}
    per_label: dict[str, Any] = {}
    for label in labels:
        thresholds[label], calibrators[label], per_label[label] = _fit_label(fit, label, settings)
    fixed = dict.fromkeys(labels, BASELINE_THRESHOLD)
    return {
        "status": "applied",
        "reason": None,
        "fit_phase": FIT_PHASE,
        "eval_phase": EVAL_PHASE,
        "method": settings.method,
        "threshold_method": settings.threshold_method,
        "baseline_threshold": BASELINE_THRESHOLD,
        "n_fit_cases": len(fit),
        "n_eval_cases": len(held),
        "per_label": per_label,
        "task_a_fixed": task_a(held, labels, thresholds=fixed, n_boot=n_boot, seed=seed).to_dict(),
        "task_a_fitted": task_a(
            held, labels, thresholds=thresholds, n_boot=n_boot, seed=seed
        ).to_dict(),
        "task_b_raw": {k: v.to_dict() for k, v in task_b(held, labels).items()},
        "task_b_calibrated": {
            k: v.to_dict() for k, v in task_b(_calibrated(held, calibrators), labels).items()
        },
    }
