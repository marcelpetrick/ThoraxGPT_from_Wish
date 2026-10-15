# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Browser acceptance of the local workbench using generated synthetic data only."""

from __future__ import annotations

import json
import re
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from playwright.sync_api import Page, Route, expect, sync_playwright

from thoraxbench.config import Settings

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def ui_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    from thoraxbench.api.app import create_app

    settings = Settings(
        data_dir=tmp_path_factory.mktemp("ui-synthetic"), ollama_url="http://127.0.0.1:1"
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    address = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(base_url=address, timeout=1.0) as client:
            for _ in range(100):
                if server.started:
                    assert client.get("/").status_code == 200
                    break
                if not thread.is_alive():
                    pytest.fail("local workbench server stopped during startup")
                time.sleep(0.05)
            else:
                pytest.fail("local workbench server did not start")
        yield address
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()


@pytest.fixture
def ui_page(ui_server: str) -> Iterator[Page]:
    with sync_playwright() as playwright:
        default = Path(playwright.chromium.executable_path)
        candidates = sorted(
            (Path.home() / ".cache" / "ms-playwright").glob("chromium-*/chrome-linux*/chrome")
        )
        executable = default if default.exists() else candidates[-1] if candidates else default
        browser = playwright.chromium.launch(executable_path=str(executable))
        context = browser.new_context(locale="de-DE", color_scheme="dark", accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(15_000)
        page.goto(ui_server)
        yield page
        context.close()
        browser.close()


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
    expect(page.locator("#download-json")).to_be_visible(timeout=30_000)
    expect(page.get_by_role("table").first).to_be_visible()
    expect(page.get_by_role("table").first).to_contain_text(re.compile("nodule", re.I))
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
    _check_html_export(page, tmp_path)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    _check_about(page, language)


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
    nodule = page.locator("#findings-table tbody tr").filter(has_text="pulmonary nodule")
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
    page.route("**/api/analyze", lambda route: route.fulfill(json=response))
    page.locator("#run-analysis").click()
    expect(page.locator("#metric-status")).to_have_text("Abstained")
    expect(page.locator("#notice")).to_contain_text("The engine abstained")
    row = page.locator("#findings-body tr").first
    expect(row).to_have_text("No prediction")
    expect(row).not_to_contain_text("<img src=x onerror=alert(1)>")
    expect(row.locator("img")).to_have_count(0)
    page.locator("#language-toggle").click()
    expect(page.locator("#metric-status")).to_have_text("Enthaltung")
    expect(page.locator("#slice-slider")).to_have_attribute("aria-valuetext", re.compile("Schicht"))
    page.unroute("**/api/analyze")
    page.route(
        "**/api/analyze",
        lambda route: route.fulfill(status=503, json={"detail": "Synthetic service offline"}),
    )
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
    expect(page.get_by_text(re.compile("GPL-3.0", re.I)).first).to_be_visible()
    _check_research_disclaimer(page, language)
    licenses = page.get_by_role("table").first
    expect(licenses).to_be_visible()
    expect(licenses).to_contain_text("fastapi")
    expect(licenses).to_contain_text("pydantic")


@pytest.mark.parametrize("outcome", ["completed", "error"])
def test_request_elapsed_advances_while_pending_and_freezes(ui_page: Page, outcome: str) -> None:
    page = ui_page
    page.locator("#create-demo").click()
    expect(page.locator("#run-analysis")).to_be_enabled()
    expect(page.locator("#request-forecast")).to_contain_text("Initial workstation guess")
    pending: list[Route] = []

    def hold_request(route: Route) -> None:
        pending.append(route)

    page.route("**/api/analyze", hold_request)
    page.clock.install()
    page.locator("#run-analysis").click()
    expect(page.locator("#request-timer")).to_be_visible()
    assert len(pending) == 1
    expect(page.locator("#request-elapsed")).to_have_text("0.0 s")
    page.clock.fast_forward(1300)
    expect(page.locator("#request-elapsed")).to_have_text("1.3 s")
    page.clock.fast_forward(60_000)
    expect(page.locator("#request-forecast")).to_have_text(
        "Taking longer than estimated; still running"
    )
    expect(page.locator("#request-elapsed")).to_have_attribute("aria-live", "off")
    expect(page.locator("#run-analysis")).to_be_disabled()
    page.locator("#language-toggle").click()
    expect(page.locator("#request-timer")).to_contain_text("Verstrichene Anfragezeit im Browser")
    if outcome == "completed":
        pending[0].fulfill(json=_mock_model_output("heuristic-hu"))
        expect(page.locator("#metric-time")).to_have_text("0.100 s")
    else:
        pending[0].fulfill(status=503, json={"detail": "Synthetic service offline"})
        expect(page.locator("#notice")).to_contain_text("Anfrage fehlgeschlagen")
    expect(page.locator("#run-analysis")).to_be_enabled()
    stopped = page.locator("#request-elapsed").inner_text()
    page.clock.fast_forward(5000)
    expect(page.locator("#request-elapsed")).to_have_text(stopped)
    page.locator("#study-select").dispatch_event("change")
    expect(page.locator("#request-timer")).to_be_hidden()
    if outcome == "completed":
        expect(page.locator("#request-forecast")).to_contain_text(
            "Aus lokalem Anfrageverlauf geschätzt"
        )
        history = page.evaluate("JSON.parse(localStorage.getItem('thoraxbench.duration-history'))")
        assert set(history) == {"heuristic-hu:4"}
        assert all(isinstance(value, (int, float)) for value in history["heuristic-hu:4"])
    else:
        assert page.evaluate("localStorage.getItem('thoraxbench.duration-history')") is None


def _mock_model_output(model_id: str, *, abstain: bool = False) -> dict[str, object]:
    return {
        "id": f"run-{model_id}",
        "result": {
            "model_id": model_id,
            "perf": {"total_s": 0.1},
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
    pending: list[Route] = []
    requested: list[str] = []

    def respond(route: Route) -> None:
        model = route.request.post_data_json["model_id"]
        requested.append(model)
        if model == "heuristic-hu":
            pending.append(route)
        elif model == "qwen3-vl-4b":
            route.fulfill(status=503, json={"detail": "Synthetic service offline"})
        else:
            response = _mock_model_output(model, abstain=model == "medgemma1.5-q4")
            if model == "medgemma1.5-q8":
                response["result"]["report"]["findings"].insert(
                    0, {"label": "pulmonary_nodule", "present": False, "confidence": 0.9}
                )
            route.fulfill(json=response)

    export_requests: list[dict[str, object]] = []

    def export(route: Route) -> None:
        export_requests.append(route.request.post_data_json)
        route.fulfill(json={"downloads": {"html": "/mock/comparison.html"}})

    page.route("**/api/analyze", respond)
    page.route("**/api/compare", export)
    page.clock.install()
    page.locator("#run-analysis").click()
    expect(page.locator("#batch-status")).to_contain_text("heuristic-hu")
    assert requested == ["heuristic-hu"]
    expect(page.locator("#compare-models")).to_be_disabled()
    page.clock.fast_forward(2100)
    expect(page.locator("#model-elapsed")).to_have_text("2.1 s")
    pending[0].fulfill(json=_mock_model_output("heuristic-hu"))
    expect(page.locator("#comparison-download")).to_be_visible()
    _check_comparison_results(page, requested, export_requests)


def _check_comparison_results(
    page: Page, requested: list[str], export_requests: list[dict[str, object]]
) -> None:
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
    expect(page.locator("#comparison-findings-table")).to_contain_text("pulmonary nodule")
    expect(page.locator("#comparison-findings-table")).to_contain_text("0.80")
    expect(page.locator("#comparison-findings-body tr td").nth(3)).to_have_text(
        "Not detected · 0.10; Present · 0.80"
    )
    expect(page.locator("#comparison-panel")).to_contain_text(
        "not directly comparable across model families"
    )
    assert len(export_requests) == 1
    assert len(export_requests[0]["result_ids"]) == 3
    assert {entry["status"] for entry in export_requests[0]["omissions"]} == {"skipped", "error"}
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
    expect(page.locator("#comparison-body")).not_to_contain_text("Synthetic service offline")
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
    page.route("**/api/analyze", lambda route: route.fulfill(json=response))
    page.locator("#run-analysis").click()
    row = page.locator("#findings-body tr").first
    expect(row.locator("td").nth(1)).to_have_text("Uncertain")
    expect(row.locator("td").nth(2)).to_have_text("—")
    expect(row).to_contain_text("<img src=x onerror=alert(1)>")
    expect(row.locator("img")).to_have_count(0)
    expect(page.locator("#findings-body tr").nth(1)).to_contain_text("Not detected")
    expect(page.locator("#findings-body tr").nth(1)).to_contain_text("0.20")
    expect(page.locator("#findings-body tr").nth(2)).to_contain_text("Present")
    expect(page.locator("#findings-body tr").nth(2)).to_contain_text("0.80")


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
    page.clock.install()
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
