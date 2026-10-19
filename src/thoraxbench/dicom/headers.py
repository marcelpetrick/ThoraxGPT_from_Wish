# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Strict header reads, including deferred DICOM value conversion failures."""

import struct
from pathlib import Path

import pydicom
from pydicom.dataset import Dataset
from pydicom.errors import BytesLengthException, InvalidDicomError

HEADER_ERRORS = (
    InvalidDicomError,
    BytesLengthException,
    OSError,
    EOFError,
    ValueError,
    TypeError,
    LookupError,
    NotImplementedError,
    OverflowError,
    struct.error,
)


def record_header_error(error: BaseException, issue_types: dict[str, int] | None) -> None:
    """Count only fixed reader exception categories; never include error text."""
    if issue_types is not None:
        category = next(kind.__name__ for kind in HEADER_ERRORS if isinstance(error, kind))
        issue_types[category] = issue_types.get(category, 0) + 1


def read_header(
    path: Path, stats: dict[str, int] | None = None, issue_types: dict[str, int] | None = None
) -> Dataset | None:
    """Return a fully converted header or None; never force-read or load pixel bytes."""
    try:
        header = pydicom.dcmread(path, stop_before_pixels=True)
        # dcmread stores raw elements. Iteration converts nested values now, inside
        # the failure boundary, instead of raising later during ds.get/iterall.
        for _element in header.iterall():
            pass
        return header
    except InvalidDicomError:
        if stats is not None:
            stats["non_dicom_files"] = stats.get("non_dicom_files", 0) + 1
        return None
    except HEADER_ERRORS as error:
        record_header_error(error, issue_types)
        if stats is not None:
            stats["headers_unreadable"] = stats.get("headers_unreadable", 0) + 1
        return None
