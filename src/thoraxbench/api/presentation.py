# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Educational UI context from the same reference rules used by research reports."""

from __future__ import annotations

from typing import Any

from thoraxbench.analysis import AnalysisResult
from thoraxbench.ontology.clinical import load_clinical_kb
from thoraxbench.reports.study_report import severity_of, status_of


def finding_presentation(result: AnalysisResult) -> dict[str, Any]:
    """Return display codes, never advice or severity for unavailable/absent findings.

    The browser translates these codes. Model observations and generated reports remain
    unchanged. This educational reference cannot establish whether review or care is needed.
    """
    kb = load_clinical_kb()
    usable = (
        result.report.study_quality.adequate
        and not result.report.abstain
        and result.raw_error is None
    )
    findings: list[dict[str, str | int | None]] = []
    for index, finding in enumerate(result.report.findings):
        status = status_of(finding, 0.5) if usable else "uncertain"
        entry = kb.get(finding.label)
        severity = attention = None
        if usable and status == "present" and entry is not None:
            severity = severity_of(entry, finding)[0].name.lower()
            attention = entry.urgency.value
        findings.append(
            {
                "finding_index": index,
                "label": finding.label,
                "status": status.replace(" ", "_"),
                "severity": severity,
                "attention": attention,
            }
        )
    return {"findings": findings, "knowledge_version": kb.version, "educational_only": True}
