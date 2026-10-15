# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""English Markdown report for one analysed study.

For every finding the report gives the medical term, a plain-language explanation, a severity
rating, whether it typically needs treatment, how common it is, and guideline-based follow-up
(Fleischner 2017 for nodules is computed in code from the structured size, never by the model).
Knowledge comes from the cited knowledge base (``ontology/clinical_kb.yaml``). The report is
research output and says so at the top and bottom.

Decision rule: a label is reported as *present* when its probability is >= the threshold
(uncalibrated default ``PRESENT_THRESHOLD`` = 0.5; calibrated per-label thresholds from the
benchmark can be passed in), *uncertain* when the model said so, otherwise *not detected*.
"""

from __future__ import annotations

from thoraxbench.analysis import AnalysisResult
from thoraxbench.ontology import load_ontology
from thoraxbench.ontology.clinical import ClinicalEntry, Severity, load_clinical_kb
from thoraxbench.ontology.guidelines import fleischner, size_bin
from thoraxbench.schemas import Finding, ReferenceLabels

PRESENT_THRESHOLD = 0.5
NODULE_WORKUP_MM = 8.0
NODULE_FOLLOWUP_MM = 6.0


def severity_of(entry: ClinicalEntry, finding: Finding) -> tuple[Severity, str]:
    """Typical severity of the label, adjusted by deterministic size rules for nodules/masses."""
    sev, why = entry.severity, "typical severity of this finding"
    if finding.label == "pulmonary_nodule" and finding.size_mm is not None:
        if finding.size_mm > NODULE_WORKUP_MM:
            sev, why = Severity.MODERATE, "nodule > 8 mm (Fleischner work-up range)"
        elif finding.size_mm >= NODULE_FOLLOWUP_MM:
            sev, why = max(sev, Severity.LOW), "nodule 6-8 mm (short-interval follow-up range)"
    if finding.label == "pulmonary_mass":
        sev, why = max(sev, Severity.HIGH), "lung lesion >= 30 mm needs diagnostic work-up"
    return sev, why


def probability_of(finding: Finding) -> float | None:
    """P(present) implied by one finding (``None`` when the model was uncertain)."""
    if finding.present is None:
        return None
    conf = 1.0 if finding.confidence is None else finding.confidence
    return conf if finding.present else 1.0 - conf


def status_of(finding: Finding, threshold: float) -> str:
    """``present``, ``uncertain`` or ``not detected``."""
    p = probability_of(finding)
    if p is None:
        return "uncertain"
    return "present" if p >= threshold else "not detected"


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "/")


def _header(result: AnalysisResult) -> list[str]:
    rep, qc = result.report, result.qc
    spacing = qc.get("spacing_mm", ("?", "?", "?"))
    adequate = rep.study_quality.adequate and not rep.abstain
    limits = rep.study_quality.limitations
    out = [
        f"# Chest CT research report — {result.case_id}",
        "",
        f"> **{result.disclaimer}**",
        "",
        "## Study",
        "",
        f"- Dataset / case: `{result.dataset}` / `{result.case_id}` "
        f"(patient `{result.patient_id}`)",
        f"- Series: `{result.series_uid}` — {qc.get('n_slices', '?')} slices, slice spacing "
        f"{spacing[0]} mm, coverage {float(qc.get('axial_coverage_mm', 0.0)):.0f} mm",
        f"- Study quality: {'adequate' if adequate else 'limited'}"
        + (f" — {'; '.join(limits)}" if limits else ""),
        f"- Model: `{result.model_id}` (local), {len(result.image_captions)} image(s), sampling "
        f"`{result.view_meta.get('strategy', '-')}`, prompt `{result.request.prompt_id}`, "
        f"{result.perf.total_s:.1f} s",
        "",
    ]
    if rep.abstain or result.raw_error:
        reason = f" ({result.raw_error})" if result.raw_error else ""
        out += [
            "## Abstention",
            "",
            f"The model did not provide a usable reading{reason}. " + "; ".join(rep.parse_warnings),
            "",
        ]
    return out


def _finding_section(entry: ClinicalEntry, f: Finding) -> list[str]:
    sev, why = severity_of(entry, f)
    evidence = [_cell(f.description)] if f.description else []
    if f.laterality.value != "unknown":
        evidence.append(f"side: {f.laterality.value}")
    if f.size_mm is not None:
        evidence.append(f"size about {f.size_mm:.0f} mm ({size_bin(f.size_mm)})")
    if f.evidence_images:
        evidence.append(f"images {', '.join(str(i) for i in f.evidence_images[:8])}")
    follow = _cell(entry.follow_up)
    if f.label == "pulmonary_nodule":
        advice = fleischner(f.size_mm)
        follow = f"{advice.guideline}: {advice.category} → {advice.advice} ({advice.caveat})"
    out = [f"## {entry.medical_term}", ""]
    if entry.synonyms:
        out += [f"*Also called:* {', '.join(entry.synonyms[:6])}", ""]
    out += [
        f"**What it means:** {_cell(entry.plain_language)}",
        "",
        f"**What the model saw:** {'; '.join(evidence) or 'no further detail given'}",
        "",
        f"**Severity:** {sev.name.lower()} ({why}). More serious when: "
        + "; ".join(_cell(m) for m in entry.severity_modifiers[:3]),
        "",
        "**General treatment context (educational):** "
        f"typically {entry.treatment_typically_needed} — "
        f"{_cell(entry.treatment_note)}",
        "",
        f"**Guideline context (educational):** {follow}",
        "",
        f"**How common:** {_cell(entry.prevalence)}",
        "",
        "Sources: " + ", ".join(f"<{u}>" for u in entry.sources[:3]),
        "",
    ]
    return out


def _reference_section(
    result: AnalysisResult, reference: ReferenceLabels, thresholds: dict[str, float]
) -> list[str]:
    outcome = {
        (True, True): "true positive",
        (True, False): "false negative",
        (False, True): "false positive",
        (False, False): "true negative",
    }
    out = [
        "## Comparison with the reference labels",
        "",
        "| Label | Reference | Model P | Result |",
        "|---|---|---|---|",
    ]
    for label, truth in sorted(reference.labels.items()):
        if truth is None:
            continue
        p = result.report.label_probability(label)
        uncertain = any(f.label == label and f.present is None for f in result.report.findings)
        unavailable = result.report.abstain or result.raw_error or p is None or uncertain
        predicted = p is not None and p >= thresholds.get(label, PRESENT_THRESHOLD)
        decision = (
            "unscored (unavailable or uncertain)" if unavailable else outcome[(truth, predicted)]
        )
        shown = "-" if p is None else f"{p:.2f}"
        out.append(f"| {label} | {'present' if truth else 'absent'} | {shown} | {decision} |")
    if reference.lesions:
        out += [
            "",
            "Reference lesions: "
            + "; ".join(
                f"{les.diameter_mm:.0f} mm ({les.readers} reader(s))"
                for les in reference.lesions[:10]
            ),
        ]
    return [*out, ""]


def render_study_report(
    result: AnalysisResult,
    *,
    reference: ReferenceLabels | None = None,
    thresholds: dict[str, float] | None = None,
) -> str:
    """Render the clinical Markdown report of *result* (optionally scored against *reference*)."""
    kb = load_clinical_kb()
    onto = load_ontology()
    limits = thresholds or {}
    rep = result.report
    lines = _header(result)
    usable = not rep.abstain and not result.raw_error
    known = [(f, kb.get(f.label)) for f in rep.findings if usable and onto.normalise(f.label)]
    entries = [(f, e) for f, e in known if e is not None]
    shown = [
        (f, e)
        for f, e in entries
        if status_of(f, limits.get(f.label, PRESENT_THRESHOLD)) != "not detected"
    ]
    shown.sort(key=lambda fe: (-severity_of(fe[1], fe[0])[0], fe[0].label))
    lines += ["## Summary", ""]
    lines += [
        "Scores are uncalibrated research outputs. Educational severity, treatment and "
        "guideline context below do not establish treatment suitability or a patient care plan.",
        "",
    ]
    if not usable:
        lines.append("No usable prediction is available; this run abstained.")
    elif not shown:
        lines.append("No abnormality was reported above the decision threshold.")
    else:
        lines += [
            "| Finding | Status | Probability | Severity | Urgency | Treatment typically "
            "needed | How common |",
            "|---|---|---|---|---|---|---|",
        ]
        for f, e in shown:
            p = probability_of(f)
            lines.append(
                f"| {e.medical_term} | {status_of(f, limits.get(f.label, PRESENT_THRESHOLD))} | "
                f"{'-' if p is None else f'{p:.2f}'} | {severity_of(e, f)[0].name.lower()} | "
                f"{e.urgency.value} | {e.treatment_typically_needed} | "
                f"{_cell(e.prevalence)[:160]} |"
            )
    lines.append("")
    for f, e in shown:
        lines += _finding_section(e, f)
    shown_labels = {f.label for f, _ in shown}
    negatives = sorted({e.medical_term for f, e in entries if f.label not in shown_labels})
    negatives += [n for n in rep.negative_findings if usable and n not in negatives]
    if negatives:
        lines += ["## Not detected", "", ", ".join(negatives) + ".", ""]
    if usable and rep.impression:
        lines += [
            "## Model impression (verbatim)",
            "",
            *[f"- {_cell(i)}" for i in rep.impression],
            "",
        ]
    if usable and rep.urgent_flags:
        lines += [
            "## Urgent flags raised by the model",
            "",
            *[f"- ⚠ {_cell(x)}" for x in rep.urgent_flags],
            "",
        ]
    lines += ["## Deterministic measurements", "", result.context or "none", ""]
    if reference is not None:
        lines += _reference_section(result, reference, limits)
    lines += [
        "---",
        "",
        f"*{result.disclaimer}* Generated by ThoraxBench Local "
        f"{result.provenance.thoraxbench_version} (commit "
        f"{str(result.provenance.git_commit)[:10]}). Follow-up guidance is assigned by fixed "
        "rules from cited guidelines, not by the model.",
    ]
    return "\n".join(lines) + "\n"
