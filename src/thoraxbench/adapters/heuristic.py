# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Deterministic non-AI baseline that turns HU measurements into findings.

The heuristic model is a *control*: it shows how much of a label can be recovered from
simple, reproducible Hounsfield-unit rules (docs/reading_practice.md §3.7) without any
learned model. Every output carries ``source = "heuristic"``.

It consumes any object that satisfies :class:`HUCuesLike` (implemented by
``thoraxbench.preprocess.hu_cues``), or a study object that exposes such cues as ``.cues``.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, is_dataclass
from typing import Any, Protocol, runtime_checkable

from thoraxbench.adapters.base import ModelConfig
from thoraxbench.ontology import Ontology, load_ontology
from thoraxbench.parsing import parse_findings
from thoraxbench.preprocess import HUCues
from thoraxbench.schemas import (
    AnalysisRequest,
    Capabilities,
    FindingsReport,
    PreparedInput,
    RawOutput,
)

VIEW_ID = "hu_cues"
VIEW_VERSION = "1"

# Rule parameters (versioned with VIEW_VERSION).
EMPHYSEMA_LAA_MIDPOINT_PCT = 6.0  # %LAA-950 where P(emphysema) = 0.5
EFFUSION_MIDPOINT_ML = 20.0
PNEUMOTHORAX_MIDPOINT_ML = 10.0
CALCIUM_MIDPOINT_VOXELS = 10.0
METAL_MIDPOINT_VOXELS = 20.0
METAL_MIDPOINT_COMPONENTS = 0.5
CONSOLIDATION_MIDPOINT_PCT = 3.0
GGO_MIDPOINT_PCT = 15.0
NODULE_MIN_MM = 3.0
MASS_MIN_MM = 30.0


@runtime_checkable
class NoduleCandidateLike(Protocol):
    """A dense lung blob found by HU thresholding."""

    diameter_mm: float
    side: str
    z_index: int


@runtime_checkable
class HUCuesLike(Protocol):
    """The deterministic measurements the heuristic baseline needs.

    Optional cues (``pneumothorax_air_ml``, ``metal_voxels``) may be missing; they are read
    with ``getattr(..., default)``.
    """

    emphysema_laa950_pct: float
    effusion_ml_left: float
    effusion_ml_right: float
    nodule_candidates: list[Any]
    calcium_voxels: int


def _logistic(value: float, midpoint: float, steepness: float = 1.0) -> float:
    """Smooth monotone mapping of a measurement to a pseudo-probability in (0, 1)."""
    x = steepness * (value - midpoint) / max(midpoint, 1e-6)
    return 1.0 / (1.0 + math.exp(-4.0 * x))


def _cues_of(study: Any) -> HUCuesLike | HUCues:
    cues = getattr(study, "cues", study)
    if isinstance(cues, HUCues):
        return cues
    if not isinstance(cues, HUCuesLike):
        msg = "heuristic model needs HU cues (emphysema_laa950_pct, effusion_ml_*, …)"
        raise TypeError(msg)
    return cues


def _cues_dict(cues: HUCuesLike | HUCues) -> dict[str, Any]:
    if isinstance(cues, HUCues):
        return {
            "emphysema_laa950_pct": cues.emphysema_laa950_pct,
            "effusion_ml_left": cues.pleural_fluid_ml["left"],
            "effusion_ml_right": cues.pleural_fluid_ml["right"],
            # cardiac-region calcium volume in mm^3 (~ voxels at 1 mm^3)
            "calcium_voxels": round(cues.cardiac_calcium_ml * 1000.0),
            "pneumothorax_air_ml": cues.pleural_air_ml,
            "metal_components": cues.metal_components,
            "consolidation_pct": cues.consolidation_pct,
            "ggo_burden_pct": cues.ggo_burden_pct,
            "nodule_candidates": [
                {"diameter_mm": c.diameter_mm, "side": c.side, "z_index": c.z_index}
                for c in cues.nodule_candidates
            ],
        }
    if is_dataclass(cues) and not isinstance(cues, type):
        data: dict[str, Any] = asdict(cues)
        return data
    return {
        "emphysema_laa950_pct": cues.emphysema_laa950_pct,
        "effusion_ml_left": cues.effusion_ml_left,
        "effusion_ml_right": cues.effusion_ml_right,
        "calcium_voxels": cues.calcium_voxels,
        "pneumothorax_air_ml": getattr(cues, "pneumothorax_air_ml", 0.0),
        "metal_voxels": getattr(cues, "metal_voxels", 0),
        "nodule_candidates": [
            {"diameter_mm": c.diameter_mm, "side": c.side, "z_index": c.z_index}
            for c in cues.nodule_candidates
        ],
    }


def _finding(label: str, prob: float, description: str, **extra: Any) -> dict[str, Any]:
    present = prob >= 0.5
    return {
        "label": label,
        "present": present,
        "confidence": round(prob if present else 1.0 - prob, 4),
        "description": description,
        "source": "heuristic",
        **extra,
    }


def _side(sides: set[str]) -> str:
    if {"left", "right"} <= sides:
        return "bilateral"
    return next(iter(sides)) if sides else "unknown"


def heuristic_findings(cues: dict[str, Any]) -> dict[str, Any]:
    """Apply the deterministic rules to a cue dictionary and return a findings JSON object."""
    laa = float(cues.get("emphysema_laa950_pct", 0.0))
    left = float(cues.get("effusion_ml_left", 0.0))
    right = float(cues.get("effusion_ml_right", 0.0))
    ptx = float(cues.get("pneumothorax_air_ml", 0.0) or 0.0)
    calcium = float(cues.get("calcium_voxels", 0))
    metal = float(cues.get("metal_voxels", 0) or 0)
    metal_components = cues.get("metal_components")
    candidates = list(cues.get("nodule_candidates", []))
    nodules = [c for c in candidates if NODULE_MIN_MM <= c["diameter_mm"] < MASS_MIN_MM]
    masses = [c for c in candidates if c["diameter_mm"] >= MASS_MIN_MM]

    findings = [
        _finding(
            "emphysema", _logistic(laa, EMPHYSEMA_LAA_MIDPOINT_PCT), f"%LAA-950 = {laa:.1f} %"
        ),
        _finding(
            "pleural_effusion",
            _logistic(max(left, right), EFFUSION_MIDPOINT_ML),
            f"dependent fluid-density collection left {left:.0f} ml, right {right:.0f} ml",
            laterality=_side({s for s, v in (("left", left), ("right", right)) if v >= 1.0}),
        ),
        _finding(
            "pneumothorax",
            _logistic(ptx, PNEUMOTHORAX_MIDPOINT_ML),
            f"extra-pulmonary air {ptx:.0f} ml",
        ),
        _finding(
            "coronary_calcification",
            _logistic(calcium, CALCIUM_MIDPOINT_VOXELS),
            f"{calcium:.0f} voxels > 130 HU in the coronary region",
        ),
        _finding(
            "medical_device",
            _logistic(float(metal_components), METAL_MIDPOINT_COMPONENTS)
            if metal_components is not None
            else _logistic(metal, METAL_MIDPOINT_VOXELS),
            f"{metal_components} metal-density component(s)"
            if metal_components is not None
            else f"{metal:.0f} metal-density voxels",
        ),
    ]
    if "consolidation_pct" in cues:
        cons = float(cues["consolidation_pct"])
        ggo = float(cues.get("ggo_burden_pct", 0.0))
        findings.append(
            _finding(
                "consolidation",
                _logistic(cons, CONSOLIDATION_MIDPOINT_PCT),
                f"{cons:.1f} % of the lung envelope at soft-tissue density",
            )
        )
        findings.append(
            _finding(
                "ground_glass_opacity",
                _logistic(ggo, GGO_MIDPOINT_PCT),
                f"{ggo:.1f} % of the lung envelope in the ground-glass HU range",
            )
        )
    for label, group in (("pulmonary_nodule", nodules), ("pulmonary_mass", masses)):
        if group:
            biggest = max(group, key=lambda c: c["diameter_mm"])
            prob = min(0.95, 0.55 + 0.02 * biggest["diameter_mm"])
            findings.append(
                _finding(
                    label,
                    prob,
                    f"{len(group)} dense lung candidate(s), "
                    f"largest {biggest['diameter_mm']:.1f} mm",
                    size_mm=round(float(biggest["diameter_mm"]), 1),
                    laterality=_side({str(c["side"]) for c in group}),
                    evidence_images=sorted({int(c["z_index"]) for c in group}),
                )
            )
        else:
            findings.append(_finding(label, 0.15, "no dense lung candidate in range"))
    return {
        "study_quality": {"adequate": True, "limitations": []},
        "findings": findings,
        "uncertainty": "deterministic HU rules; not a learned model",
        "abstain": False,
    }


class HeuristicModel:
    """The HU-rule baseline wrapped in the :class:`ThoraxModel` interface."""

    def __init__(self, config: ModelConfig, ontology: Ontology | None = None) -> None:
        self.config = config
        self.id = config.id
        self.ontology = ontology or load_ontology()

    def capabilities(self) -> Capabilities:
        """Probabilistic classification of the cue-backed labels only."""
        return Capabilities(classification=True, probabilities=True, localization=True)

    def available(self) -> bool:
        """Return True: the rules are pure Python."""
        return True

    def prepare(self, study: Any, request: AnalysisRequest) -> PreparedInput:
        """Extract the cue dictionary (``request`` is unused: rules cover fixed labels)."""
        cues = _cues_of(study)
        return PreparedInput(
            view_id=VIEW_ID, view_version=VIEW_VERSION, meta={"cues": _cues_dict(cues)}
        )

    def infer(self, prepared: PreparedInput, request: AnalysisRequest) -> RawOutput:
        """Apply the rules; restrict to ``request.labels`` when given."""
        start = time.perf_counter()
        report = heuristic_findings(prepared.meta.get("cues", {}))
        if request.labels:
            report["findings"] = [f for f in report["findings"] if f["label"] in request.labels]
        return RawOutput(
            text=json.dumps(report),
            latency_s=time.perf_counter() - start,
            meta={"rules_version": VIEW_VERSION},
        )

    def parse(self, raw: RawOutput) -> FindingsReport:
        """Parse the rule output (always valid JSON)."""
        return parse_findings(raw, self.ontology)
