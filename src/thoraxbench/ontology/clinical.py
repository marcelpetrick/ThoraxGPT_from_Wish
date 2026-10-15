# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Clinical knowledge base: terminology, plain language, severity, follow-up, prevalence.

The data in ``clinical_kb.yaml`` was compiled from cited guidelines and literature (see the
``sources`` of every entry and ``docs/reading_practice.md``). It feeds the per-study English
Markdown report. It is research material, not medical advice.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from functools import cache
from importlib import resources

import yaml
from pydantic import BaseModel, ConfigDict


class Severity(IntEnum):
    """Ordered severity scale used in reports."""

    INCIDENTAL = 0
    LOW = 1
    MODERATE = 2
    HIGH = 3
    CRITICAL = 4

    @classmethod
    def parse(cls, text: str) -> Severity:
        """Parse a lower-case severity name."""
        return cls[text.strip().upper()]


class Urgency(StrEnum):
    """How quickly a typical case needs clinical attention."""

    ROUTINE = "routine"
    SOON = "soon"
    URGENT = "urgent"
    EMERGENCY = "emergency"


class ClinicalEntry(BaseModel):
    """Knowledge for one canonical label."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str
    medical_term: str
    synonyms: list[str]
    plain_language: str
    typical_severity: str
    severity_modifiers: list[str]
    urgency: Urgency
    treatment_typically_needed: str
    treatment_note: str
    follow_up: str
    prevalence: str
    ct_rate_label: str | None = None
    deterministic_hints: list[str]
    sources: list[str]

    @property
    def severity(self) -> Severity:
        """Typical severity as an ordered enum."""
        return Severity.parse(self.typical_severity)


class ClinicalKB(BaseModel):
    """All entries plus the disclaimer."""

    disclaimer: str
    version: str
    entries: dict[str, ClinicalEntry]

    def get(self, label_id: str) -> ClinicalEntry | None:
        """Entry for *label_id*, or ``None`` if the label has no knowledge entry."""
        return self.entries.get(label_id)


@cache
def load_clinical_kb() -> ClinicalKB:
    """Load the packaged knowledge base (cached)."""
    raw = resources.files("thoraxbench.ontology").joinpath("clinical_kb.yaml").read_text("utf-8")
    data = yaml.safe_load(raw)
    entries = {item["id"]: ClinicalEntry.model_validate(item) for item in data["findings"]}
    meta = data["meta"]
    return ClinicalKB(
        disclaimer=" ".join(str(meta["disclaimer"]).split()),
        version=str(meta["version"]),
        entries=entries,
    )
