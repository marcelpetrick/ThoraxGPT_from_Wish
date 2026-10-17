# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Typed per-case inputs shared by all scoring tasks."""

from __future__ import annotations

from dataclasses import dataclass, field

from thoraxbench.schemas import FindingsReport, LesionAnnotation


@dataclass(frozen=True)
class PredictedLesion:
    """A predicted lesion point (z, y, x in mm) with optional diameter and score."""

    center_zyx: tuple[float, float, float]
    diameter_mm: float | None = None
    score: float = 1.0


@dataclass
class CaseRecord:
    """One scored study.

    Attributes:
        case_id: Study identifier.
        patient_id: Patient identifier (bootstrap resampling unit).
        y_true: Reference per label; ``None`` = unknown (excluded from that label).
        y_score: Model probability per label; ``None`` = not stated (excluded).
        report: Parsed model output (for safety/report metrics), if any.
        reference_lesions: Annotated lesions (Task C).
        predicted_lesions: Predicted lesions (Task C) with an optional score.
        ignored_lesions: Annotated findings that are neither targets nor false positives
            (LUNA16 "irrelevant findings", e.g. nodules marked by fewer readers).
    """

    case_id: str
    patient_id: str
    y_true: dict[str, bool | None] = field(default_factory=dict)
    y_score: dict[str, float | None] = field(default_factory=dict)
    report: FindingsReport | None = None
    reference_lesions: list[LesionAnnotation] = field(default_factory=list)
    predicted_lesions: list[PredictedLesion] = field(default_factory=list)
    ignored_lesions: list[LesionAnnotation] = field(default_factory=list)
