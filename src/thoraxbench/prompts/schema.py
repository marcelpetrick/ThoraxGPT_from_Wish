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


def findings_json_schema(
    labels: list[str] | None = None, *, n_images: int | None = None
) -> dict[str, Any]:
    """Return the JSON schema of the findings report.

    Args:
        labels: when given, ``findings[].label`` is restricted to these canonical ids
            (label-constrained prompts P2/P3/P4).
        n_images: optional attached-image count; evidence references are one-based and
            cannot exceed this count. No image reference is valid when the count is zero.
    """
    label_schema: dict[str, Any] = {"type": "string"}
    if labels:
        label_schema = {"type": "string", "enum": list(labels)}
    evidence_item: dict[str, Any] = {"type": "integer", "minimum": 1}
    if n_images is not None:
        if n_images < 0:
            raise ValueError("Image count cannot be negative")
        evidence_item["maximum"] = n_images
    finding = {
        "type": "object",
        "properties": {
            "label": label_schema,
            "present": {"type": ["boolean", "null"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "laterality": {"type": "string", "enum": [m.value for m in Laterality]},
            "region": {"type": ["string", "null"]},
            "size_bin": {"type": ["string", "null"], "enum": [*SIZE_BINS, None]},
            "evidence_images": {"type": "array", "items": evidence_item},
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
            "negative_findings": {"type": "array", "items": label_schema},
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


#: Free-text bounds of the strict schema (llama.cpp grammars enforce ``maxLength``/``maxItems``).
STRICT_LIMITS: dict[str, int] = {
    "description": 160,
    "region": 40,
    "text_item": 120,
    "uncertainty": 240,
    "limitations": 2,
    "incidental": 3,
    "impression": 2,
    "urgent": 2,
    "evidence": 4,
}


#: Allowed strict-schema confidences (0.05 steps). Ollama 0.40.4 ignores ``maximum`` on
#: numbers, so a literal ``enum`` bounds the value instead.
CONFIDENCE_LEVELS: tuple[float, ...] = tuple(round(k * 0.05, 2) for k in range(21))


def _bounded_strings(max_items: int, max_length: int) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "string", "maxLength": max_length},
        "maxItems": max_items,
    }


def strict_findings_json_schema(labels: list[str], *, n_images: int) -> dict[str, Any]:
    """Return the strict (version 2) findings schema for label-constrained prompts.

    Differences from :func:`findings_json_schema`:

    * ``findings`` comes first and has exactly one entry per requested label, in order
      (``prefixItems`` with a ``const`` label, ``minItems == maxItems``; an additional
      ``items`` schema made Ollama 0.40.4 ignore ``prefixItems``, so none is given);
    * every object sets ``additionalProperties: false``;
    * free text has ``maxLength`` and lists have ``maxItems`` to bound output growth;
      a fixed generation budget can still be exhausted;
    * evidence references are one-based integers ``1..n_images`` (at most four).

    Ollama 0.40.4 enforced ``prefixItems``/``const``, ``minItems``/``maxItems``,
    ``maxLength`` and integer ``minimum``/``maximum`` in a synthetic probe, but not
    ``maximum`` on numbers, so confidence is a literal enum of 0.05 steps. The parser
    still clamps confidence and the analysis still validates image evidence.

    Raises:
        ValueError: if *labels* is empty or *n_images* is negative.
    """
    if not labels:
        raise ValueError("strict schema needs at least one requested label")
    if n_images < 0:
        raise ValueError("Image count cannot be negative")
    lim = STRICT_LIMITS

    def finding(label: str) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "label": {"const": label},
                "present": {"type": ["boolean", "null"]},
                "confidence": {"type": "number", "enum": list(CONFIDENCE_LEVELS)},
                "evidence_images": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1, "maximum": max(n_images, 1)},
                    "maxItems": min(lim["evidence"], n_images),
                },
                "laterality": {"type": "string", "enum": [m.value for m in Laterality]},
                "size_bin": {"type": ["string", "null"], "enum": [*SIZE_BINS, None]},
                "region": {"type": ["string", "null"], "maxLength": lim["region"]},
                "description": {"type": "string", "maxLength": lim["description"]},
            },
            "required": ["label", "present", "confidence", "evidence_images"],
            "additionalProperties": False,
        }

    return {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "prefixItems": [finding(label) for label in labels],
                "minItems": len(labels),
                "maxItems": len(labels),
            },
            "study_quality": {
                "type": "object",
                "properties": {
                    "adequate": {"type": "boolean"},
                    "limitations": _bounded_strings(lim["limitations"], lim["text_item"]),
                },
                "required": ["adequate", "limitations"],
                "additionalProperties": False,
            },
            "negative_findings": {
                "type": "array",
                "items": {"type": "string", "enum": list(labels)},
                "maxItems": len(labels),
            },
            "incidental_findings": _bounded_strings(lim["incidental"], lim["text_item"]),
            "impression": _bounded_strings(lim["impression"], lim["text_item"]),
            "urgent_flags": _bounded_strings(lim["urgent"], lim["text_item"]),
            "uncertainty": {"type": "string", "maxLength": lim["uncertainty"]},
            "abstain": {"type": "boolean"},
        },
        "required": [
            "findings",
            "study_quality",
            "negative_findings",
            "incidental_findings",
            "impression",
            "urgent_flags",
            "uncertainty",
            "abstain",
        ],
        "additionalProperties": False,
    }
