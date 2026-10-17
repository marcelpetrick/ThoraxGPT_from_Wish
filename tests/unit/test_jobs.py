# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Job queue: ordering, cancellation, duplicates, bounds and preserved outcomes."""

from __future__ import annotations

import threading
from collections.abc import Callable
from uuid import UUID, uuid4

import pytest

from thoraxbench.api.jobs import (
    JobCancelledError,
    JobContext,
    JobError,
    JobManager,
    JobOutcome,
    QueueFullError,
)

TIMEOUT = 5.0


def _uid(snapshot: dict[str, object]) -> UUID:
    return UUID(str(snapshot["id"]))


class Gate:
    """A work function that blocks at a stage until released."""

    def __init__(self, outcome: JobOutcome | None = None) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.outcome = outcome or JobOutcome("succeeded", result={"ok": True})
        self.stages: list[str] = []

    def __call__(self, context: JobContext) -> JobOutcome:
        context.stage("preprocess")
        self.stages.append("preprocess")
        self.started.set()
        assert self.release.wait(TIMEOUT)
        context.stage("parse")
        self.stages.append("parse")
        return self.outcome


def _done(outcome: JobOutcome) -> Callable[[JobContext], JobOutcome]:
    return lambda _context: outcome


def test_jobs_run_sequentially_in_submission_order() -> None:
    manager = JobManager()
    order: list[str] = []
    first = Gate()

    def record(name: str) -> Callable[[JobContext], JobOutcome]:
        def work(_context: JobContext) -> JobOutcome:
            order.append(name)
            return JobOutcome("succeeded")

        return work

    one, created = manager.submit("analysis", "a", {"dataset": "demo"}, first)
    assert created
    assert one["status"] == "queued"
    assert first.started.wait(TIMEOUT)
    two, _ = manager.submit("analysis", "b", {}, record("b"))
    three, _ = manager.submit("analysis", "c", {}, record("c"))
    listed = {job["id"]: job for job in manager.snapshots()}
    assert listed[one["id"]]["status"] == "running"
    assert listed[one["id"]]["stage"] == "preprocess"
    assert listed[two["id"]]["queue_position"] == 1
    assert listed[three["id"]]["queue_position"] == 2
    assert "result" not in listed[one["id"]]
    first.release.set()
    assert manager.wait(_uid(three), TIMEOUT)["status"] == "succeeded"  # type: ignore[index]
    assert order == ["b", "c"]
    finished = manager.get(_uid(one))
    assert finished is not None
    assert finished["result"] == {"ok": True}
    assert finished["elapsed_s"] is not None
    assert finished["elapsed_s"] >= 0
    assert finished["started_at"]
    assert finished["finished_at"]
    assert finished["finished"]


def test_cancel_queued_is_immediate_and_running_stops_at_stage_boundary() -> None:
    manager = JobManager()
    gate = Gate()
    aborted = threading.Event()
    running, _ = manager.submit("analysis", "run", {}, gate)
    assert gate.started.wait(TIMEOUT)
    queued, _ = manager.submit("analysis", "queued", {}, _done(JobOutcome("succeeded")))
    cancelled = manager.cancel(_uid(queued))
    assert cancelled is not None
    assert cancelled["status"] == "cancelled"
    assert cancelled["elapsed_s"] is None
    assert cancelled["started_at"] is None

    # An abort hook registered by the work receives the stop request at once.
    def hook_work(context: JobContext) -> JobOutcome:
        context.on_abort(aborted.set)
        context.stage("inference")
        assert aborted.wait(TIMEOUT)
        context.stage("parse")
        return JobOutcome("succeeded")

    gate.release.set()
    manager.wait(_uid(running), TIMEOUT)
    hooked, _ = manager.submit("analysis", "hook", {}, hook_work)
    for _ in range(100):
        snap = manager.get(_uid(hooked))
        if snap and snap["stage"] == "inference":
            break
        threading.Event().wait(0.02)
    stopping = manager.cancel(_uid(hooked))
    assert stopping is not None
    assert stopping["status"] == "cancelling"
    assert stopping["cancel_stage"] == "inference"
    final = manager.wait(_uid(hooked), TIMEOUT)
    assert final is not None
    assert final["status"] == "cancelled"
    assert final["result"] is None
    assert aborted.is_set()
    assert manager.cancel(uuid4()) is None
    # Cancelling a finished job changes nothing.
    again = manager.cancel(_uid(hooked))
    assert again is not None
    assert again["status"] == "cancelled"


def test_cancel_before_start_never_runs_work_and_late_abort_hook_fires() -> None:
    manager = JobManager()
    gate = Gate()
    manager.submit("analysis", "first", {}, gate)
    assert gate.started.wait(TIMEOUT)
    ran: list[bool] = []

    def never(_context: JobContext) -> JobOutcome:
        ran.append(True)
        return JobOutcome("succeeded")

    queued, _ = manager.submit("analysis", "second", {}, never)
    manager.cancel(_uid(queued))
    gate.release.set()
    fired = threading.Event()

    def late(context: JobContext) -> JobOutcome:
        context._job.cancel.set()
        context.on_abort(fired.set)()
        context.check()
        return JobOutcome("succeeded")

    job, _ = manager.submit("analysis", "late", {}, late)
    assert manager.wait(_uid(job), TIMEOUT)["status"] == "cancelled"  # type: ignore[index]
    assert fired.is_set()
    assert not ran


def test_duplicate_submission_returns_existing_job() -> None:
    manager = JobManager()
    gate = Gate()
    first, created = manager.submit("analysis", "same", {}, gate)
    again, duplicate = manager.submit("analysis", "same", {}, gate)
    assert created
    assert not duplicate
    assert again["id"] == first["id"]
    gate.release.set()
    manager.wait(_uid(first), TIMEOUT)
    later, created_later = manager.submit("analysis", "same", {}, _done(JobOutcome("succeeded")))
    assert created_later
    assert later["id"] != first["id"]


def test_queue_and_retention_limits() -> None:
    manager = JobManager(max_queued=2, max_retained=2)
    gate = Gate()
    manager.submit("analysis", "busy", {}, gate)
    assert gate.started.wait(TIMEOUT)
    manager.submit("analysis", "q1", {}, _done(JobOutcome("succeeded")))
    last, _ = manager.submit("analysis", "q2", {}, _done(JobOutcome("succeeded")))
    with pytest.raises(QueueFullError):
        manager.submit("analysis", "q3", {}, _done(JobOutcome("succeeded")))
    gate.release.set()
    manager.wait(_uid(last), TIMEOUT)
    assert len(manager.snapshots()) == 2
    assert manager.clear_finished() == 2
    assert manager.snapshots() == []


def test_failures_abstentions_and_partial_steps_are_preserved() -> None:
    manager = JobManager()

    def broken(_context: JobContext) -> JobOutcome:
        raise KeyError("/private/path")

    def expected(_context: JobContext) -> JobOutcome:
        raise JobError("Study is unavailable for development")

    def comparison(context: JobContext) -> JobOutcome:
        assert [step["model_id"] for step in context.steps()] == ["a", "b", "c", "d"]
        context.step(0, status="running")
        context.step_output(0, {"id": "r0"})
        context.step(0, status="completed", detail="x" * 900)
        context.step(1, status="running")
        context.step(1, status="abstained")
        context.step(2, status="running")
        context.step(2, status="error", detail="offline")
        context.step(3, status="running")
        raise JobCancelledError

    failing, _ = manager.submit("analysis", "f", {}, broken)
    error, _ = manager.submit("analysis", "e", {}, expected)
    abstained, _ = manager.submit("analysis", "x", {}, _done(JobOutcome("abstained", result={})))
    steps = [{"model_id": m, "status": "waiting", "detail": ""} for m in "abcd"]
    batch, _ = manager.submit("comparison", "c", {"models": list("abcd")}, comparison, steps)
    final = manager.wait(_uid(batch), TIMEOUT)
    assert final is not None
    first = manager.get(_uid(failing))
    assert first is not None
    assert first["status"] == "failed"
    assert first["error"] == "Job failed unexpectedly (KeyError)"
    assert manager.get(_uid(error))["error"] == "Study is unavailable for development"  # type: ignore[index]
    assert manager.get(_uid(abstained))["status"] == "abstained"  # type: ignore[index]
    assert final["status"] == "cancelled"
    assert final["models"] == list("abcd")
    assert [step["status"] for step in final["steps"]] == [
        "completed",
        "abstained",
        "error",
        "cancelled",
    ]
    assert len(final["steps"][0]["detail"]) == 500
    assert final["steps"][0]["output"] == {"id": "r0"}
    assert all(step["elapsed_s"] is not None for step in final["steps"])
    assert final["result_available"]
    assert (
        "output"
        not in next(job for job in manager.snapshots() if job["id"] == batch["id"])["steps"][0]
    )


def test_elapsed_uses_injected_monotonic_clock_and_open_steps_fail_without_cancel() -> None:
    now = [100.0]
    manager = JobManager(clock=lambda: now[0], wall=lambda: 1_700_000_000.0)
    gate = threading.Event()
    seen = threading.Event()

    def work(context: JobContext) -> JobOutcome:
        context.step(0, status="running")
        seen.set()
        assert gate.wait(TIMEOUT)
        return JobOutcome("failed", error="boom")

    job, _ = manager.submit("comparison", "k", {}, work, [{"model_id": "a", "status": "waiting"}])
    assert seen.wait(TIMEOUT)
    now[0] = 165.5
    running = manager.get(_uid(job))
    assert running is not None
    assert running["elapsed_s"] == pytest.approx(65.5)
    assert running["steps"][0]["elapsed_s"] == pytest.approx(65.5)
    gate.set()
    final = manager.wait(_uid(job), TIMEOUT)
    assert final is not None
    assert final["steps"][0]["status"] == "error"
    now[0] = 500.0
    frozen = manager.get(_uid(job))
    assert frozen is not None
    assert frozen["elapsed_s"] == pytest.approx(65.5)
    assert frozen["queued_at"].startswith("2023-11-14")


def test_wait_times_out_and_unknown_job() -> None:
    manager = JobManager()
    gate = Gate()
    job, _ = manager.submit("analysis", "w", {}, gate)
    pending = manager.wait(_uid(job), 0.05)
    assert pending is not None
    assert pending["status"] in {"queued", "running"}
    assert manager.wait(uuid4(), 0.01) is None
    assert manager.get(uuid4()) is None
    gate.release.set()
    manager.wait(_uid(job), TIMEOUT)


def test_failing_abort_hook_does_not_break_cancellation() -> None:
    manager = JobManager()
    started = threading.Event()

    def work(context: JobContext) -> JobOutcome:
        def broken() -> None:
            raise OSError("socket gone")

        unregister = context.on_abort(broken)
        started.set()
        while not context.cancelled:
            threading.Event().wait(0.01)
        unregister()
        unregister()
        context.stage("parse")
        return JobOutcome("succeeded")

    job, _ = manager.submit("analysis", "abort", {}, work)
    assert started.wait(TIMEOUT)
    assert manager.cancel(_uid(job))["status"] == "cancelling"  # type: ignore[index]
    assert manager.wait(_uid(job), TIMEOUT)["status"] == "cancelled"  # type: ignore[index]
