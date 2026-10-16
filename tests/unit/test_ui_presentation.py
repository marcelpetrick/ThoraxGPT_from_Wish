# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Educational display codes retain the report's unavailable/absent semantics."""

from unittest.mock import Mock

import pytest

from thoraxbench.api.presentation import finding_presentation
from thoraxbench.schemas import Finding, FindingsReport


@pytest.mark.parametrize(
    ("present", "confidence", "expected"),
    [
        (True, 0.9, "present"),
        (False, 0.9, "not_detected"),
        (None, 0.9, "uncertain"),
        (True, None, "uncertain"),
        (False, 0.1, "present"),
    ],
)
def test_education_is_assigned_only_to_available_positive_predictions(
    present: bool | None, confidence: float | None, expected: str
) -> None:
    finding = Finding(label="pulmonary_nodule", present=present, confidence=confidence, size_mm=12)
    result = Mock(report=FindingsReport(findings=[finding]), raw_error=None)
    data = finding_presentation(result)
    row = data["findings"][0]
    assert row["status"] == expected
    assert row["finding_index"] == 0
    assert (row["severity"] is not None) == (expected == "present")
    assert (row["attention"] is not None) == (expected == "present")
    assert data["educational_only"] is True
    assert data["knowledge_version"]
    if expected == "present":
        assert row["severity"] == "moderate"


@pytest.mark.parametrize(("abstain", "error"), [(True, None), (False, "failed")])
def test_abstained_and_failed_outputs_have_no_severity(abstain: bool, error: str | None) -> None:
    result = Mock(
        report=FindingsReport(
            abstain=abstain,
            findings=[Finding(label="pulmonary_nodule", present=True, confidence=1)],
        ),
        raw_error=error,
    )
    row = finding_presentation(result)["findings"][0]
    assert row["status"] == "uncertain"
    assert row["severity"] is None
    assert row["attention"] is None


def test_unknown_reference_label_cannot_invent_education() -> None:
    result = Mock(
        report=FindingsReport(
            findings=[Finding(label="unknown_label", present=True, confidence=1)]
        ),
        raw_error=None,
    )
    row = finding_presentation(result)["findings"][0]
    assert row["severity"] is None
    assert row["attention"] is None


def test_inadequate_report_cannot_receive_educational_severity() -> None:
    from thoraxbench.schemas import StudyQuality

    result = Mock(
        report=FindingsReport(
            study_quality=StudyQuality(adequate=False),
            findings=[Finding(label="pulmonary_nodule", present=True, confidence=1)],
        ),
        raw_error=None,
    )
    row = finding_presentation(result)["findings"][0]
    assert row["status"] == "uncertain"
    assert row["severity"] is None
    assert row["attention"] is None
