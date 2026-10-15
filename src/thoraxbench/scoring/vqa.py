# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Task F: targeted questions (VQA) with exact-match and ontology-aware scoring."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from thoraxbench.ontology import load_ontology
from thoraxbench.scoring.classification import safe_div

_YES = {"yes", "y", "true", "present", "positive", "seen"}
_NO = {"no", "n", "false", "absent", "negative", "none", "not seen"}
_SIDES = {
    "left": "left",
    "l": "left",
    "right": "right",
    "r": "right",
    "bilateral": "bilateral",
    "both": "bilateral",
    "midline": "midline",
}


def _clean(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def normalise_answer(answer: str, kind: str) -> str | None:  # noqa: PLR0911
    """Normalise a free-text answer for question *kind* (yes_no, laterality, label, text)."""
    text = _clean(answer)
    if kind == "yes_no":
        first = text.split(" ")[0] if text else ""
        if text in _NO or first in _NO:
            return "no"
        if text in _YES or first in _YES:
            return "yes"
        return None
    if kind == "laterality":
        for word in text.split():
            if word in _SIDES:
                return _SIDES[word]
        return None
    if kind == "label":
        return load_ontology().normalise(answer)
    return " ".join(text.split()) or None


@dataclass(frozen=True)
class VqaItem:
    """One question with its reference and the model's answer."""

    question: str
    kind: str
    reference: str
    answer: str


def score_vqa(items: Sequence[VqaItem]) -> dict[str, float | int | None]:
    """Exact-match accuracy (raw string) and ontology-aware accuracy (normalised)."""
    n = len(items)
    exact = sum(_clean(i.answer) == _clean(i.reference) for i in items)
    aware = 0
    unparsable = 0
    for i in items:
        got = normalise_answer(i.answer, i.kind)
        if got is None:
            unparsable += 1
        elif got == normalise_answer(i.reference, i.kind):
            aware += 1
    return {
        "n": n,
        "exact_match": safe_div(exact, n),
        "ontology_aware": safe_div(aware, n),
        "unparsable": unparsable,
    }
