# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Bounded, local Ollama download jobs; never send study data or account credentials."""

import json
import time
from datetime import UTC, datetime
from threading import RLock, Thread
from typing import Any
from uuid import UUID, uuid4

import httpx

from thoraxbench.adapters.factory import require_local_endpoint
from thoraxbench.analysis import DISCLAIMER
from thoraxbench.api.abortable_http import abortable_client
from thoraxbench.api.jobs import JobContext, JobManager, JobOutcome


class PullBusyError(RuntimeError):
    """Another model download is still active."""


class ModelPullJobs:
    """Serialize downloads and retain at most 32 progress snapshots in memory."""

    def __init__(self, base_url: str, queue: JobManager | None = None) -> None:
        self._queue = queue
        self._queue_ids: dict[UUID, UUID] = {}
        self._base_url = base_url
        self._lock = RLock()
        self._jobs: dict[UUID, dict[str, Any]] = {}
        self._times: dict[UUID, tuple[float, float | None]] = {}

    def get(self, identifier: UUID) -> dict[str, Any] | None:
        """Return an isolated progress snapshot without local filesystem details."""
        with self._lock:
            job = self._jobs.get(identifier)
            if job is None:
                return None
            snapshot = dict(job)
            queued = self._queue_ids.get(identifier)
            if self._queue is not None and queued is not None:
                state = self._queue.get(queued)
                if state is not None:
                    snapshot.update(
                        status={"succeeded": "completed", "failed": "error"}.get(
                            state["status"], state["status"]
                        ),
                        elapsed_s=state["elapsed_s"],
                        started_at=state["started_at"],
                        job_id=state["id"],
                    )
                    if state["finished"]:
                        self._jobs[identifier].update(snapshot)
                elif job["status"] in {"queued", "running", "cancelling"}:
                    snapshot.update(status="cancelled", detail="Job metadata no longer retained")
                    self._jobs[identifier].update(snapshot)
            return snapshot

    def snapshots(self) -> list[dict[str, Any]]:
        """All retained downloads with server-measured elapsed seconds, oldest first."""
        now = time.monotonic()
        snapshots: list[dict[str, Any]] = []
        with self._lock:
            for identifier, job in self._jobs.items():
                start, end = self._times.get(identifier, (now, now))
                elapsed = max(0.0, (end if end is not None else now) - start)
                snapshots.append({"elapsed_s": elapsed} | (self.get(identifier) or dict(job)))
        return snapshots

    def start(self, model_id: str, tag: str) -> dict[str, Any]:
        """Start an acknowledged configured tag at an already validated loopback endpoint."""
        require_local_endpoint(self._base_url)
        with self._lock:
            if any(
                (self.get(key) or job)["status"] in {"queued", "running", "cancelling"}
                for key, job in self._jobs.items()
            ):
                raise PullBusyError("A model download is already active")
            if len(self._jobs) >= 32:
                oldest = next(iter(self._jobs))
                del self._jobs[oldest]
                self._times.pop(oldest, None)
                self._queue_ids.pop(oldest, None)
            identifier = uuid4()
            self._times[identifier] = (time.monotonic(), None)
            self._jobs[identifier] = {
                "id": str(identifier),
                "model_id": model_id,
                "status": "queued",
                "detail": "Waiting for local Ollama",
                "completed": None,
                "total": None,
                "started_at": datetime.now(UTC).isoformat(),
                "disclaimer": DISCLAIMER,
            }
            if self._queue is None:
                Thread(target=self._run, args=(identifier, tag), daemon=True).start()
            else:

                def work(context: JobContext) -> JobOutcome:
                    self._run(identifier, tag, context)
                    context.check()
                    state = self.get(identifier)
                    failed = state is not None and state["detail"] != "Download completed"
                    return JobOutcome("failed" if failed else "succeeded")

                try:
                    queued, _ = self._queue.submit(
                        "download", f"download|{model_id}", {"models": [model_id]}, work
                    )
                except RuntimeError:
                    del self._jobs[identifier]
                    self._times.pop(identifier, None)
                    raise
                self._queue_ids[identifier] = UUID(queued["id"])
            return self.get(identifier) or dict(self._jobs[identifier])

    def _update(self, identifier: UUID, **fields: Any) -> None:
        with self._lock:
            self._jobs[identifier].update(fields)
            if fields.get("status") in {"completed", "error"} and identifier in self._times:
                self._times[identifier] = (self._times[identifier][0], time.monotonic())

    def _run(self, identifier: UUID, tag: str, context: JobContext | None = None) -> None:
        self._update(identifier, status="running", detail="Connecting to local Ollama")
        client = httpx.Client(timeout=120.0, trust_env=False, follow_redirects=False)
        unregister = None
        if context is not None:
            client.close()
            client, transport = abortable_client(120.0)
            unregister = context.on_abort(transport.abort)
        try:
            if context is not None:
                context.stage("download")
            with (
                client,
                client.stream(
                    "POST",
                    f"{self._base_url.rstrip('/')}/api/pull",
                    json={"model": tag, "stream": True},
                ) as response,
            ):
                response.raise_for_status()
                success = False
                for line in response.iter_lines():
                    if context is not None:
                        context.check()
                    if not line:
                        continue
                    payload = json.loads(line)
                    if not isinstance(payload, dict):
                        raise ValueError("Invalid download progress")
                    if payload.get("error"):
                        raise ValueError(str(payload["error"])[:500])
                    status = str(payload.get("status", "Downloading"))[:500]
                    completed, total = payload.get("completed"), payload.get("total")
                    valid_bytes = (
                        type(completed) is int
                        and type(total) is int
                        and 0 <= completed <= total
                        and total > 0
                    )
                    self._update(
                        identifier,
                        detail=status,
                        completed=completed if valid_bytes else None,
                        total=total if valid_bytes else None,
                    )
                    if status == "success":
                        success = True
                        break
                if not success:
                    raise ValueError("Download ended without an Ollama success status")
            self._update(identifier, status="completed", detail="Download completed")
        except (httpx.HTTPError, OSError, ValueError) as exc:
            self._update(
                identifier, status="error", detail=str(exc)[:500], completed=None, total=None
            )

        finally:
            if unregister is not None:
                unregister()
            client.close()
