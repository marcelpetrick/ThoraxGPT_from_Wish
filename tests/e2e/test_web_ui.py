# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Browser acceptance of the local workbench using generated synthetic data only."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, Route, expect

from tests.e2e.mock_jobs import MockJobs

pytestmark = pytest.mark.e2e


def test_preferences_tooltips_and_mobile_layout(ui_page: Page) -> None:
    page = ui_page
    expect(page.locator("html")).to_have_attribute("lang", "en")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    expect(page.locator("#create-demo")).to_contain_text("Create synthetic demo")
    page.locator("#theme-toggle").hover()
    expect(page.get_by_role("tooltip")).to_be_visible()
    expect(page.get_by_role("tooltip")).not_to_have_text("")
    page.locator("#language-toggle").focus()
    expect(page.get_by_role("tooltip")).to_be_visible()
    expect(page.get_by_role("tooltip")).not_to_have_text("")
    page.locator("#language-toggle").press("Escape")
    expect(page.get_by_role("tooltip")).to_be_hidden()
    page.locator("#language-toggle").press("Enter")
    expect(page.locator("html")).to_have_attribute("lang", "de")
    expect(page.locator("#create-demo")).not_to_contain_text("Create synthetic demo")
    page.locator("#theme-toggle").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.reload()
    expect(page.locator("html")).to_have_attribute("lang", "de")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator("#create-demo").scroll_into_view_if_needed()
    expect(page.locator("#create-demo")).to_be_in_viewport()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.locator("#nav-about").click()
    expect(page.get_by_text("Marcel Petrick", exact=False).first).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize(("language", "theme"), [("en", "light"), ("de", "dark")])
def test_synthetic_study_analysis_downloads_and_about(
    ui_page: Page, tmp_path: Path, language: str, theme: str
) -> None:
    page = ui_page
    _set_preferences(page, language, theme)
    _check_research_disclaimer(page, language)
    page.locator("#create-demo").click()
    option = page.locator("#study-select option").filter(has_text=re.compile("phantom", re.I))
    expect(option).to_have_count(1)
    value = option.get_attribute("value")
    assert value is not None
    page.locator("#study-select").select_option(value)
    slider = page.locator("#slice-slider")
    expect(slider).to_be_enabled()
    slider.fill("22")
    slider.dispatch_event("input")
    # A successful rendered image must load real pixels, not just occupy a placeholder box.
    expect(page.locator("img[src*='/slice/']")).to_be_visible()
    page.wait_for_function(
        "() => { const image = document.querySelector(\"img[src*='/slice/']\"); "
        "return image && image.complete && image.naturalWidth > 0; }"
    )
    slider.focus()
    slider.press("ArrowRight")
    expect(slider).to_have_value("23")
    model = page.locator("select").filter(has=page.locator("option[value='heuristic-hu']"))
    model.select_option("heuristic-hu")
    page.locator("#run-analysis").click()
    # Download links are always visible (aria-disabled); wait until a result enables them.
    expect(page.locator("#download-json")).to_have_attribute(
        "aria-disabled", "false", timeout=30_000
    )
    expect(page.get_by_role("table").first).to_be_visible()
    expect(page.get_by_role("table").first).to_contain_text(re.compile("nodule", re.I))
    expect(page.locator("#metric-images")).to_have_text("0")
    _check_findings_scores(page, language)
    _check_control_tooltips(page)
    with page.expect_download() as downloaded:
        page.locator("#download-json").click()
    json_path = tmp_path / "result.json"
    downloaded.value.save_as(json_path)
    result = json.loads(json_path.read_text())
    assert any(
        f["label"] == "pulmonary_nodule" and f["present"] for f in result["report"]["findings"]
    )
    assert not result["report"]["abstain"]
    with page.expect_download() as downloaded:
        page.locator("#download-report").click()
    report_path = tmp_path / "report.md"
    downloaded.value.save_as(report_path)
    report = report_path.read_text()
    assert "research" in report.lower()
    assert "not medical advice" in report.lower()
    assert "nodule" in report.lower()
    _check_inline_report(page)
    _check_html_export(page, tmp_path)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    _check_about(page, language)


def _check_inline_report(page: Page) -> None:
    with page.expect_popup() as popup:
        page.locator("#open-html").click()
    review = popup.value
    review.wait_for_load_state()
    expect(review.get_by_role("img").first).to_be_visible()
    assert (
        review.evaluate("getComputedStyle(document.querySelector('.hero')).backgroundImage")
        != "none"
    )
    assert review.evaluate("window.opener === null")
    review.wait_for_function(
        "[...document.images].every(image => image.complete && image.naturalWidth > 0)"
    )
    review.close()


def _check_html_export(page: Page, tmp_path: Path) -> None:
    with page.expect_download() as downloaded:
        page.locator("#download-html").click()
    html_path = tmp_path / "report.html"
    downloaded.value.save_as(html_path)
    html = html_path.read_text()
    assert "data:image/png;base64," in html
    assert "nodule" in html.lower()
    assert "<script" not in html.lower()
    assert "not medical advice from a qualified healthcare professional" in html.lower()
    assert "self-made experimental research tool" in html.lower()
    assert "incorrect, incomplete or misleading" in html.lower()
    assert "do not use them for diagnosis or treatment decisions" in html.lower()
    export_page = page.context.new_page()
    export_requests: list[str] = []
    export_page.on("request", lambda request: export_requests.append(request.url))
    export_page.goto(html_path.as_uri())
    expect(export_page.get_by_role("img").first).to_be_visible()
    export_page.wait_for_function(
        "() => [...document.images].every(image => image.complete && image.naturalWidth > 0)"
    )
    assert not any(url.startswith(("http://", "https://")) for url in export_requests)
    export_page.close()


def test_form_actions_and_labels_have_keyboard_help(ui_page: Page) -> None:
    page = ui_page
    page.locator("#create-demo").click()
    expect(page.locator("#slice-slider")).to_be_enabled()
    _check_control_tooltips(page)
    page.locator("#language-toggle").click()
    page.locator("#theme-toggle").click()
    _check_control_tooltips(page)
    page.locator("#nav-about").click()
    expect(page.locator("#libraries-table")).to_contain_text("pydantic")
    _check_control_tooltips(page)


def _check_control_tooltips(page: Page) -> None:
    controls = page.locator("[data-tip]:not(:disabled)")
    for control in controls.all():
        if not control.is_visible():
            continue
        control.scroll_into_view_if_needed()
        control.focus()
        page.clock.fast_forward(700)
        expect(
            page.get_by_role("tooltip"),
            f"keyboard help for {control.get_attribute('id') or control.inner_text()}",
        ).to_be_visible()
        expect(control).to_have_accessible_description(re.compile(r"\S+"))
        page.keyboard.press("Escape")
        expect(page.get_by_role("tooltip")).to_be_hidden()


def _check_findings_scores(page: Page, language: str) -> None:
    emphysema = page.locator("#findings-table tbody tr").filter(has_text="emphysema")
    expect(emphysema).to_contain_text("Not detected" if language == "en" else "Nicht erkannt")
    expect(emphysema).to_contain_text("0.02")
    nodule = page.locator("#findings-table tbody tr").filter(has_text="pulmonary_nodule")
    expect(nodule).to_contain_text("0.79")


def test_abstention_failure_and_missing_confidence_are_explicit(ui_page: Page) -> None:
    page = ui_page
    page.locator("#create-demo").click()
    expect(page.locator("#run-analysis")).to_be_enabled()
    # Mock the model boundary only; the selected study and viewer remain synthetic.
    response = {
        "result": {
            "model_id": "synthetic-test",
            "perf": {"total_s": 0.1},
            "report": {
                "abstain": True,
                "findings": [
                    {
                        "label": "<img src=x onerror=alert(1)>",
                        "present": True,
                        "confidence": None,
                    }
                ],
            },
            "raw_error": "Synthetic model failure",
        },
        "markdown": "Research only. Synthetic model failure; no useful prediction.",
        "downloads": {},
    }
    jobs = MockJobs(page, lambda _model: response)
    page.locator("#run-analysis").click()
    expect(page.locator("#metric-status")).to_have_text("Abstained")
    expect(page.locator("#metric-images")).to_have_text("—")
    expect(page.locator("#notice")).to_contain_text("The engine abstained")
    expect(page.locator("#result-abstention")).to_contain_text("Synthetic model failure")
    expect(page.locator("#result-reading-summary")).to_contain_text(
        "Model image assessment: Unavailable"
    )
    row = page.locator("#findings-body tr").first
    expect(row).to_have_text("No prediction")
    expect(row).not_to_contain_text("<img src=x onerror=alert(1)>")
    expect(row.locator("img")).to_have_count(0)
    page.locator("#language-toggle").click()
    expect(page.locator("#metric-status")).to_have_text("Enthaltung")
    expect(page.locator("#slice-slider")).to_have_attribute("aria-valuetext", re.compile("Schicht"))
    jobs.respond = lambda _model: ("error", "Synthetic service offline")
    page.locator("#run-analysis").click()
    expect(page.locator("#notice")).to_contain_text("Anfrage fehlgeschlagen")
    expect(page.locator("#notice")).to_contain_text("Synthetic service offline")
    expect(page.locator("#results-content")).to_be_hidden()
    expect(page.locator("#download-json")).not_to_have_attribute("href", re.compile(".+"))
    expect(page.locator("#run-analysis")).to_be_enabled()


def _set_preferences(page: Page, language: str, theme: str) -> None:
    if language == "de":
        page.locator("#language-toggle").click()
    if theme == "dark":
        page.locator("#theme-toggle").click()


def _check_research_disclaimer(page: Page, language: str) -> None:
    disclaimer = page.locator(".research-banner")
    if language == "en":
        expect(disclaimer).to_contain_text("Self-made experimental research tool")
        expect(disclaimer).to_contain_text(
            "Not medical advice from a qualified healthcare professional"
        )
        expect(disclaimer).to_contain_text("incorrect, incomplete or misleading")
        expect(disclaimer).to_contain_text("do not use for diagnosis or treatment decisions")
    else:
        expect(disclaimer).to_contain_text("Selbst entwickeltes experimentelles Forschungswerkzeug")
        expect(disclaimer).to_contain_text(
            "Keine medizinische Beratung durch qualifiziertes medizinisches Fachpersonal"
        )
        expect(disclaimer).to_contain_text("falsch, unvollständig oder irreführend")
        expect(disclaimer).to_contain_text(
            "nicht für Diagnose- oder Behandlungsentscheidungen verwenden"
        )


def _check_about(page: Page, language: str) -> None:
    page.locator("#nav-about").click()
    expect(page.get_by_text("Marcel Petrick", exact=False).first).to_be_visible()
    expect(page.locator("#about-license")).to_contain_text("GPL-3.0")
    _check_research_disclaimer(page, language)
    licenses = page.get_by_role("table").first
    expect(licenses).to_be_visible()
    expect(licenses).to_contain_text("fastapi")
    expect(licenses).to_contain_text("pydantic")


@pytest.mark.parametrize("outcome", ["completed", "error"])
def test_job_elapsed_uses_server_clock_everywhere_and_freezes(ui_page: Page, outcome: str) -> None:
    page = ui_page
    page.locator("#create-demo").click()
    expect(page.locator("#run-analysis")).to_be_enabled()
    expect(page.locator("#request-forecast")).to_contain_text("Initial workstation guess")
    jobs = MockJobs(page, lambda _model: "hold")
    page.locator("#run-analysis").click()
    expect(page.locator("#request-timer")).to_be_visible()
    expect(page.locator("#request-elapsed")).to_have_text("00:00")
    # The server reports 75 s. Advancing browser time never invents server elapsed.
    jobs.elapsed = 75
    page.clock.fast_forward(1000)
    expect(page.locator("#request-elapsed")).to_have_text("01:15")
    page.clock.fast_forward(2000)
    expect(page.locator("#request-elapsed")).to_have_text("01:15")
    expect(page.locator("#job-bar")).to_contain_text("Running: Analysis · demo / phantom")
    expect(page.locator("#job-indicator-elapsed")).to_have_text("01:15")
    assert page.title().startswith("⏳ 01:15 · ThoraxBench Local")
    expect(page.locator("#request-forecast")).to_have_text(
        "Taking longer than estimated; still running"
    )
    expect(page.locator("#request-elapsed")).to_have_attribute("aria-live", "off")
    expect(page.locator("#job-indicator-elapsed")).to_have_attribute("aria-live", "off")
    # Queueing stays possible while a job runs.
    expect(page.locator("#run-analysis")).to_be_enabled()
    page.locator("#nav-about").click()
    expect(page.locator("#job-bar")).to_be_visible()
    jobs.elapsed = 77
    page.clock.fast_forward(1000)
    expect(page.locator("#job-indicator-elapsed")).to_have_text("01:17")
    page.locator("#nav-analysis").click()
    page.locator("#language-toggle").click()
    expect(page.locator("#request-timer")).to_contain_text("Laufzeit des Auftrags (Serveruhr)")
    expect(page.locator("#job-bar")).to_contain_text("Läuft: Analyse")
    _finish_and_check_frozen(page, jobs, outcome)


def _finish_and_check_frozen(page: Page, jobs: MockJobs, outcome: str) -> None:
    jobs.elapsed = 80
    if outcome == "completed":
        jobs.finish(_mock_model_output("heuristic-hu"))
        page.clock.fast_forward(1000)
        expect(page.locator("#metric-time")).to_have_text("0.100 s")
    else:
        jobs.finish(("error", "Synthetic service offline"))
        page.clock.fast_forward(1000)
        expect(page.locator("#notice")).to_contain_text("Anfrage fehlgeschlagen")
    expect(page.locator("#request-elapsed")).to_have_text("01:20")
    expect(page.locator("#job-bar")).to_be_hidden()
    expect(page.locator("#job-notice")).to_be_visible()
    page.clock.fast_forward(5000)
    expect(page.locator("#request-elapsed")).to_have_text("01:20")
    assert not page.title().startswith("⏳")
    page.locator("#study-select").dispatch_event("change")
    expect(page.locator("#request-timer")).to_be_hidden()
    if outcome == "completed":
        expect(page.locator("#request-forecast")).to_contain_text(
            "Aus lokalem Anfrageverlauf geschätzt"
        )
        history = page.evaluate("JSON.parse(localStorage.getItem('thoraxbench.duration-history'))")
        assert history == {"heuristic-hu:4": [80]}
    else:
        assert page.evaluate("localStorage.getItem('thoraxbench.duration-history')") is None


def _mock_model_output(model_id: str, *, abstain: bool = False) -> dict[str, object]:
    return {
        "id": f"run-{model_id}",
        "result": {
            "model_id": model_id,
            "perf": {"total_s": 0.1, "n_images": 0 if model_id == "heuristic-hu" else 9},
            "report": {
                "abstain": abstain,
                "findings": []
                if abstain
                else [{"label": "pulmonary_nodule", "present": True, "confidence": 0.8}],
            },
            "raw_error": "Synthetic abstention" if abstain else None,
        },
        "markdown": "Research use only. Synthetic mocked model output, not medical advice.",
        "downloads": {"html": f"/mock/{model_id}.html"},
    }


def test_recommended_comparison_is_sequential_and_keeps_partial_results(ui_page: Page) -> None:
    page = ui_page
    inventory = [
        {"id": model, "available": model != "gemma3-4b", "recommended": True}
        for model in [
            "heuristic-hu",
            "medgemma1.5-q4",
            "medgemma1.5-q8",
            "gemma3-4b",
            "qwen3-vl-4b",
        ]
    ]
    inventory.append({"id": "extra-unrecommended", "available": True, "recommended": False})
    page.route("**/api/models", lambda route: route.fulfill(json={"models": inventory}))
    page.reload()
    page.locator("#create-demo").click()
    expect(page.locator("#run-analysis")).to_be_enabled()
    page.locator("#compare-models").check()
    expect(page.locator("#image-count")).to_be_enabled()
    expect(page.locator("#model-select")).to_be_disabled()
    expect(page.locator("#comparison-body")).to_contain_text("Skipped: unavailable")
    requested: list[str] = []

    def respond(model: str) -> dict[str, object] | tuple[str, str] | str:
        requested.append(model)
        if model == "heuristic-hu":
            return "hold"
        if model == "qwen3-vl-4b":
            return ("error", "Synthetic service offline")
        response = _mock_model_output(model, abstain=model == "medgemma1.5-q4")
        if model == "medgemma1.5-q8":
            response["result"]["report"]["findings"].insert(  # type: ignore[index]
                0, {"label": "pulmonary_nodule", "present": False, "confidence": 0.9}
            )
        return response

    recommended = [entry["id"] for entry in inventory if entry["recommended"]]
    jobs = MockJobs(page, respond, models=[str(model) for model in recommended])
    jobs.skip("gemma3-4b")
    page.locator("#run-analysis").click()
    expect(page.locator("#batch-status")).to_contain_text("heuristic-hu")
    assert requested == ["heuristic-hu"]
    assert jobs.requests[0]["kind"] == "comparison"
    jobs.elapsed = 2.1
    page.clock.fast_forward(1000)
    expect(page.locator("#model-elapsed")).to_have_text("00:02")
    jobs.finish_step(jobs.jobs[0], 0, _mock_model_output("heuristic-hu"))
    page.clock.fast_forward(1000)
    expect(page.locator("#comparison-download")).to_be_visible()
    _check_comparison_results(page, requested)


def _check_comparison_results(page: Page, requested: list[str]) -> None:
    assert requested == ["heuristic-hu", "medgemma1.5-q4", "medgemma1.5-q8", "qwen3-vl-4b"]
    expect(page.locator("#comparison-body tr[data-model='heuristic-hu']")).to_contain_text(
        "Completed"
    )
    expect(page.locator("#comparison-body tr[data-model='medgemma1.5-q4']")).to_contain_text(
        "Abstained"
    )
    expect(page.locator("#comparison-body tr[data-model='qwen3-vl-4b']")).to_contain_text(
        "Synthetic service offline"
    )
    opened = page.locator("#comparison-body tr[data-model='medgemma1.5-q4'] a[target='_blank']")
    expect(opened).to_have_attribute("href", "/mock/medgemma1.5-q4.html?inline=true")
    expect(page.locator("#comparison-open")).to_have_attribute("href", re.compile(r"inline=true$"))
    expect(page.locator("#comparison-findings-table")).to_contain_text("pulmonary_nodule")
    expect(page.locator("#comparison-findings-table")).to_contain_text("0.80")
    expect(page.locator("#comparison-findings-body tr td").nth(3)).to_have_text(
        "Not detected · 0.10; Present · 0.80"
    )
    expect(page.locator("#comparison-panel")).to_contain_text(
        "not directly comparable across model families"
    )
    expect(page.locator("#comparison-body tr[data-model='gemma3-4b']")).to_contain_text(
        "Skipped: unavailable"
    )
    expect(page.locator("#comparison-body tr[data-model='medgemma1.5-q8'] td").nth(2)).to_have_text(
        "9"
    )
    expect(page.locator("#metric-images")).to_have_text("9")
    expect(page.locator("#metric-model")).to_have_text("medgemma1.5-q8")
    page.locator("#comparison-body tr[data-model='heuristic-hu'] button").click()
    expect(page.locator("#metric-model")).to_have_text("heuristic-hu")
    _check_control_tooltips(page)
    page.locator("#language-toggle").click()
    expect(page.locator("#comparison-download")).to_have_text("Vergleich als HTML herunterladen")
    expect(page.locator("#comparison-body tr[data-model='medgemma1.5-q4']")).to_contain_text(
        "Enthaltung"
    )
    _check_control_tooltips(page)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    stopped = page.locator("#request-elapsed").inner_text()
    page.clock.fast_forward(5000)
    expect(page.locator("#request-elapsed")).to_have_text(stopped)
    page.locator("#study-select").dispatch_event("change")
    expect(page.locator("#comparison-body")).to_contain_text("Synthetic service offline")
    _check_comparison_preserved_after_study_change(page)
    expect(page.locator("#batch-status")).to_be_hidden()


def test_missing_confidence_is_uncertain_and_model_text_is_escaped(ui_page: Page) -> None:
    page = ui_page
    page.locator("#create-demo").click()
    expect(page.locator("#run-analysis")).to_be_enabled()
    response = _mock_model_output("heuristic-hu")
    response["result"]["report"]["findings"] = [
        {"label": "<img src=x onerror=alert(1)>", "present": True, "confidence": None},
        {"label": "positive_low_confidence", "present": True, "confidence": 0.2},
        {"label": "negative_low_confidence", "present": False, "confidence": 0.2},
    ]
    MockJobs(page, lambda _model: response)
    page.locator("#run-analysis").click()
    row = page.locator("#findings-body tr").filter(has_text="<img src=x onerror=alert(1)>")
    expect(row.locator("td").nth(1)).to_have_text("Uncertain")
    expect(row.locator("td").nth(2)).to_have_text("—")
    expect(row).to_contain_text("<img src=x onerror=alert(1)>")
    expect(row.locator("img")).to_have_count(0)
    expect(
        page.locator("#findings-body tr").filter(has_text="positive_low_confidence")
    ).to_contain_text("Not detected")
    expect(
        page.locator("#findings-body tr").filter(has_text="positive_low_confidence")
    ).to_contain_text("0.20")
    expect(
        page.locator("#findings-body tr").filter(has_text="negative_low_confidence")
    ).to_contain_text("Present")
    expect(
        page.locator("#findings-body tr").filter(has_text="negative_low_confidence")
    ).to_contain_text("0.80")


@pytest.mark.parametrize("outcome", ["completed", "error"])
def test_model_download_requires_terms_and_reports_actual_layer_bytes(
    ui_page: Page, outcome: str
) -> None:
    page = ui_page
    inventory = [
        {"id": "heuristic-hu", "adapter": "heuristic", "available": True, "recommended": True},
        {
            "id": "gemma3-4b",
            "adapter": "ollama",
            "available": False,
            "recommended": True,
            "download_supported": True,
            "license": "Gemma Terms of Use",
            "terms_url": "https://ai.google.dev/gemma/terms",
            "tag": "gemma3:4b-test",
            "notes": "Synthetic provider metadata.",
            "setup_steps": ["Review model terms."],
        },
        {
            "id": "ct-clip",
            "adapter": "http_service",
            "available": False,
            "recommended": False,
            "download_supported": False,
            "license": "CC-BY-NC-SA-4.0",
            "notes": "Weights require publisher access.",
        },
    ]
    page.route("**/api/models", lambda route: route.fulfill(json={"models": inventory}))
    page.reload()
    page.locator("#create-demo").click()
    expect(page.locator("#run-analysis")).to_be_enabled()
    page.locator("#model-setup > summary").click()
    _check_download_setup(page)
    requested: list[dict[str, object]] = []

    def pull(route: Route) -> None:
        requested.append(route.request.post_data_json)
        route.fulfill(
            json={
                "id": "pull-test",
                "model_id": "gemma3-4b",
                "status": "running",
                "detail": "pulling layer",
                "completed": 25,
                "total": 100,
            }
        )

    page.route("**/api/models/gemma3-4b/pull", pull)
    page.route(
        "**/api/model-pulls/pull-test",
        lambda route: route.fulfill(
            json={
                "id": "pull-test",
                "model_id": "gemma3-4b",
                "status": outcome,
                "detail": "Synthetic terminal status",
                "completed": None,
                "total": None,
            }
        ),
    )
    _start_and_check_download(page, requested)
    inventory[1]["available"] = outcome == "completed"
    page.clock.fast_forward(1500)
    expect(page.locator("#pull-progress")).to_contain_text(
        "Download finished" if outcome == "completed" else "Download failed"
    )
    expect(page.locator("#pull-progress")).not_to_contain_text("25 / 100")
    expect(page.locator("#run-analysis")).to_be_enabled()
    page.locator("#language-toggle").click()
    expect(page.locator("#model-setup > summary")).to_have_text(
        "Modellverfügbarkeit und Einrichtung"
    )
    expect(page.locator("#pull-progress")).to_contain_text(
        "Download beendet" if outcome == "completed" else "Download fehlgeschlagen"
    )
    _check_control_tooltips(page)


def _check_download_setup(page: Page) -> None:
    gemma = page.locator("tr[data-setup-model='gemma3-4b']")
    expect(gemma).to_contain_text("Gemma Terms of Use")
    expect(gemma.get_by_role("link", name="Model terms")).to_have_attribute(
        "href", "https://ai.google.dev/gemma/terms"
    )
    expect(gemma.get_by_role("button", name="Download model weights")).to_be_disabled()
    service = page.locator("tr[data-setup-model='ct-clip']")
    expect(service).to_contain_text("required access approval")
    expect(service).to_contain_text("loopback HTTP service")
    expect(service.get_by_role("button")).to_have_count(0)


def _start_and_check_download(page: Page, requested: list[dict[str, object]]) -> None:
    gemma = page.locator("tr[data-setup-model='gemma3-4b']")
    assert requested == []
    gemma.get_by_role("checkbox").check()
    gemma.get_by_role("button", name="Download model weights").click()
    expect(page.locator("#pull-progress")).to_contain_text("Active layer bytes: 25 / 100")
    assert requested == [{"terms_acknowledged": True}]
    expect(page.locator("#run-analysis")).to_be_disabled()
    expect(page.locator("#create-demo")).to_be_disabled()
    expect(gemma.get_by_role("checkbox")).to_be_disabled()
    expect(page.locator("#refresh-models")).to_be_disabled()


def test_slice_target_help_and_actual_prepared_image_count_are_distinct(ui_page: Page) -> None:
    page = ui_page
    page.route(
        "**/api/models",
        lambda route: route.fulfill(
            json={
                "models": [
                    {"id": "medgemma1.5-q4", "available": True, "recommended": True},
                ]
            }
        ),
    )
    page.reload()
    page.locator("#create-demo").click()
    expect(page.locator("#run-analysis")).to_be_enabled()
    page.locator("#model-select").select_option("medgemma1.5-q4")
    page.locator("#image-count").fill("2")
    label = page.locator("label[for='image-count']")
    expect(label).to_have_text("Target source slices")
    label.focus()
    expect(page.get_by_role("tooltip")).to_contain_text("more landmark slices than requested")
    expect(page.get_by_role("tooltip")).to_contain_text(
        "coronal and multi-window views can add images"
    )

    jobs = MockJobs(page, lambda _model: _mock_model_output("medgemma1.5-q4"))
    page.locator("#run-analysis").click()
    expect(page.locator("#metric-images")).to_have_text("9")
    assert jobs.requests[0]["n_images"] == 2
    expect(page.locator("#image-count")).to_have_value("2")
    summary = page.locator("#prepared-image-summary")
    expect(summary).to_contain_text("Actual prepared model images")
    summary.focus()
    expect(page.get_by_role("tooltip")).to_contain_text("not the requested source-slice target")
    page.locator("#language-toggle").click()
    expect(label).to_have_text("Zielanzahl der Quellschichten")
    expect(summary).to_contain_text("Tatsächlich vorbereitete Modellbilder")
    expect(page.locator("#metric-images")).to_have_text("9")
    label.focus()
    expect(page.get_by_role("tooltip")).to_contain_text("mehr Landmarken-Schichten")
    summary.focus()
    expect(page.get_by_role("tooltip")).to_contain_text(
        "nicht die angeforderte Quellschicht-Zielanzahl"
    )


def test_tooltip_delay_cancels_on_leave_blur_switch_and_escape(ui_page: Page) -> None:
    page = ui_page
    page.clock.pause_at(page.evaluate("Date.now() / 1000 + 1"))
    theme = page.locator("#theme-toggle")
    language = page.locator("#language-toggle")
    tooltip = page.get_by_role("tooltip")
    theme.hover()
    expect(tooltip).to_be_hidden()
    page.clock.fast_forward(600)
    expect(tooltip).to_be_hidden()
    # Focus and hover on the same control preserve the existing dwell timer.
    theme.focus()
    page.clock.fast_forward(50)
    expect(tooltip).to_be_visible()
    expect(tooltip).to_contain_text("light and dark")
    language.hover()
    expect(tooltip).to_be_hidden()
    page.mouse.move(0, 0)
    page.clock.fast_forward(1000)
    expect(tooltip).to_be_hidden()
    language.focus()
    page.clock.fast_forward(400)
    language.blur()
    page.clock.fast_forward(1000)
    expect(tooltip).to_be_hidden()
    language.focus()
    page.clock.fast_forward(650)
    expect(tooltip).to_contain_text("English and German")
    language.press("Escape")
    expect(tooltip).to_be_hidden()
    page.clock.fast_forward(1000)
    expect(tooltip).to_be_hidden()
    # Escape also cancels a tooltip whose delay has not elapsed.
    theme.focus()
    page.clock.fast_forward(300)
    theme.press("Escape")
    page.clock.fast_forward(1000)
    expect(tooltip).to_be_hidden()


def test_library_search_groups_recovery_and_mobile_progression(ui_page: Page) -> None:
    page = ui_page
    page.locator("#create-demo").click()
    expect(page.locator("#run-analysis")).to_be_enabled()
    png = page.request.get(f"{page.url.rstrip('/')}/api/studies/demo/phantom/slice/0.png").body()
    page.route("**/slice/**", lambda route: route.fulfill(body=png, content_type="image/png"))
    rows = [
        {
            "dataset": "demo",
            "case_id": "phantom",
            "n_slices": 64,
            "phase": "synthetic",
            "qc_adequate": True,
        },
        {
            "dataset": "synthetic_development",
            "case_id": "synthetic-a",
            "n_slices": 64,
            "phase": "calibration",
            "qc_adequate": True,
        },
        {
            "dataset": "synthetic_other",
            "case_id": "synthetic-b",
            "n_slices": 64,
            "phase": "internal_test",
            "qc_adequate": True,
        },
    ]
    libraries = [
        {"dataset": "synthetic_missing", "status": "not_indexed", "available_studies": 0},
        {"dataset": "synthetic_unsplit", "status": "split_required", "available_studies": 0},
    ]
    refreshed: list[str] = []

    def library(route: Route) -> None:
        refreshed.append(route.request.url)
        route.fulfill(json={"studies": rows, "libraries": libraries})

    page.route("**/api/studies", library)
    page.reload()
    expect(page.locator("#study-select")).to_have_value("1")
    expect(page.locator("#study-select optgroup")).to_have_count(3)
    expect(page.locator("#library-counts")).to_contain_text("2 development studies")
    expect(page.locator("#library-status")).to_contain_text("Development index missing")
    expect(page.locator("#library-status")).to_contain_text("Create the development/sealed split")
    page.locator("#study-search").fill("synthetic-b")
    expect(page.locator("#study-select option")).to_have_count(1)
    expect(page.locator("#study-select")).to_have_value("2")
    page.locator("#dataset-filter").select_option("synthetic_development")
    expect(page.locator("#study-select")).to_contain_text("No matching studies")
    expect(page.locator("#run-analysis")).to_be_disabled()
    page.locator("#study-search").fill("")
    expect(page.locator("#study-select")).to_have_value("1")
    page.locator("#dataset-filter").select_option("")
    page.locator("#study-select").select_option("1")
    rows[:] = [rows[1], rows[2], rows[0]]
    with page.expect_response("**/api/studies"):
        page.locator("#refresh-studies").click()
    expect(page.locator("#library-counts")).to_contain_text("3 / 3 visible")
    expect(page.locator("#study-select")).to_have_value("0")
    expect(page.locator("#study-select option:checked")).to_have_text("synthetic-a")
    assert len(refreshed) == 2
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate(
        "document.querySelector('#study-panel').getBoundingClientRect().top < "
        "document.querySelector('.viewer-panel').getBoundingClientRect().top && "
        "document.querySelector('.viewer-panel').getBoundingClientRect().top < "
        "document.querySelector('#model-panel').getBoundingClientRect().top"
    )
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_about_history_preserves_pending_analysis_and_result_context(ui_page: Page) -> None:
    page = ui_page
    page.locator("#create-demo").click()
    expect(page.locator("#run-analysis")).to_be_enabled()
    jobs = MockJobs(page, lambda _model: "hold")
    page.locator("#run-analysis").click()
    expect(page.locator("#job-bar")).to_be_visible()
    page.locator("#nav-about").click()
    expect(page.locator("#about-page")).to_be_visible()
    expect(page.locator("#job-bar")).to_contain_text("Running: Analysis")
    expect(page.locator("#libraries-table")).to_contain_text("fastapi")
    page.clock.fast_forward(2000)
    page.go_back()
    expect(page.locator("#analysis-page")).to_be_visible()
    expect(page.locator("#request-timer")).to_be_visible()
    assert len(jobs.requests) == 1
    jobs.finish(_mock_model_output("heuristic-hu"))
    page.clock.fast_forward(1000)
    expect(page.locator("#result-context")).to_contain_text("demo / phantom")
    href = page.locator("#download-html").get_attribute("href")
    page.locator("#nav-about").click()
    page.locator("#nav-analysis").click()
    expect(page.locator("#download-html")).to_have_attribute("href", href or "")
    page.locator("#image-count").evaluate(
        "element => {element.value = '8'; element.dispatchEvent(new Event('input'));}"
    )
    expect(page.locator("#previous-settings")).to_be_visible()
    expect(page.locator("#result-context")).to_contain_text("Target source slices: 4")
    expect(page.locator("#download-html")).to_have_attribute("href", href or "")
    page.locator("#image-count").evaluate(
        "element => {element.value = '4'; element.dispatchEvent(new Event('input'));}"
    )
    expect(page.locator("#previous-settings")).to_be_hidden()
    page.locator("#image-count").evaluate(
        "element => {element.value = '8'; element.dispatchEvent(new Event('input'));}"
    )
    allowed = "['thoraxbench.language', 'thoraxbench.theme', 'thoraxbench.duration-history']"
    assert page.evaluate(f"Object.keys(localStorage).every(key => {allowed}.includes(key))")
    page.go_back()
    expect(page.locator("#about-page")).to_be_visible()
    page.go_forward()
    expect(page.locator("#analysis-page")).to_be_visible()
    expect(page.locator("#previous-settings")).to_be_visible()


def test_translated_findings_and_education_require_explicit_presentation(ui_page: Page) -> None:
    page = ui_page
    page.locator("#create-demo").click()
    expect(page.locator("#run-analysis")).to_be_enabled()
    response = _mock_model_output("heuristic-hu")
    response["presentation"] = {
        "findings": [
            {
                "finding_index": 0,
                "label": "pulmonary_nodule",
                "status": "present",
                "severity": "moderate",
                "attention": "soon",
            }
        ]
    }
    MockJobs(page, lambda _model: response)
    page.locator("#run-analysis").click()
    row = page.locator("#findings-body tr").filter(has_text="pulmonary_nodule")
    expect(row).to_contain_text("Pulmonary nodule")
    expect(row.locator("td").nth(5)).to_have_text("Moderate")
    expect(row.locator("td").nth(6)).to_have_text("Earlier review")
    page.locator("#language-toggle").click()
    expect(row).to_contain_text("Lungenrundherd")
    expect(row).to_contain_text("pulmonary_nodule")
    expect(row.locator("td").nth(5)).to_have_text("Mäßig")
    response.pop("presentation")
    page.locator("#run-analysis").click()
    expect(row.locator("td").nth(5)).to_have_text("—")
    expect(row.locator("td").nth(6)).to_have_text("—")


def test_help_descriptions_are_stable_and_tooltip_is_hoverable(ui_page: Page) -> None:
    page = ui_page
    page.clock.pause_at(page.evaluate("Date.now() / 1000 + 1"))
    theme = page.locator("#theme-toggle")
    language = page.locator("#language-toggle")
    theme_description = theme.get_attribute("aria-describedby")
    language_description = language.get_attribute("aria-describedby")
    assert theme_description != language_description
    theme.hover()
    page.clock.fast_forward(650)
    tooltip = page.get_by_role("tooltip")
    expect(tooltip).to_be_visible()
    tooltip.hover()
    page.clock.fast_forward(1000)
    expect(tooltip).to_be_visible()
    expect(theme).to_have_accessible_description(re.compile("light and dark"))
    expect(language).to_have_accessible_description(re.compile("English and German"))
    page.keyboard.press("Escape")
    expect(tooltip).to_be_hidden()


def test_slice_failure_has_specific_recovery_and_clears_after_success(ui_page: Page) -> None:
    page = ui_page
    page.locator("#create-demo").click()
    expect(page.locator("#run-analysis")).to_be_enabled()
    page.route("**/slice/**", lambda route: route.fulfill(status=500, body="Synthetic failure"))
    page.locator("#slice-slider").press("ArrowRight")
    expect(page.locator("#viewer-empty-title")).to_have_text("Slice unavailable")
    expect(page.locator("#viewer-empty-note")).to_contain_text("another slice or display window")
    expect(page.locator("#viewer-empty-note")).not_to_contain_text("demo")
    page.locator("#language-toggle").click()
    expect(page.locator("#viewer-empty-title")).to_have_text("Schicht nicht verfügbar")
    page.unroute("**/slice/**")
    page.locator("#window-select").select_option("bone")
    page.wait_for_function(
        "document.querySelector('#ct-image').complete && "
        "document.querySelector('#ct-image').naturalWidth > 0"
    )
    expect(page.locator("#viewer-empty")).to_be_hidden()
    expect(page.locator("#notice")).to_be_hidden()


def test_about_github_link_is_translated_and_explained(ui_page: Page) -> None:
    page = ui_page
    page.locator("#nav-about").click()
    link = page.locator("#about-github")
    expect(link).to_have_attribute("href", "https://github.com/marcelpetrick/ThoraxGPT_from_Wish")
    expect(link).to_have_attribute("target", "_blank")
    expect(link).to_have_attribute("rel", "noopener noreferrer")
    expect(link).to_have_text("GitHub: fork and contribute")
    link.focus()
    page.clock.fast_forward(600)
    expect(page.get_by_role("tooltip")).to_contain_text("contribute")
    page.locator("#language-toggle").click()
    expect(link).to_contain_text("mitwirken")
    link.focus()
    page.clock.fast_forward(600)
    expect(page.get_by_role("tooltip")).to_contain_text("GitHub")


def test_direct_about_and_nearby_model_setup_are_reachable(ui_page: Page) -> None:
    page = ui_page
    page.goto(f"{page.url.rstrip('/')}/about")
    expect(page.locator("#about-page")).to_be_visible()
    expect(page.locator("#libraries-table")).to_contain_text("fastapi")
    page.locator("#nav-analysis").click()
    expect(page.locator("#analysis-page")).to_be_visible()
    page.locator("#open-model-setup").click()
    expect(page.locator("#model-setup")).to_have_attribute("open", "")
    expect(page.locator("#model-setup-body tr:focus")).to_have_count(1)
    expect(page.locator("#model-setup-table")).to_be_visible()


def _check_comparison_preserved_after_study_change(page: Page) -> None:
    combined = page.locator("#comparison-download").get_attribute("href")
    model_link = page.locator("#comparison-body tr[data-model='heuristic-hu'] a").first
    individual = model_link.get_attribute("href")
    png = page.request.get(f"{page.url.rstrip('/')}/api/studies/demo/phantom/slice/0.png").body()
    page.route("**/slice/**", lambda route: route.fulfill(body=png, content_type="image/png"))
    studies = [
        {
            "dataset": "demo",
            "case_id": case,
            "n_slices": 64,
            "phase": "synthetic",
            "qc_adequate": True,
        }
        for case in ["phantom", "phantom-other"]
    ]
    page.route("**/api/studies", lambda route: route.fulfill(json={"studies": studies}))
    with page.expect_response("**/api/studies"):
        page.locator("#refresh-studies").click()
    page.locator("#study-search").fill("phantom-other")
    expect(page.locator("#comparison-previous-settings")).to_be_visible()
    expect(page.locator("#comparison-download")).to_have_attribute("href", combined or "")
    page.locator("#study-search").fill("")
    page.locator("#study-select").select_option("1")
    expect(model_link).to_have_attribute("href", individual or "")
    page.locator("#comparison-body tr[data-model='heuristic-hu'] button").click()
    expect(page.locator("#result-context")).to_contain_text("demo / phantom")
    expect(page.locator("#previous-settings")).to_be_visible()
    expect(page.locator("#comparison-download")).to_have_attribute("href", combined or "")


CONTRAST_SCRIPT = r"""() => {
  const luminance = color => {
    const rgb = color.match(/[\d.]+/g).slice(0,3).map(Number).map(value => value / 255);
    const linear = rgb.map(
      value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
    );
    return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
  };
  const pairs = [
    ['.page-heading p', 'body'],
    ['.research-banner', '.research-banner'],
    ['#study-phase', '#study-phase'],
  ];
  return pairs.map(([text, background]) => {
    const foreground = luminance(getComputedStyle(document.querySelector(text)).color);
    const behind = luminance(
      getComputedStyle(document.querySelector(background)).backgroundColor
    );
    return (Math.max(foreground, behind) + 0.05) / (Math.min(foreground, behind) + 0.05);
  });
}"""


def test_small_text_contrast_in_primary_muted_and_badge_contexts(ui_page: Page) -> None:
    page = ui_page
    for _ in range(2):
        ratios = page.evaluate(CONTRAST_SCRIPT)
        assert all(ratio >= 4.5 for ratio in ratios), ratios
        page.locator("#theme-toggle").click()


def test_p6_controls_keep_one_image_and_explain_failed_readiness(ui_page: Page) -> None:
    page = ui_page
    page.locator("#model-select").select_option("medgemma1.5-q4-p6")
    expect(page.locator("#image-count")).to_have_value("1")
    expect(page.locator("#image-count")).to_be_disabled()
    expect(page.locator("#model-input-note")).to_contain_text("failed")
    page.locator("#language-toggle").click()
    expect(page.locator("#model-input-note")).to_contain_text("nicht bestanden")
    page.locator("#model-select").select_option("gemma3-4b")
    expect(page.locator("#image-count")).to_be_enabled()
