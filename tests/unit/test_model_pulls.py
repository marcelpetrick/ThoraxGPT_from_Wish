# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Model downloads are mocked; tests never acquire weights or contact real services."""

import json
from unittest.mock import Mock
from uuid import UUID

import httpx
import pytest
import respx

from thoraxbench.api import model_pulls
from thoraxbench.api.model_pulls import ModelPullJobs, PullBusyError


@pytest.fixture
def jobs(monkeypatch: pytest.MonkeyPatch) -> ModelPullJobs:
    monkeypatch.setattr(model_pulls, "Thread", Mock())
    return ModelPullJobs("http://localhost:11434")


@respx.mock
def test_pull_records_actual_layer_bytes_and_success(jobs: ModelPullJobs) -> None:
    job = jobs.start("test-model", "configured:tag")
    route = respx.post("http://localhost:11434/api/pull").mock(
        return_value=httpx.Response(
            200,
            text="\n".join(
                json.dumps(p)
                for p in [
                    {"status": "pulling layer", "completed": 3, "total": 10},
                    {"status": "success"},
                ]
            ),
        )
    )
    jobs._run(UUID(job["id"]), "configured:tag")
    result = jobs.get(UUID(job["id"]))
    assert result is not None
    assert result["status"] == "completed"
    assert result["completed"] is None
    assert json.loads(route.calls[0].request.content) == {"model": "configured:tag", "stream": True}
    result["status"] = "changed"
    assert jobs.get(UUID(job["id"]))["status"] == "completed"


@pytest.mark.parametrize(
    "progress",
    [
        "not json",
        "[]",
        '{"error":"not permitted"}',
        '{"status":"downloading","completed":true,"total":100}',
        '{"status":"downloading","completed":1000,"total":100}',
        "",
    ],
)
@respx.mock
def test_invalid_or_incomplete_pull_is_error(jobs: ModelPullJobs, progress: str) -> None:
    job = jobs.start("test-model", "configured:tag")
    respx.post("http://localhost:11434/api/pull").mock(
        return_value=httpx.Response(200, text=progress)
    )
    jobs._run(UUID(job["id"]), "configured:tag")
    assert jobs.get(UUID(job["id"]))["status"] == "error"


def test_pull_serializes_jobs_and_rejects_remote_endpoint(jobs: ModelPullJobs) -> None:
    jobs.start("first", "configured:first")
    with pytest.raises(PullBusyError):
        jobs.start("second", "configured:second")
    with pytest.raises(RuntimeError, match="loopback"):
        ModelPullJobs("https://remote.example").start("test", "configured:tag")


@respx.mock
def test_failed_finished_jobs_are_bounded(jobs: ModelPullJobs) -> None:
    respx.post("http://localhost:11434/api/pull").mock(side_effect=httpx.ConnectError("offline"))
    first = None
    for _ in range(33):
        job = jobs.start("test", "configured:tag")
        first = first or UUID(job["id"])
        jobs._run(UUID(job["id"]), "configured:tag")
    assert first is not None
    assert jobs.get(first) is None
