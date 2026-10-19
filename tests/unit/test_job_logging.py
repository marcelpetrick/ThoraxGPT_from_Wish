# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Durable job events retain safe counts/traces without labels or medical values."""

import json
import logging
from pathlib import Path
from threading import Event
from uuid import UUID

import pytest

from thoraxbench.api.job_logging import LOGGER, configure_job_logging
from thoraxbench.api.jobs import JobContext, JobManager, JobOutcome


@pytest.fixture
def log_path(tmp_path: Path):
    path = configure_job_logging(tmp_path / "logs")
    try:
        yield path
    finally:
        for handler in LOGGER.handlers[:]:
            LOGGER.removeHandler(handler)
            handler.close()
        LOGGER.propagate = True
        LOGGER.setLevel(logging.NOTSET)


def test_actual_job_progress_and_diagnostics_persist_without_private_values(
    log_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manager = JobManager()
    entered, finish = Event(), Event()

    def work(context: JobContext) -> JobOutcome:
        context.stage("study")
        context.progress("pixel_decode", 25, 80)
        entered.set()
        assert finish.wait(5)
        raise ValueError("PRIVATE-PATIENT /secret/source")

    queued, _ = manager.submit("study-import", "SECRET-KEY", {"case_id": "PRIVATE-ID"}, work)
    assert entered.wait(5)
    snapshot = manager.get(UUID(queued["id"]))
    assert snapshot is not None
    assert snapshot["progress"] == {"operation": "pixel_decode", "completed": 25, "total": 80}
    snapshot["progress"]["completed"] = 999
    assert manager.get(UUID(queued["id"]))["progress"]["completed"] == 25
    finish.set()
    done = manager.wait(UUID(queued["id"]), timeout=5)
    assert done is not None
    assert done["status"] == "failed"
    assert done["progress"] is None
    lines = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert [line["event"] for line in lines] == [
        "queued",
        "started",
        "stage",
        "progress",
        "finished",
    ]
    assert lines[-1]["trace_id"] == done["diagnostic"]["trace_id"]
    assert lines[3]["progress"]["completed"] == 25
    assert lines[-1]["stage"] == "study"
    assert lines[-1]["software_version"]
    captured = log_path.read_text() + capsys.readouterr().err
    for value in ("PRIVATE", "SECRET", "/secret/source"):
        assert value not in captured
    assert log_path.stat().st_mode & 0o777 == 0o600
    assert log_path.parent.stat().st_mode & 0o777 == 0o700


def test_rotation_and_reconfiguration_keep_files_private(log_path: Path) -> None:
    first = LOGGER.handlers[0]
    first.maxBytes = 1
    for _ in range(5):
        LOGGER.info("safe", extra={"job_event": {"event": "test"}})
    files = list(log_path.parent.iterdir())
    assert len(files) == 4
    assert all(file.stat().st_mode & 0o777 == 0o600 for file in files)
    configure_job_logging(log_path.parent)
    assert len(LOGGER.handlers) == 2


@pytest.mark.parametrize(
    ("operation", "completed", "total"),
    [
        ("PRIVATE-PATH", 1, 2),
        ("header_check", -1, 1),
        ("header_check", True, 2),
        ("header_check", 3, 2),
        ("header_check", 0, True),
    ],
)
def test_invalid_progress_fails_without_unsafe_values(
    operation: str, completed: int, total: int
) -> None:
    manager = JobManager()

    def work(context: JobContext) -> JobOutcome:
        context.progress(operation, completed, total)
        return JobOutcome("succeeded")

    queued, _ = manager.submit("study-import", "safe", {}, work)
    done = manager.wait(UUID(queued["id"]), timeout=5)
    assert done is not None
    assert done["status"] == "failed"
    assert "PRIVATE-PATH" not in json.dumps(done)


def test_log_destination_symlinks_are_refused(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        configure_job_logging(alias)
    (target / "jobs.jsonl").symlink_to(tmp_path / "untouched")
    with pytest.raises(ValueError, match="symlink"):
        configure_job_logging(target)
    assert not (tmp_path / "untouched").exists()
