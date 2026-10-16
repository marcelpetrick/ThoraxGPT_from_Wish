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


def test_manifest_input_scoring_and_reference_hashes(study: Study, tmp_path: Path) -> None:
    from thoraxbench.provenance import sha256_of_file

    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    (tmp_path / "configs").symlink_to(Settings().configs_dir, target_is_directory=True)
    for kind in ("datasets", "splits"):
        path = settings.manifests_dir / kind / "synthetic.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"version": "synthetic-only"}')
    index = settings.data_path("index", "synthetic.json")
    index.parent.mkdir(parents=True)
    index.write_text('{"reference_version": 1}')
    result = analyze_study(study, "heuristic-hu", settings)
    provenance = result.provenance
    assert provenance.dataset_manifest_hash == sha256_of_file(
        settings.manifests_dir / "datasets" / "synthetic.json"
    )
    assert provenance.split_manifest_hash == sha256_of_file(
        settings.manifests_dir / "splits" / "synthetic.json"
    )
    assert provenance.ground_truth_hash == sha256_of_file(index)
    assert provenance.scoring_hash
    assert provenance.input_hash
    first = provenance.fingerprint()
    index.write_text('{"reference_version": 2}')
    assert analyze_study(study, "heuristic-hu", settings).provenance.fingerprint() != first


def test_direct_header_values_redacted_from_model_outputs(
    phantom_dir: Path, tmp_path: Path
) -> None:
    import shutil

    import pydicom

    copied = Path(shutil.copytree(phantom_dir, tmp_path / "study"))
    first = next(copied.rglob("*.dcm"))
    header = pydicom.dcmread(first)
    header.PatientName = "SYNTHETICSECRET^Researchperson"
    header.InstitutionName = "Synthetic Secret Institution"
    header.save_as(first)
    loaded = load_study_dir(copied, dataset="synthetic", case_id="redaction-case")
    assert "SYNTHETICSECRET^Researchperson" in loaded.identifiers

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                json={
                    "message": {
                        "content": json.dumps(
                            {
                                "findings": [
                                    {
                                        "label": "pulmonary_nodule",
                                        "present": True,
                                        "confidence": 0.8,
                                        "description": (
                                            "SYNTHETICSECRET Researchperson at "
                                            "Synthetic Secret Institution"
                                        ),
                                    }
                                ]
                            }
                        )
                    }
                },
            )
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = analyze_study(
            loaded,
            "medgemma1.5-q4",
            Settings(),
            client=client,
            request=AnalysisRequest(question="SYNTHETICSECRET^Researchperson"),
            view_overrides={"n": 1, "size": 64, "coronal": False},
        )
    output = result.model_dump_json()
    assert "SYNTHETICSECRET" not in output
    assert "Researchperson" not in output
    assert "Synthetic Secret Institution" not in output
    assert "[redacted]" in output
    assert result.patient_id == loaded.patient_id
    assert result.provenance.input_hash


@pytest.mark.parametrize("kind", ["unsafe_key", "symlink_escape"])
def test_metadata_identity_rejected_before_inference(
    study: Study, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    from dataclasses import replace

    from thoraxbench import analysis

    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    key = "../sealed/forbidden" if kind == "unsafe_key" else "synthetic"
    if kind == "symlink_escape":
        folder = settings.data_path("index")
        folder.mkdir(parents=True)
        (folder / "synthetic.json").symlink_to(tmp_path / "never-read.json")
    monkeypatch.setattr(analysis, "sha256_of_file", lambda *_args: pytest.fail("unsafe file read"))
    monkeypatch.setattr(analysis, "load_model", lambda *_args, **_kwargs: pytest.fail("inference"))
    with pytest.raises(ValueError, match="metadata"):
        analyze_study(replace(study, dataset=key), "heuristic-hu", settings)


def test_canonical_hu_changes_input_identity(study: Study) -> None:
    first = analyze_study(study, "heuristic-hu", Settings())
    changed = deepcopy(study)
    changed.volume.hu[0, 0, 0] += 1
    second = analyze_study(changed, "heuristic-hu", Settings())
    assert first.provenance.input_hash != second.provenance.input_hash


def test_prepared_tensor_bytes_are_hashed(
    study: Study, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import Mock

    from thoraxbench import analysis
    from thoraxbench.schemas import Finding, FindingsReport, PreparedInput, RawOutput

    tensor = tmp_path / "synthetic-tensor"
    tensor.write_bytes(b"synthetic tensor version 1")
    model = Mock()
    model.prepare.return_value = PreparedInput(
        view_id="synthetic-tensor", view_version="1", tensor_path=str(tensor)
    )
    model.infer.return_value = RawOutput(text="synthetic response")
    model.parse.return_value = FindingsReport(
        findings=[Finding(label="pulmonary_nodule", confidence=0.8)]
    )
    monkeypatch.setattr(analysis, "load_model", lambda *_args, **_kwargs: model)
    first = analyze_study(study, "heuristic-hu", Settings())
    tensor.write_bytes(b"synthetic tensor version 2")
    second = analyze_study(study, "heuristic-hu", Settings())
    assert first.provenance.input_hash != second.provenance.input_hash


@pytest.mark.parametrize("kind", ["missing_confidence", "uncertain", "other_label"])
def test_no_available_requested_prediction_abstains(study: Study, kind: str) -> None:
    finding: dict[str, object] = {"label": "pulmonary_nodule", "present": True}
    if kind == "uncertain":
        finding.update(present=None, confidence=0.8)
    elif kind == "other_label":
        finding.update(label="pulmonary_mass", confidence=0.8)

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                json={
                    "message": {
                        "content": json.dumps(
                            {
                                "findings": [finding],
                            }
                        )
                    }
                },
            )
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = analyze_study(
            study,
            "medgemma1.5-q4",
            Settings(),
            client=client,
            request=AnalysisRequest(labels=["pulmonary_nodule"]),
            view_overrides={"n": 1, "size": 64, "coronal": False},
        )
    assert result.report.abstain
    assert result.perf.failed
    assert "no available requested-label predictions returned" in result.report.parse_warnings
    assert result.raw_meta["responses"]


@pytest.mark.parametrize("prompt", ["P0", "P2", "P3", "P4"])
@pytest.mark.parametrize("evidence", [[], [0, 70], [1, 1, 70]])
def test_visual_evidence_bounds_preserve_raw_and_constrained_unknowns(
    study: Study, prompt: str, evidence: list[int]
) -> None:
    raw = json.dumps(
        {
            "findings": [
                {
                    "label": "pulmonary_nodule",
                    "present": True,
                    "confidence": 0.9,
                    "evidence_images": evidence,
                }
            ]
        }
    )

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            return httpx.Response(200, json={"message": {"content": raw}})
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = analyze_study(
            study,
            "medgemma1.5-q4",
            Settings(),
            client=client,
            prompt_id=prompt,
            request=AnalysisRequest(prompt_id=prompt, labels=["pulmonary_nodule"]),
            view_overrides={"strategy": "uniform", "n": 2, "size": 64, "coronal": False},
        )
    finding = result.report.findings[0]
    assert result.raw_text == raw
    assert finding.evidence_images == ([1] if 1 in evidence else [])
    unsupported = prompt != "P0" and 1 not in evidence
    assert result.report.abstain == unsupported
    assert finding.presence_probability() == (None if unsupported else 0.9)
    if unsupported:
        assert any("marked unavailable" in warning for warning in result.report.parse_warnings)


def test_context_ablation_preserves_empty_actual_model_context(study: Study) -> None:
    messages: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            messages.append(json.loads(request.content)["messages"][1]["content"])
            return httpx.Response(200, json={"message": {"content": '{"findings": []}'}})
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = analyze_study(
            study,
            "medgemma1.5-q4",
            Settings(),
            client=client,
            prompt_id="P2",
            view_overrides={
                "strategy": "uniform",
                "n": 2,
                "size": 64,
                "coronal": False,
                "include_cues": False,
            },
        )
    assert "No deterministic measurements are available" in messages[0]
    assert "nodule candidate" not in messages[0]
    assert result.context == ""
    assert result.view_meta["include_cues"] is False


@pytest.mark.parametrize(
    ("present", "confidence", "expected", "abstain"),
    [
        (False, 0.1, None, True),
        (True, 0.1, 0.1, False),
        (False, 0.9, 0.1, False),
        (False, 0.5, None, True),
    ],
)
def test_evidence_guard_uses_implied_presence_probability(
    study: Study, present: bool, confidence: float, expected: float | None, abstain: bool
) -> None:
    from thoraxbench.analysis import _check_image_evidence
    from thoraxbench.schemas import Finding, FindingsReport

    report = FindingsReport(
        findings=[Finding(label="pulmonary_nodule", present=present, confidence=confidence)]
    )
    _check_image_evidence(report, 2, required=True)
    if expected is None:
        assert report.findings[0].presence_probability() is None
    else:
        assert report.findings[0].presence_probability() == pytest.approx(expected)
    assert any("marked unavailable" in w for w in report.parse_warnings) == abstain


def test_model_declared_inadequate_abstains_even_when_raw_abstain_is_false(study: Study) -> None:
    text = json.dumps(
        {
            "study_quality": {"adequate": False, "limitations": ["not visible"]},
            "findings": [{"label": "pulmonary_nodule", "present": False, "confidence": 0.9}],
            "abstain": False,
        }
    )

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"message": {"content": text}} if request.url.path == "/api/chat" else {}
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = analyze_study(
            study,
            "medgemma1.5-q4",
            Settings(),
            client=client,
            view_overrides={"strategy": "uniform", "n": 2, "size": 64, "coronal": False},
        )
    assert result.report.abstain
    assert not result.report.study_quality.adequate
    assert result.report.label_probability("pulmonary_nodule") is None
    assert result.perf.failed
    assert result.raw_text == text
    assert "model marked prepared study inadequate" in result.report.parse_warnings
