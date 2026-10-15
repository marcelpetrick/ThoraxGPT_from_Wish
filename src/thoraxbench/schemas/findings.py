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

    @field_validator("laterality", mode="before")
    @classmethod
    def _coerce_laterality(cls, value: object) -> object:
        if value is None:
            return Laterality.UNKNOWN
        text = str(value).strip().lower()
        return text if text in {m.value for m in Laterality} else Laterality.UNKNOWN


class FindingsReport(BaseModel):
    """Study-level structured result (Vision §11). Abstention is a first-class outcome."""

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

    def label_probability(self, label: str) -> float | None:
        """Return P(label present) implied by the report, or ``None`` if not stated.

        Positive findings map to their confidence (default 1.0), explicit negatives to
        ``1 - confidence`` (default 0.0), uncertain findings to 0.5.
        """
        for f in self.findings:
            if f.label != label:
                continue
            if f.present is None:
                return 0.5
            conf = 1.0 if f.confidence is None else f.confidence
            return conf if f.present else 1.0 - conf
        if label in self.negative_findings:
            return 0.0
        return None

    def positive_labels(self) -> set[str]:
        """Labels reported as present."""
        return {f.label for f in self.findings if f.present is True}
