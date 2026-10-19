# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Traceability retains actionable stages/classes while excluding sensitive values."""

import json
from uuid import UUID

import pytest
from pydicom.errors import BytesLengthException

from thoraxbench.api.diagnostics import (
    cause_chain,
    failure_code,
    header_warning_diagnostic,
    job_diagnostic,
)
from thoraxbench.api.jobs import JobContext, JobError, JobManager, JobOutcome
from thoraxbench.api.local_studies import SourceChangedError
from thoraxbench.splits import SealedAccessError
from thoraxbench.study import StudyLoadError


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (PermissionError("private/path"), "permission_denied"),
        (FileNotFoundError("private/path"), "folder_unavailable"),
        (SealedAccessError("patient-secret"), "sealed_input"),
        (SourceChangedError("patient-secret"), "source_changed"),
        (BytesLengthException("patient-secret"), "dicom_read_error"),
        (StudyLoadError("private/path"), "no_eligible_ct"),
        (RuntimeError("patient-secret"), "unexpected_error"),
        (None, "job_failed"),
    ],
)
def test_failure_codes_do_not_depend_on_sensitive_messages(
    error: BaseException | None, code: str
) -> None:
    assert failure_code(error) == code
    data = job_diagnostic(error, "folder_check")
    assert data["stage"] == "folder_check"
    assert data["code"] == code
    UUID(data["trace_id"])
    assert "patient-secret" not in json.dumps(data)
    assert "private/path" not in json.dumps(data)


def test_diagnostic_follows_causes_and_retains_failure_stage_and_safe_frames(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(context: JobContext) -> JobOutcome:
        context.stage("folder_check")
        try:
            raise BytesLengthException("PRIVATE-PATIENT /secret/folder")
        except BytesLengthException as error:
            raise JobError("The DICOM input could not be read") from error

    manager = JobManager()
    queued, _ = manager.submit("study-import", "synthetic", {}, broken)
    done = manager.wait(UUID(queued["id"]), timeout=5)
    assert done is not None
    assert done["status"] == "failed"
    assert done["stage"] == "done"
    diagnostic = done["diagnostic"]
    assert diagnostic["stage"] == "folder_check"
    assert diagnostic["exception_type"] == "BytesLengthException"
    assert diagnostic["causes"] == ["JobError", "BytesLengthException"]
    assert diagnostic["frames"]
    assert diagnostic["trace_id"] in caplog.text
    assert "PRIVATE-PATIENT" not in caplog.text
    assert "/secret/folder" not in caplog.text
    assert all("/" not in item["file"] for item in diagnostic["frames"])
    assert "PRIVATE-PATIENT" not in json.dumps(done)
    assert "/secret/folder" not in json.dumps(done)


def test_explicit_failed_outcome_gets_trace_without_an_exception() -> None:
    manager = JobManager()
    queued, _ = manager.submit(
        "analysis", "synthetic", {}, lambda _: JobOutcome("failed", error="No model output")
    )
    done = manager.wait(UUID(queued["id"]), timeout=5)
    assert done is not None
    assert done["diagnostic"]["code"] == "job_failed"
    assert done["diagnostic"]["frames"] == []


def test_cyclic_cause_and_untrusted_discovery_values_are_bounded() -> None:
    error = StudyLoadError(
        "private/path",
        {"discovery": {"headers_readable": 0, "patient": "PRIVATE", "files_scanned": -1}},
    )
    error.__cause__ = error
    assert len(cause_chain(error)) == 1
    result = job_diagnostic(error, "study")
    assert result["code"] == "no_dicom_files"
    assert result["discovery"] == {"headers_readable": 0}
    assert "PRIVATE" not in json.dumps(result)


def test_successful_warning_retains_only_safe_counts_and_survives_job_snapshot() -> None:
    diagnostic = header_warning_diagnostic(
        {"files_scanned": 42, "headers_unreadable": 2, "patient": "SECRET", "bad": -1},
        {"BytesLengthException": 2, "SECRET-PATH": 3, "ValueError": True},
    )
    assert diagnostic["severity"] == "warning"
    assert diagnostic["code"] == "unreadable_dicom_headers"
    assert diagnostic["discovery"] == {"files_scanned": 42, "headers_unreadable": 2}
    assert diagnostic["header_error_types"] == {"BytesLengthException": 2}
    assert "SECRET" not in json.dumps(diagnostic)
    manager = JobManager()
    queued, _ = manager.submit(
        "study-import",
        "synthetic",
        {},
        lambda _: JobOutcome("succeeded", result={"study": {}}, diagnostic=diagnostic),
    )
    done = manager.wait(UUID(queued["id"]), timeout=5)
    assert done is not None
    assert done["status"] == "succeeded"
    assert done["diagnostic"]["trace_id"] == diagnostic["trace_id"]
