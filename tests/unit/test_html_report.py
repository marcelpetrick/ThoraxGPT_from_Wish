# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Portable HTML preserves image inputs and distinguishes claimed evidence from localization."""

import base64
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from thoraxbench.analysis import DISCLAIMER, AnalysisResult
from thoraxbench.cli import main as cli
from thoraxbench.config import Settings
from thoraxbench.perf import PerfRecord
from thoraxbench.provenance import RunProvenance
from thoraxbench.reports.html_report import render_comparison_report, render_html_report
from thoraxbench.reports.outcome import SHORT_DISCLAIMER, build_outcome
from thoraxbench.schemas import AnalysisRequest, Finding, FindingsReport, LesionCandidate
from thoraxbench.study import Study, load_study_dir
from thoraxbench.views import render_slice_png


@pytest.fixture
def study(phantom_dir: Path) -> Study:
    return load_study_dir(phantom_dir)


@pytest.fixture
def result() -> AnalysisResult:
    return AnalysisResult(
        dataset="synthetic",
        case_id="HTML-test",
        patient_id="PHANTOM-0001",
        series_uid="1.2.3",
        model_id="medgemma1.5-q4",
        request=AnalysisRequest(),
        report=FindingsReport(),
        raw_text="{}",
        perf=PerfRecord(),
        provenance=RunProvenance(),
    )


def test_html_embeds_exact_model_inputs_and_links_one_based_evidence(
    result: AnalysisResult, study: Study
) -> None:
    png = render_slice_png(study.volume.hu[22], "lung", size=64)
    result.prepared_images = [png]
    result.image_captions = ["Image 1: axial lung, slice 23/64"]
    result.report.findings = [
        Finding(
            label="pulmonary_nodule", evidence_images=[1, 1, 0, 99], description="dense candidate"
        )
    ]
    html = render_html_report(result, study)
    assert "Actual model-input gallery" in html
    assert base64.b64encode(png).decode() in html
    assert 'href="#input-1"' in html
    assert html.count('href="#input-1"') == 1
    assert "Image 1: axial lung, slice 23/64" in html
    assert "Unavailable reference(s): 0, 99" in html
    assert "not verified localization" in html
    assert "prepared_images" not in result.model_dump()
    assert "prepared_images" not in result.model_dump_json()


def test_html_escapes_every_untrusted_text(result: AnalysisResult, study: Study) -> None:
    attack = '<script>alert("x")</script><img src=x onerror=alert(1)>'
    result.case_id = attack
    result.raw_text = attack
    result.disclaimer = attack
    result.report.findings = [Finding(label=attack, description=attack)]
    result.image_captions = [attack]
    result.prepared_images = [b"png"]
    html = render_html_report(result, study)
    assert "<script>" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html
    assert 'alt="&lt;script&gt;alert(&quot;x&quot;)' in html
    assert "default-src 'none'" in html
    assert 'src="http' not in html


def test_heuristic_uses_source_slices_and_shows_invalid_evidence(
    result: AnalysisResult, study: Study
) -> None:
    result.model_id = "heuristic-hu"
    result.report.findings = [Finding(label="pulmonary_nodule", evidence_images=[22, -1, 500])]
    html = render_html_report(result, study)
    assert 'href="#source-22"' in html
    assert 'id="source-22"' in html
    assert "Source slice index 22 (slice 23/64)" in html
    assert "no images were sent to an image model" in html
    assert "Unavailable reference(s): -1, 500" in html
    assert "data:image/png;base64," in html


def test_heuristic_without_valid_evidence_shows_center_without_inventing_link(
    result: AnalysisResult, study: Study
) -> None:
    result.model_id = "heuristic-hu"
    result.report.findings = [Finding(label="pleural_effusion", evidence_images=[999])]
    html = render_html_report(result, study)
    assert 'id="source-32"' in html
    assert 'href="#source-32"' not in html
    assert "No image-specific evidence provided." in html
    assert "Unavailable reference(s): 999" in html


def test_heuristic_gallery_is_bounded(result: AnalysisResult, study: Study) -> None:
    result.model_id = "heuristic-hu"
    result.report.findings = [Finding(label="pulmonary_nodule", evidence_images=list(range(30)))]
    html = render_html_report(result, study)
    assert html.count("<figure ") == 16
    assert "Unavailable reference(s): 16, 17" in html


def test_model_missing_caption_and_missing_evidence_are_explicit(
    result: AnalysisResult, study: Study
) -> None:
    result.prepared_images = [b"png"]
    result.report.findings = [Finding(label="pulmonary_nodule", present=None)]
    html = render_html_report(result, study)
    assert "Image 1: caption unavailable" in html
    assert "No image-specific evidence provided." in html
    assert "uncertain" in html
    result.prepared_images = []
    assert "No rendered image inputs were recorded" in render_html_report(result, study)


@pytest.mark.parametrize("raw_error", [None, "token limit reached"])
def test_abstention_has_no_usable_reading_claim(
    result: AnalysisResult, study: Study, raw_error: str | None
) -> None:
    result.report.abstain = True
    result.raw_error = raw_error
    result.report.parse_warnings = ["unavailable"]
    html = render_html_report(result, study)
    assert '<h2><span class="l-en">Abstention</span>' in html
    assert "No usable research reading is available" in html
    assert "No abnormality" not in html
    assert "not medical advice" in html


def test_no_findings_is_explicit(result: AnalysisResult, study: Study) -> None:
    assert "No structured findings were supplied" in render_html_report(result, study)


def test_comparison_preserves_uncertainty_missing_predictions_and_escaped_omissions(
    result: AnalysisResult,
) -> None:
    result.report.findings = [Finding(label="pulmonary_nodule", present=None)]
    missing = result.model_copy(deep=True)
    missing.model_id = "other"
    missing.report.findings = []
    html = render_comparison_report(
        [(result, "<html><body>one</body></html>"), (missing, "<html><body>two</body></html>")],
        [{"model_id": "<script>x</script>", "status": "error", "detail": "<img src=x>"}],
    )
    assert "uncertain · score uncertain" in html
    assert "Not supplied" in html
    assert "<script>x</script>" not in html
    assert "<img src=x>" not in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html
    assert 'srcdoc="&lt;html&gt;' in html
    assert "Agreement does not establish correctness" in html


def test_review_has_visible_severity_and_scoped_guideline_context(
    result: AnalysisResult, study: Study
) -> None:
    result.report.findings = [
        Finding(label="pulmonary_nodule", present=True, confidence=0.8, size_mm=12)
    ]
    html = render_html_report(result, study)
    assert 'aria-label="Report sections"' in html
    assert "Typical severity (educational)" in html
    assert '<span class="status">moderate</span>' in html
    assert "Typical attention:" in html
    assert "Fleischner Society 2017" in html
    assert "Illustrative solid-nodule, single-nodule, low-risk assumptions" in html
    assert "eligibility have not been established" in html
    assert "Severity is general educational context, not an assessment of this scan." in html
    assert "Understanding the terminology" in html


@pytest.mark.parametrize(("present", "confidence"), [(True, None), (None, 0.8), (False, 0.9)])
def test_no_severity_assignment_for_absent_or_uncertain_finding(
    result: AnalysisResult, study: Study, present: bool | None, confidence: float | None
) -> None:
    result.report.findings = [
        Finding(label="pulmonary_nodule", present=present, confidence=confidence)
    ]
    html = render_html_report(result, study)
    assert "Not assigned — finding absent or uncertain" in html
    assert "Understanding the terminology" not in html
    if confidence is None:
        assert '<td class="score">uncertain</td>' in html


def test_educational_reference_text_is_escaped(
    result: AnalysisResult, study: Study, monkeypatch: pytest.MonkeyPatch
) -> None:
    from thoraxbench.reports import html_report

    kb = html_report.load_clinical_kb()
    entry = kb.get("pleural_effusion")
    assert entry is not None
    attack = '<script>alert("context")</script>'
    modified = entry.model_copy(update={"plain_language": attack, "follow_up": attack})
    monkeypatch.setattr(
        html_report,
        "load_clinical_kb",
        lambda: kb.model_copy(update={"entries": {entry.id: modified}}),
    )
    result.report.findings = [Finding(label="pleural_effusion", present=True, confidence=0.9)]
    html = render_html_report(result, study)
    assert '<script>alert("context")</script>' not in html
    assert "&lt;script&gt;alert(&quot;context&quot;)&lt;/script&gt;" in html


def test_cli_html_written_to_nested_path_even_when_abstaining(
    tmp_path: Path, phantom_dir: Path, result: AnalysisResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    from thoraxbench import analysis

    result.report.abstain = True
    monkeypatch.setattr(analysis, "analyze_study", Mock(return_value=result))
    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    destination = settings.data_path("results", "reports", "view.html")
    response = CliRunner().invoke(
        cli.app, ["analyze", str(phantom_dir), "--html", str(destination)]
    )
    assert response.exit_code == 1
    assert destination.is_file()
    assert "Abstention" in destination.read_text()


def test_comparison_keeps_every_finding_with_the_same_label(result: AnalysisResult) -> None:
    result.report.findings = [
        Finding(label="pulmonary_nodule", present=False, confidence=0.95),
        Finding(label="pulmonary_nodule", present=True, confidence=0.85),
        Finding(label="pulmonary_nodule", present=None),
    ]
    html = render_comparison_report([(result, "<html><body>Evidence</body></html>")], [])
    assert "not detected · score 0.05; present · score 0.85; uncertain · score uncertain" in html


def test_educational_context_keeps_size_specific_guidance_for_each_occurrence(
    result: AnalysisResult, study: Study
) -> None:
    result.report.findings = [
        Finding(label="pulmonary_nodule", present=True, confidence=0.9, size_mm=5),
        Finding(label="pulmonary_nodule", present=True, confidence=0.8, size_mm=12),
    ]
    html = render_html_report(result, study)
    assert html.count('class="context-card"') == 2
    assert "Reported finding 1 · size 5.0 mm" in html
    assert "Reported finding 2 · size 12.0 mm" in html
    assert "No routine follow-up." in html
    assert "Consider CT at 3 months, PET/CT, or tissue sampling." in html


def test_abstention_keeps_input_qc_separate_and_escapes_diagnostics(
    result: AnalysisResult, study: Study
) -> None:
    result.qc = {"adequate": True}
    result.report.abstain = True
    result.raw_error = "generation token limit reached"
    result.raw_meta["generation_limits"] = [
        {"tokens_generated": 2048, "note": "<script>bad</script>"}
    ]
    html = render_html_report(result, study)
    assert "Input-QC</span></dt><dd>Adequate" in html
    assert "Bildbewertung des Modells</span></dt><dd>Unavailable" in html
    assert "generation token limit reached" in html
    assert "Generation limit diagnostics" in html
    assert "&lt;script&gt;bad&lt;/script&gt;" in html
    assert "<script>bad</script>" not in html


def test_outcome_states_yes_bias_once_in_both_languages(
    result: AnalysisResult, study: Study
) -> None:
    labels = ["pulmonary_nodule", "pleural_effusion", "emphysema", "cardiomegaly"]
    result.request = AnalysisRequest(labels=labels)
    result.qc = {"n_slices": 317, "adequate": True}
    result.slice_indices = [0, 105, 211, 316]
    result.report.abstain = True
    result.report.parse_warnings = [
        f"{label}: positive has no valid attached-image evidence; prediction marked unavailable"
        for label in labels
    ]
    en = build_outcome(result, "en")
    de = build_outcome(result, "de")
    assert en.verdict == de.verdict == "not_assessable"
    assert en.yes_bias
    assert len(en.sentences) <= 3
    assert len(de.sentences) <= 3
    assert "answered yes to all 4 findings" in en.sentences[0]
    assert "4 of 317 slices (1 %)" in en.sentences[1]
    assert "alle 4 Befunde" in de.sentences[0]
    html = render_html_report(result, study)
    assert html.count('id="outcome"') == 1
    assert 'id="lang-de"' in html
    assert 'lang="de"' in html
    assert "Parser details" in html  # warnings collapse instead of one long paragraph
    readable = html.split("Structured result and provenance")[0]
    assert DISCLAIMER not in readable  # the full text stays only in the embedded JSON
    # One visible notice at the top; the footer and the collapsed Markdown repeat one line.
    assert html.count(f'<p class="notice"><span class="l-en">{SHORT_DISCLAIMER["en"]}') == 1
    assert f'"series_uid": "{result.series_uid}"' not in html
    assert result.patient_id not in html


def test_outcome_lists_strong_detector_candidates_and_counts_hidden(
    result: AnalysisResult, study: Study
) -> None:
    result.model_id = "monai-lung-nodule"
    result.dataset, result.case_id = study.dataset, study.case_id
    result.series_uid = study.volume.series_uid
    result.qc = {"n_slices": 64, "spacing_mm": [5.0, 2.5, 2.5], "adequate": True}
    result.report.findings = [
        Finding(label="pulmonary_nodule", confidence=0.91, laterality="right", source="detector")
    ]
    result.report.lesions = [
        LesionCandidate(center_zyx_mm=(100.0, 150.0, 60.0), diameter_mm=5.3, score=0.91),
        LesionCandidate(center_zyx_mm=(50.0, 150.0, 250.0), diameter_mm=6.2, score=0.15),
    ]
    width = float((study.volume.shape[2] - 1) * study.volume.spacing_mm[2])
    outcome = build_outcome(result, "en", width_mm=width)
    assert outcome.verdict == "findings_to_review"
    assert outcome.hidden_candidates == 1
    assert [(item.side, item.slice_number) for item in outcome.look_here] == [("right", 21)]
    assert (
        "5 mm pulmonary nodule candidate in the right lung near slice 21 of 64"
        in (outcome.sentences[0])
    )
    assert "only lung nodules were searched" in outcome.sentences[1]
    assert build_outcome(result, "de").sentences[0].startswith("Zur Prüfung markiert: ")
    html = render_html_report(result, study)
    assert "Look here" in html
    assert "Hier prüfen" in html
    assert "1 low-score candidate(s) below 0.5" in html


def test_outcome_without_findings_says_what_was_checked(result: AnalysisResult) -> None:
    result.model_id = "monai-lung-nodule"
    result.qc = {"n_slices": 64}
    result.report.lesions = []
    outcome = build_outcome(result, "en")
    assert outcome.verdict == "nothing_flagged"
    assert outcome.sentences == [
        "Nothing was flagged in the checked area.",
        "Checked: whole volume; only lung nodules were searched.",
        "This does not rule out findings; the radiologist's report remains the reference.",
    ]


def test_failed_detector_does_not_recommend_itself(result: AnalysisResult) -> None:
    result.model_id = "monai-lung-nodule"
    result.qc = {"n_slices": 64}
    result.raw_error = "RuntimeError: weights missing"
    outcome = build_outcome(result, "en")
    assert outcome.verdict == "not_assessable"
    assert "Check the detector setup" in outcome.sentences[2]
    assert "Run the lung-nodule detector" not in " ".join(outcome.sentences)


@pytest.mark.parametrize(
    ("model_id", "en", "de"),
    [
        (
            "heuristic-hu",
            "Checked: whole volume with simple density rules only; treat these as rough cues.",
            "Geprüft: gesamtes Volumen, nur mit einfachen Dichteregeln; das sind grobe Hinweise.",
        ),
        (
            "medgemma1.5-q4",
            "Checked: 2 of 64 slices (3 %); other slices were not looked at.",
            "Geprüft: 2 von 64 Schichten (3 %); andere Schichten wurden nicht angesehen.",
        ),
    ],
)
def test_flagged_coverage_matches_how_the_model_looked(
    result: AnalysisResult, model_id: str, en: str, de: str
) -> None:
    # A whole-volume density run must not also claim that other areas were skipped.
    result.model_id = model_id
    result.qc = {"n_slices": 64}
    result.slice_indices = [10, 20]
    result.report.findings = [
        Finding(label="pleural_effusion", present=True, confidence=0.9, evidence_images=[1])
    ]
    assert build_outcome(result, "en").sentences[1] == en
    assert build_outcome(result, "de").sentences[1] == de
