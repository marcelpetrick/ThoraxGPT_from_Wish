# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Job queue API over the synthetic demo with a scripted loopback Ollama stand-in."""

from __future__ import annotations

import shutil
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from tests.e2e.fake_ollama import FakeOllama, fake_ollama
from thoraxbench.api import app as api
from thoraxbench.config import Settings

Q4 = "medgemma1.5:4b-it-q4_K_M"


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


def _submit(client: TestClient, **body: Any) -> dict[str, Any]:
    payload = {"kind": "analysis", "dataset": "demo", "case_id": "phantom"} | body
    response = client.post("/api/jobs", json=payload)
    assert response.status_code == 200, response.text
    return dict(response.json())


def _until(
    client: TestClient, job_id: str, predicate: Any, timeout: float = 30.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if predicate(job):
            return dict(job)
        time.sleep(0.05)
    pytest.fail(f"job {job_id} did not reach the expected state")


def test_analysis_job_result_downloads_and_list_summary(client: TestClient, tmp_path: Path) -> None:
    created = _submit(client)
    assert created["created"] is True
    job = created["job"]
    assert job["kind"] == "analysis"
    assert job["models"] == ["heuristic-hu"]
    done = _until(client, job["id"], lambda j: j["finished"])
    assert done["status"] in {"succeeded", "abstained"}
    assert done["stage"] == "done"
    assert done["elapsed_s"] >= 0
    result = done["result"]
    assert result["result"]["model_id"] == "heuristic-hu"
    assert client.get(result["downloads"]["html"]).status_code == 200
    listed = client.get("/api/jobs").json()
    assert listed["downloads"] == []
    assert listed["limits"]["max_queued"] == 8
    assert "result" not in listed["jobs"][0]
    assert str(tmp_path) not in str(listed["jobs"][0])
    assert "/tmp/" not in str(listed["jobs"][0])  # no local filesystem paths
    assert client.post("/api/jobs/clear").json() == {"removed": 1}
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404


def test_queue_duplicate_cancel_and_stop_aborts_provider_request(
    client: TestClient, ollama: FakeOllama
) -> None:
    running = _submit(client, model_id="medgemma1.5-q4")["job"]
    _until(client, running["id"], lambda j: j["stage"] == "inference")
    duplicate = _submit(client, model_id="medgemma1.5-q4")
    assert duplicate["created"] is False
    assert duplicate["job"]["id"] == running["id"]
    queued = _submit(client)["job"]
    assert client.get(f"/api/jobs/{queued['id']}").json()["queue_position"] == 1
    cancelled = client.post(f"/api/jobs/{queued['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["started_at"] is None
    stopping = client.post(f"/api/jobs/{running['id']}/cancel").json()
    assert stopping["status"] in {"cancelling", "cancelled"}
    final = _until(client, running["id"], lambda j: j["finished"])
    assert final["status"] == "cancelled"
    assert final["cancel_stage"] == "inference"
    assert final["result"] is None
    deadline = time.monotonic() + 5
    while ollama.disconnects < 1 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert ollama.disconnects == 1
    # The worker continues with later jobs after a stop.
    after = _submit(client)["job"]
    assert _until(client, after["id"], lambda j: j["finished"])["status"] != "cancelled"


def test_comparison_job_preserves_steps_and_exports(client: TestClient, ollama: FakeOllama) -> None:
    ollama.release(4)
    job = _submit(client, kind="comparison", n_images=2)["job"]
    assert next(step["model_id"] for step in job["steps"]) == "monai-lung-nodule"
    planned = {step["model_id"]: step["status"] for step in job["steps"]}
    assert planned["medgemma1.5-q4"] == "waiting"
    assert planned["gemma3-4b"] == "skipped"
    done = _until(client, job["id"], lambda j: j["finished"])
    steps = {step["model_id"]: step for step in done["steps"]}
    assert steps["medgemma1.5-q4"]["status"] == "abstained"
    assert steps["medgemma1.5-q4"]["output"]["result"]["report"]["abstain"] is True
    assert steps["qwen3-vl-4b-nothink"]["status"] == "skipped"
    assert steps["heuristic-hu"]["elapsed_s"] is not None
    assert done["status"] in {"succeeded", "abstained"}
    exported = client.get(done["result"]["comparison_download"])
    assert exported.status_code == 200
    assert "skipped" in exported.text.lower()


def test_comparison_records_failed_step_and_failed_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api, "analyze_study", Mock(side_effect=ValueError("bad config")))
    monkeypatch.setattr(api, "_ollama_tags", lambda _config: set())
    job = _submit(client, kind="comparison")["job"]
    done = _until(client, job["id"], lambda j: j["finished"])
    assert done["status"] == "failed"
    assert done["error"] == "No model produced a result"
    heuristic = next(step for step in done["steps"] if step["model_id"] == "heuristic-hu")
    assert heuristic["status"] == "error"
    assert "check the local model configuration" in heuristic["detail"]


def test_job_guards_limits_and_unknown_ids(client: TestClient, tmp_path: Path) -> None:
    base = {"dataset": "demo", "case_id": "phantom"}
    assert client.post("/api/jobs", json=base | {"kind": "other"}).status_code == 422
    assert (
        client.post("/api/jobs", json=base | {"kind": "analysis", "n_images": 0}).status_code == 422
    )
    unknown = base | {"kind": "analysis", "model_id": "missing"}
    assert client.post("/api/jobs", json=unknown).status_code == 422
    missing = {"kind": "analysis", "dataset": "lidc_idri", "case_id": "nope"}
    assert client.post("/api/jobs", json=missing).status_code in {403, 404}
    assert (
        client.post(
            "/api/jobs", json={"kind": "analysis", "dataset": "demo", "case_id": "other"}
        ).status_code
        == 404
    )
    cross = client.post(
        "/api/jobs", json=base | {"kind": "analysis"}, headers={"origin": "https://remote.example"}
    )
    assert cross.status_code == 403
    assert client.get("/api/jobs", headers={"host": "remote.example"}).status_code == 403
    identifier = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/jobs/{identifier}").status_code == 404
    assert client.post(f"/api/jobs/{identifier}/cancel").status_code == 404
    assert client.get("/api/jobs/not-a-uuid").status_code == 422
    # One held job runs; eight distinct jobs may wait; the next is refused.
    running = _submit(client, model_id="medgemma1.5-q4")["job"]
    _until(client, running["id"], lambda j: j["status"] == "running")
    for count in range(1, 9):
        _submit(client, n_images=count)
    refused = client.post("/api/jobs", json=base | {"kind": "analysis", "n_images": 9})
    assert refused.status_code == 429
    assert client.get("/jobs").status_code == 200
    shutil.rmtree(tmp_path / "data" / "demo")
    assert client.post("/api/jobs", json=base | {"kind": "analysis"}).status_code == 404


def test_blocking_analyze_runs_through_queue_and_reports_cancellation(
    client: TestClient, ollama: FakeOllama
) -> None:
    running = _submit(client, model_id="medgemma1.5-q4")["job"]
    _until(client, running["id"], lambda j: j["stage"] == "inference")
    client.post(f"/api/jobs/{running['id']}/cancel")
    ollama.release(8)
    response = client.post(
        "/api/analyze", json={"dataset": "demo", "case_id": "phantom", "model_id": "medgemma1.5-q4"}
    )
    ollama.release()
    assert response.status_code in {200, 409}


def test_model_downloads_appear_in_job_list(client: TestClient) -> None:
    running = _submit(client, model_id="medgemma1.5-q4")["job"]
    _until(client, running["id"], lambda j: j["stage"] == "inference")
    started = client.post("/api/models/gemma3-4b/pull", json={"terms_acknowledged": True})
    assert started.status_code == 200
    downloads = client.get("/api/jobs").json()["downloads"]
    assert [entry["model_id"] for entry in downloads] == ["gemma3-4b"]
    assert downloads[0]["status"] == "queued"
    assert downloads[0]["elapsed_s"] is None
    assert downloads[0]["started_at"] is None
    queued_id = downloads[0]["job_id"]
    state = client.get(f"/api/jobs/{queued_id}").json()
    assert state["kind"] == "download"
    assert state["queue_position"] == 1
    assert client.post(f"/api/jobs/{queued_id}/cancel").json()["status"] == "cancelled"
    assert client.get(f"/api/model-pulls/{downloads[0]['id']}").json()["status"] == "cancelled"
    client.post(f"/api/jobs/{running['id']}/cancel")


def test_running_download_stop_closes_request_and_releases_queue(
    client: TestClient, ollama: FakeOllama
) -> None:
    response = client.post("/api/models/gemma3-4b/pull", json={"terms_acknowledged": True})
    assert response.status_code == 200
    identifier = response.json()["job_id"]
    _until(client, identifier, lambda j: j["stage"] == "download")
    # Wait until the provider received the stream request before stopping it.
    deadline = time.monotonic() + 5
    while ollama.pulls == 0 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert ollama.pulls == 1
    client.post(f"/api/jobs/{identifier}/cancel")
    assert _until(client, identifier, lambda j: j["finished"])["status"] == "cancelled"
    status = client.get(f"/api/model-pulls/{response.json()['id']}").json()
    assert status["status"] == "cancelled"
    after = _submit(client)["job"]
    assert _until(client, after["id"], lambda j: j["finished"])["status"] == "succeeded"


def test_download_success_is_retained_with_server_elapsed(
    client: TestClient, ollama: FakeOllama
) -> None:
    ollama.release()
    response = client.post("/api/models/gemma3-4b/pull", json={"terms_acknowledged": True})
    assert response.status_code == 200
    job = _until(client, response.json()["job_id"], lambda j: j["finished"])
    assert job["status"] == "succeeded"
    status = client.get(f"/api/model-pulls/{response.json()['id']}").json()
    assert status["status"] == "completed"
    assert status["elapsed_s"] >= 0
