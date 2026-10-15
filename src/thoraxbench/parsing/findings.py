# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Convert raw model output into a validated :class:`FindingsReport`.

Principles (Vision §11, §20):

* never invent findings — unparseable or empty output becomes an abstention;
* labels are normalised to the canonical ontology; unknown labels are kept as incidental
  findings (with a parse warning) instead of being silently mapped;
* raw self-reported confidence is recorded but clamped to [0, 1];
* precise sizes the model was not asked for are kept but flagged as unsupported;
* probabilities from classifier services become findings with ``source = "probability"``.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from thoraxbench.ontology import Ontology, load_ontology
from thoraxbench.parsing.json_extract import extract_json
from thoraxbench.prompts.schema import SIZE_BINS
from thoraxbench.schemas import FindingsReport, RawOutput, StudyQuality

_VERBAL_CONFIDENCE = {
    "very high": 0.95,
    "high": 0.85,
    "medium": 0.6,
    "moderate": 0.6,
    "low": 0.35,
    "very low": 0.15,
}
_PRESENT_WORDS = {"true", "yes", "present", "positive", "seen", "1"}
_ABSENT_WORDS = {"false", "no", "absent", "negative", "not seen", "none", "0"}
_UNCERTAIN_WORDS = {"null", "uncertain", "unknown", "indeterminate", "possible", "maybe"}
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _abstain(reason: str, warnings: list[str]) -> FindingsReport:
    return FindingsReport(
        study_quality=StudyQuality(adequate=True, limitations=[]),
        abstain=True,
        uncertainty=reason,
        parse_warnings=[*warnings, reason],
    )


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None and str(v).strip()]
    return [str(value)]


def _confidence(value: object, warnings: list[str], label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        conf = float(value)
    else:
        text = str(value).strip().lower().rstrip("%")
        if text in _VERBAL_CONFIDENCE:
            return _VERBAL_CONFIDENCE[text]
        match = _NUMBER.search(text)
        if not match:
            warnings.append(f"{label}: unreadable confidence {value!r}")
            return None
        conf = float(match.group())
    if 1.0 < conf <= 100.0:
        conf /= 100.0
    if not 0.0 <= conf <= 1.0:
        warnings.append(f"{label}: confidence {value!r} clamped to [0, 1]")
        conf = min(1.0, max(0.0, conf))
    return conf


def _present(value: object) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _PRESENT_WORDS:
        return True
    if text in _ABSENT_WORDS:
        return False
    return None


def _size(item: dict[str, Any], warnings: list[str], label: str) -> tuple[float | None, str]:
    """Return (size_mm, extra description) from ``size_bin`` or ``size_mm``."""
    size_bin = item.get("size_bin")
    if isinstance(size_bin, str) and size_bin.strip():
        key = size_bin.strip().lower().replace(" ", "")
        if key in SIZE_BINS:
            return SIZE_BINS[key], f"size bin {key}"
        warnings.append(f"{label}: unknown size bin {size_bin!r}")
    raw = item.get("size_mm")
    if raw is None:
        return None, ""
    match = _NUMBER.search(str(raw))
    if not match:
        return None, ""
    size = abs(float(match.group()))
    if not item.get("evidence_images") and "mm" not in str(item.get("description", "")):
        warnings.append(f"{label}: unsupported measurement {size} mm (no evidence given)")
    return size, ""


def _evidence(value: object) -> list[int]:
    out: list[int] = []
    for v in value if isinstance(value, list) else [value]:
        try:
            out.append(int(str(v)))
        except ValueError:
            continue
    return out


def _normalise_items(findings: object) -> list[dict[str, Any]]:
    """Accept list[dict], list[str] or {label: verdict} and return list[dict]."""
    if isinstance(findings, dict):
        items: list[dict[str, Any]] = []
        for key, val in findings.items():
            if isinstance(val, dict):
                items.append({"label": key, **val})
            elif isinstance(val, bool) or val is None:
                items.append({"label": key, "present": val})
            elif isinstance(val, int | float):
                items.append({"label": key, "present": True, "confidence": val})
            else:
                items.append({"label": key, "present": val})
        return items
    if isinstance(findings, list):
        return [
            item if isinstance(item, dict) else {"label": str(item), "present": True}
            for item in findings
        ]
    return []


def _from_probabilities(
    probabilities: dict[str, float], ontology: Ontology, warnings: list[str]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, p in sorted(probabilities.items()):
        label = ontology.normalise(name)
        if label is None:
            warnings.append(f"probability for unknown label {name!r} ignored")
            continue
        prob = min(1.0, max(0.0, float(p)))
        present = prob >= 0.5
        out.append(
            {
                "label": label,
                "present": present,
                "confidence": prob if present else 1.0 - prob,
                "description": f"model probability {prob:.3f}",
                "source": "probability",
            }
        )
    return out


def parse_findings(  # noqa: PLR0912 - one linear normalisation step per field
    raw: RawOutput | str, ontology: Ontology | None = None
) -> FindingsReport:
    """Parse *raw* model output into a :class:`FindingsReport` (never raises)."""
    onto = ontology or load_ontology()
    output = RawOutput(text=raw) if isinstance(raw, str) else raw
    warnings: list[str] = []
    if output.error:
        return _abstain(f"model error: {output.error}", warnings)

    data: dict[str, Any] = {}
    if output.text.strip():
        value, repairs = extract_json(output.text)
        warnings.extend(f"json: {r}" for r in repairs)
        if isinstance(value, list):
            value = {"findings": value}
        if isinstance(value, dict):
            data = value
        elif not output.probabilities:
            return _abstain("no usable JSON in model output", warnings)
    elif not output.probabilities:
        return _abstain("empty model output", warnings)

    items = _normalise_items(data.get("findings"))
    items.extend(_from_probabilities(output.probabilities, onto, warnings))
    incidental = _as_list(data.get("incidental_findings"))
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        raw_label = str(item.get("label", "")).strip()
        label = onto.normalise(raw_label) if raw_label else None
        if label is None:
            if raw_label:
                warnings.append(f"unknown label {raw_label!r} moved to incidental findings")
                desc = str(item.get("description", "")).strip()
                incidental.append(f"{raw_label}: {desc}" if desc else raw_label)
            continue
        if label in seen:
            warnings.append(f"duplicate label {label!r}; first entry kept")
            continue
        seen.add(label)
        size_mm, size_note = _size(item, warnings, label)
        description = str(item.get("description") or "").strip()
        if size_note:
            description = f"{description} ({size_note})" if description else size_note
        findings.append(
            {
                "label": label,
                "present": _present(item.get("present", True)),
                "confidence": _confidence(item.get("confidence"), warnings, label),
                "laterality": item.get("laterality"),
                "region": str(item["region"]) if item.get("region") else None,
                "size_mm": size_mm,
                "evidence_images": _evidence(item.get("evidence_images", [])),
                "description": description,
                "source": str(item.get("source", "model")),
            }
        )

    negatives: list[str] = []
    for name in _as_list(data.get("negative_findings")):
        label = onto.normalise(name)
        if label is None:
            warnings.append(f"unknown negative finding {name!r} ignored")
        elif label not in seen and label not in negatives:
            negatives.append(label)

    quality = data.get("study_quality")
    quality = quality if isinstance(quality, dict) else {}
    adequate = _present(quality.get("adequate", True))
    report = {
        "study_quality": {
            "adequate": adequate is not False,
            "limitations": _as_list(quality.get("limitations")),
        },
        "findings": findings,
        "negative_findings": negatives,
        "incidental_findings": incidental,
        "impression": _as_list(data.get("impression")),
        "urgent_flags": _as_list(data.get("urgent_flags")),
        "uncertainty": str(data.get("uncertainty") or ""),
        "abstain": _present(data.get("abstain", False)) is True,
        "parse_warnings": warnings,
    }
    try:
        return FindingsReport.model_validate(report)
    except ValidationError as exc:  # pragma: no cover - inputs are normalised above
        return _abstain(f"schema validation failed: {exc.error_count()} error(s)", warnings)
