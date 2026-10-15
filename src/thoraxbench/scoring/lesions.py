# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Task C: lesion-level nodule detection / localization (FROC).

Matching rule (documented in ``docs/benchmarking.md``): a prediction *hits* a reference
lesion when the Euclidean distance between their centres (mm, ``z, y, x``) is at most
``max(reference_diameter / 2, MIN_HIT_RADIUS_MM)``. Predictions are matched greedily in
descending score order; each reference lesion can be hit once; every unmatched prediction
is a false positive.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from thoraxbench.schemas import LesionAnnotation
from thoraxbench.scoring.classification import safe_div
from thoraxbench.scoring.records import CaseRecord, PredictedLesion

MIN_HIT_RADIUS_MM = 5.0
FROC_FP_RATES = (0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
# Fleischner-aligned size strata (mm); >= 30 mm is a mass.
SIZE_BINS: tuple[tuple[str, float, float], ...] = (
    ("<6", 0.0, 6.0),
    ("6-8", 6.0, 8.0),
    ("8-15", 8.0, 15.0),
    ("15-30", 15.0, 30.0),
    (">=30", 30.0, math.inf),
)
READER_LEVELS = (1, 2, 3, 4)


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.dist(a, b)


def match_lesions(
    reference: Sequence[LesionAnnotation],
    predicted: Sequence[PredictedLesion],
    *,
    min_score: float = -math.inf,
) -> tuple[list[bool], int]:
    """Return ``(hit flag per reference lesion, number of false positives)``."""
    preds = sorted((p for p in predicted if p.score >= min_score), key=lambda p: -p.score)
    hit = [False] * len(reference)
    fps = 0
    for p in preds:
        best: int | None = None
        best_d = math.inf
        for i, r in enumerate(reference):
            if hit[i]:
                continue
            d = _distance(p.center_zyx, r.center_zyx)
            if d <= max(r.diameter_mm / 2, MIN_HIT_RADIUS_MM) and d < best_d:
                best, best_d = i, d
        if best is None:
            fps += 1
        else:
            hit[best] = True
    return hit, fps


@dataclass
class TaskCResult:
    """Lesion-level metrics."""

    n_scans: int
    n_lesions: int
    sensitivity: float | None
    fp_per_scan: float | None
    froc: list[dict[str, float]] = field(default_factory=list)
    froc_at: dict[str, float] = field(default_factory=dict)
    froc_average: float | None = None
    by_size: dict[str, dict[str, float | int | None]] = field(default_factory=dict)
    by_readers: dict[str, dict[str, float | int | None]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return dict(vars(self))


def _stratum(hits: list[tuple[LesionAnnotation, bool]]) -> dict[str, float | int | None]:
    n = len(hits)
    k = sum(h for _, h in hits)
    return {"n": n, "hits": k, "sensitivity": safe_div(k, n)}


def task_c(cases: Sequence[CaseRecord]) -> TaskCResult:
    """Score lesion detection over all scans (Vision §13 Task C)."""
    n_scans = len(cases)
    all_hits: list[tuple[LesionAnnotation, bool]] = []
    total_fp = 0
    for c in cases:
        hit, fps = match_lesions(c.reference_lesions, c.predicted_lesions)
        all_hits.extend(zip(c.reference_lesions, hit, strict=True))
        total_fp += fps
    n_lesions = len(all_hits)
    result = TaskCResult(
        n_scans=n_scans,
        n_lesions=n_lesions,
        sensitivity=safe_div(sum(h for _, h in all_hits), n_lesions),
        fp_per_scan=safe_div(total_fp, n_scans),
    )
    # FROC: sweep the prediction-score threshold
    scores = sorted({p.score for c in cases for p in c.predicted_lesions}, reverse=True)
    for t in scores:
        tp = fp = 0
        for c in cases:
            hit, fps = match_lesions(c.reference_lesions, c.predicted_lesions, min_score=t)
            tp += sum(hit)
            fp += fps
        result.froc.append(
            {
                "threshold": t,
                "fp_per_scan": fp / n_scans if n_scans else 0.0,
                "sensitivity": tp / n_lesions if n_lesions else 0.0,
            }
        )
    for rate in FROC_FP_RATES:
        ok = [pt["sensitivity"] for pt in result.froc if pt["fp_per_scan"] <= rate]
        result.froc_at[str(rate)] = max(ok) if ok else 0.0
    if n_lesions:
        result.froc_average = float(np.mean(list(result.froc_at.values())))
    for name, lo, hi in SIZE_BINS:
        result.by_size[name] = _stratum([(r, h) for r, h in all_hits if lo <= r.diameter_mm < hi])
    for level in READER_LEVELS:
        result.by_readers[f">={level}"] = _stratum(
            [(r, h) for r, h in all_hits if r.readers >= level]
        )
    return result
