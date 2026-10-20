# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Bounded structured job logs: no labels, input paths, header values or error text."""

import json
import logging
import os
from datetime import UTC, datetime
from io import TextIOWrapper
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from uuid import UUID

from thoraxbench import __version__
from thoraxbench.config import REPO_ROOT
from thoraxbench.provenance import git_state

LOGGER = logging.getLogger("thoraxbench.job_events")
OPERATIONS = frozenset(
    {
        "path_check",
        "header_check",
        "discovery",
        "pixel_decode",
        "input_qc",
        "source_recheck",
        "review_images",
    }
)


class PrivateRotatingHandler(RotatingFileHandler):
    """Keep newly created and rotated logs readable only by their owner."""

    def _open(self) -> TextIOWrapper[Any]:
        descriptor = os.open(
            self.baseFilename, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600
        )
        os.fchmod(descriptor, 0o600)
        return os.fdopen(descriptor, "a", encoding="utf-8")


class EventFormatter(logging.Formatter):
    """Format explicit event dictionaries only, never arbitrary logging messages."""

    def __init__(self) -> None:
        super().__init__()
        self.commit, self.dirty = git_state(REPO_ROOT)

    def format(self, record: logging.LogRecord) -> str:
        """Serialize the safe event without traceback or exception-message interpolation."""
        event = getattr(record, "job_event", {})
        return json.dumps(
            {
                "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "software_version": __version__,
                "git_commit": self.commit,
                "git_dirty": self.dirty,
                **event,
            },
            allow_nan=False,
        )


def configure_job_logging(directory: Path) -> Path:
    """Write up to four 2 MiB files and matching JSON lines to stderr/journald."""
    if directory.is_symlink():
        raise ValueError("Job log directory must not be a symlink")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    target = directory / "jobs.jsonl"
    if target.is_symlink():
        raise ValueError("Job log file must not be a symlink")
    handler = PrivateRotatingHandler(
        target, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    target.chmod(0o600)
    formatter = EventFormatter()
    handler.setFormatter(formatter)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    for old in LOGGER.handlers[:]:
        LOGGER.removeHandler(old)
        old.close()
    LOGGER.addHandler(handler)
    LOGGER.addHandler(console)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
    return target


def job_event(
    event: str,
    identifier: UUID,
    *,
    kind: str,
    stage: str,
    status: str,
    progress: dict[str, Any] | None = None,
    elapsed_s: float | None = None,
    diagnostic: dict[str, Any] | None = None,
) -> None:
    """Emit a fixed field set; never serialize work labels, results or raw exceptions."""
    payload: dict[str, Any] = {
        "event": event,
        "job_id": str(identifier),
        "kind": kind,
        "stage": stage,
        "status": status,
    }
    if progress is not None:
        payload["progress"] = dict(progress)
    if elapsed_s is not None:
        payload["elapsed_s"] = elapsed_s
    if diagnostic is not None:
        payload["trace_id"] = diagnostic["trace_id"]
        payload["code"] = diagnostic["code"]
        payload["severity"] = diagnostic["severity"]
        payload["exception_type"] = diagnostic.get("exception_type")
        payload["causes"] = diagnostic.get("causes", [])
        payload["frames"] = diagnostic.get("frames", [])
        payload["discovery"] = diagnostic.get("discovery", {})
        payload["header_error_types"] = diagnostic.get("header_error_types", {})
    LOGGER.info("job event", extra={"job_event": payload})
