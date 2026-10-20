# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""An LLM may only rephrase the verdict facts; anything beyond them falls back to the template."""

from __future__ import annotations

import httpx
import pytest
import respx

from thoraxbench.reports.llm_summary import check_summary, facts, llm_summary
from thoraxbench.reports.outcome import LookHere, Outcome

OUTCOME = Outcome(
    "findings_to_review",
    [
        "Flagged for review: a 5 mm pulmonary nodule candidate in the right lung near slice 188 "
        "of 317.",
        "Checked: whole volume; only lung nodules were searched, and 7 low-score candidates "
        "were not counted.",
        "Show these locations to a radiologist and compare with the official report.",
    ],
    "whole volume",
    look_here=[LookHere("pulmonary_nodule", "right", 5.33, 188, 0.913, "detector")],
    hidden_candidates=7,
)
URL = "http://ollama.test"


def test_facts_hold_no_identifiers() -> None:
    assert set(facts(OUTCOME)) == {
        "verdict",
        "coverage",
        "template_verdict",
        "look_here",
        "hidden_low_score_candidates",
        "model_answered_yes_to_everything",
    }


@pytest.mark.parametrize(
    ("text", "rejection"),
    [
        ("One 5 mm spot in the right lung near slice 188 needs a radiologist's look.", None),
        ("Ein Rundherd von 5 mm rechts bei Schicht 188 sollte geprüft werden.", None),
        ("A 9 mm spot was found.", "unsupported number"),
        ("A spot was found. It is small. It is right. Show it.", "sentence count"),
        ("The 5 mm spot is probably benign.", "diagnostic or causal wording"),
        ("A pleural effusion and a nodule were found.", "finding outside the facts"),
    ],
)
def test_check_summary_accepts_only_restated_facts(text: str, rejection: str | None) -> None:
    assert check_summary(text, OUTCOME) == rejection


@respx.mock
def test_llm_text_is_used_only_when_it_passes_the_check() -> None:
    route = respx.post(f"{URL}/api/chat")
    route.mock(
        return_value=httpx.Response(
            200,
            json={"message": {"content": "One 5 mm right-lung spot near slice 188 needs review."}},
        )
    )
    text, source, rejection = llm_summary(OUTCOME, "en", base_url=URL, tag="medgemma")
    assert (source, rejection) == ("llm", None)
    assert "slice 188" in text
    sent = route.calls[0].request.content.decode()
    assert '"images"' not in sent
    route.mock(return_value=httpx.Response(200, json={"message": {"content": "It is cancer."}}))
    text, source, rejection = llm_summary(OUTCOME, "en", base_url=URL, tag="medgemma")
    assert (source, rejection) == ("template", "diagnostic or causal wording")
    assert text == " ".join(OUTCOME.sentences)
    route.mock(side_effect=httpx.ConnectError("down"))
    assert llm_summary(OUTCOME, "de", base_url=URL, tag="medgemma")[1] == "template"
