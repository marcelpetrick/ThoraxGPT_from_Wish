# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Task C: lesion-level nodule detection / localization (FROC).

Matching rule (documented in ``docs/benchmarking.md``): a prediction *hits* a reference
lesion when the Euclidean distance between their centres (mm, ``z, y, x``) is at most
``max(reference_diameter / 2, MIN_HIT_RADIUS_MM)``. Predictions are matched greedily in
descending score order; each reference lesion can be hit once; every unmatched prediction
is a false positive.

Optional LUNA16-style relaxations: predictions that hit an *ignored* annotation (an
"irrelevant finding", e.g. a nodule marked by fewer readers) are dropped, and with
``ignore_duplicate_hits`` a further prediction on an already-hit lesion is dropped instead
of counted as a false positive. Greedy matching in score order makes the outcome at every
threshold a prefix of one full pass, so the FROC sweep needs a single pass per scan.
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
TP, FP, IGNORED = 1, 0, -1


def _within(p: PredictedLesion, r: LesionAnnotation) -> bool:
    return math.dist(p.center_zyx, r.center_zyx) <= max(r.diameter_mm / 2, MIN_HIT_RADIUS_MM)


def _greedy(
    reference: Sequence[LesionAnnotation],
    predicted: Sequence[PredictedLesion],
    ignored: Sequence[LesionAnnotation] = (),
    *,
    ignore_duplicate_hits: bool = False,
) -> tuple[list[bool], list[tuple[float, int]]]:
    """One greedy pass: hit flags and ``(score, TP/FP/IGNORED)`` per prediction, best first."""
    hit = [False] * len(reference)
    events: list[tuple[float, int]] = []
    for p in sorted(predicted, key=lambda q: -q.score):
        best: int | None = None
        best_d = math.inf
        for i, r in enumerate(reference):
            if hit[i]:
                continue
            d = math.dist(p.center_zyx, r.center_zyx)
            if d <= max(r.diameter_mm / 2, MIN_HIT_RADIUS_MM) and d < best_d:
                best, best_d = i, d
        if best is not None:
            hit[best] = True
            events.append((p.score, TP))
        elif (ignore_duplicate_hits and any(_within(p, r) for r in reference)) or any(
            _within(p, r) for r in ignored
        ):
            events.append((p.score, IGNORED))
        else:
            events.append((p.score, FP))
    return hit, events


def match_lesions(
    reference: Sequence[LesionAnnotation],
    predicted: Sequence[PredictedLesion],
    *,
    min_score: float = -math.inf,
    ignored: Sequence[LesionAnnotation] = (),
    ignore_duplicate_hits: bool = False,
) -> tuple[list[bool], int]:
    """Return ``(hit flag per reference lesion, number of false positives)``."""
    hit, events = _greedy(
        reference,
        [p for p in predicted if p.score >= min_score],
        ignored,
        ignore_duplicate_hits=ignore_duplicate_hits,
    )
    return hit, sum(1 for _, outcome in events if outcome == FP)


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


def task_c(cases: Sequence[CaseRecord], *, ignore_duplicate_hits: bool = False) -> TaskCResult:
    """Score lesion detection over all scans (Vision §13 Task C).

    The FROC curve keeps each operating point where sensitivity rises plus the last point.
    Those points carry the lowest false-positive rate for their sensitivity, so ``froc_at``
    equals a sweep over every distinct score. ``froc_average`` over the seven rates
    0.125-8 FP/scan is the LUNA16 competition performance metric (CPM) form.
    """
    n_scans = len(cases)
    all_hits: list[tuple[LesionAnnotation, bool]] = []
    events: list[tuple[float, int]] = []
    for c in cases:
        hit, case_events = _greedy(
            c.reference_lesions,
            c.predicted_lesions,
            c.ignored_lesions,
            ignore_duplicate_hits=ignore_duplicate_hits,
        )
        all_hits.extend(zip(c.reference_lesions, hit, strict=True))
        events.extend(case_events)
    n_lesions = len(all_hits)
    total_fp = sum(1 for _, outcome in events if outcome == FP)
    result = TaskCResult(
        n_scans=n_scans,
        n_lesions=n_lesions,
        sensitivity=safe_div(sum(h for _, h in all_hits), n_lesions),
        fp_per_scan=safe_div(total_fp, n_scans),
    )
    # FROC: sweep the score threshold; all predictions with one score enter together.
    events.sort(key=lambda e: -e[0])
    tp = fp = 0
    last_tp = -1
    for k, (score, outcome) in enumerate(events):
        tp += outcome == TP
        fp += outcome == FP
        last = k + 1 == len(events)
        if not last and events[k + 1][0] == score:
            continue
        if tp != last_tp or last:
            result.froc.append(
                {
                    "threshold": score,
                    "fp_per_scan": fp / n_scans if n_scans else 0.0,
                    "sensitivity": tp / n_lesions if n_lesions else 0.0,
                }
            )
            last_tp = tp
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
