# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Browser-side stand-in for ``/api/jobs*`` returning scripted, labelled model outputs.

Tests that need a specific model response (abstention, escaping, translations) mock the
job API at the browser boundary. The real job queue is covered by integration tests and
by the end-to-end flow against a scripted local Ollama stand-in.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from playwright.sync_api import Page, Route

Output = dict[str, Any]
# A responder returns an output payload, ``("error", detail)`` or ``"hold"``.
Responder = Callable[[str], Output | tuple[str, str] | str]


def _status_of(output: Output) -> str:
    result = output["result"]
    return (
        "abstained" if result["report"].get("abstain") or result.get("raw_error") else "succeeded"
    )


class MockJobs:
    """Minimal in-memory job API; ``elapsed`` is the scripted server-clock reading."""

    def __init__(self, page: Page, respond: Responder, models: list[str] | None = None) -> None:
        self.page = page
        self.respond = respond
        self.models = models or ["heuristic-hu"]
        self.jobs: list[dict[str, Any]] = []
        self.requests: list[dict[str, Any]] = []
        self.elapsed = 0.0
        self.skipped: set[str] = set()
        page.route(re.compile(r".*/api/jobs(/.*)?$"), self._handle)

    def skip(self, model: str) -> None:
        """Plan *model* as unavailable (skipped) in future comparison jobs."""
        self.skipped.add(model)

    def _summary(self, job: dict[str, Any]) -> dict[str, Any]:
        steps = [{k: v for k, v in step.items() if k != "output"} for step in job["steps"]]
        return {k: v for k, v in job.items() if k != "result"} | {"steps": steps}

    def _tick(self, job: dict[str, Any]) -> None:
        if not job["finished"]:
            job["elapsed_s"] = self.elapsed
            for step in job["steps"]:
                if step["status"] == "running":
                    step["elapsed_s"] = self.elapsed

    def _settle(self, job: dict[str, Any]) -> None:
        """Advance a job through every non-held step."""
        if job["kind"] == "analysis":
            reply = self.respond(job["models"][0])
            if reply == "hold":
                return
            self._finish_analysis(job, reply)
            return
        for index, step in enumerate(job["steps"]):
            if step["status"] != "waiting":
                if step["status"] == "running":
                    return
                continue
            step["status"], step["elapsed_s"] = "running", 0.0
            reply = self.respond(step["model_id"])
            if reply == "hold":
                return
            self.finish_step(job, index, reply)
            return
        statuses = [step["status"] for step in job["steps"]]
        job.update(
            status="succeeded" if "completed" in statuses else "abstained",
            stage="done",
            finished=True,
            result={"comparison_download": "/mock/comparison.html"},
            elapsed_s=self.elapsed,
        )

    def _finish_analysis(self, job: dict[str, Any], reply: Output | tuple[str, str] | str) -> None:
        if isinstance(reply, tuple):
            job.update(status="failed", error=reply[1], result=None)
        elif isinstance(reply, dict):
            job.update(status=_status_of(reply), result=reply, result_available=True)
        job.update(stage="done", finished=True, elapsed_s=self.elapsed)

    def finish(self, output: Output | tuple[str, str], index: int = -1) -> None:
        """Complete a held analysis job."""
        self._finish_analysis(self.jobs[index], output)

    def finish_step(
        self, job: dict[str, Any], index: int, reply: Output | tuple[str, str] | str
    ) -> None:
        """Complete one held comparison step, then continue with the next one."""
        step = job["steps"][index]
        step["elapsed_s"] = self.elapsed
        if isinstance(reply, tuple):
            step.update(status="error", detail=reply[1])
        elif isinstance(reply, dict):
            status = "abstained" if _status_of(reply) == "abstained" else "completed"
            step.update(status=status, output=reply, result_id=reply.get("id"))
            job["result_available"] = True
        self._settle(job)

    def _create(self, body: dict[str, Any]) -> dict[str, Any]:
        comparison = body["kind"] == "comparison"
        models = self.models if comparison else [body["model_id"]]
        job: dict[str, Any] = {
            "id": str(uuid4()),
            "kind": body["kind"],
            "status": "running",
            "stage": "inference",
            "dataset": body["dataset"],
            "case_id": body["case_id"],
            "n_images": body["n_images"],
            "models": models,
            "queued_at": "2026-10-17T08:00:00+00:00",
            "started_at": "2026-10-17T08:00:00+00:00",
            "finished_at": None,
            "elapsed_s": self.elapsed,
            "finished": False,
            "queue_position": None,
            "steps": [
                {
                    "model_id": model,
                    "status": "skipped" if model in self.skipped else "waiting",
                    "detail": "",
                    "elapsed_s": None,
                }
                for model in models
            ]
            if comparison
            else [],
            "error": None,
            "cancel_requested": False,
            "cancel_stage": None,
            "result_available": False,
            "result": None,
        }
        self.jobs.append(job)
        self._settle(job)
        return job

    def _handle(self, route: Route) -> None:
        request = route.request
        path = request.url.split("/api/jobs", 1)[1].split("?", 1)[0]
        for job in self.jobs:
            self._tick(job)
        if request.method == "POST" and path == "":
            body = json.loads(request.post_data or "{}")
            self.requests.append(body)
            route.fulfill(json={"job": self._create(body), "created": True})
        elif request.method == "POST" and path == "/clear":
            before = len(self.jobs)
            self.jobs = [job for job in self.jobs if not job["finished"]]
            route.fulfill(json={"removed": before - len(self.jobs)})
        elif request.method == "POST" and path.endswith("/cancel"):
            job = next(job for job in self.jobs if job["id"] == path.split("/")[1])
            job.update(status="cancelled", stage="done", finished=True, cancel_requested=True)
            route.fulfill(json=job)
        elif path == "":
            route.fulfill(json={"jobs": [self._summary(job) for job in self.jobs], "downloads": []})
        else:
            job = next((job for job in self.jobs if job["id"] == path.strip("/")), None)
            if job is None:
                route.fulfill(status=404, json={"detail": "Unknown job"})
            else:
                route.fulfill(json=job)
