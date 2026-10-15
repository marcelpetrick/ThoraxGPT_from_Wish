# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Rule-based guideline categories, assigned in code (never by the model).

Implements the Fleischner Society 2017 recommendations for *incidental* pulmonary nodules
(MacMahon et al., Radiology 2017, https://doi.org/10.1148/radiol.2017161659) and a size-only
Lung-RADS v2022 baseline category for screening context. Inputs come from structured
findings; results are research annotations, not clinical recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

SMALL_MM = 6.0
LARGE_MM = 8.0
MASS_MM = 30.0


class NoduleType(StrEnum):
    """Attenuation type of a nodule."""

    SOLID = "solid"
    GROUND_GLASS = "ground_glass"
    PART_SOLID = "part_solid"


@dataclass(frozen=True)
class GuidelineAdvice:
    """A guideline-derived follow-up suggestion."""

    guideline: str
    category: str
    advice: str
    applicable: bool = True
    caveat: str = ""


FLEISCHNER = "Fleischner Society 2017"
_SCOPE = (
    "Applies only to incidental nodules in adults >= 35 years without known cancer or "
    "immunosuppression and outside lung-cancer screening."
)


def size_bin(size_mm: float) -> str:
    """Guideline size bin of an average nodule diameter."""
    if size_mm >= MASS_MM:
        return ">=30 mm (mass)"
    if size_mm > LARGE_MM:
        return ">8 mm"
    if size_mm >= SMALL_MM:
        return "6-8 mm"
    return "<6 mm"


def fleischner(
    size_mm: float | None,
    *,
    nodule_type: NoduleType = NoduleType.SOLID,
    multiple: bool = False,
    high_risk: bool = False,
) -> GuidelineAdvice:
    """Fleischner 2017 follow-up for the dominant nodule.

    Unknown size returns a non-applicable advice asking for measurement.
    """
    if size_mm is None:
        return GuidelineAdvice(
            FLEISCHNER,
            "size unknown",
            "Nodule size is needed to apply the guideline; a radiologist should measure it.",
            False,
            _SCOPE,
        )
    if size_mm >= MASS_MM:
        return GuidelineAdvice(
            FLEISCHNER,
            "mass",
            "Lesions >= 30 mm are masses, not nodules; "
            "Fleischner does not apply. Prompt diagnostic work-up is usual.",
            False,
            _SCOPE,
        )
    small = size_mm < SMALL_MM
    if nodule_type is NoduleType.SOLID:
        advice = _solid_advice(size_mm, multiple=multiple, high_risk=high_risk)
        category = (
            f"solid, {'multiple' if multiple else 'single'}, {size_bin(size_mm)}, "
            f"{'high' if high_risk else 'low'} risk"
        )
        return GuidelineAdvice(FLEISCHNER, category, advice, True, _SCOPE)
    if multiple:
        advice = (
            "CT at 3-6 months; if stable, consider CT at 2 and 4 years."
            if small
            else "CT at 3-6 months; further management based on the most suspicious nodule."
        )
    elif small:
        advice = "No routine follow-up."
    elif nodule_type is NoduleType.GROUND_GLASS:
        advice = "CT at 6-12 months to confirm persistence, then every 2 years until 5 years."
    else:
        advice = (
            "CT at 3-6 months to confirm persistence; if unchanged and solid component < 6 mm, "
            "annual CT for 5 years."
        )
    category = (
        f"{nodule_type.value.replace('_', '-')}, {'multiple' if multiple else 'single'}, "
        f"{'<6 mm' if small else '>=6 mm'}"
    )
    return GuidelineAdvice(FLEISCHNER, category, advice, True, _SCOPE)


def _solid_advice(size_mm: float, *, multiple: bool, high_risk: bool) -> str:
    then = "CT" if high_risk else "consider CT"
    if size_mm < SMALL_MM:
        return "Optional CT at 12 months." if high_risk else "No routine follow-up."
    if multiple:
        return f"CT at 3-6 months, then {then} at 18-24 months."
    if size_mm <= LARGE_MM:
        return f"CT at 6-12 months, then {then} at 18-24 months."
    return "Consider CT at 3 months, PET/CT, or tissue sampling."


def lung_rads_baseline_solid(size_mm: float | None) -> GuidelineAdvice:
    """Size-only Lung-RADS v2022 baseline category for a solid nodule (screening context)."""
    name = "Lung-RADS v2022 (screening, size-only)"
    caveat = "Only for lung-cancer screening LDCT; ignores growth, morphology and priors."
    if size_mm is None:
        return GuidelineAdvice(name, "0", "Incomplete: size unknown.", False, caveat)
    if size_mm < SMALL_MM:
        return GuidelineAdvice(name, "2", "Benign appearance: annual LDCT.", True, caveat)
    if size_mm < LARGE_MM:
        return GuidelineAdvice(name, "3", "Probably benign: LDCT in 6 months.", True, caveat)
    if size_mm < 15.0:
        return GuidelineAdvice(
            name, "4A", "Suspicious: LDCT in 3 months; PET/CT if solid part >= 8 mm.", True, caveat
        )
    return GuidelineAdvice(
        name, "4B", "Very suspicious: diagnostic CT, PET/CT and/or tissue sampling.", True, caveat
    )
