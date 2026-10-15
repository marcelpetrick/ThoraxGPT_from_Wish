# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Bounded, local Ollama download jobs; never send study data or account credentials."""

import json
from threading import RLock, Thread
from typing import Any
from uuid import UUID, uuid4

import httpx

from thoraxbench.adapters.factory import require_local_endpoint
from thoraxbench.analysis import DISCLAIMER


class PullBusyError(RuntimeError):
    """Another model download is still active."""


class ModelPullJobs:
    """Serialize downloads and retain at most 32 progress snapshots in memory."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url
        self._lock = RLock()
        self._jobs: dict[UUID, dict[str, Any]] = {}

    def get(self, identifier: UUID) -> dict[str, Any] | None:
        """Return an isolated progress snapshot without local filesystem details."""
        with self._lock:
            job = self._jobs.get(identifier)
            return dict(job) if job is not None else None

    def start(self, model_id: str, tag: str) -> dict[str, Any]:
        """Start an acknowledged configured tag at an already validated loopback endpoint."""
        require_local_endpoint(self._base_url)
        with self._lock:
            if any(job["status"] in {"queued", "running"} for job in self._jobs.values()):
                raise PullBusyError("A model download is already active")
            if len(self._jobs) >= 32:
                del self._jobs[next(iter(self._jobs))]
            identifier = uuid4()
            self._jobs[identifier] = {
                "id": str(identifier),
                "model_id": model_id,
                "status": "queued",
                "detail": "Waiting for local Ollama",
                "completed": None,
                "total": None,
                "disclaimer": DISCLAIMER,
            }
            Thread(target=self._run, args=(identifier, tag), daemon=True).start()
            return dict(self._jobs[identifier])

    def _update(self, identifier: UUID, **fields: Any) -> None:
        with self._lock:
            self._jobs[identifier].update(fields)

    def _run(self, identifier: UUID, tag: str) -> None:
        self._update(identifier, status="running", detail="Connecting to local Ollama")
        try:
            with (
                httpx.Client(timeout=120.0, trust_env=False, follow_redirects=False) as client,
                client.stream(
                    "POST",
                    f"{self._base_url.rstrip('/')}/api/pull",
                    json={"model": tag, "stream": True},
                ) as response,
            ):
                response.raise_for_status()
                success = False
                for line in response.iter_lines():
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
