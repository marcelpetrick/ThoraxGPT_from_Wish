# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Full thorax review over a synthetic phantom with a scripted image model (no model runs)."""

from __future__ import annotations

import dataclasses
import json
import shutil
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from tests.detector_stub import scripted_result
from tests.e2e.fake_ollama import FakeOllama, fake_ollama
from thoraxbench.adapters.base import ModelUnavailableError
from thoraxbench.analysis import analyze_study
from thoraxbench.api import app as api
from thoraxbench.config import Settings
from thoraxbench.fullreview import run_full_review
from thoraxbench.fullreview import runner as runner_module
from thoraxbench.ontology import load_ontology
from thoraxbench.parsing import parse_findings
from thoraxbench.reports.full_review import render_full_review_html
from thoraxbench.sampling import ThoraxSweep
from thoraxbench.schemas import AnalysisRequest, FindingsReport, PreparedInput, RawOutput
from thoraxbench.study import Study, load_study_dir

Q4 = "medgemma1.5:4b-it-q4_K_M"


class ScriptedVlm:
    """Labelled scripted answers per slab centre; records every prepared input."""

    def __init__(
        self,
        positive: Callable[[int], set[str]],
        *,
        error: bool = False,
        abstain: bool | str = False,
    ) -> None:
        self.positive = positive
        self.error = error
        self.abstain = abstain
        self.seen: list[PreparedInput] = []

    def infer(self, prepared: PreparedInput, request: AnalysisRequest) -> RawOutput:
        self.seen.append(prepared)
        if self.error:
            return RawOutput(error="http error: scripted outage")
        found = self.positive(prepared.slice_indices[0])
        findings = [
            {
                "label": label,
                "present": label in found,
                "confidence": 0.9,
                "evidence_images": [1] if label in found else [],
                "description": "scripted round density, right lung" if label in found else "",
                "laterality": "right" if label in found else "unknown",
            }
            for label in request.labels
            if self.abstain != "empty"
        ]
        return RawOutput(
            text=json.dumps(
                {
                    "study_quality": {"adequate": True, "limitations": []},
                    "findings": findings,
                    "negative_findings": [],
                    "abstain": bool(self.abstain),
                    "uncertainty": "Scripted synthetic response; no model ran.",
                }
            )
        )

    def parse(self, raw: RawOutput) -> FindingsReport:
        return parse_findings(raw, load_ontology())


@pytest.fixture(scope="module")
def study(phantom_dir: Path) -> Study:
    return load_study_dir(phantom_dir, dataset="phantom")


@pytest.fixture
def scripted_detector(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scripted detector output (labelled, no network); other engines stay real."""

    def analyze(study: Study, model_id: str, settings: Settings, **kwargs: Any) -> Any:
        if model_id == "monai-lung-nodule":
            return scripted_result(study, model_id, settings, **kwargs)
        return analyze_study(study, model_id, settings, **kwargs)

    available = Mock()
    available.available.return_value = True
    monkeypatch.setattr(runner_module, "analyze_study", analyze)
    monkeypatch.setattr(runner_module, "load_model", lambda *_a, **_k: available)


def _nodule_slab(index: int) -> set[str]:
    return {"pulmonary_nodule"} if 20 <= index <= 23 else set()


def test_full_review_agrees_detector_hu_and_vlm(study: Study, scripted_detector: None) -> None:
    vlm = ScriptedVlm(_nodule_slab)
    calls: list[tuple[int, int, float | None]] = []
    stages: list[str] = []
    run = run_full_review(
        study,
        "medgemma1.5-q4",
        Settings(),
        model=vlm,  # type: ignore[arg-type]  # scripted stand-in for the Ollama adapter
        on_progress=lambda done, total, rate: calls.append((done, total, rate)),
        on_stage=stages.append,
    )
    summary = run.summary
    total = summary["coverage"]["slabs_total"]
    assert stages == ["heuristic", "detector", "slabs", "aggregate"]
    assert calls[0] == (0, total, None)
    assert [c[0] for c in calls] == list(range(total + 1))
    assert all(rate is not None and rate >= 0 for _, _, rate in calls[1:])
    assert len(vlm.seen) == total
    assert all(len(p.images) == 1 and p.image_captions[0].startswith("IMAGE 1:") for p in vlm.seen)
    first_two = [p.slice_indices[0] for p in vlm.seen[:2]]
    assert first_two[0] < first_two[1]  # both ends first: cranial end, then caudal end
    assert summary["verdict"] == "findings_to_review"
    assert summary["coverage"] | {"partial": False, "stopped": False} == summary["coverage"]
    assert summary["detector"]["status"] == "completed"
    top = summary["look_here"][0]
    assert top["label"] == "pulmonary_nodule"
    assert top["sources"] == ["detector", "hu", "vlm"]
    assert top["agreement"] is True
    assert top["side"] == "right"
    assert summary["labels_flagged"] == ["pulmonary_nodule"]
    assert "pleural_effusion" in [item["label"] for item in summary["look_here"]]
    assert summary["per_label"]["pulmonary_nodule"]["clusters"][0]["positive_slabs"] == 4
    assert summary["provenance"]["strategy"]["id"] == "thorax_sweep"
    assert summary["provenance"]["thresholds"]["constant_label_rate"] == 0.6
    assert summary["provenance"]["prompt_hash"] is None  # scripted model has no prompt
    text = json.dumps(summary)
    assert study.volume.series_uid not in text
    assert "PHANTOM-0001" not in text
    assert [s["position"] for s in summary["slabs"]] == list(range(total))
    page = render_full_review_html(summary, run.thumbnails)
    assert "Something to show a radiologist" in page
    assert study.volume.series_uid not in page


def test_constant_yes_model_is_not_informative(study: Study) -> None:
    labels = set(load_ontology().ids(core_only=True))
    run = run_full_review(
        study,
        "medgemma1.5-q4",
        Settings(),
        model=ScriptedVlm(lambda _i: labels),  # type: ignore[arg-type]
        detector_id=None,
        strategy=ThoraxSweep(n=12),
    )
    summary = run.summary
    assert summary["model_constant"] is True
    assert sorted(summary["labels_not_informative"]) == sorted(labels)
    assert all("vlm" not in item["sources"] for item in summary["look_here"])
    assert summary["detector"]["status"] == "not_configured"


def test_stop_between_slabs_keeps_partial_coverage(study: Study) -> None:
    vlm = ScriptedVlm(_nodule_slab)
    run = run_full_review(
        study,
        "medgemma1.5-q4",
        Settings(),
        model=vlm,  # type: ignore[arg-type]
        detector_id=None,
        should_stop=lambda: len(vlm.seen) >= 5,
    )
    cov = run.summary["coverage"]
    assert (cov["slabs_visited"], cov["slabs_answered"]) == (5, 5)
    assert cov["partial"] is True
    assert cov["stopped"] is True
    assert cov["slabs_total"] > 5
    positions = sorted(s["position"] for s in run.summary["slabs"])
    assert positions[0] == 0
    assert positions[-1] == cov["slabs_total"] - 1


def test_runtime_outage_stops_early_and_is_not_assessable(study: Study) -> None:
    vlm = ScriptedVlm(_nodule_slab, error=True)
    run = run_full_review(
        study,
        "medgemma1.5-q4",
        Settings(),
        model=vlm,  # type: ignore[arg-type]
        detector_id=None,
    )
    cov = run.summary["coverage"]
    assert cov["runtime_failed"] is True
    assert cov["slabs_visited"] == runner_module.MAX_INITIAL_FAILURES
    assert run.summary["slabs"][0]["status"] == "error"
    # HU cues still produce places to look; the image model contributed nothing.
    assert all("vlm" not in item["sources"] for item in run.summary["look_here"])


def test_abstaining_model_and_inadequate_study(study: Study) -> None:
    abstaining = run_full_review(
        study,
        "medgemma1.5-q4",
        Settings(),
        model=ScriptedVlm(_nodule_slab, abstain="empty"),  # type: ignore[arg-type]
        detector_id=None,
        strategy=ThoraxSweep(n=12),
    )
    assert abstaining.summary["coverage"]["slabs_answered"] == 0
    assert abstaining.summary["coverage"]["runtime_failed"] is False
    assert set(abstaining.summary["labels_unanswered"]) == set(load_ontology().ids(core_only=True))
    volume = dataclasses.replace(study.volume, qc=dataclasses.replace(study.volume.qc, n_slices=1))
    inadequate = dataclasses.replace(study, volume=volume)
    assert not inadequate.qc.adequate
    run = run_full_review(
        inadequate,
        "medgemma1.5-q4",
        Settings(),
        model=ScriptedVlm(_nodule_slab),  # type: ignore[arg-type]
    )
    assert run.summary["verdict"] == "not_assessable"
    assert run.summary["coverage"]["slabs_total"] == 0


def test_slab_self_abstention_keeps_per_label_answers(study: Study) -> None:
    """MedGemma abstains per slab ("one slice visible") while answering every label."""
    run = run_full_review(
        study,
        "medgemma1.5-q4",
        Settings(),
        model=ScriptedVlm(_nodule_slab, abstain=True),  # type: ignore[arg-type]
        detector_id=None,
        strategy=ThoraxSweep(n=12),
    )
    assert run.summary["coverage"]["slabs_answered"] == 12
    assert any(
        "self-abstention ignored" in warning
        for slab in run.summary["slabs"]
        for warning in slab["warnings"]
    )


def test_whole_volume_review_without_image_model(study: Study) -> None:
    """The slab sweep is optional; the detector/HU baseline alone still give an outcome."""
    run = run_full_review(study, "heuristic-hu", Settings(), detector_id=None)
    assert run.summary["coverage"]["slabs_total"] == 0
    assert run.summary["heuristic"]["status"] == "completed"
    assert run.summary["coverage"]["stopped"] is False


def test_service_models_are_refused(study: Study) -> None:
    with pytest.raises(ModelUnavailableError):
        run_full_review(study, "ct-chat", Settings())


# -- job API over a scripted loopback Ollama stand-in ---------------------------------------
@pytest.fixture
def ollama() -> Iterator[FakeOllama]:
    with fake_ollama([Q4]) as fake:
        yield fake


@pytest.fixture
def client(tmp_path: Path, ollama: FakeOllama) -> TestClient:
    shutil.copytree(Settings().configs_dir, tmp_path / "configs")
    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data", ollama_url=ollama.url)
    client = TestClient(api.create_app(settings))
    assert client.post("/api/demo").status_code == 200
    return client


def _until(client: TestClient, job_id: str, predicate: Any, timeout: float = 60.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if predicate(job):
            return job
        time.sleep(0.05)
    pytest.fail(f"job {job_id} did not reach the expected state")


def _submit(client: TestClient, model_id: str = "medgemma1.5-q4") -> Any:
    body = {"kind": "full-review", "dataset": "demo", "case_id": "phantom", "model_id": model_id}
    return client.post("/api/jobs", json=body)


def test_full_review_job_reports_progress_and_outcome(
    client: TestClient, ollama: FakeOllama
) -> None:
    assert _submit(client, "ct-chat").status_code == 422  # service models cannot sweep
    job = _submit(client).json()["job"]
    assert job["kind"] == "full-review"
    assert job["models"] == ["medgemma1.5-q4"]
    assert job["n_images"] is None
    ollama.release(1)
    running = _until(client, job["id"], lambda j: (j["progress"] or {}).get("completed", 0) >= 1)
    progress = running["progress"]
    assert progress["operation"] == "review_images"
    assert progress["seconds_per_item"] >= 0
    assert progress["remaining_s"] >= 0
    assert _submit(client).json()["created"] is False
    ollama.release(200)
    done = _until(client, job["id"], lambda j: j["finished"])
    # The scripted provider abstains and no detector ran: HU cues alone are weak, listed
    # but never the verdict, so nothing usable checked the scan.
    assert done["status"] == "abstained"
    summary = done["result"]["summary"]
    assert summary["verdict"] == "not_assessable"
    assert summary["look_here"]
    assert all(item["weak"] for item in summary["look_here"])
    assert summary["coverage"]["slabs_answered"] == 0
    assert summary["detector"]["status"] in {"unavailable", "completed"}
    page = client.get(done["result"]["downloads"]["html"] + "?inline=true")
    assert page.status_code == 200
    assert "Full thorax review" in page.text
    assert client.get(done["result"]["downloads"]["json"]).json()["verdict"] == summary["verdict"]
    listed = client.get("/api/jobs").json()["jobs"][0]
    assert "result" not in listed
    assert "/tmp/" not in json.dumps(done)


def test_full_review_cancel_keeps_partial_result(client: TestClient, ollama: FakeOllama) -> None:
    job = _submit(client).json()["job"]
    ollama.release(2)
    _until(client, job["id"], lambda j: (j["progress"] or {}).get("completed", 0) >= 2)
    stopping = client.post(f"/api/jobs/{job['id']}/cancel").json()
    assert stopping["status"] in {"cancelling", "cancelled"}
    final = _until(client, job["id"], lambda j: j["finished"])
    assert final["status"] == "cancelled"
    cov = final["result"]["summary"]["coverage"]
    assert cov["partial"] is True
    assert cov["stopped"] is True
    assert cov["slabs_visited"] == 2
    assert final["result_available"] is True
    assert client.get(final["result"]["downloads"]["html"]).status_code == 200
