# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Self-contained, escaped image/evidence research reports; no external resources."""

import base64
import json
from html import escape
from pathlib import Path

from thoraxbench.analysis import AnalysisResult
from thoraxbench.config import Settings
from thoraxbench.ontology.clinical import load_clinical_kb
from thoraxbench.ontology.guidelines import fleischner
from thoraxbench.reports.candidates import candidate_review
from thoraxbench.reports.study_report import (
    probability_of,
    render_study_report,
    severity_of,
    status_of,
)
from thoraxbench.schemas import Finding
from thoraxbench.study import Study
from thoraxbench.views import render_slice_png

MAX_SOURCE_PREVIEWS = 16

REPORT_STYLE = """
:root{color-scheme:light;--ink:#162c3d;--muted:#506779;--line:#dce5eb;--teal:#086c70}
*{box-sizing:border-box}html{scroll-padding-top:24px}
body{margin:0;background:#edf3f6;color:var(--ink);font:16px/1.65 system-ui,sans-serif}
.shell{max-width:1240px;margin:auto;padding:40px 28px 24px}
.hero{padding:36px 40px;border-radius:24px;background:linear-gradient(120deg,#122e42,#105d62);
color:white;box-shadow:0 16px 40px #183e4c18}
.eyebrow{text-transform:uppercase;letter-spacing:.18em;font-size:12px;font-weight:750;
color:#b6e4de;margin:0 0 12px}.hero h1{font-size:clamp(28px,4vw,44px);max-width:850px;
line-height:1.16;margin:0 0 16px;overflow-wrap:anywhere}.hero p:last-child{margin-bottom:0}
.notice{border-left:4px solid #d7ad54;background:#fff7e5;padding:16px 20px;border-radius:8px;
font-size:14px;color:#62491d;margin:22px 0}
nav{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}nav a{background:white;padding:8px 16px;
border:1px solid var(--line);border-radius:30px;text-decoration:none;font-weight:650;font-size:14px}
a{color:var(--teal)}a:hover{text-decoration:underline}a:focus-visible,summary:focus-visible{
outline:3px solid #c58d16;outline-offset:4px}
.metadata{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:24px 0}
.metadata div{padding:18px 20px;background:white;border:1px solid var(--line);border-radius:14px}
dt{font-size:12px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);font-weight:700}
dd{margin:5px 0 0;font-weight:700;overflow-wrap:anywhere}dd small{display:block;font-size:12px;
font-weight:400;color:var(--muted)}
.panel{background:white;border:1px solid var(--line);border-radius:18px;padding:28px;margin:24px 0}
h2{font-size:24px;line-height:1.3;margin:0 0 12px}h3{font-size:19px;margin:0 0 8px}
.panel>p{color:var(--muted);max-width:960px;font-size:14px}.table-wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}th{background:#eff5f7;font-size:11px;
letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}th,td{padding:16px 12px;
border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
td:first-child{min-width:160px;
font-weight:650}td:last-child{min-width:175px}td code{display:block;font-size:11px;
font-weight:400;color:var(--muted)}.status{display:inline-block;border-radius:20px;padding:3px 10px;
background:#eaf3f5;font-size:12px;font-weight:700;white-space:nowrap}.present{background:#fff1d4;
color:#795515}.uncertain{background:#f0eafb;color:#624380}.score{font-variant-numeric:tabular-nums;
font-size:19px;font-weight:700}.gallery{display:grid;grid-template-columns:repeat(auto-fill,
minmax(min(100%,300px),1fr));gap:20px;margin-top:24px}figure{margin:0;overflow:hidden;
border:1px solid var(--line);border-radius:14px;background:#f5f8fa;scroll-margin-top:24px}
figure img{display:block;width:100%;height:auto;background:#05090c}figcaption{padding:14px 16px;
font-size:13px;font-weight:600}figure:target{outline:4px solid #d59b23;outline-offset:4px}
.context-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));
gap:18px}.context-card{padding:20px;border-radius:12px;background:#f3f8f9;border:1px solid #e0ebed}
.context-card p{font-size:14px;margin-bottom:0;color:var(--muted);overflow-wrap:anywhere}
details{margin:16px 0;background:white;border:1px solid var(--line);border-radius:12px;
overflow:hidden}
summary{padding:18px 22px;cursor:pointer;font-weight:650}details[open] summary{
border-bottom:1px solid var(--line)}pre{margin:0;padding:22px;white-space:pre-wrap;
overflow-wrap:anywhere;font:13px/1.8 ui-monospace,monospace;background:#f8fafc}
footer{padding:24px 4px;font-size:12px;color:var(--muted)}
@media(max-width:760px){.shell{padding:18px 14px}.hero{padding:26px 22px;border-radius:16px}
.metadata{grid-template-columns:repeat(2,minmax(0,1fr))}.panel{padding:20px 16px}}
@media print{body{background:white}.shell{padding:0}.hero{background:#123d4b;box-shadow:none}
nav{display:none}.panel,figure,.context-card{break-inside:avoid}details{break-inside:avoid}}
"""


def _review_status(finding: Finding) -> str:
    return "uncertain" if finding.confidence is None else status_of(finding, 0.5)


def _severity_context(finding: Finding) -> str:
    entry = load_clinical_kb().get(finding.label)
    if entry is None:
        return "Unknown — no educational reference available."
    if _review_status(finding) != "present":
        return "Not assigned — finding absent or uncertain; this does not establish safety."
    severity, reason = severity_of(entry, finding)
    return (
        f'<span class="status">{escape(severity.name.lower())}</span>'
        f"<br>{escape(reason)}<br>Typical attention: {escape(entry.urgency.value)}"
    )


def require_results_path(path: Path, settings: Settings) -> None:
    """Keep image-bearing reports inside results, including through existing symlinks."""
    root = settings.data_dir.resolve() / "results"
    if not path.resolve().is_relative_to(root) or path.resolve() == root:
        raise ValueError("Reports must remain inside the ignored data/results directory")


def _figure(identifier: str, caption: str, png: bytes) -> str:
    encoded = base64.b64encode(png).decode("ascii")
    return (
        f'<figure id="{identifier}"><img src="data:image/png;base64,{encoded}" '
        f'alt="{escape(caption, quote=True)}"><figcaption>{escape(caption)}</figcaption></figure>'
    )


def _gallery(result: AnalysisResult, study: Study) -> tuple[str, dict[int, str]]:
    figures: list[str] = []
    anchors: dict[int, str] = {}
    if result.model_id == "heuristic-hu":
        references = sorted(
            {
                index
                for finding in result.report.findings
                for index in finding.evidence_images
                if 0 <= index < study.volume.shape[0]
            }
        )[:MAX_SOURCE_PREVIEWS]
        if not references:
            references = [study.volume.shape[0] // 2]
        description = (
            "Source slice previews rendered for explanation in lung window. The heuristic "
            "used the HU volume; no images were sent to an image model. Source indices "
            "are zero-based. A representative center slice is shown when no valid source "
            "slice is cited. Previews are not verified localization."
        )
        for index in references:
            anchors[index] = f"source-{index}"
            figures.append(
                _figure(
                    anchors[index],
                    f"Source slice index {index} (slice {index + 1}/{study.volume.shape[0]})",
                    render_slice_png(study.volume.hu[index], "lung"),
                )
            )
        title = "Source slice previews"
    else:
        description = (
            "These are the exact rendered image bytes prepared for the model, in input order. "
            "Model evidence references resolve to the one-based Image N caption labels; "
            "unavailable references are never guessed. Associations are model claims, "
            "not verified localization."
        )
        for index, png in enumerate(result.prepared_images, start=1):
            anchors[index] = f"input-{index}"
            caption = (
                result.image_captions[index - 1]
                if index <= len(result.image_captions)
                else f"Image {index}: caption unavailable"
            )
            figures.append(_figure(anchors[index], caption, png))
        title = "Actual model-input gallery"
        if not figures:
            figures.append("<p>No rendered image inputs were recorded for this run.</p>")
    return (
        f"<h2>{title}</h2><p>{description}</p><div class=gallery>{''.join(figures)}</div>",
        anchors,
    )


def _findings(result: AnalysisResult, anchors: dict[int, str]) -> str:
    if result.report.abstain or result.raw_error:
        return (
            "<h2>Abstention</h2><p>No usable research reading is available. "
            + escape(result.raw_error or "; ".join(result.report.parse_warnings))
            + "</p>"
        )
    rows: list[str] = []
    kb = load_clinical_kb()
    prefix = "Source slice index" if result.model_id == "heuristic-hu" else "Image"
    for finding in sorted(
        result.report.findings,
        key=lambda item: {"present": 0, "uncertain": 1, "not detected": 2}[_review_status(item)],
    ):
        links: list[str] = []
        unresolved: list[str] = []
        for index in dict.fromkeys(finding.evidence_images):
            if index in anchors:
                links.append(f'<a href="#{anchors[index]}">{prefix} {index}</a>')
            else:
                unresolved.append(str(index))
        evidence = ", ".join(links) or "No image-specific evidence provided."
        if unresolved:
            evidence += " Unavailable reference(s): " + ", ".join(unresolved) + "."
        probability = None if finding.confidence is None else probability_of(finding)
        score = "uncertain" if probability is None else f"{probability:.2f}"
        status = _review_status(finding)
        entry = kb.get(finding.label)
        name = entry.medical_term if entry is not None else finding.label
        rows.append(
            f"<tr><td>{escape(name)}<code>{escape(finding.label)}</code></td>"
            f'<td><span class="status {status.replace(" ", "-")}">{status}</span></td>'
            f'<td class="score">{score}</td><td>{_severity_context(finding)}</td>'
            f"<td>Source: {escape(finding.source)}<br>{escape(finding.description)}</td>"
            f"<td>{evidence}</td></tr>"
        )
    if not rows:
        return "<h2>Findings</h2><p>No structured findings were supplied.</p>"
    return (
        "<h2>Findings and evidence references</h2><p>Scores are uncalibrated research outputs. "
        "Links show supplied evidence associations; they do not establish localization.</p>"
        '<p class="notice">Severity and typical attention are educational reference context, '
        "not validated urgency or a decision about whether you should be checked. Model outputs "
        "may be incorrect; an absent or low-rated finding does not establish that no review "
        "is needed. No diagnosis or treatment decisions should be based on this report.</p>"
        '<div class="table-wrap"><table><thead><tr><th>Finding</th><th>Status</th>'
        "<th>Score</th><th>Typical severity (educational)</th><th>Observation</th>"
        "<th>Evidence</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        "</div>"
    )


def _candidate_gallery(result: AnalysisResult, study: Study) -> str:
    review = candidate_review(result, study)
    if review is None:
        return ""
    rows: list[str] = []
    figures: list[str] = []
    for candidate in review["candidates"]:
        number = candidate["number"]
        previews = candidate["previews"]
        centre = ", ".join(f"{c:.2f}" for c in candidate["center_zyx_mm"])
        size = candidate["diameter_mm"]
        link = f'<a href="#candidate-{number}-axial">{number}</a>' if previews else str(number)
        rows.append(
            f"<tr><td>{link}</td><td>{escape(candidate['source'])}</td>"
            f"<td>{candidate['score']:.3f}</td><td>{centre}</td>"
            f"<td>{size if size is not None else 'unknown'}</td></tr>"
        )
        for preview in previews:
            plane = preview["plane"]
            caption = (
                f"Candidate {number}: {plane} illustrative crop; source: {candidate['source']}"
            )
            figures.append(
                f'<figure id="candidate-{number}-{plane}"><img '
                f'src="{preview["data_url"]}" alt="{escape(caption, quote=True)}">'
                f"<figcaption>{escape(caption)}</figcaption></figure>"
            )
    if not rows:
        rows.append(
            '<tr><td colspan="5">No detector candidates. This does not establish health.</td></tr>'
        )
    return (
        '<section class="panel" id="candidates"><h2>Localised detector candidates</h2>'
        '<p class="notice">Post-inference illustrations only. These crops were not input '
        "to the detector or verified by a VLM. Detector scores are uncalibrated. LUNA16 "
        "training overlaps LIDC-IDRI; results there cannot establish unbiased accuracy.</p>"
        f"<p>{review['previewed']} of {review['total']} candidates have axial/coronal previews. "
        "64 mm lung-window crops; size is approximate. Coordinates are canonical z/y/x "
        "millimetres, not patient/world coordinates. Possible training overlap: "
        f"{escape(str(review['possible_training_overlap']))}.</p>"
        f"<p>Illustrative crop view SHA-256: <code>{review['crop_view_sha256']}</code></p>"
        '<div class="table-wrap"><table><thead><tr><th>Candidate</th><th>Source</th>'
        "<th>Detector score</th><th>Centre z/y/x (mm)</th><th>Box size (mm)</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
        '<div class="gallery">' + "".join(figures) + "</div></section>"
    )


def _educational_context(result: AnalysisResult) -> str:
    if result.report.abstain or result.raw_error:
        return ""
    kb = load_clinical_kb()
    cards: list[str] = []
    for occurrence, finding in enumerate(result.report.findings, start=1):
        entry = kb.get(finding.label)
        if entry is None or _review_status(finding) != "present":
            continue
        follow_up = entry.follow_up
        if finding.label == "pulmonary_nodule":
            advice = fleischner(finding.size_mm)
            follow_up = (
                f"{advice.guideline}: {advice.category}. {advice.advice} {advice.caveat} "
                "Illustrative solid-nodule, single-nodule, low-risk assumptions; patient risk, "
                "morphology and eligibility have not been established by this research tool."
            )
        cards.append(
            f'<article class="context-card"><h3>{escape(entry.medical_term)}</h3>'
            f"<p>Reported finding {occurrence} · size "
            f"{finding.size_mm if finding.size_mm is not None else 'unknown'} mm · "
            f"side {escape(finding.laterality.value)}</p>"
            f"<p>{escape(entry.plain_language)}</p>"
            f"<p><strong>Educational follow-up context</strong><br>{escape(follow_up)}</p>"
            f"<p>Reference sources: {escape(', '.join(entry.sources[:3]))}</p></article>"
        )
    if not cards:
        return ""
    return (
        '<section class="panel" id="context"><h2>Understanding the terminology</h2>'
        "<p>General educational explanations of the reported terms. These descriptions "
        "do not validate a model finding or establish a diagnosis. Detailed educational "
        "context and references are included in the complete report below.</p>"
        '<div class="context-grid">' + "".join(cards) + "</div></section>"
    )


def render_html_report(result: AnalysisResult, study: Study) -> str:
    """Embed actual model images or explanatory HU slice previews in a portable report.

    Images remain in memory/local outputs and are excluded from JSON serialization.
    Evidence indices resolve against actual input ordering, never invented positions.
    """
    gallery, anchors = _gallery(result, study)
    markdown = render_study_report(result)
    title = f"ThoraxBench research report — {result.case_id}"
    unavailable = result.report.abstain or bool(result.raw_error)
    input_qc = (
        "Adequate"
        if result.qc.get("adequate") is True
        else "Limited"
        if result.qc.get("adequate") is False
        else "Unavailable"
    )
    assessment = (
        "Unavailable"
        if unavailable
        else "Adequate"
        if result.report.study_quality.adequate
        else "Limited"
    )
    limits = result.raw_meta.get("generation_limits", [])
    diagnostics = (
        (
            "<details><summary>Generation limit diagnostics</summary>"
            "<p>Per-call budgets and counts; repeated labels describe text, "
            "not recovered findings.</p>"
            f"<pre>{escape(json.dumps(limits, indent=2))}</pre></details>"
        )
        if limits
        else ""
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        f"<title>{escape(title)}</title><style>{REPORT_STYLE}</style></head><body>"
        '<main class="shell"><header class="hero"><p class="eyebrow">'
        "ThoraxBench Local · Research review</p>"
        f"<h1>{escape(title)}</h1><p>Experimental findings, image evidence and "
        "reproducible context in one offline review.</p></header>"
        f'<p class="notice">{escape(result.disclaimer)}</p>'
        '<nav aria-label="Report sections"><a href="#findings">Review findings</a>'
        '<a href="#images">Inspect images</a><a href="#report">Complete report</a></nav>'
        '<dl class="metadata">'
        f"<div><dt>Dataset</dt><dd>{escape(result.dataset)}</dd></div>"
        f"<div><dt>Model</dt><dd>{escape(result.model_id)}<small>Local inference</small></dd></div>"
        f"<div><dt>Input QC</dt><dd>{input_qc}"
        "<small>Deterministic checks, not model success</small></dd></div>"
        f"<div><dt>Model image assessment</dt><dd>{assessment}</dd></div>"
        f"<div><dt>Reading status</dt><dd>{'Abstained' if unavailable else 'Completed'}</dd></div>"
        f"<div><dt>Analysis stages</dt><dd>{result.perf.total_s:.3f} s"
        "<small>Excludes DICOM loading and reporting</small></dd></div></dl>"
        '<p class="notice">A negative on sampled model images cannot exclude findings '
        "elsewhere in the study. Source labels distinguish detector, model "
        "and heuristic output.</p>"
        '<section class="panel" id="findings">'
        + _findings(result, anchors)
        + '</section><section class="panel" id="images">'
        + gallery
        + "</section>"
        + _candidate_gallery(result, study)
        + _educational_context(result)
        + diagnostics
        + '<details id="report"><summary>Complete research report and educational context</summary>'
        f"<pre>{escape(markdown)}</pre></details>"
        "<details><summary>Original model response (escaped)</summary>"
        f"<pre>{escape(result.raw_text)}</pre></details>"
        "<details><summary>Structured result and provenance</summary>"
        f"<pre>{escape(result.model_dump_json(indent=2))}</pre></details>"
        f"<footer><p>{escape(result.disclaimer)}</p>"
        "<p>ThoraxBench Local · Self-contained research export · No external assets required</p>"
        "</footer></main></body></html>"
    )


def render_comparison_report(
    reports: list[tuple[AnalysisResult, str]], omissions: list[dict[str, str]]
) -> str:
    """Compare completed local runs with their exact offline evidence reports embedded."""
    headings = "".join(f"<th>{escape(r.model_id)}</th>" for r, _ in reports)
    labels = sorted({f.label for r, _ in reports for f in r.report.findings})
    rows: list[str] = []
    for label in labels:
        cells: list[str] = []
        for result, _ in reports:
            findings = [f for f in result.report.findings if f.label == label]
            if result.report.abstain or result.raw_error:
                text = "Unavailable — abstention or model error"
            elif not findings:
                text = "Not supplied"
            else:
                occurrences: list[str] = []
                for finding in findings:
                    probability = probability_of(finding)
                    score = "uncertain" if probability is None else f"{probability:.2f}"
                    occurrences.append(f"{_review_status(finding)} · score {score}")
                text = "; ".join(occurrences)
            cells.append(f"<td>{escape(text)}</td>")
        rows.append(f"<tr><th>{escape(label)}</th>{''.join(cells)}</tr>")
    status_rows: list[str] = []
    embedded: list[str] = []
    for index, (result, html) in enumerate(reports, start=1):
        status = (
            "Error" if result.raw_error else "Abstention" if result.report.abstain else "Completed"
        )
        reason = result.raw_error or "; ".join(result.report.parse_warnings)
        status_rows.append(
            f'<tr><th><a href="#run-{index}">{escape(result.model_id)}</a></th>'
            f"<td>{status}</td><td>{result.perf.total_s:.3f} s</td><td>{escape(reason)}</td></tr>"
        )
        embedded.append(
            f'<details id="run-{index}"><summary>{escape(result.model_id)} — '
            f"{status}: full findings, educational severity and image evidence</summary>"
            f'<iframe sandbox title="{escape(result.model_id, quote=True)} research report" '
            f'srcdoc="{escape(html, quote=True)}"></iframe></details>'
        )
    for item in omissions:
        status_rows.append(
            f"<tr><th>{escape(item['model_id'])}</th><td>{escape(item['status'])}</td>"
            f"<td>Not measured</td><td>{escape(item['detail'])}</td></tr>"
        )
    first = reports[0][0]
    single = (
        "Only one completed run is available; no cross-model comparison is possible."
        if len(reports) == 1
        else ""
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "frame-src 'self'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; "
        "form-action 'none'\"><title>ThoraxBench model comparison</title>"
        f"<style>{REPORT_STYLE}iframe{{display:block;width:100%;height:900px;border:0}}</style>"
        '</head><body><main class="shell"><header class="hero">'
        '<p class="eyebrow">ThoraxBench Local · Research comparison</p>'
        f"<h1>Model comparison — {escape(first.case_id)}</h1>"
        f"<p>{len(reports)} completed local run(s) · {escape(first.dataset)}</p></header>"
        f'<p class="notice">{escape(first.disclaimer)}</p>'
        '<section class="panel"><h2>Run status</h2>'
        "<p>Failed and abstained outputs remain unavailable. Timings cover engine stages, "
        "excluding DICOM loading and reporting; this is not a speed benchmark.</p>"
        f"<p>{single}</p><div class=table-wrap><table><thead><tr><th>Model</th><th>Status</th>"
        "<th>Engine stages</th><th>Notes</th></tr></thead><tbody>"
        + "".join(status_rows)
        + '</tbody></table></div></section><section class="panel">'
        "<h2>Findings across models</h2><p>Scores are uncalibrated and not directly comparable "
        "across models. Agreement does not establish correctness. No reference-label evaluation "
        "or accuracy ranking is performed. Missing predictions do not establish absence. "
        "Open each model report below for observations, educational severity "
        "and image evidence.</p>"
        '<div class="table-wrap"><table><thead><tr><th>Finding</th>'
        + headings
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div></section>"
        + "".join(embedded)
        + f"<footer>{escape(first.disclaimer)}</footer></main></body></html>"
    )
