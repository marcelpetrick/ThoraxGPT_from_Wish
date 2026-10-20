# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Pure aggregation of a full thorax review (no I/O, no model calls).

* :func:`aggregate_labels` turns per-slab yes/no answers into per-label positive rates and
  localized clusters, and flags constant answers as not informative (B3).
* :func:`rank_look_here` merges detector candidates, HU cues and VLM clusters into one
  ranked "look here" list with sources and agreement (B4).
* :func:`verdict_of` and :func:`next_steps` derive the plain outcome; next steps reuse the
  existing rule-based guideline code and knowledge base only (no new medical advice).

Every threshold is a named constant and is recorded in the run provenance via
:func:`thresholds`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from thoraxbench.ontology.clinical import load_clinical_kb
from thoraxbench.ontology.guidelines import fleischner

#: Version of the aggregation/ranking rules (bump on any rule change).
AGGREGATION_VERSION = "2"
#: A label positive on more than this share of its answered slabs is "not informative".
CONSTANT_LABEL_RATE = 0.6
#: A model whose positives exceed this share of all answered (label, slab) pairs is constant.
MODEL_CONSTANT_RATE = 0.85
#: Non-positive slabs allowed inside one cluster (``1`` = a single missing slab is bridged).
CLUSTER_GAP_SLABS = 1
#: A detector/HU point inside a VLM cluster widened by this many slabs counts as agreement.
MATCH_TOLERANCE_SLABS = 1
#: Detector and HU candidates closer than this (z, millimetres) are the same place.
CANDIDATE_MATCH_MM = 10.0
#: Detector candidates at or above this score enter the list (adapter convention).
DETECTOR_MIN_SCORE = 0.5
#: Bounded output: at most this many HU nodule candidates and look-here entries.
MAX_HU_CANDIDATES = 10
MAX_LOOK_HERE = 25
MAX_NEXT_STEPS = 8
#: Labels whose VLM clusters can agree with a nodule detector / HU nodule candidate.
NODULE_LABELS = frozenset({"pulmonary_nodule", "pulmonary_mass"})

Verdict = Literal["findings_to_review", "nothing_flagged_in_checked_area", "not_assessable"]
LabelStatus = Literal["flagged", "not_informative", "no_flags", "unanswered"]


def thresholds() -> dict[str, Any]:
    """All aggregation constants for provenance."""
    return {
        "aggregation_version": AGGREGATION_VERSION,
        "constant_label_rate": CONSTANT_LABEL_RATE,
        "model_constant_rate": MODEL_CONSTANT_RATE,
        "cluster_gap_slabs": CLUSTER_GAP_SLABS,
        "match_tolerance_slabs": MATCH_TOLERANCE_SLABS,
        "candidate_match_mm": CANDIDATE_MATCH_MM,
        "detector_min_score": DETECTOR_MIN_SCORE,
        "max_hu_candidates": MAX_HU_CANDIDATES,
        "max_look_here": MAX_LOOK_HERE,
        "max_next_steps": MAX_NEXT_STEPS,
    }


@dataclass(frozen=True)
class SlabAnswers:
    """Answers of one visited slab: ``position`` is the cranial-first slab number."""

    position: int
    lo: int
    hi: int  # half-open source-slice range
    answers: dict[str, bool | None]
    evidence: dict[str, str] = field(default_factory=dict)
    sides: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Cluster:
    """Neighbouring positive slabs of one label (slice range inclusive, zero-based)."""

    label: str
    first_slab: int
    last_slab: int
    slice_lo: int
    slice_hi: int
    positive_slabs: int
    spanned_slabs: int
    side: str
    evidence: list[str]


@dataclass(frozen=True)
class LabelSummary:
    """Per-label aggregate across all answered slabs."""

    label: str
    status: LabelStatus
    answered: int
    positives: int
    positive_rate: float | None
    clusters: list[Cluster]


@dataclass(frozen=True)
class Aggregate:
    """Result of :func:`aggregate_labels`."""

    labels: dict[str, LabelSummary]
    model_constant: bool
    overall_positive_rate: float | None


@dataclass(frozen=True)
class Candidate:
    """A located detector or HU candidate (``slice_index`` zero-based)."""

    source: Literal["detector", "hu"]
    label: str
    slice_index: int
    side: str = "unknown"
    score: float | None = None
    size_mm: float | None = None


@dataclass(frozen=True)
class StudyLevelCue:
    """A positive HU heuristic finding without a slice location (e.g. effusion volume)."""

    label: str
    side: str = "unknown"
    description: str = ""


@dataclass
class LookHere:
    """One place to look; ``slice_lo``/``slice_hi`` are ``None`` for whole-scan cues."""

    label: str
    slice_lo: int | None
    slice_hi: int | None
    side: str
    sources: list[str]
    agreement: bool = False
    detector_score: float | None = None
    size_mm: float | None = None
    vlm_positive_slabs: int = 0
    vlm_spanned_slabs: int = 0
    evidence: list[str] = field(default_factory=list)
    rank: int = 0
    #: Only the HU density rules point here; listed as a weak cue, never the verdict alone.
    weak: bool = False

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready dictionary."""
        return asdict(self)


def _side_of(sides: list[str]) -> str:
    known = [s for s in sides if s in {"left", "right", "bilateral"}]
    if not known:
        return "unknown"
    counts = Counter(known)
    if {"left", "right"} <= set(counts) or "bilateral" in counts:
        return "bilateral"
    return counts.most_common(1)[0][0]


def _clusters(label: str, slabs: list[SlabAnswers]) -> list[Cluster]:
    """Group positive slabs; up to ``CLUSTER_GAP_SLABS`` non-positive slabs are bridged."""
    positives = sorted((s for s in slabs if s.answers.get(label) is True), key=lambda s: s.position)
    groups: list[list[SlabAnswers]] = []
    for slab in positives:
        if groups and slab.position - groups[-1][-1].position <= CLUSTER_GAP_SLABS + 1:
            groups[-1].append(slab)
        else:
            groups.append([slab])
    out: list[Cluster] = []
    for group in groups:
        texts = [s.evidence[label] for s in group if s.evidence.get(label)]
        out.append(
            Cluster(
                label=label,
                first_slab=group[0].position,
                last_slab=group[-1].position,
                slice_lo=group[0].lo,
                slice_hi=group[-1].hi - 1,
                positive_slabs=len(group),
                spanned_slabs=group[-1].position - group[0].position + 1,
                side=_side_of([s.sides.get(label, "unknown") for s in group]),
                evidence=list(dict.fromkeys(texts))[:3],
            )
        )
    return out


def aggregate_labels(slabs: list[SlabAnswers], labels: list[str]) -> Aggregate:
    """Per-label rates and clusters; constant answers are not informative (B3).

    A label's rate counts only slabs that answered it (``True``/``False``); ``None`` is
    unavailable, never negative. When the whole model is constant (overall positive share
    above ``MODEL_CONSTANT_RATE``) every label with positives is not informative.
    """
    answered_pairs = 0
    positive_pairs = 0
    counts: dict[str, tuple[int, int]] = {}
    for label in labels:
        values = [s.answers.get(label) for s in slabs]
        answered = sum(v is not None for v in values)
        positives = sum(v is True for v in values)
        counts[label] = (answered, positives)
        answered_pairs += answered
        positive_pairs += positives
    overall = positive_pairs / answered_pairs if answered_pairs else None
    model_constant = overall is not None and overall > MODEL_CONSTANT_RATE
    summaries: dict[str, LabelSummary] = {}
    for label in labels:
        answered, positives = counts[label]
        rate = positives / answered if answered else None
        status: LabelStatus
        clusters: list[Cluster] = []
        if not answered:
            status = "unanswered"
        elif positives and (model_constant or (rate is not None and rate > CONSTANT_LABEL_RATE)):
            status = "not_informative"
        elif positives:
            status = "flagged"
            clusters = _clusters(label, slabs)
        else:
            status = "no_flags"
        summaries[label] = LabelSummary(label, status, answered, positives, rate, clusters)
    return Aggregate(summaries, model_constant, overall)


def _near(z: int, lo: int, hi: int, tolerance: int) -> bool:
    return lo - tolerance <= z <= hi + tolerance


def _sides_compatible(a: str, b: str) -> bool:
    return "unknown" in {a, b} or "bilateral" in {a, b} or a == b


def rank_look_here(
    clusters: list[Cluster],
    candidates: list[Candidate],
    cues: list[StudyLevelCue],
    *,
    slab_slices: int,
    spacing_z_mm: float,
) -> list[LookHere]:
    """One ranked list of places to look, with sources and agreement (pure, B4).

    *slab_slices* is the slab thickness in slices (agreement tolerance), *spacing_z_mm*
    converts ``CANDIDATE_MATCH_MM`` to slices. Detector candidates below
    ``DETECTOR_MIN_SCORE`` are ignored. Order: more independent sources first, then
    agreement, detector score, VLM support, cranial position and label.
    """
    tolerance = MATCH_TOLERANCE_SLABS * max(1, slab_slices)
    match_slices = max(1, round(CANDIDATE_MATCH_MM / max(spacing_z_mm, 1e-6)))
    items: list[LookHere] = []
    detector = sorted(
        (
            c
            for c in candidates
            if c.source == "detector" and (c.score or 0.0) >= DETECTOR_MIN_SCORE
        ),
        key=lambda c: (-(c.score or 0.0), c.slice_index),
    )
    for cand in detector:
        items.append(
            LookHere(
                label=cand.label,
                slice_lo=cand.slice_index,
                slice_hi=cand.slice_index,
                side=cand.side,
                sources=["detector"],
                detector_score=cand.score,
                size_mm=cand.size_mm,
            )
        )
    hu = sorted(
        (c for c in candidates if c.source == "hu"),
        key=lambda c: (-(c.size_mm or 0.0), c.slice_index),
    )[:MAX_HU_CANDIDATES]
    for cand in hu:
        match = next(
            (
                item
                for item in items
                if item.slice_lo is not None
                and item.slice_hi is not None
                and "hu" not in item.sources
                and _near(cand.slice_index, item.slice_lo, item.slice_hi, match_slices)
                and _sides_compatible(cand.side, item.side)
            ),
            None,
        )
        if match is not None:
            match.sources.append("hu")
            match.size_mm = match.size_mm if match.size_mm is not None else cand.size_mm
            continue
        items.append(
            LookHere(
                label=cand.label,
                slice_lo=cand.slice_index,
                slice_hi=cand.slice_index,
                side=cand.side,
                sources=["hu"],
                size_mm=cand.size_mm,
            )
        )
    for cluster in sorted(clusters, key=lambda c: (c.slice_lo, c.label)):
        match = (
            next(
                (
                    item
                    for item in items
                    if "vlm" not in item.sources
                    and item.slice_lo is not None
                    and _near(item.slice_lo, cluster.slice_lo, cluster.slice_hi, tolerance)
                    and _sides_compatible(item.side, cluster.side)
                ),
                None,
            )
            if cluster.label in NODULE_LABELS
            else None
        )
        if match is not None:
            match.sources.append("vlm")
            match.vlm_positive_slabs = cluster.positive_slabs
            match.vlm_spanned_slabs = cluster.spanned_slabs
            match.evidence.extend(cluster.evidence)
            if match.side == "unknown":
                match.side = cluster.side
            continue
        items.append(
            LookHere(
                label=cluster.label,
                slice_lo=cluster.slice_lo,
                slice_hi=cluster.slice_hi,
                side=cluster.side,
                sources=["vlm"],
                vlm_positive_slabs=cluster.positive_slabs,
                vlm_spanned_slabs=cluster.spanned_slabs,
                evidence=list(cluster.evidence),
            )
        )
    for cue in cues:
        items.append(
            LookHere(
                label=cue.label,
                slice_lo=None,
                slice_hi=None,
                side=cue.side,
                sources=["hu"],
                evidence=[cue.description] if cue.description else [],
            )
        )
    for item in items:
        item.agreement = len(set(item.sources)) >= 2
        item.weak = set(item.sources) == {"hu"}
    items.sort(
        key=lambda i: (
            i.weak,
            -len(set(i.sources)),
            not i.agreement,
            -(i.detector_score or 0.0),
            -i.vlm_positive_slabs,
            i.slice_lo if i.slice_lo is not None else 1 << 30,
            i.label,
        )
    )
    ranked = items[:MAX_LOOK_HERE]
    for rank, item in enumerate(ranked, start=1):
        item.rank = rank
    return ranked


def verdict_of(
    look_here: list[LookHere],
    *,
    answered_slabs: int,
    model_constant: bool,
    detector_completed: bool,
    study_adequate: bool = True,
) -> Verdict:
    """Plain outcome: something to review, nothing flagged where checked, or not assessable."""
    if not study_adequate:
        return "not_assessable"
    # HU density rules over-report on real scans (test runs 2026-10-20); alone they are
    # weak cues that support other sources but never make the verdict.
    if any(not item.weak for item in look_here):
        return "findings_to_review"
    vlm_usable = answered_slabs > 0 and not model_constant
    if vlm_usable or detector_completed:
        return "nothing_flagged_in_checked_area"
    return "not_assessable"


def _where(item: LookHere) -> str:
    if item.slice_lo is None or item.slice_hi is None:
        return "whole-scan measurement"
    span = (
        f"slice {item.slice_lo + 1}"
        if item.slice_lo == item.slice_hi
        else f"slices {item.slice_lo + 1}-{item.slice_hi + 1}"
    )
    return span + (f", {item.side} side" if item.side not in {"unknown", ""} else "")


def next_steps(look_here: list[LookHere], verdict: Verdict, names: dict[str, str]) -> list[str]:
    """Rule-based next steps: guideline text from existing code/knowledge base only.

    Nodules with a measured size use :func:`~thoraxbench.ontology.guidelines.fleischner`;
    other labels quote the knowledge-base follow-up note. Slice numbers are one-based for
    people. Nothing here is advice for this study; it is educational guideline context.
    """
    if verdict == "not_assessable":
        return ["No usable result. Ask a radiologist to read the scan; this tool cannot assess it."]
    if verdict == "nothing_flagged_in_checked_area":
        return [
            "Nothing was flagged, but this research tool can miss findings. "
            "A radiologist's report remains the reference."
        ]
    kb = load_clinical_kb()
    steps = ["Show the listed places (slice numbers) to a radiologist and ask for a review."]
    seen: set[str] = set()
    for item in look_here:
        name = names.get(item.label, item.label)
        if item.label == "pulmonary_nodule":
            advice = fleischner(item.size_mm)
            size = f", about {item.size_mm:.0f} mm" if item.size_mm is not None else ""
            text = (
                f"{name} ({_where(item)}{size}): {advice.guideline} guideline context — "
                f"{advice.category}: {advice.advice} {advice.caveat}"
            )
        else:
            entry = kb.get(item.label)
            if entry is None or item.label in seen:
                continue
            text = f"{name}: general guideline context — {' '.join(entry.follow_up.split())}"
        seen.add(item.label)
        if text not in steps:
            steps.append(text)
    return steps[:MAX_NEXT_STEPS]
