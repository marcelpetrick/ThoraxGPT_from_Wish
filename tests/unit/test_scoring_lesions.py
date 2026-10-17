# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Task C single-pass FROC equals a per-threshold sweep; LUNA16-style relaxations."""

import random

import pytest

from thoraxbench.schemas import LesionAnnotation
from thoraxbench.scoring import CaseRecord, PredictedLesion, task_c
from thoraxbench.scoring.lesions import FROC_FP_RATES, match_lesions


def _brute_force_froc_at(cases: list[CaseRecord]) -> dict[str, float]:
    """The original definition: re-match every scan at every distinct score threshold."""
    n_scans = len(cases)
    n_lesions = sum(len(c.reference_lesions) for c in cases)
    points = []
    for t in sorted({p.score for c in cases for p in c.predicted_lesions}, reverse=True):
        tp = fp = 0
        for c in cases:
            hit, fps = match_lesions(c.reference_lesions, c.predicted_lesions, min_score=t)
            tp += sum(hit)
            fp += fps
        points.append((fp / n_scans, tp / n_lesions))
    return {
        str(rate): max((s for f, s in points if f <= rate), default=0.0) for rate in FROC_FP_RATES
    }


def test_single_pass_froc_matches_brute_force_sweep() -> None:
    rng = random.Random(7)  # noqa: S311 - deterministic synthetic test cases, not security
    cases = []
    for k in range(12):
        refs = [
            LesionAnnotation(
                center_zyx=(rng.uniform(0, 100), rng.uniform(0, 100), rng.uniform(0, 100)),
                diameter_mm=rng.uniform(3, 25),
            )
            for _ in range(rng.randint(0, 3))
        ]
        preds = [
            PredictedLesion(
                (
                    r.center_zyx[0] + rng.uniform(-6, 6),
                    r.center_zyx[1] + rng.uniform(-6, 6),
                    r.center_zyx[2],
                ),
                None,
                round(rng.random(), 2),  # rounded scores create ties across scans
            )
            for r in refs
            if rng.random() < 0.8
        ] + [
            PredictedLesion(
                (rng.uniform(0, 100), rng.uniform(0, 100), rng.uniform(0, 100)),
                None,
                round(rng.random(), 2),
            )
            for _ in range(rng.randint(0, 6))
        ]
        cases.append(CaseRecord(f"c{k}", f"p{k}", reference_lesions=refs, predicted_lesions=preds))
    result = task_c(cases)
    assert result.froc_at == pytest.approx(_brute_force_froc_at(cases))
    assert result.froc[-1]["fp_per_scan"] == result.fp_per_scan
    sens = [pt["sensitivity"] for pt in result.froc]
    assert sens == sorted(sens)


def test_ignored_lesions_and_duplicate_hits() -> None:
    target = LesionAnnotation(center_zyx=(10, 10, 10), diameter_mm=8, readers=4)
    minor = LesionAnnotation(center_zyx=(60, 60, 60), diameter_mm=6, readers=1)
    preds = [
        PredictedLesion((10, 10, 11), None, 0.9),  # hit
        PredictedLesion((11, 10, 10), None, 0.8),  # duplicate on the hit target
        PredictedLesion((60, 60, 61), None, 0.7),  # on a fewer-reader lesion
        PredictedLesion((90, 90, 90), None, 0.6),  # real FP
    ]
    strict = task_c([CaseRecord("a", "p", reference_lesions=[target], predicted_lesions=preds)])
    assert (strict.sensitivity, strict.fp_per_scan) == (1.0, 3.0)
    relaxed = task_c(
        [
            CaseRecord(
                "a",
                "p",
                reference_lesions=[target],
                ignored_lesions=[minor],
                predicted_lesions=preds,
            )
        ],
        ignore_duplicate_hits=True,
    )
    assert (relaxed.sensitivity, relaxed.fp_per_scan) == (1.0, 1.0)
    hit, fps = match_lesions([target], preds, ignored=[minor], ignore_duplicate_hits=True)
    assert (hit, fps) == ([True], 1)


def test_no_predictions_or_lesions() -> None:
    empty = task_c([CaseRecord("a", "p")])
    assert empty.froc == []
    assert empty.froc_average is None
    assert empty.froc_at["8.0"] == 0.0
    only_fp = task_c([CaseRecord("a", "p", predicted_lesions=[PredictedLesion((0, 0, 0))])])
    assert only_fp.froc == [{"threshold": 1.0, "fp_per_scan": 1.0, "sensitivity": 0.0}]
