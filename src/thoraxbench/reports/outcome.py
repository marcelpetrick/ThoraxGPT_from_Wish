# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Plain-language outcome of one analysis: verdict, coverage and where to look.

Deterministic templates only (EN/DE). The verdict uses at most three sentences and is built
from the structured result, so every number and label it names exists in that result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from thoraxbench.analysis import AnalysisResult

Language = Literal["en", "de"]
Verdict = Literal["findings_to_review", "nothing_flagged", "not_assessable"]

# Detector candidates at or above this score are listed; the rest are counted as hidden.
SHOW_SCORE = 0.5
# Share of requested labels claimed positive without image evidence that marks a yes-bias.
YES_BIAS_SHARE = 0.75
NO_EVIDENCE = "positive has no valid attached-image evidence"

SHORT_DISCLAIMER = {
    "en": "Research tool, not a diagnosis: have every result reviewed by a radiologist.",
    "de": "Forschungswerkzeug, keine Diagnose: Jedes Ergebnis von Radiologen prüfen lassen.",
}

LABELS_DE = {
    "pulmonary_nodule": "Lungenrundherd",
    "pulmonary_mass": "Raumforderung der Lunge",
    "consolidation": "Konsolidierung",
    "ground_glass_opacity": "Milchglastrübung",
    "atelectasis": "Atelektase",
    "emphysema": "Emphysem",
    "fibrosis_interstitial": "Fibrose / interstitielle Veränderung",
    "bronchiectasis": "Bronchiektasen",
    "pleural_effusion": "Pleuraerguss",
    "pneumothorax": "Pneumothorax",
    "lymphadenopathy": "Lymphknotenvergrößerung",
    "cardiomegaly": "Herzvergrößerung",
    "pericardial_effusion": "Perikarderguss",
    "coronary_calcification": "Koronarverkalkung",
    "arterial_wall_calcification": "Gefäßwandverkalkung",
    "hiatal_hernia": "Hiatushernie",
}

SIDES = {
    "en": {"right": "right", "left": "left", "bilateral": "both", "unknown": "unknown"},
    "de": {"right": "rechts", "left": "links", "bilateral": "beidseits", "unknown": "unbekannt"},
}


def label_name(label: str, lang: Language) -> str:
    """Readable finding name; German names for the fixed ontology labels."""
    if lang == "de" and label in LABELS_DE:
        return LABELS_DE[label]
    return label.replace("_", " ").capitalize()


@dataclass(frozen=True)
class LookHere:
    """One place worth showing to a radiologist."""

    label: str
    side: str
    size_mm: float | None
    slice_number: int | None  # one-based, as in the viewer
    score: float | None
    source: str


@dataclass(frozen=True)
class Outcome:
    """Structured plain-language outcome; ``sentences`` holds at most three sentences."""

    verdict: Verdict
    sentences: list[str]
    coverage: str
    look_here: list[LookHere] = field(default_factory=list)
    hidden_candidates: int = 0
    yes_bias: bool = False


def _side(x_mm: float, width_mm: float) -> str:
    # Columns run from patient right (x = 0) to patient left, as in the detector adapter.
    return "right" if x_mm < width_mm / 2 else "left"


def yes_bias(result: AnalysisResult) -> bool:
    """Report whether most requested labels were claimed positive without image evidence."""
    requested = len(result.request.labels) or len(result.report.findings)
    unsupported = sum(NO_EVIDENCE in w for w in result.report.parse_warnings)
    return requested > 0 and unsupported >= YES_BIAS_SHARE * requested


def _coverage(result: AnalysisResult, lang: Language) -> str:
    total = int(result.qc.get("n_slices") or 0)
    if result.report.lesions is not None or result.model_id == "heuristic-hu":
        return "whole volume" if lang == "en" else "gesamtes Volumen"
    shown = len(result.slice_indices)
    share = f"{100 * shown / total:.0f} %" if total else "?"
    if lang == "de":
        return f"{shown} von {total} Schichten ({share})"
    return f"{shown} of {total} slices ({share})"


def _look_here(result: AnalysisResult, width_mm: float | None) -> tuple[list[LookHere], int]:
    lesions = result.report.lesions or []
    dz = float((result.qc.get("spacing_mm") or (1.0,))[0]) or 1.0
    # Without the volume width only the top candidate's side is known (detector finding).
    top_side = next(
        (f.laterality.value for f in result.report.findings if f.source == "detector"), "unknown"
    )
    ranked = sorted(lesions, key=lambda item: -item.score)
    shown = [
        LookHere(
            label=lesion.label,
            side=_side(lesion.center_zyx_mm[2], width_mm)
            if width_mm
            else (top_side if rank == 0 else "unknown"),
            size_mm=lesion.diameter_mm,
            slice_number=round(lesion.center_zyx_mm[0] / dz) + 1,
            score=lesion.score,
            source=lesion.source,
        )
        for rank, lesion in enumerate(ranked)
        if lesion.score >= SHOW_SCORE
    ]
    if not lesions:
        shown = [
            LookHere(
                label=finding.label,
                side=finding.laterality.value,
                size_mm=finding.size_mm,
                slice_number=None,
                score=finding.presence_probability(),
                source=finding.source,
            )
            for finding in result.report.findings
            if finding.present is True
        ]
    return shown, len(lesions) - len([item for item in lesions if item.score >= SHOW_SCORE])


def _place(item: LookHere, total: int, lang: Language) -> str:
    side = SIDES[lang].get(item.side, item.side)
    size = f"{item.size_mm:.0f} mm" if item.size_mm else ""
    name = label_name(item.label, lang)
    if lang == "de":
        details = [part for part in (size, side if item.side != "unknown" else "") if part]
        if item.slice_number:
            details.append(f"Schicht {item.slice_number} von {total}")
        return f"{name} ({', '.join(details)})" if details else name
    lung = f" in the {side} lung" if item.side in {"right", "left"} else ""
    where = f" near slice {item.slice_number} of {total}" if item.slice_number else ""
    return f"a {size + ' ' if size else ''}{name.lower()} candidate{lung}{where}"


def build_outcome(
    result: AnalysisResult, lang: Language = "en", *, width_mm: float | None = None
) -> Outcome:
    """Summarize *result* for a non-expert reader in at most three sentences.

    *width_mm* is the in-plane volume width (left-right); it places every candidate's side.
    """
    total = int(result.qc.get("n_slices") or 0)
    coverage = _coverage(result, lang)
    biased = yes_bias(result)
    detector = result.report.lesions is not None
    if result.report.abstain or result.raw_error:
        if biased:
            labels = len(result.request.labels) or len(result.report.findings)
            first = (
                f"Kein verwertbares Ergebnis: Das Modell hat alle {labels} Befunde mit Ja "
                "beantwortet, ohne auf ein Bild zu zeigen."
                if lang == "de"
                else f"No usable result: the model answered yes to all {labels} findings "
                "without pointing to any image."
            )
        else:
            first = (
                "Kein verwertbares Ergebnis: Das Modell hat keine auswertbare Antwort geliefert."
                if lang == "de"
                else "No usable result: the model did not return an answer that could be checked."
            )
        second = (
            f"Geprüft wurden {coverage}; diese Auswertung sagt nichts über die Aufnahme aus."
            if lang == "de"
            else f"It was shown {coverage}; this run says nothing about the scan."
        )
        third = (
            "Für Lungenrundherde den Detektor (1️⃣ monai-lung-nodule) auf dieselbe Studie anwenden."
            if lang == "de"
            else "Run the lung-nodule detector (1️⃣ monai-lung-nodule) on the same study."
        )
        return Outcome("not_assessable", [first, second, third], coverage, yes_bias=biased)
    places, hidden = _look_here(result, width_mm)
    if not places:
        first = (
            "Im geprüften Bereich wurde nichts markiert."
            if lang == "de"
            else "Nothing was flagged in the checked area."
        )
        second = (
            f"Geprüft: {coverage}" + ("; nur Lungenrundherde wurden gesucht." if detector else ".")
            if lang == "de"
            else f"Checked: {coverage}"
            + ("; only lung nodules were searched." if detector else ".")
        )
        third = (
            "Das schließt Befunde nicht aus; maßgeblich bleibt der radiologische Befundbericht."
            if lang == "de"
            else "This does not rule out findings; the radiologist's report remains the reference."
        )
        return Outcome(
            "nothing_flagged", [first, second, third], coverage, hidden_candidates=hidden
        )
    listed = "; ".join(_place(item, total, lang) for item in places[:3])
    more = len(places) - 3
    if lang == "de":
        first = f"Zur Prüfung markiert: {listed}" + (f" und {more} weitere." if more > 0 else ".")
        second = (
            f"Geprüft: {coverage}; nur Lungenrundherde wurden gesucht"
            + (f", {hidden} Kandidaten mit niedrigem Wert wurden nicht gezählt." if hidden else ".")
            if detector
            else f"Geprüft: {coverage}; andere Bereiche wurden nicht angesehen."
        )
        third = (
            "Diese Stelle(n) Radiologen zeigen und mit dem offiziellen Befundbericht vergleichen."
        )
    else:
        first = f"Flagged for review: {listed}" + (f", and {more} more." if more > 0 else ".")
        second = (
            f"Checked: {coverage}; only lung nodules were searched"
            + (f", and {hidden} low-score candidates were not counted." if hidden else ".")
            if detector
            else f"Checked: {coverage}; other areas were not looked at."
        )
        third = "Show these locations to a radiologist and compare with the official report."
    return Outcome(
        "findings_to_review",
        [first, second, third],
        coverage,
        look_here=places,
        hidden_candidates=hidden,
        yes_bias=biased,
    )
