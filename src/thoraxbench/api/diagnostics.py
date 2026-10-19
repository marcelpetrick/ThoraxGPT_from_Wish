# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Traceable job failures without input paths, header values or exception messages."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from thoraxbench import __version__
from thoraxbench.config import REPO_ROOT
from thoraxbench.provenance import git_state
from thoraxbench.splits import SealedAccessError
from thoraxbench.study import StudyLoadError

# Aggregate discovery counters safe to export. ``private_values_raw`` counts vendor-private
# header values kept as raw bytes; it is informational and never a warning or failure.
DISCOVERY_COUNTERS = frozenset(
    {
        "files_scanned",
        "headers_readable",
        "headers_unreadable",
        "non_dicom_files",
        "private_values_raw",
    }
)

RECOVERY: dict[str, str] = {
    "no_eligible_ct": (
        "Choose a DICOM CT study folder with at least 20 axial images; scouts are "
        "excluded. File extensions are not required."
    ),
    "no_dicom_files": (
        "No readable DICOM images were found. Choose the study folder rather than an "
        "archive, empty folder or image export."
    ),
    "sealed_input": (
        "Choose an allowed individual study folder. Protected or non-development "
        "inputs cannot be opened; do not copy files to bypass the guard."
    ),
    "source_changed": (
        "The source changed while loading. Wait until copying or editing finishes, "
        "then reopen the folder."
    ),
    "permission_denied": ("Check read permissions for the folder and its files, then retry."),
    "folder_unavailable": (
        "The folder or one of its files is no longer available. Check its location and reopen it."
    ),
    "dicom_read_error": (
        "The DICOM reader could not decode this input. Check the file format and "
        "transfer syntax with the trace details; do not rename files as a repair."
    ),
    "unexpected_error": (
        "Download the diagnostic JSON and report its trace ID, failure stage and "
        "software version. Input paths and header values are excluded."
    ),
    "unreadable_dicom_headers": (
        "Some files were excluded because their DICOM headers could not be read. "
        "Check the selected series and input QC; readable-header count is not selected-slice count."
    ),
    "job_failed": (
        "Inspect the recorded result and failure stage. Download diagnostic JSON when "
        "reporting the failure."
    ),
}


def cause_chain(error: BaseException | None) -> list[BaseException]:
    """Retain class/stack identity only; never serialize potentially identifying values."""
    chain: list[BaseException] = []
    seen: set[int] = set()
    while error is not None and id(error) not in seen and len(chain) < 8:
        seen.add(id(error))
        chain.append(error)
        error = error.__cause__ or error.__context__
    return chain


def failure_code(error: BaseException | None) -> str:
    """Classify known failures without matching or returning raw exception messages."""
    chain = cause_chain(error)
    for item in chain:
        explicit = getattr(item, "code", None)
        if isinstance(explicit, str) and explicit in RECOVERY:
            return explicit
    for kind, code in (
        (SealedAccessError, "sealed_input"),
        (PermissionError, "permission_denied"),
        (FileNotFoundError, "folder_unavailable"),
    ):
        if any(isinstance(item, kind) for item in chain):
            return code
    for item in chain:
        if isinstance(item, StudyLoadError):
            counts = getattr(item, "discovery", {})
            return "no_dicom_files" if counts.get("headers_readable") == 0 else "no_eligible_ct"
    if any(type(item).__module__.startswith("pydicom") for item in chain):
        return "dicom_read_error"
    return "unexpected_error" if error is not None else "job_failed"


def job_diagnostic(error: BaseException | None, stage: str) -> dict[str, Any]:
    """Bounded technical frames; no locals, source text, raw error strings or patient data."""
    chain = cause_chain(error)
    code = failure_code(error)
    frames: list[dict[str, Any]] = []
    for item in chain:
        trace = item.__traceback__
        while trace is not None and len(frames) < 24:
            frame = trace.tb_frame
            frames.append(
                {
                    "file": Path(frame.f_code.co_filename).name,
                    "function": frame.f_code.co_name,
                    "line": trace.tb_lineno,
                }
            )
            trace = trace.tb_next
    commit, dirty = git_state(REPO_ROOT)
    diagnostic: dict[str, Any] = {
        "trace_id": str(uuid4()),
        "severity": "error",
        "code": code,
        "stage": stage,
        "exception_type": type(chain[-1]).__name__ if chain else "JobFailure",
        "causes": [type(item).__name__ for item in chain],
        "frames": frames,
        "hint": RECOVERY[code],
        "created_at": datetime.now(UTC).isoformat(),
        "software_version": __version__,
        "git_commit": commit,
        "git_dirty": dirty,
    }
    for item in reversed(chain):
        counts = getattr(item, "discovery", None)
        if isinstance(counts, dict):
            diagnostic["discovery"] = {
                key: value
                for key, value in counts.items()
                if key in DISCOVERY_COUNTERS and type(value) is int and value >= 0
            }
            break
    for item in reversed(chain):
        error_types = getattr(item, "header_error_types", None)
        if isinstance(error_types, dict):
            diagnostic["header_error_types"] = safe_header_error_types(error_types)
            break
    return diagnostic


def header_warning_diagnostic(
    discovery: dict[str, Any], error_types: dict[str, Any]
) -> dict[str, Any]:
    """Record aggregate header warnings, without input filenames or header values."""
    diagnostic = job_diagnostic(None, "folder_check")
    diagnostic.update(
        code="unreadable_dicom_headers",
        severity="warning",
        exception_type="HeaderReadWarning",
        hint=RECOVERY["unreadable_dicom_headers"],
        discovery={
            key: value
            for key, value in discovery.items()
            if key in DISCOVERY_COUNTERS and type(value) is int and value >= 0
        },
        header_error_types=safe_header_error_types(error_types),
    )
    return diagnostic


def safe_header_error_types(error_types: dict[str, Any]) -> dict[str, int]:
    """Allow only fixed aggregate parser categories, never source-provided names."""
    allowed = {
        "InvalidDicomError",
        "BytesLengthException",
        "OSError",
        "EOFError",
        "ValueError",
        "TypeError",
        "LookupError",
        "NotImplementedError",
        "OverflowError",
        "error",
        "HeaderReadError",
    }
    return {
        key: value
        for key, value in error_types.items()
        if key in allowed and type(value) is int and value > 0
    }
