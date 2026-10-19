# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""In-process research job queue with one sequential worker (one local GPU).

Jobs live in memory for the current server session only. Each job records server-side
monotonic start/end times and its current engine stage, so every browser view (and a
reloaded page) shows the same state. Cancellation is cooperative: queued jobs stop
immediately; running jobs stop at the next stage boundary, and registered abort hooks
interrupt an in-flight provider request where possible. Snapshots never contain local
filesystem paths.
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Condition, Event, RLock, Thread
from typing import Any, Literal
from uuid import UUID, uuid4

from thoraxbench.analysis import DISCLAIMER
from thoraxbench.api.diagnostics import job_diagnostic
from thoraxbench.api.job_logging import OPERATIONS, job_event

JobStatus = Literal[
    "queued", "running", "cancelling", "succeeded", "failed", "abstained", "cancelled"
]
ACTIVE: frozenset[str] = frozenset({"queued", "running", "cancelling"})
TERMINAL: frozenset[str] = frozenset({"succeeded", "failed", "abstained", "cancelled"})
STEP_OPEN: frozenset[str] = frozenset({"waiting", "running"})
MAX_DETAIL = 500
LOGGER = logging.getLogger(__name__)


class JobCancelledError(Exception):
    """Raised at a stage boundary after the operator asked to stop the job.

    Deliberately not a ``RuntimeError``/``ValueError`` so engine error handling that turns
    those into inspectable failures cannot swallow a cancellation.
    """


class JobError(Exception):
    """An expected, user-presentable job failure (bounded message, no local paths)."""


class QueueFullError(RuntimeError):
    """The bounded queue already holds the maximum number of waiting jobs."""


@dataclass
class JobOutcome:
    """Terminal result of a job's work function."""

    status: Literal["succeeded", "failed", "abstained"]
    result: dict[str, Any] | None = None
    error: str | None = None
    diagnostic: dict[str, Any] | None = None


def _iso(seconds: float | None) -> str | None:
    return None if seconds is None else datetime.fromtimestamp(seconds, UTC).isoformat()


@dataclass
class _Job:
    id: UUID
    kind: str
    key: str
    label: dict[str, Any]
    work: Callable[[JobContext], JobOutcome]
    queued_wall: float
    queued_mono: float
    steps: list[dict[str, Any]] = field(default_factory=list)
    status: str = "queued"
    stage: str = "queued"
    started_wall: float | None = None
    started_mono: float | None = None
    finished_wall: float | None = None
    finished_mono: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    diagnostic: dict[str, Any] | None = None
    progress: dict[str, Any] | None = None
    cancel: Event = field(default_factory=Event)
    cancel_stage: str | None = None
    aborters: list[Callable[[], None]] = field(default_factory=list)
    step_outputs: dict[int, dict[str, Any]] = field(default_factory=dict)
    step_times: dict[int, tuple[float, float | None]] = field(default_factory=dict)


class JobContext:
    """Handle passed to a running job's work function."""

    def __init__(self, manager: JobManager, job: _Job) -> None:
        self._manager = manager
        self._job = job

    @property
    def cancelled(self) -> bool:
        """Whether the operator asked to stop this job."""
        return self._job.cancel.is_set()

    def steps(self) -> list[dict[str, Any]]:
        """Return copies of this job's planned sub-steps."""
        return self._manager._steps(self._job)

    def check(self) -> None:
        """Raise :class:`JobCancelledError` when a stop was requested."""
        if self._job.cancel.is_set():
            raise JobCancelledError

    def stage(self, name: str) -> None:
        """Record the next engine stage; this is a cooperative cancellation boundary."""
        self.check()
        self._manager._set_stage(self._job, name)

    def progress(self, operation: str, completed: int, total: int | None = None) -> None:
        """Record measured local-loading counters and allow cooperative cancellation."""
        self.check()
        self._manager._set_progress(self._job, operation, completed, total)

    def step(self, index: int, **fields: Any) -> None:
        """Update one sub-step (comparison model) and time it on the server clock."""
        self._manager._update_step(self._job, index, fields)

    def step_output(self, index: int, output: dict[str, Any]) -> None:
        """Attach a completed sub-step's result payload (detail view only)."""
        self._manager._step_output(self._job, index, output)

    def on_abort(self, abort: Callable[[], None]) -> Callable[[], None]:
        """Register an in-flight request abort hook; returns its unregister function."""
        return self._manager._on_abort(self._job, abort)


class JobManager:
    """Bounded FIFO queue; one daemon worker executes jobs strictly in submission order."""

    def __init__(
        self,
        *,
        max_queued: int = 8,
        max_retained: int = 32,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
    ) -> None:
        self.max_queued = max_queued
        self.max_retained = max_retained
        self._clock = clock
        self._wall = wall
        self._lock = RLock()
        self._changed = Condition(self._lock)
        self._jobs: dict[UUID, _Job] = {}
        self._worker: Thread | None = None

    # -- public API ----------------------------------------------------------------------
    def submit(
        self,
        kind: str,
        key: str,
        label: dict[str, Any],
        work: Callable[[JobContext], JobOutcome],
        steps: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Queue *work*; an identical queued/running job is returned instead (``False``)."""
        with self._lock:
            for job in self._jobs.values():
                if job.key == key and job.status in {"queued", "running"}:
                    return self._snapshot(job, detail=True), False
            if sum(job.status == "queued" for job in self._jobs.values()) >= self.max_queued:
                raise QueueFullError(f"At most {self.max_queued} jobs can wait in the queue")
            job = _Job(
                id=uuid4(),
                kind=kind,
                key=key,
                label=dict(label),
                work=work,
                queued_wall=self._wall(),
                queued_mono=self._clock(),
                steps=[dict(step) for step in steps or []],
            )
            self._jobs[job.id] = job
            self._event(job, "queued")
            if self._worker is None or not self._worker.is_alive():
                self._worker = Thread(target=self._run_forever, name="thoraxbench-jobs")
                self._worker.daemon = True
                self._worker.start()
            self._changed.notify_all()
            return self._snapshot(job, detail=True), True

    def snapshots(self) -> list[dict[str, Any]]:
        """Summaries (no result payloads), oldest first."""
        with self._lock:
            return [self._snapshot(job, detail=False) for job in self._jobs.values()]

    def get(self, identifier: UUID) -> dict[str, Any] | None:
        """Full snapshot including result payloads, or ``None``."""
        with self._lock:
            job = self._jobs.get(identifier)
            return None if job is None else self._snapshot(job, detail=True)

    def cancel(self, identifier: UUID) -> dict[str, Any] | None:
        """Cancel a queued job now, or ask a running job to stop at its next boundary."""
        aborters: list[Callable[[], None]] = []
        with self._lock:
            job = self._jobs.get(identifier)
            if job is None:
                return None
            if job.status == "queued":
                job.cancel.set()
                job.status = job.stage = "cancelled"
                job.finished_wall = self._wall()
                self._close_steps(job)
                self._trim()
                self._changed.notify_all()
            elif job.status == "running":
                job.cancel.set()
                job.status = "cancelling"
                job.cancel_stage = job.stage
                aborters = list(job.aborters)
                self._changed.notify_all()
            self._event(job, "cancel_requested")
            snapshot = self._snapshot(job, detail=True)
        for abort in aborters:
            self._safe_abort(abort)
        return snapshot

    def clear_finished(self) -> int:
        """Forget every terminal job; returns how many were removed."""
        with self._lock:
            finished = [key for key, job in self._jobs.items() if job.status in TERMINAL]
            for key in finished:
                del self._jobs[key]
            self._changed.notify_all()
            return len(finished)

    def wait(self, identifier: UUID, timeout: float | None = None) -> dict[str, Any] | None:
        """Block until the job is terminal (or *timeout*); returns its full snapshot."""
        deadline = None if timeout is None else self._clock() + timeout
        with self._lock:
            while True:
                job = self._jobs.get(identifier)
                if job is None or job.status in TERMINAL:
                    return None if job is None else self._snapshot(job, detail=True)
                remaining = None if deadline is None else deadline - self._clock()
                if remaining is not None and remaining <= 0:
                    return self._snapshot(job, detail=True)
                self._changed.wait(remaining if remaining is not None else 1.0)

    # -- worker --------------------------------------------------------------------------
    def _next(self) -> _Job:
        with self._lock:
            while True:
                job = next((j for j in self._jobs.values() if j.status == "queued"), None)
                if job is not None:
                    job.status = "running"
                    job.stage = "starting"
                    job.started_wall = self._wall()
                    job.started_mono = self._clock()
                    self._event(job, "started")
                    self._changed.notify_all()
                    return job
                self._changed.wait()

    def _run_forever(self) -> None:
        while True:
            job = self._next()
            self._execute(job)

    def _execute(self, job: _Job) -> None:
        context = JobContext(self, job)
        cancelled = False
        diagnostic: dict[str, Any] | None = None
        try:
            context.check()
            outcome = job.work(context)
            diagnostic = outcome.diagnostic
        except JobCancelledError:
            outcome, cancelled = JobOutcome("failed"), True
        except JobError as exc:
            outcome = JobOutcome("failed", error=str(exc)[:MAX_DETAIL])
            diagnostic = job_diagnostic(exc, job.stage)
        except Exception as exc:
            outcome = JobOutcome("failed", error=f"Job failed unexpectedly ({type(exc).__name__})")
            diagnostic = job_diagnostic(exc, job.stage)
        if outcome.status == "failed" and not cancelled and diagnostic is None:
            diagnostic = job_diagnostic(None, job.stage)
        if diagnostic is not None:
            LOGGER.warning(
                "Job %s diagnostic: trace=%s code=%s stage=%s",
                job.id,
                diagnostic["trace_id"],
                diagnostic["code"],
                diagnostic["stage"],
            )
        with self._lock:
            job.finished_wall = self._wall()
            job.finished_mono = self._clock()
            job.aborters.clear()
            if cancelled:
                job.cancel.set()
                job.status = "cancelled"
            else:
                job.status = outcome.status
                job.result = outcome.result
                job.error = outcome.error
                job.diagnostic = diagnostic
            self._event(job, "finished")
            job.progress = None
            job.stage = "done"
            self._close_steps(job)
            self._trim()
            self._changed.notify_all()

    # -- context helpers -----------------------------------------------------------------
    def _set_stage(self, job: _Job, name: str) -> None:
        with self._lock:
            job.stage = name
            job.progress = None
            self._event(job, "stage")
            self._changed.notify_all()

    def _event(self, job: _Job, event: str) -> None:
        elapsed = (
            None
            if job.started_mono is None
            else (
                (job.finished_mono if job.finished_mono is not None else self._clock())
                - job.started_mono
            )
        )
        job_event(
            event,
            job.id,
            kind=job.kind,
            stage=job.stage,
            status=job.status,
            progress=job.progress,
            elapsed_s=elapsed,
            diagnostic=job.diagnostic,
        )

    def _set_progress(self, job: _Job, operation: str, completed: int, total: int | None) -> None:
        if operation not in OPERATIONS or type(completed) is not int or completed < 0:
            raise ValueError("Invalid progress operation or completed count")
        if total is not None and (type(total) is not int or total < completed):
            raise ValueError("Invalid progress total")
        with self._lock:
            job.progress = {"operation": operation, "completed": completed, "total": total}
            self._event(job, "progress")
            self._changed.notify_all()

    def _steps(self, job: _Job) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(step) for step in job.steps]

    def _update_step(self, job: _Job, index: int, fields: dict[str, Any]) -> None:
        with self._lock:
            step = job.steps[index]
            status = fields.get("status")
            if status == "running":
                job.step_times[index] = (self._clock(), None)
            elif status is not None and status not in STEP_OPEN and index in job.step_times:
                start, _ = job.step_times[index]
                job.step_times[index] = (start, self._clock())
            if "detail" in fields and fields["detail"] is not None:
                fields = fields | {"detail": str(fields["detail"])[:MAX_DETAIL]}
            step.update(fields)
            self._changed.notify_all()

    def _step_output(self, job: _Job, index: int, output: dict[str, Any]) -> None:
        with self._lock:
            job.step_outputs[index] = output

    def _on_abort(self, job: _Job, abort: Callable[[], None]) -> Callable[[], None]:
        with self._lock:
            job.aborters.append(abort)
            already = job.cancel.is_set()

        def unregister() -> None:
            with self._lock:
                if abort in job.aborters:
                    job.aborters.remove(abort)

        if already:
            self._safe_abort(abort)
        return unregister

    @staticmethod
    def _safe_abort(abort: Callable[[], None]) -> None:
        with contextlib.suppress(Exception):  # best effort; the stage check still stops
            abort()

    def _close_steps(self, job: _Job) -> None:
        now = self._clock()
        for index, step in enumerate(job.steps):
            if step.get("status") in STEP_OPEN:
                step["status"] = "cancelled" if job.cancel.is_set() else "error"
                if index in job.step_times and job.step_times[index][1] is None:
                    job.step_times[index] = (job.step_times[index][0], now)

    def _trim(self) -> None:
        finished = [key for key, job in self._jobs.items() if job.status in TERMINAL]
        for key in finished[: max(0, len(finished) - self.max_retained)]:
            del self._jobs[key]

    # -- snapshots -----------------------------------------------------------------------
    def _elapsed(self, start: float | None, end: float | None) -> float | None:
        if start is None:
            return None
        return max(0.0, (end if end is not None else self._clock()) - start)

    def _snapshot(self, job: _Job, *, detail: bool) -> dict[str, Any]:
        queued = [j.id for j in self._jobs.values() if j.status == "queued"]
        steps: list[dict[str, Any]] = []
        for index, step in enumerate(job.steps):
            start, end = job.step_times.get(index, (None, None))
            entry = dict(step) | {"elapsed_s": self._elapsed(start, end)}
            if detail and index in job.step_outputs:
                entry["output"] = job.step_outputs[index]
            steps.append(entry)
        snapshot: dict[str, Any] = {
            "id": str(job.id),
            "kind": job.kind,
            "status": job.status,
            "stage": job.stage,
            **job.label,
            "queued_at": _iso(job.queued_wall),
            "started_at": _iso(job.started_wall),
            "finished_at": _iso(job.finished_wall),
            "elapsed_s": self._elapsed(job.started_mono, job.finished_mono),
            "finished": job.status in TERMINAL,
            "queue_position": queued.index(job.id) + 1 if job.id in queued else None,
            "steps": steps,
            "error": job.error,
            "cancel_requested": job.cancel.is_set(),
            "cancel_stage": job.cancel_stage,
            "result_available": job.result is not None or bool(job.step_outputs),
            "diagnostic": job.diagnostic,
            "progress": dict(job.progress) if job.progress else None,
            "disclaimer": DISCLAIMER,
        }
        if detail:
            snapshot["result"] = job.result
        return snapshot
