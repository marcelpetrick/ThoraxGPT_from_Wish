# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Compact JSON schema of :class:`~thoraxbench.schemas.FindingsReport` for model prompts.

The same schema is passed to Ollama's ``format`` field (structured outputs), so a model is
constrained to emit the common output schema of Vision §11.

Models are asked for guideline-aligned **size bins** instead of precise millimetres
(``docs/reading_practice.md`` §4.4). Guideline categories (Fleischner, Lung-RADS) are
assigned later by code, never by the model.
"""

from __future__ import annotations

from typing import Any

from thoraxbench.schemas import Laterality

#: Allowed size/extent bins and the representative size in mm used for scoring
#: (``None`` = qualitative bin without a diameter).
SIZE_BINS: dict[str, float | None] = {
    "<6mm": 4.0,
    "6-8mm": 7.0,
    ">8mm": 12.0,
    ">30mm": 40.0,
    "small": None,
    "moderate": None,
    "large": None,
    "normal": None,
    "dilated": None,
    "aneurysmal": None,
}

_STR_LIST: dict[str, Any] = {"type": "array", "items": {"type": "string"}}


def findings_json_schema(labels: list[str] | None = None) -> dict[str, Any]:
    """Return the JSON schema of the findings report.

    Args:
        labels: when given, ``findings[].label`` is restricted to these canonical ids
            (label-constrained prompts P2/P3/P4).
    """
    label_schema: dict[str, Any] = {"type": "string"}
    if labels:
        label_schema = {"type": "string", "enum": list(labels)}
    finding = {
        "type": "object",
        "properties": {
            "label": label_schema,
            "present": {"type": ["boolean", "null"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "laterality": {"type": "string", "enum": [m.value for m in Laterality]},
            "region": {"type": ["string", "null"]},
            "size_bin": {"type": ["string", "null"], "enum": [*SIZE_BINS, None]},
            "evidence_images": {"type": "array", "items": {"type": "integer"}},
            "description": {"type": "string"},
        },
        "required": ["label", "present", "confidence"],
    }
    return {
        "type": "object",
        "properties": {
            "study_quality": {
                "type": "object",
                "properties": {"adequate": {"type": "boolean"}, "limitations": _STR_LIST},
                "required": ["adequate", "limitations"],
            },
            "findings": {"type": "array", "items": finding},
            "negative_findings": _STR_LIST,
            "incidental_findings": _STR_LIST,
            "impression": _STR_LIST,
            "urgent_flags": _STR_LIST,
            "uncertainty": {"type": "string"},
            "abstain": {"type": "boolean"},
        },
        "required": [
            "study_quality",
            "findings",
            "negative_findings",
            "incidental_findings",
            "impression",
            "urgent_flags",
            "uncertainty",
            "abstain",
        ],
    }
