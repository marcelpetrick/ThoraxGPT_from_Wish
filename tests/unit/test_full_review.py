# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Full thorax review: sweep coverage/order, aggregation, ranking, outcome and HTML."""

from __future__ import annotations

import base64
import itertools
from pathlib import Path
from typing import Any

import pytest

from thoraxbench.fullreview import (
    Candidate,
    Cluster,
    SlabAnswers,
    StudyLevelCue,
    aggregate_labels,
    next_steps,
    rank_look_here,
    thresholds,
    verdict_of,
)
from thoraxbench.fullreview import aggregate as agg
from thoraxbench.reports.full_review import SHORT_DISCLAIMER, render_full_review_html
from thoraxbench.sampling import ThoraxSweep, coarse_to_fine, get_strategy
from thoraxbench.study import Study, load_study_dir

LABELS = ["pulmonary_nodule", "pleural_effusion", "emphysema"]


@pytest.fixture(scope="module")
def study(phantom_dir: Path) -> Study:
    return load_study_dir(phantom_dir, dataset="phantom")


# -- B1 strategy --------------------------------------------------------------------------
@pytest.mark.parametrize("n", [0, 1, 2, 3, 5, 9, 17, 64])
def test_coarse_to_fine_visits_every_position_once(n: int) -> None:
    order = coarse_to_fine(n)
    assert sorted(order) == list(range(n))


def test_coarse_to_fine_is_ends_middle_quarters_then_eighths() -> None:
    order = coarse_to_fine(9)
    assert order[:3] == [0, 8, 4]
    assert set(order[3:5]) == {2, 6}
    assert set(order[5:]) == {1, 3, 5, 7}


def test_thorax_sweep_tiles_lungs_plus_margins_contiguously(study: Study) -> None:
    sweep = ThoraxSweep()
    sel = sweep.select(study.volume, study.cues)
    dz = study.volume.spacing_mm[0]
    lo, hi = study.cues.lung_z_extent or (0, 0)
    bounds = sel.slab_bounds
    assert bounds[0][0] == max(0, lo - round(sweep.cranial_margin_mm / dz))
    assert bounds[-1][1] - 1 == min(study.volume.shape[0] - 1, hi + round(30.0 / dz))
    assert all(a[1] == b[0] for a, b in itertools.pairwise(bounds))
    assert all(a < b for a, b in bounds)
    assert sel.indices == sorted(set(sel.indices))
    assert all(a <= c < b for c, (a, b) in zip(sel.indices, bounds, strict=True))
    assert sorted(sel.visit_order) == list(range(len(bounds)))
    assert sel.visit_order[:2] == [0, len(bounds) - 1]
    assert sel.slab_mm == pytest.approx(5.0)
    assert any("upper abdomen" in tag for tag in sel.tags)
    assert any("chest" in tag for tag in sel.tags)


def test_thorax_sweep_widens_slabs_to_respect_cap(study: Study) -> None:
    sel = get_strategy("thorax_sweep", n=8).select(study.volume, study.cues)
    assert len(sel.indices) <= 8
    assert sel.slab_mm > 5.0
    span = sel.slab_bounds[-1][1] - sel.slab_bounds[0][0]
    assert sum(b - a for a, b in sel.slab_bounds) == span


def test_thorax_sweep_without_landmarks_and_hash(study: Study) -> None:
    cues = study.cues.model_copy(update={"landmarks": None})
    sel = ThoraxSweep().select(study.volume, cues)
    assert {"upper chest", "mid chest", "lower chest"} <= set(sel.tags)
    assert ThoraxSweep().sha256 != ThoraxSweep(slab_mm=10.0).sha256
    assert ThoraxSweep().params["caudal_margin_mm"] == 30.0


# -- B3 aggregation -----------------------------------------------------------------------
def _slab(position: int, **answers: bool | None) -> SlabAnswers:
    return SlabAnswers(
        position,
        position * 2,
        position * 2 + 2,
        {label: answers.get(label, False) for label in LABELS},
        evidence={k: f"spot {position}" for k, v in answers.items() if v},
        sides={k: "right" for k, v in answers.items() if v},
    )


def test_clusters_bridge_one_slab_gap_but_not_two() -> None:
    slabs = [_slab(i) for i in range(12)]
    for pos in (2, 4, 9):
        slabs[pos] = _slab(pos, pulmonary_nodule=True)
    result = aggregate_labels(slabs, LABELS)
    nodule = result.labels["pulmonary_nodule"]
    assert nodule.status == "flagged"
    assert [(c.first_slab, c.last_slab) for c in nodule.clusters] == [(2, 4), (9, 9)]
    first = nodule.clusters[0]
    assert (first.slice_lo, first.slice_hi) == (4, 9)
    assert (first.positive_slabs, first.spanned_slabs) == (2, 3)
    assert first.side == "right"
    assert first.evidence == ["spot 2", "spot 4"]
    assert result.labels["emphysema"].status == "no_flags"
    assert result.model_constant is False


def test_constant_label_is_not_informative_and_none_is_not_negative() -> None:
    slabs = [_slab(i, emphysema=True) for i in range(7)] + [_slab(7), _slab(8)]
    slabs.append(SlabAnswers(9, 18, 20, dict.fromkeys(LABELS)))
    result = aggregate_labels(slabs, LABELS)
    emphysema = result.labels["emphysema"]
    assert emphysema.status == "not_informative"
    assert emphysema.clusters == []
    assert emphysema.answered == 9
    assert emphysema.positive_rate == pytest.approx(7 / 9)
    assert result.labels["pleural_effusion"].status == "no_flags"


def test_rate_at_threshold_is_still_informative() -> None:
    slabs = [_slab(i, emphysema=i < 3) for i in range(5)]  # 3/5 = 0.6, not above
    assert aggregate_labels(slabs, LABELS).labels["emphysema"].status == "flagged"


def test_model_answering_yes_everywhere_is_constant() -> None:
    slabs = [_slab(i, **dict.fromkeys(LABELS, True)) for i in range(10)]
    slabs[0] = _slab(0, pulmonary_nodule=True)
    result = aggregate_labels(slabs, LABELS)
    assert result.model_constant is True
    assert {s.status for s in result.labels.values()} == {"not_informative"}
    assert all(not s.clusters for s in result.labels.values())


def test_unanswered_labels_and_empty_input() -> None:
    result = aggregate_labels([], LABELS)
    assert result.overall_positive_rate is None
    assert {s.status for s in result.labels.values()} == {"unanswered"}


# -- B4 ranking ---------------------------------------------------------------------------
def _cluster(label: str, lo: int, hi: int, side: str = "right", positives: int = 2) -> Cluster:
    return Cluster(label, lo // 2, hi // 2, lo, hi, positives, positives, side, ["seen"])


def test_detector_inside_vlm_nodule_cluster_ranks_first_with_agreement() -> None:
    ranked = rank_look_here(
        [_cluster("pulmonary_nodule", 20, 25), _cluster("consolidation", 40, 45)],
        [
            Candidate("detector", "pulmonary_nodule", 23, "right", 0.7, 6.0),
            Candidate("detector", "pulmonary_nodule", 60, "left", 0.95, 9.0),
            Candidate("detector", "pulmonary_nodule", 70, "left", 0.2, 4.0),
            Candidate("hu", "pulmonary_nodule", 24, "right", None, 7.5),
        ],
        [StudyLevelCue("pleural_effusion", "left", "fluid 300 ml")],
        slab_slices=2,
        spacing_z_mm=2.5,
    )
    assert [i.rank for i in ranked] == list(range(1, len(ranked) + 1))
    top = ranked[0]
    assert top.sources == ["detector", "hu", "vlm"]
    assert top.agreement is True
    assert (top.slice_lo, top.detector_score, top.size_mm) == (23, 0.7, 6.0)
    assert top.vlm_positive_slabs == 2
    assert top.evidence == ["seen"]
    labels = [(i.label, tuple(i.sources)) for i in ranked]
    assert ("pulmonary_nodule", ("detector",)) in labels  # the 0.95 candidate alone
    assert all(i.detector_score != 0.2 for i in ranked)  # below cut-off ignored
    assert ("consolidation", ("vlm",)) in labels  # non-nodule clusters never merge
    assert ranked[-1].slice_lo is None  # whole-scan cue last among single sources
    lone = next(i for i in ranked if i.sources == ["detector"])
    assert ranked.index(lone) < labels.index(("consolidation", ("vlm",)))


def test_ranking_respects_side_and_tolerance() -> None:
    ranked = rank_look_here(
        [_cluster("pulmonary_nodule", 20, 21, side="left")],
        [
            Candidate("detector", "pulmonary_nodule", 21, "right", 0.8, None),
            Candidate("detector", "pulmonary_nodule", 30, "left", 0.8, None),
        ],
        [],
        slab_slices=2,
        spacing_z_mm=5.0,
    )
    assert all(not item.agreement for item in ranked)
    assert len(ranked) == 3


def test_ranking_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agg, "MAX_LOOK_HERE", 3)
    many = [Candidate("hu", "pulmonary_nodule", i * 10, "right", None, 5.0) for i in range(8)]
    assert len(rank_look_here([], many, [], slab_slices=1, spacing_z_mm=1.0)) == 3


# -- B6 outcome ---------------------------------------------------------------------------
def test_verdicts() -> None:
    item = rank_look_here([], [], [StudyLevelCue("emphysema")], slab_slices=1, spacing_z_mm=1)
    kwargs: dict[str, Any] = {"answered_slabs": 10, "model_constant": False}
    # Density rules alone are a weak cue: listed, but never the verdict (2026-10-20 review).
    assert item[0].weak
    assert verdict_of(item, detector_completed=False, **kwargs) == (
        "nothing_flagged_in_checked_area"
    )
    detector = rank_look_here(
        [],
        [Candidate("detector", "pulmonary_nodule", 40, "right", 0.9, 5.3)],
        [StudyLevelCue("emphysema")],
        slab_slices=1,
        spacing_z_mm=1,
    )
    assert [entry.weak for entry in detector] == [False, True]
    assert verdict_of(detector, detector_completed=True, **kwargs) == "findings_to_review"
    assert verdict_of([], detector_completed=False, **kwargs) == "nothing_flagged_in_checked_area"
    assert (
        verdict_of([], answered_slabs=10, model_constant=True, detector_completed=False)
        == "not_assessable"
    )
    assert (
        verdict_of([], answered_slabs=0, model_constant=False, detector_completed=True)
        == "nothing_flagged_in_checked_area"
    )
    assert verdict_of(item, study_adequate=False, detector_completed=True, **kwargs) == (
        "not_assessable"
    )


def test_next_steps_use_existing_guideline_rules_only() -> None:
    names = {"pulmonary_nodule": "Pulmonary nodule", "pleural_effusion": "Pleural effusion"}
    items = rank_look_here(
        [],
        [Candidate("detector", "pulmonary_nodule", 10, "right", 0.9, 7.0)],
        [StudyLevelCue("pleural_effusion", "left")],
        slab_slices=1,
        spacing_z_mm=1.0,
    )
    steps = next_steps(items, "findings_to_review", names)
    assert steps[0].startswith("Show the listed places")
    assert "Fleischner Society 2017" in steps[1]
    assert "slice 11, right side, about 7 mm" in steps[1]
    assert steps[2].startswith("Pleural effusion: general guideline context")
    assert "radiologist" in next_steps([], "nothing_flagged_in_checked_area", names)[0]
    assert "cannot assess" in next_steps([], "not_assessable", names)[0]
    assert thresholds()["constant_label_rate"] == agg.CONSTANT_LABEL_RATE


# -- HTML ---------------------------------------------------------------------------------
def _summary(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "verdict": "findings_to_review",
        "model_id": "medgemma1.5-q4",
        "prompt_id": "P7",
        "coverage": {
            "slabs_total": 10,
            "slabs_visited": 4,
            "slabs_answered": 4,
            "partial": True,
            "stopped": True,
            "slab_mm": 5.0,
            "slices_total": 64,
            "covered_slices": [2, 61],
        },
        "label_names": {"pulmonary_nodule": "Pulmonary nodule", "emphysema": "Emphysema"},
        "look_here": [
            {
                "label": "pulmonary_nodule",
                "slice_lo": 20,
                "slice_hi": 23,
                "side": "right",
                "sources": ["detector", "vlm"],
                "agreement": True,
                "detector_score": 0.81,
                "size_mm": 7.0,
                "vlm_positive_slabs": 2,
                "vlm_spanned_slabs": 2,
                "evidence": ["<script>alert(1)</script>"],
                "rank": 1,
            }
        ],
        "labels_no_flags": ["emphysema"],
        "labels_not_informative": [],
        "labels_unanswered": [],
        "model_constant": False,
        "next_steps": ["Show the listed places (slice numbers) to a radiologist."],
        "detector": {"status": "completed", "candidates": 3},
        "heuristic": {"status": "completed"},
        "slabs": [
            {"position": 4, "slice_lo": 20, "slice_hi": 21},
            {"position": 5, "slice_lo": 22, "slice_hi": 23},
        ],
        "timing": {"seconds_per_image": 9.84, "total_s": 120.0},
        "provenance": {"strategy": {"id": "thorax_sweep"}, "strategy_sha256": "ab" * 32},
    }
    return base | overrides


def test_html_is_plain_escaped_and_embeds_model_slab_images() -> None:
    page = render_full_review_html(_summary(), {4: b"\x89PNG-fake", 5: b"\x89PNG-two"})
    assert page.count(SHORT_DISCLAIMER) == 1
    assert "Something to show a radiologist" in page
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert "slices 21 to 24, right side" in page
    assert "checked 4 of 10 slabs (40 %)" in page
    assert "partial result because it was stopped" in page
    assert page.count("data:image/png;base64,") == 2
    assert base64.b64encode(b"\x89PNG-fake").decode() in page
    assert "Several independent tools" in page
    assert "9.8 s" in page


@pytest.mark.parametrize(
    ("verdict", "text"),
    [
        ("nothing_flagged_in_checked_area", "does not mean the scan is normal"),
        ("not_assessable", "could not be assessed"),
    ],
)
def test_html_other_verdicts_and_constant_model(verdict: str, text: str) -> None:
    summary = _summary(
        verdict=verdict,
        look_here=[],
        model_constant=True,
        overall_positive_rate=0.97,
        detector={"status": "unavailable"},
        coverage={
            "slabs_total": 0,
            "slabs_visited": 0,
            "slabs_answered": 0,
            "partial": False,
            "slab_mm": 0.0,
            "slices_total": 64,
        },
    )
    page = render_full_review_html(summary, {})
    assert text in page
    assert "97 %" in page
    assert "did not run (unavailable)" in page
    assert "No part of the scan was checked" in page


def test_html_lists_constant_labels_and_runtime_failure() -> None:
    cov = _summary()["coverage"] | {"stopped": False, "runtime_failed": True}
    page = render_full_review_html(_summary(labels_not_informative=["emphysema"], coverage=cov), {})
    assert "said “yes” on most slabs (Emphysema)" in page
    assert "model runtime kept failing" in page
