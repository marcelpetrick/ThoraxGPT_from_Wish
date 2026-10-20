# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Optional local-LLM rephrasing of the deterministic verdict, with a strict fact check.

The model receives only the structured outcome (never images or identifiers). Its text is
accepted only when it has at most three sentences, every number it contains occurs in the
facts, it names no finding outside the facts and avoids causal or diagnostic wording.
Otherwise the deterministic template verdict is returned.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any

import httpx

from thoraxbench.reports.outcome import LABELS_DE, Language, Outcome, label_name

MAX_SENTENCES = 3
# Words that would turn a summary into a diagnosis or a cause; the facts never contain them.
BLOCKED_WORDS = (
    "cancer",
    "malignan",
    "benign",
    "tumor",
    "tumour",
    "metasta",
    "krebs",
    "bösartig",
    "gutartig",
    "diagnos",
    "caused by",
    "verursacht",
)
SYSTEM = (
    "You rewrite structured research facts about one chest CT analysis for a non-expert. "
    "Write at most three short sentences in {language}. Use only the given facts. Do not add "
    "findings, numbers, causes, diagnoses or advice beyond the facts' next step."
)


def facts(outcome: Outcome) -> dict[str, Any]:
    """Structured, identifier-free facts handed to the model."""
    return {
        "verdict": outcome.verdict,
        "coverage": outcome.coverage,
        "template_verdict": " ".join(outcome.sentences),
        "look_here": [asdict(item) for item in outcome.look_here],
        "hidden_low_score_candidates": outcome.hidden_candidates,
        "model_answered_yes_to_everything": outcome.yes_bias,
    }


def _numbers(text: str) -> set[float]:
    return {float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", text)}


def check_summary(text: str, outcome: Outcome) -> str | None:
    """Return why *text* is rejected, or None when it only restates the facts."""
    sentences = [part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part]
    if not sentences or len(sentences) > MAX_SENTENCES:
        return "sentence count"
    allowed = _numbers(json.dumps(facts(outcome)))
    # Rounded presentations of allowed values (e.g. 5.33 → 5) are accepted too.
    allowed |= {float(round(value)) for value in allowed}
    if not _numbers(text) <= allowed:
        return "unsupported number"
    lowered = text.lower()
    if any(word in lowered for word in BLOCKED_WORDS):
        return "diagnostic or causal wording"
    present = {item.label for item in outcome.look_here}
    for label, german in LABELS_DE.items():
        if label in present:
            continue
        names = (label_name(label, "en").lower(), german.lower())
        if any(name in lowered for name in names):
            return "finding outside the facts"
    return None


def llm_summary(
    outcome: Outcome, lang: Language, *, base_url: str, tag: str, timeout_s: float = 120.0
) -> tuple[str, str, str | None]:
    """Return ``(text, source, rejection)``; source is ``llm`` or ``template``."""
    template = " ".join(outcome.sentences)
    payload = {
        "model": tag,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM.format(language="German" if lang == "de" else "English"),
            },
            {"role": "user", "content": json.dumps(facts(outcome), ensure_ascii=False)},
        ],
        "stream": False,
        "options": {"temperature": 0, "seed": 0, "num_predict": 160},
    }
    try:
        response = httpx.post(f"{base_url}/api/chat", json=payload, timeout=timeout_s)
        response.raise_for_status()
        text = str(response.json().get("message", {}).get("content", "")).strip()
    except (httpx.HTTPError, ValueError) as exc:
        return template, "template", f"model unavailable ({type(exc).__name__})"
    rejection = check_summary(text, outcome)
    if rejection is not None:
        return template, "template", rejection
    return text, "llm", None
