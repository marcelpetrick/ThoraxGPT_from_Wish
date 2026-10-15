# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Synthetic study through local adapter, parsing, timings and provenance."""

import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from thoraxbench.analysis import DISCLAIMER, AnalysisResult, analyze_study
from thoraxbench.config import Settings
from thoraxbench.schemas import AnalysisRequest
from thoraxbench.study import Study, load_study_dir


@pytest.fixture(scope="module")
def study(phantom_dir: Path) -> Study:
    return load_study_dir(phantom_dir, dataset="synthetic", case_id="test-case")


def test_heuristic_analysis_roundtrip_and_qc(study: Study) -> None:
    request = AnalysisRequest(labels=["pulmonary_nodule"], prompt_id="P1")
    result = analyze_study(study, "heuristic-hu", Settings(), request=request)
    assert result.request == request
    assert result.dataset == "synthetic"
    assert result.case_id == "test-case"
    assert result.report.positive_labels() == {"pulmonary_nodule"}
    assert result.disclaimer == DISCLAIMER
    assert result.report.study_quality.adequate == study.qc.adequate
    assert set(result.perf.stages_s) == {"preprocess", "inference", "parse"}
    assert result.perf.total_s >= sum(result.perf.stages_s.values())
    assert not result.perf.failed
    assert result.provenance.config_hash
    assert result.provenance.preprocess_hash
    assert result.provenance.model_id == "heuristic-hu"
    assert "cues" not in result.view_meta
    assert AnalysisResult.model_validate_json(result.model_dump_json()).model_dump(
        mode="json"
    ) == result.model_dump(mode="json")


@pytest.mark.parametrize("failed", [False, True])
def test_local_ollama_analysis(study: Study, failed: bool) -> None:
    payloads: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "localhost"
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "medgemma1.5:4b-it-q4_K_M", "digest": "sha256:test-weights"}
                    ]
                },
            )
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"family": "gemma3"}})
        assert request.url.path == "/api/chat"
        payloads.append(json.loads(request.content))
        if failed:
            return httpx.Response(503, text="local model unavailable")
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {"findings": [{"label": "pulmonary_nodule", "confidence": 0.9}]}
                    )
                },
                "eval_count": 11,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = analyze_study(
            study,
            "medgemma1.5-q4",
            Settings(),
            prompt_id="P0",
            view_overrides={"n": 2, "size": 64, "coronal": False},
            client=client,
        )
    assert result.provenance.model_hash == "sha256:test-weights"
    assert len(payloads) == 1
    assert result.request.prompt_id == "P0"
    assert result.perf.n_images == len(result.image_captions) > 0
    assert result.perf.input_bytes is not None
    assert result.perf.input_bytes > 0
    assert result.report.abstain == failed
    assert result.perf.failed == failed
    if failed:
        assert result.raw_error
        assert result.perf.error == result.raw_error
    else:
        assert result.report.label_probability("pulmonary_nodule") == 0.9
        assert result.perf.tokens_generated == 11
        assert result.provenance.prompt_hash == result.raw_meta["prompt_sha256"]


def test_inadequate_study_skips_all_model_and_cue_work(study: Study) -> None:
    limited = deepcopy(study)
    limited.volume.qc.n_slices = 1
    limited._cues = None

    def reject_network(request: httpx.Request) -> httpx.Response:
        pytest.fail(f"inadequate study made network request {request.url}")

    with httpx.Client(transport=httpx.MockTransport(reject_network)) as client:
        result = analyze_study(limited, "medgemma1.5-q4", Settings(), client=client)
    assert limited._cues is None
    assert result.report.abstain
    assert not result.report.study_quality.adequate
    assert "only 1 slices" in result.report.study_quality.limitations
    assert result.perf.failed
    assert not result.image_captions
    assert not result.perf.stages_s
    assert not result.report.findings


def test_prompt_conflict_rejected_before_inference(study: Study) -> None:
    with pytest.raises(ValueError, match="must agree"):
        analyze_study(
            study,
            "heuristic-hu",
            Settings(),
            request=AnalysisRequest(prompt_id="P0"),
            prompt_id="P1",
        )


def test_changed_request_and_view_affect_provenance(study: Study) -> None:
    first = analyze_study(study, "heuristic-hu", Settings())
    second = analyze_study(
        study, "heuristic-hu", Settings(), request=AnalysisRequest(labels=["pulmonary_nodule"])
    )
    third = analyze_study(study, "heuristic-hu", Settings(), view_overrides={"n": 2})
    assert first.provenance.config_hash != second.provenance.config_hash
    assert first.provenance.config_hash != third.provenance.config_hash
    assert first.provenance.preprocess_hash != third.provenance.preprocess_hash


def test_empty_model_predictions_abstain(study: Study) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            return httpx.Response(200, json={"message": {"content": '{"findings": []}'}})
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = analyze_study(
            study,
            "medgemma1.5-q4",
            Settings(),
            client=client,
            view_overrides={"n": 1, "size": 64, "coronal": False},
        )
    assert result.report.abstain
    assert "no label predictions returned" in result.report.parse_warnings
    assert result.perf.failed
