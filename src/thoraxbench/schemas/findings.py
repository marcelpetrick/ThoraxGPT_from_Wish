# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""The common structured output every model is converted to (Vision §11)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Laterality(StrEnum):
    """Side of a finding."""

    LEFT = "left"
    RIGHT = "right"
    BILATERAL = "bilateral"
    MIDLINE = "midline"
    UNKNOWN = "unknown"


class StudyQuality(BaseModel):
    """Whether the study was adequate for reading, and why not."""

    adequate: bool = True
    limitations: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    """One labelled finding. ``present=None`` means the model is uncertain."""

    model_config = ConfigDict(extra="ignore")

    label: str
    present: bool | None = True
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    laterality: Laterality = Laterality.UNKNOWN
    region: str | None = None
    size_mm: float | None = Field(default=None, ge=0.0)
    evidence_images: list[int] = Field(default_factory=list)
    description: str = ""
    source: str = "model"

    def presence_probability(self) -> float | None:
        """Implied P(present), without inventing confidence for an unknown answer."""
        if self.present is None or self.confidence is None:
            return None
        return self.confidence if self.present else 1.0 - self.confidence

    @field_validator("laterality", mode="before")
    @classmethod
    def _coerce_laterality(cls, value: object) -> object:
        if value is None:
            return Laterality.UNKNOWN
        text = str(value).strip().lower()
        return text if text in {m.value for m in Laterality} else Laterality.UNKNOWN


class LesionCandidate(BaseModel):
    """One localised lesion candidate in canonical volume millimetres (Task C input).

    ``center_zyx_mm`` uses the reference-lesion frame: ``z = slice_index * dz`` (slice 0
    cranial), ``y = row * dy``, ``x = col * dx``. ``score`` is the model's own detection
    score, not a calibrated probability.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    label: str = "pulmonary_nodule"
    center_zyx_mm: tuple[float, float, float]
    diameter_mm: float | None = Field(default=None, ge=0.0)
    score: float = Field(ge=0.0, le=1.0)
    source: str = "detector"


class FindingsReport(BaseModel):
    """Study-level structured result (Vision §11). Abstention is a first-class outcome.

    ``lesions`` is ``None`` when the model does not localise in millimetres (no Task C);
    an empty list means it localises and proposed no candidate.
    """

    model_config = ConfigDict(extra="ignore")

    study_quality: StudyQuality = Field(default_factory=StudyQuality)
    findings: list[Finding] = Field(default_factory=list)
    negative_findings: list[str] = Field(default_factory=list)
    incidental_findings: list[str] = Field(default_factory=list)
    impression: list[str] = Field(default_factory=list)
    urgent_flags: list[str] = Field(default_factory=list)
    uncertainty: str = ""
    abstain: bool = False
    parse_warnings: list[str] = Field(default_factory=list)
    lesions: list[LesionCandidate] | None = None

    def label_probability(self, label: str) -> float | None:
        """Return P(label present) implied by the report, or ``None`` if not stated.

        Unknown presence, missing confidence and abstentions remain unavailable.
        Explicit negative-list entries imply zero only when no finding overrides them.
        """
        if self.abstain:
            return None
        for f in self.findings:
            if f.label != label:
                continue
            return f.presence_probability()
        if label in self.negative_findings:
            return 0.0
        return None

    def positive_labels(self) -> set[str]:
        """Labels with an available implied presence probability at least 0.5."""
        return {
            f.label
            for f in self.findings
            if (probability := self.label_probability(f.label)) is not None and probability >= 0.5
        }
