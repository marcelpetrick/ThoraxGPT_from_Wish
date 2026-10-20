# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Report decision boundaries and research report content."""

import pytest

from thoraxbench.analysis import DISCLAIMER, AnalysisResult
from thoraxbench.ontology.clinical import Severity, load_clinical_kb
from thoraxbench.perf import PerfRecord
from thoraxbench.provenance import RunProvenance
from thoraxbench.reports.outcome import SHORT_DISCLAIMER
from thoraxbench.reports.study_report import (
    probability_of,
    render_study_report,
    severity_of,
    status_of,
)
from thoraxbench.schemas import AnalysisRequest, Finding, FindingsReport, ReferenceLabels
from thoraxbench.schemas.reference import LesionAnnotation


@pytest.fixture
def result() -> AnalysisResult:
    return AnalysisResult(
        dataset="synthetic",
        case_id="test-case",
        patient_id="test-patient",
        series_uid="1.2.3",
        model_id="heuristic-hu",
        request=AnalysisRequest(),
        report=FindingsReport(),
        raw_text="{}",
        perf=PerfRecord(),
        provenance=RunProvenance(git_commit="0123456789abcdef"),
    )


def test_heuristic_evidence_names_source_slices(result: AnalysisResult) -> None:
    result.report.findings = [
        Finding(label="pulmonary_nodule", source="heuristic", evidence_images=[22])
    ]
    text = render_study_report(result)
    assert "source slice indices (zero-based) 22" in text
    assert "images 22" not in text


@pytest.mark.parametrize(
    ("present", "confidence", "probability", "status"),
    [
        (True, None, None, "uncertain"),
        (False, None, None, "uncertain"),
        (True, 0.5, None, "uncertain"),
        (False, 0.8, 0.2, "not detected"),
        (None, 0.9, None, "uncertain"),
    ],
)
def test_probability_and_threshold(
    present: bool | None,
    confidence: float | None,
    probability: float | None,
    status: str,
) -> None:
    finding = Finding(label="pulmonary_nodule", present=present, confidence=confidence)
    if probability is None:
        assert probability_of(finding) is None
    else:
        assert probability_of(finding) == pytest.approx(probability)
    assert status_of(finding, 0.5) == status


@pytest.mark.parametrize(
    ("label", "size", "severity"),
    [
        ("pulmonary_nodule", None, Severity.LOW),
        ("pulmonary_nodule", 5.9, Severity.LOW),
        ("pulmonary_nodule", 6.0, Severity.LOW),
        ("pulmonary_nodule", 8.0, Severity.LOW),
        ("pulmonary_nodule", 8.1, Severity.MODERATE),
        ("pulmonary_mass", 30.0, Severity.HIGH),
    ],
)
def test_size_severity_boundaries(label: str, size: float | None, severity: Severity) -> None:
    entry = load_clinical_kb().get(label)
    assert entry is not None
    assert severity_of(entry, Finding(label=label, size_mm=size))[0] == severity


def test_empty_and_failed_report(result: AnalysisResult) -> None:
    text = render_study_report(result)
    # One short disclaimer line; the full text lives once in docs/DISCLAIMER.md.
    assert DISCLAIMER not in text
    assert text.count(SHORT_DISCLAIMER["en"]) == 1
    assert "## Verdict\n\nNothing was flagged in the checked area." in text
    assert result.series_uid not in text
    assert f"patient `{result.patient_id}`" not in text
    assert "No abnormality was reported above the decision threshold." in text
    assert "## Deterministic measurements\n\nnone" in text
    result.report.abstain = True
    result.raw_error = "local runtime unavailable"
    result.report.parse_warnings = ["failed to parse"]
    text = render_study_report(result)
    assert "Model image assessment: unavailable" in text
    assert "## Abstention" in text
    assert "local runtime unavailable" in text
    assert "failed to parse" in text


def test_report_findings_guideline_thresholds_and_reference(result: AnalysisResult) -> None:
    result.report = FindingsReport(
        findings=[
            Finding(
                label="pulmonary_nodule",
                size_mm=9.0,
                confidence=0.9,
                laterality="left",
                description="dense | rounded\nlesion",
                evidence_images=list(range(12)),
            ),
            Finding(label="emphysema", confidence=0.6),
            Finding(label="pleural_effusion", present=None),
            Finding(label="unknown_label", confidence=1.0),
        ],
        negative_findings=["emphysema", "pneumothorax"],
        impression=["test | impression\ncontinued"],
        urgent_flags=["review | test"],
    )
    result.context = "Synthetic HU cues"
    reference = ReferenceLabels(
        dataset="synthetic",
        patient_id="test-patient",
        study_uid="1.2",
        labels={
            "pulmonary_nodule": True,
            "emphysema": False,
            "pleural_effusion": True,
            "pneumothorax": False,
            "pulmonary_mass": True,
            "consolidation": None,
        },
        lesions=[LesionAnnotation(center_zyx=(1, 2, 3), diameter_mm=9, readers=3)],
    )
    text = render_study_report(result, reference=reference, thresholds={"emphysema": 0.8})
    assert "| 0.90 | moderate |" in text
    assert "| uncertain | - |" in text
    assert "dense / rounded lesion" in text
    assert "side: left" in text
    assert "images 0, 1, 2, 3, 4, 5, 6, 7" in text
    assert "Fleischner" in text
    assert "**What it means:**" in text
    assert "**General treatment context (educational):**" in text
    assert "**How common:**" in text
    assert "## Not detected" in text
    assert "unknown_label" not in text
    assert "test / impression continued" in text
    assert "review / test" in text
    assert "Synthetic HU cues" in text
    assert "| pulmonary_nodule | present | 0.90 | true positive |" in text
    assert "| emphysema | absent | 0.60 | true negative |" in text
    assert "| pneumothorax | absent | 0.00 | true negative |" in text
    assert "| pulmonary_mass | present | - | unscored (unavailable or uncertain) |" in text
    assert "| consolidation |" not in text
    assert "9 mm (3 reader(s))" in text


@pytest.mark.parametrize("failed", ["abstain", "runtime"])
def test_abstention_suppresses_predictions_and_reference_scores(
    result: AnalysisResult,
    failed: str,
) -> None:
    result.report = FindingsReport(
        findings=[Finding(label="pulmonary_nodule", size_mm=9, confidence=0.9)],
        negative_findings=["pneumothorax"],
        impression=["model impression"],
        urgent_flags=["model urgent flag"],
        abstain=failed == "abstain",
    )
    result.raw_error = "local runtime unavailable" if failed == "runtime" else None
    reference = ReferenceLabels(
        dataset="synthetic",
        patient_id="test-patient",
        study_uid="1.2",
        labels={"pulmonary_nodule": True},
    )
    text = render_study_report(result, reference=reference)
    assert "No usable prediction is available" in text
    assert "No abnormality was reported" not in text
    assert "## Not detected" not in text
    assert "model impression" not in text
    assert "model urgent flag" not in text
    assert "**What the model saw:**" not in text
    assert "unscored (unavailable or uncertain)" in text
    assert "true positive" not in text
