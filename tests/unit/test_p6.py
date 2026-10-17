# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""P6 protocol contracts: single image, separate labels, honest score availability."""

import json
import math
from typing import Any

import httpx
import pytest

from thoraxbench.adapters.factory import load_model
from thoraxbench.adapters.p6 import P6OllamaModel, binary_answer_probability, nonconstant_readiness
from thoraxbench.config import Settings
from thoraxbench.schemas import AnalysisRequest, PreparedInput


def _body(content: str, **extra: Any) -> dict[str, Any]:
    return {
        "message": {"content": content},
        "done_reason": "stop",
        "eval_count": 8,
        "prompt_eval_count": 100,
        "total_duration": 1000000000,
        **extra,
    }


def _answer(word: str = "yes") -> dict[str, Any]:
    return _body(
        json.dumps(word),
        logprobs=[
            {
                "token": word,
                "top_logprobs": [
                    {"token": "yes", "logprob": math.log(0.8)},
                    {"token": "no", "logprob": math.log(0.2)},
                ],
            }
        ],
    )


def _model(bodies: list[dict[str, Any]], requests: list[dict[str, Any]]) -> P6OllamaModel:
    def handle(req: httpx.Request) -> httpx.Response:
        requests.append(json.loads(req.content))
        return httpx.Response(200, json=bodies.pop(0))

    model = load_model(
        "medgemma1.5-q4-p6",
        Settings(),
        client=httpx.Client(transport=httpx.MockTransport(handle), trust_env=False),
    )
    assert isinstance(model, P6OllamaModel)
    return model


def _prepared(n: int = 1) -> PreparedInput:
    return PreparedInput(
        view_id="crop-test",
        view_version="1",
        images=[b"synthetic png"] * n,
        image_captions=["IMAGE 1: synthetic axial crop"],
        context="do not copy heuristic context",
    )


def test_p6_factory_and_requested_labels_preserve_both_calls() -> None:
    sent: list[dict[str, Any]] = []
    model = _model(
        [
            _body("Small round focus. Final Answer: yes"),
            _answer(),
            _body("No mass. Final Answer: no"),
            _answer("no"),
        ],
        sent,
    )
    raw = model.infer(
        _prepared(), AnalysisRequest(labels=["pulmonary_nodule", "pulmonary_mass"], prompt_id="P6")
    )
    report = model.parse(raw)
    assert not report.abstain
    assert [finding.label for finding in report.findings] == ["pulmonary_nodule", "pulmonary_mass"]
    assert report.label_probability("pulmonary_nodule") == pytest.approx(0.8)
    assert report.label_probability("pulmonary_mass") == pytest.approx(0.8)
    assert all(not finding.evidence_images for finding in report.findings)
    assert len(sent) == len(raw.meta["requests"]) == len(raw.meta["responses"]) == 4
    assert raw.meta["image_association"].startswith("sole prepared input")
    assert "format" not in sent[0]
    assert sent[1]["format"] == {"type": "string", "enum": ["yes", "no"]}
    assert sent[1]["logprobs"] is True
    assert "images" in sent[0]["messages"][1]
    assert "images" not in sent[1]["messages"][1]
    assert "pulmonary_mass" not in sent[0]["messages"][1]["content"]
    assert "pulmonary_nodule" not in sent[2]["messages"][1]["content"]
    assert all("do not copy" not in str(value) for value in sent)
    assert "images" not in raw.meta["requests"][0]["messages"][1]
    assert raw.meta["requests"][0]["messages"][1]["image_sha256"]
    assert raw.tokens_generated == 32
    assert raw.prompt_tokens == 400
    assert raw.meta["total_duration_s"] == 4


@pytest.mark.parametrize("n", [0, 2])
def test_p6_refuses_multi_image_without_network(n: int) -> None:
    sent: list[dict[str, Any]] = []
    model = _model([], sent)
    raw = model.infer(_prepared(n), AnalysisRequest(labels=["pulmonary_nodule"]))
    assert "exactly one" in (raw.error or "")
    assert model.parse(raw).abstain
    assert not sent


@pytest.mark.parametrize(
    "options", [{"unknown": 1}, [], {"reasoning_tokens": True}, {"answer_tokens": 999}]
)
def test_p6_refuses_invalid_protocol_limits(options: Any) -> None:
    sent: list[dict[str, Any]] = []
    model = _model([], sent)
    model.config = model.config.model_copy(update={"options": {"p6": options}})
    assert model.infer(_prepared(), AnalysisRequest()).error
    assert not sent


@pytest.mark.parametrize(
    ("first", "second", "reason"),
    [
        (_body("x", done_reason="length"), None, "reasoning generation"),
        (_body(""), None, "empty reasoning"),
        (_body("Unclear finding"), None, "missing explicit final answer"),
        ({"error": "provider failed"}, None, "provider error"),
        (
            _body("Reason. Final Answer: yes"),
            _body('"yes"', done_reason="length"),
            "answer generation",
        ),
        (_body("Reason. Final Answer: yes"), _body("yes"), "invalid constrained"),
        (_body("Reason. Final Answer: yes"), _body('"yes"'), "logprobs unavailable"),
        (_body("Reason. Final Answer: yes"), {"error": "provider failed"}, "provider error"),
    ],
)
def test_p6_preserves_unavailable_outputs(
    first: dict[str, Any], second: dict[str, Any] | None, reason: str
) -> None:
    sent: list[dict[str, Any]] = []
    model = _model([first] + ([second] if second else []), sent)
    raw = model.infer(_prepared(), AnalysisRequest(labels=["pulmonary_nodule"]))
    report = model.parse(raw)
    assert report.abstain
    assert any(reason in warning for warning in report.parse_warnings)
    assert report.label_probability("pulmonary_nodule") is None
    assert len(raw.meta["responses"]) == len(sent)


def test_p6_preserves_partial_failure() -> None:
    sent: list[dict[str, Any]] = []
    model = _model([{"error": "bad"}, _body("Reason. Final Answer: yes"), _answer()], sent)
    report = model.parse(
        model.infer(_prepared(), AnalysisRequest(labels=["pulmonary_mass", "pulmonary_nodule"]))
    )
    assert not report.abstain
    assert report.label_probability("pulmonary_mass") is None
    assert report.label_probability("pulmonary_nodule") == pytest.approx(0.8)


@pytest.mark.parametrize(
    "logprobs",
    [
        None,
        {},
        [None],
        [{"token": "other"}],
        [{"token": "yes"}],
        [
            {
                "token": "yes",
                "top_logprobs": [
                    None,
                    {"token": "yes", "logprob": float("nan")},
                    {"token": "no", "logprob": -1},
                ],
            }
        ],
        [{"token": "yes", "top_logprobs": [{"token": "yes", "logprob": 0}]}],
    ],
)
def test_p6_probability_requires_finite_visible_alternatives(logprobs: Any) -> None:
    assert binary_answer_probability({"logprobs": logprobs}) is None


def test_p6_probability_is_numerically_stable() -> None:
    data = {
        "logprobs": [
            {
                "token": '"Yes"',
                "top_logprobs": [
                    {"token": "yes", "logprob": -1000},
                    {"token": "no", "logprob": -1001},
                ],
            }
        ]
    }
    assert binary_answer_probability(data) == pytest.approx(1 / (1 + math.exp(-1)))


def test_p6_nonconstant_gate_is_separate_from_score_signal() -> None:
    assert nonconstant_readiness([(True, True, 0.8), (False, False, 0.2)])["passes"]
    constant = nonconstant_readiness([(True, False, 0.3), (False, False, 0.1)])
    assert constant["score_auroc"] == 1
    assert not constant["passes"]
    assert not nonconstant_readiness([])["passes"]
    assert not nonconstant_readiness([(True, True, None), (False, False, 0.2)])["passes"]
    assert not nonconstant_readiness([(True, True, 0.8)])["passes"]


@pytest.mark.parametrize(
    "labels", [["unknown-condition"], ["pulmonary_nodule", "pulmonary_nodule"]]
)
def test_p6_rejects_unknown_or_duplicate_labels(labels: list[str]) -> None:
    sent: list[dict[str, Any]] = []
    model = _model([], sent)
    assert model.infer(_prepared(), AnalysisRequest(labels=labels)).error
    assert not sent


def test_p6_refuses_extraction_that_contradicts_visual_argument() -> None:
    sent: list[dict[str, Any]] = []
    model = _model([_body("No round focus. Final Answer: no"), _answer("yes")], sent)
    raw = model.infer(_prepared(), AnalysisRequest(labels=["pulmonary_nodule"], prompt_id="P6"))
    report = model.parse(raw)
    assert report.abstain
    assert report.label_probability("pulmonary_nodule") is None
    assert any("contradicts" in warning for warning in report.parse_warnings)
    assert len(raw.meta["responses"]) == 2
