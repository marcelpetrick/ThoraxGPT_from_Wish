# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Task A: study-level multi-label detection metrics with patient-level bootstrap CIs."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve

from thoraxbench.scoring.records import CaseRecord

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int_]
Statistic = Callable[[IntArray, FloatArray], float | None]
FIXED_SPECIFICITIES = (0.8, 0.9, 0.95)
MIN_VALID_REPLICATES = 10


def label_arrays(cases: Sequence[CaseRecord], label: str) -> tuple[IntArray, FloatArray, list[str]]:
    """Return ``(y_true, y_score, patient_ids)`` for cases where both values are known."""
    ys: list[int] = []
    ps: list[float] = []
    pids: list[str] = []
    for c in cases:
        t = c.y_true.get(label)
        s = c.y_score.get(label)
        if t is None or s is None:
            continue
        ys.append(int(t))
        ps.append(float(s))
        pids.append(c.patient_id)
    return np.asarray(ys, dtype=np.int_), np.asarray(ps, dtype=np.float64), pids


def safe_div(num: float, den: float) -> float | None:
    """``num / den`` or ``None`` when the denominator is zero."""
    return num / den if den else None


@dataclass
class ConfusionCounts:
    """Binary confusion-matrix counts."""

    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    @classmethod
    def from_arrays(
        cls, y_true: IntArray, y_score: FloatArray, threshold: float
    ) -> ConfusionCounts:
        """Count outcomes at *threshold* (positive when ``score >= threshold``)."""
        pred = y_score >= threshold
        truth = y_true.astype(bool)
        return cls(
            tp=int(np.sum(pred & truth)),
            fp=int(np.sum(pred & ~truth)),
            tn=int(np.sum(~pred & ~truth)),
            fn=int(np.sum(~pred & truth)),
        )

    def add(self, other: ConfusionCounts) -> None:
        """Accumulate *other* into these counts (for micro averages)."""
        self.tp += other.tp
        self.fp += other.fp
        self.tn += other.tn
        self.fn += other.fn

    def metrics(self) -> dict[str, float | None]:
        """Sensitivity, specificity, PPV, NPV, F1 and balanced accuracy."""
        sens = safe_div(self.tp, self.tp + self.fn)
        spec = safe_div(self.tn, self.tn + self.fp)
        bal = (sens + spec) / 2 if sens is not None and spec is not None else None
        return {
            "sensitivity": sens,
            "specificity": spec,
            "ppv": safe_div(self.tp, self.tp + self.fp),
            "npv": safe_div(self.tn, self.tn + self.fn),
            "f1": safe_div(2 * self.tp, 2 * self.tp + self.fp + self.fn),
            "balanced_accuracy": bal,
        }


def auroc_auprc(y: IntArray, s: FloatArray) -> tuple[float | None, float | None]:
    """AUROC and AUPRC, or ``(None, None)`` when only one reference class is present."""
    if len(y) == 0 or len(np.unique(y)) < 2:
        return None, None
    return float(roc_auc_score(y, s)), float(average_precision_score(y, s))


def sensitivity_at_specificity(
    y_true: IntArray, y_score: FloatArray, specificity: float
) -> float | None:
    """Highest sensitivity reachable while specificity stays ``>= specificity``."""
    if len(np.unique(y_true)) < 2:
        return None
    fpr, tpr, _ = roc_curve(y_true, y_score)
    ok = (1.0 - fpr) >= specificity - 1e-12
    return float(np.max(tpr[ok]))


def bootstrap_ci(
    y_true: IntArray,
    y_score: FloatArray,
    patient_ids: Sequence[str],
    statistic: Statistic,
    *,
    n_boot: int = 1000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float] | None:
    """Percentile CI from resampling **patients** (not studies) with replacement.

    Replicates where the statistic is undefined (e.g. a single class) are skipped; with fewer
    than ten valid replicates the interval is ``None``.
    """
    if len(y_true) == 0:
        return None
    pids = np.asarray(patient_ids)
    unique = np.unique(pids)
    index_of = {p: np.flatnonzero(pids == p) for p in unique}
    rng = np.random.default_rng(seed)
    values: list[float] = []
    for _ in range(n_boot):
        drawn = rng.choice(unique, size=len(unique), replace=True)
        idx = np.concatenate([index_of[p] for p in drawn])
        val = statistic(y_true[idx], y_score[idx])
        if val is not None:
            values.append(val)
    if len(values) < MIN_VALID_REPLICATES:
        return None
    lo, hi = np.percentile(values, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


def _auroc_stat(y: IntArray, s: FloatArray) -> float | None:
    return auroc_auprc(y, s)[0]


def _point_stat(name: str, threshold: float) -> Statistic:
    def stat(y: IntArray, s: FloatArray) -> float | None:
        return ConfusionCounts.from_arrays(y, s, threshold).metrics()[name]

    return stat


@dataclass
class LabelMetrics:
    """Task-A metrics for one label."""

    label: str
    n: int
    n_positive: int
    threshold: float
    auroc: float | None = None
    auprc: float | None = None
    counts: ConfusionCounts | None = None
    point: dict[str, float | None] = field(default_factory=dict)
    sens_at_spec: dict[str, float | None] = field(default_factory=dict)
    ci: dict[str, tuple[float, float] | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "label": self.label,
            "n": self.n,
            "n_positive": self.n_positive,
            "prevalence": safe_div(self.n_positive, self.n),
            "threshold": self.threshold,
            "auroc": self.auroc,
            "auprc": self.auprc,
            "counts": vars(self.counts) if self.counts else None,
            **self.point,
            "sensitivity_at_specificity": self.sens_at_spec,
            "ci95": {k: list(v) if v else None for k, v in self.ci.items()},
            "notes": self.notes,
        }


def score_label(
    cases: Sequence[CaseRecord],
    label: str,
    *,
    threshold: float = 0.5,
    n_boot: int = 1000,
    seed: int = 0,
) -> LabelMetrics:
    """Compute every Task-A metric for *label*."""
    y, s, pids = label_arrays(cases, label)
    if len(y) == 0:
        return LabelMetrics(
            label, 0, 0, threshold, notes=["no cases with both reference and prediction"]
        )
    notes: list[str] = []
    auroc, auprc = auroc_auprc(y, s)
    if auroc is None:
        notes.append("AUROC/AUPRC undefined: only one reference class present")
    counts = ConfusionCounts.from_arrays(y, s, threshold)
    sas = {f"{sp:.2f}": sensitivity_at_specificity(y, s, sp) for sp in FIXED_SPECIFICITIES}
    ci: dict[str, tuple[float, float] | None] = {}
    if n_boot > 0:
        ci["auroc"] = bootstrap_ci(y, s, pids, _auroc_stat, n_boot=n_boot, seed=seed)
        for name in ("sensitivity", "specificity", "f1"):
            ci[name] = bootstrap_ci(
                y, s, pids, _point_stat(name, threshold), n_boot=n_boot, seed=seed
            )
    return LabelMetrics(
        label=label,
        n=len(y),
        n_positive=int(y.sum()),
        threshold=threshold,
        auroc=auroc,
        auprc=auprc,
        counts=counts,
        point=counts.metrics(),
        sens_at_spec=sas,
        ci=ci,
        notes=notes,
    )


@dataclass
class TaskAResult:
    """Task-A results across labels."""

    per_label: dict[str, LabelMetrics]
    macro_f1: float | None
    micro_f1: float | None
    macro_auroc: float | None

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "macro_f1": self.macro_f1,
            "micro_f1": self.micro_f1,
            "macro_auroc": self.macro_auroc,
            "per_label": {k: v.to_dict() for k, v in self.per_label.items()},
        }


def task_a(
    cases: Sequence[CaseRecord],
    labels: Sequence[str],
    *,
    thresholds: dict[str, float] | None = None,
    n_boot: int = 1000,
    seed: int = 0,
) -> TaskAResult:
    """Score study-level multi-label detection (Vision §13 Task A)."""
    thresholds = thresholds or {}
    per = {
        lb: score_label(cases, lb, threshold=thresholds.get(lb, 0.5), n_boot=n_boot, seed=seed)
        for lb in labels
    }
    f1s = [f for m in per.values() if (f := m.point.get("f1")) is not None]
    aucs = [m.auroc for m in per.values() if m.auroc is not None]
    total = ConfusionCounts()
    for m in per.values():
        if m.counts:
            total.add(m.counts)
    return TaskAResult(
        per_label=per,
        macro_f1=float(np.mean(f1s)) if f1s else None,
        micro_f1=total.metrics()["f1"],
        macro_auroc=float(np.mean(aucs)) if aucs else None,
    )
