# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Task B: calibration metrics (Brier, ECE, NLL, reliability curves)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from thoraxbench.scoring.classification import FloatArray, IntArray, label_arrays
from thoraxbench.scoring.records import CaseRecord

EPS = 1e-7


def brier(y: IntArray, p: FloatArray) -> float:
    """Mean squared difference between probability and outcome."""
    return float(np.mean((p - y) ** 2))


def nll(y: IntArray, p: FloatArray) -> float:
    """Mean binary negative log-likelihood (probabilities clipped to ``[1e-7, 1 - 1e-7]``)."""
    q = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))


def reliability(y: IntArray, p: FloatArray, n_bins: int = 10) -> list[dict[str, float | int]]:
    """Equal-width reliability bins with mean confidence, observed frequency and count."""
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1], right=True), 0, n_bins - 1)
    out: list[dict[str, float | int]] = []
    for b in range(n_bins):
        mask = idx == b
        if not np.any(mask):
            continue
        out.append(
            {
                "bin_low": float(edges[b]),
                "bin_high": float(edges[b + 1]),
                "mean_confidence": float(np.mean(p[mask])),
                "observed_frequency": float(np.mean(y[mask])),
                "count": int(np.sum(mask)),
            }
        )
    return out


def ece(y: IntArray, p: FloatArray, n_bins: int = 10) -> float:
    """Return the ECE: count-weighted mean |confidence - frequency| over bins."""
    n = len(y)
    return float(
        sum(
            int(b["count"]) / n * abs(float(b["mean_confidence"]) - float(b["observed_frequency"]))
            for b in reliability(y, p, n_bins)
        )
    )


@dataclass
class CalibrationMetrics:
    """Task-B metrics for one label."""

    label: str
    n: int
    brier: float | None
    ece: float | None
    nll: float | None
    curve: list[dict[str, float | int]]

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return dict(vars(self))


def task_b(
    cases: Sequence[CaseRecord], labels: Sequence[str], n_bins: int = 10
) -> dict[str, CalibrationMetrics]:
    """Score calibration per label (Vision §13 Task B)."""
    out: dict[str, CalibrationMetrics] = {}
    for lb in labels:
        y, p, _ = label_arrays(cases, lb)
        if len(y) == 0:
            out[lb] = CalibrationMetrics(lb, 0, None, None, None, [])
            continue
        out[lb] = CalibrationMetrics(
            lb, len(y), brier(y, p), ece(y, p, n_bins), nll(y, p), reliability(y, p, n_bins)
        )
    return out
