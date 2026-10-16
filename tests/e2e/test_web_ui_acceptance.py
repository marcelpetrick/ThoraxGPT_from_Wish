# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""UX-01…UX-08 acceptance checks (docs/ux-review-2026-10-16.md) on synthetic data only.

Model boundaries are mocked in the browser; studies are the code-generated phantom or
mocked synthetic library rows. No real study, model or network service is involved.
"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import Page, Route, expect

pytestmark = pytest.mark.e2e

ALLOWED_STORAGE = "['thoraxbench.language', 'thoraxbench.theme', 'thoraxbench.duration-history']"


def _output(model_id: str, findings: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": f"run-{model_id}",
        "result": {
            "model_id": model_id,
            "perf": {"total_s": 0.1, "n_images": 0 if model_id == "heuristic-hu" else 9},
            "report": {"abstain": False, "findings": findings},
            "raw_error": None,
        },
        "markdown": "Research use only. Synthetic mocked model output, not medical advice.",
        "downloads": {"html": f"/mock/{model_id}.html"},
    }
    body.update(extra)
    return body


NODULE = {"label": "pulmonary_nodule", "present": True, "confidence": 0.8}


def _inventory(page: Page, models: list[dict[str, Any]]) -> None:
    page.route("**/api/models", lambda route: route.fulfill(json={"models": models}))
    page.reload()


def _demo(page: Page) -> None:
    page.locator("#create-demo").click()
    expect(page.locator("#run-analysis")).to_be_enabled()


def _neutral(page: Page) -> tuple[float, float]:
    box = page.locator("#analysis-page .page-heading h1").bounding_box()
    assert box is not None
    return box["x"] + 5, box["y"] + box["height"] / 2


def _study_rows(*cases: tuple[str, str]) -> list[dict[str, Any]]:
    return [
        {"dataset": dataset, "case_id": case, "n_slices": 64, "phase": "calibration"}
        | {"qc_adequate": True}
        for dataset, case in cases
    ]


def test_ux01_empty_unavailable_library_and_identity_refresh(ui_page: Page) -> None:
    page = ui_page
    png = page.request.get(f"{page.url.rstrip('/')}/api/studies/demo/phantom/slice/0.png")
    page.route(
        "**/slice/**", lambda route: route.fulfill(body=png.body(), content_type="image/png")
    )
    state: dict[str, Any] = {
        "studies": [],
        "libraries": [
            {"dataset": "synthetic_broken", "status": "unavailable", "available_studies": 0},
            {"dataset": "synthetic_empty", "status": "ready", "available_studies": 0},
        ],
    }
    page.route("**/api/studies", lambda route: route.fulfill(json=state))
    page.reload()
    expect(page.locator("#study-select")).to_contain_text("No studies available")
    expect(page.locator("#library-status")).to_contain_text("synthetic_broken: Library unavailable")
    expect(page.locator("#library-status")).to_contain_text(
        "synthetic_empty: Indexed development library ready (0)"
    )
    expect(page.locator("#viewer-empty-note")).to_contain_text("refresh the library")
    expect(page.locator("#refresh-studies")).to_be_enabled()
    expect(page.locator("#run-analysis")).to_be_disabled()
    page.locator("#language-toggle").click()
    expect(page.locator("#library-status")).to_contain_text("Bestand nicht verfügbar")
    expect(page.locator("#study-select")).to_contain_text("Keine Studien verfügbar")
    page.locator("#language-toggle").click()
    # Recovery: the operator indexes studies, then refreshes; nothing else is needed.
    state["studies"] = _study_rows(("synthetic_a", "case-1"), ("synthetic_b", "case-2"))
    state["libraries"][1] = {"dataset": "synthetic_a", "status": "ready", "available_studies": 1}
    with page.expect_response("**/api/studies"):
        page.locator("#refresh-studies").click()
    expect(page.locator("#library-counts")).to_contain_text("2 / 2 visible")
    page.locator("#study-select").select_option(label="case-2")
    slider = page.locator("#slice-slider")
    slider.fill("5")
    slider.dispatch_event("input")
    # Reordered refresh and unrelated search input keep the same study and slice.
    state["studies"] = list(reversed(state["studies"]))
    with page.expect_response("**/api/studies"):
        page.locator("#refresh-studies").click()
    expect(page.locator("#study-select option:checked")).to_have_text("case-2")
    expect(slider).to_have_value("5")
    page.locator("#study-search").fill("case")
    expect(slider).to_have_value("5")
    # A removed selection never resolves to whichever study now occupies its old index.
    state["studies"] = _study_rows(("synthetic_a", "case-1"), ("synthetic_c", "case-3"))
    page.locator("#study-search").fill("")
    with page.expect_response("**/api/studies"):
        page.locator("#refresh-studies").click()
    expect(page.locator("#study-select option:checked")).to_have_text("case-1")
    expect(page.locator("#slice-counter")).to_have_text("33 / 64")


def _tab_sequence(page: Page) -> list[str]:
    page.locator("#study-search").focus()
    order = ["study-search"]
    for _ in range(60):
        page.keyboard.press("Tab")
        identifier = page.evaluate("document.activeElement.id")
        order.append(identifier)
        if identifier == "run-analysis":
            break
    return order


@pytest.mark.parametrize(("language", "theme"), [("en", "light"), ("de", "dark")])
def test_ux02_mobile_visual_and_keyboard_order(ui_page: Page, language: str, theme: str) -> None:
    page = ui_page
    _demo(page)
    if language == "de":
        page.locator("#language-toggle").click()
    if theme == "dark":
        page.locator("#theme-toggle").click()
    page.route(
        "**/api/analyze", lambda route: route.fulfill(json=_output("heuristic-hu", [NODULE]))
    )
    page.locator("#run-analysis").click()
    expect(page.locator("#results-content")).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("window.scrollTo(0, 0)")
    expect(page.locator("#study-search")).to_be_in_viewport()
    order = _tab_sequence(page)
    focus_points = ["study-select", "slice-slider", "model-select", "run-analysis"]
    assert all(point in order for point in focus_points), order
    assert [order.index(point) for point in focus_points] == sorted(
        order.index(point) for point in focus_points
    )
    tops = page.evaluate(
        "ids => ids.map(id => document.getElementById(id).getBoundingClientRect().top + scrollY)",
        focus_points,
    )
    assert tops == sorted(tops), tops
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    for _ in range(2):
        page.locator("#language-toggle").click()
        page.locator("#theme-toggle").click()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_ux03_grouping_unknown_labels_and_abstention_downloads(ui_page: Page) -> None:
    page = ui_page
    _demo(page)
    findings = [
        {"label": "emphysema", "present": False, "confidence": 0.9},
        {"label": "<b>synthetic_unknown</b>", "present": None, "confidence": None},
        NODULE,
        {"label": "pleural_effusion", "present": True, "confidence": 0.3},
        {"label": "<i>unknown_positive</i>", "present": True, "confidence": 0.7},
    ]
    presentation = {
        "findings": [
            {"finding_index": 2, "label": "pulmonary_nodule", "status": "present"}
            | {"severity": "moderate", "attention": "soon"},
            # A mismatched presentation for an absent finding must never be displayed.
            {"finding_index": 0, "label": "emphysema", "status": "absent"}
            | {"severity": "low", "attention": "routine"},
        ]
    }
    response = _output("heuristic-hu", findings, presentation=presentation)
    page.route("**/api/analyze", lambda route: route.fulfill(json=response))
    page.locator("#run-analysis").click()
    rows = page.locator("#findings-body tr")
    expect(rows).to_have_count(5)
    codes = [code.inner_text() for code in page.locator("#findings-body code").all()]
    assert codes == [
        "pulmonary_nodule",
        "<i>unknown_positive</i>",
        "<b>synthetic_unknown</b>",
        "emphysema",
        "pleural_effusion",
    ]
    expect(page.locator("#findings-body i, #findings-body b")).to_have_count(0)
    expect(rows.nth(0).locator("td").nth(5)).to_have_text("Moderate")
    for index in range(1, 5):
        expect(rows.nth(index).locator("td").nth(5)).to_have_text("—")
        expect(rows.nth(index).locator("td").nth(6)).to_have_text("—")
    expect(page.locator("#results-content")).to_contain_text("not advice for this study")
    abstained = _output(
        "heuristic-hu",
        [NODULE],
        presentation=presentation,
        downloads={"json": "/mock/a.json", "markdown": "/mock/a.md", "html": "/mock/a.html"},
    )
    abstained["result"]["report"]["abstain"] = True
    page.unroute("**/api/analyze")
    page.route("**/api/analyze", lambda route: route.fulfill(json=abstained))
    page.locator("#run-analysis").click()
    expect(page.locator("#metric-status")).to_have_text("Abstained")
    expect(rows).to_have_count(1)
    expect(rows.first).to_have_text("No prediction")
    for identifier, href in [
        ("download-json", "/mock/a.json"),
        ("download-report", "/mock/a.md"),
        ("download-html", "/mock/a.html"),
    ]:
        expect(page.locator(f"#{identifier}")).to_have_attribute("aria-disabled", "false")
        expect(page.locator(f"#{identifier}")).to_have_attribute("href", href)


SETUP_INVENTORY = [
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
    },
    {
        "id": "ct-clip",
        "adapter": "http_service",
        "available": False,
        "recommended": False,
        "download_supported": False,
        "license": "CC-BY-NC-SA-4.0",
    },
]


def test_ux04_selection_leads_to_matching_setup_without_download(ui_page: Page) -> None:
    page = ui_page
    pulls: list[str] = []

    def pull(route: Route) -> None:
        pulls.append(route.request.url)
        route.fulfill(status=500, json={"detail": "unexpected"})

    page.route("**/pull", pull)
    _inventory(page, SETUP_INVENTORY)
    _demo(page)
    expect(page.locator("#model-input-note")).to_contain_text("does not send images")
    page.locator("#model-select").select_option("ct-clip")
    expect(page.locator("#model-status")).to_contain_text("open model setup for this model")
    expect(page.locator("#model-input-note")).to_contain_text("configured local HTTP service")
    expect(page.locator("#model-input-note")).not_to_contain_text("does not send images")
    expect(page.locator("#run-analysis")).to_be_disabled()
    page.locator("#open-model-setup").click()
    focused = page.locator("#model-setup-body tr:focus")
    expect(focused).to_have_attribute("data-setup-model", "ct-clip")
    expect(focused).to_contain_text("loopback HTTP service")
    expect(focused.get_by_role("button")).to_have_count(0)
    page.locator("#model-select").select_option("gemma3-4b")
    expect(page.locator("#model-input-note")).to_contain_text("Vision models use prepared images")
    page.locator("#open-model-setup").click()
    focused = page.locator("#model-setup-body tr:focus")
    expect(focused).to_have_attribute("data-setup-model", "gemma3-4b")
    row = page.locator("tr[data-setup-model='gemma3-4b']")
    download = row.get_by_role("button", name="Download model weights")
    expect(download).to_be_disabled()
    row.get_by_role("checkbox").check()
    expect(download).to_be_enabled()
    assert pulls == []
    page.locator("#model-select").select_option("heuristic-hu")
    expect(page.locator("#run-analysis")).to_be_enabled()
    expect(page.locator("#model-input-note")).to_contain_text("does not send images")
    assert pulls == []


def test_ux05_session_notice_selection_and_storage(ui_page: Page) -> None:
    page = ui_page
    _demo(page)
    selected = page.locator("#study-select").input_value()
    pending: list[Route] = []
    page.route("**/api/analyze", lambda route: pending.append(route))  # noqa: PLW0108
    page.locator("#run-analysis").click()
    expect(page.locator("#session-status")).to_be_hidden()
    page.locator("#nav-about").click()
    expect(page.locator("#session-status")).to_be_visible()
    expect(page.locator("#session-status")).to_contain_text("does not cancel or repeat it")
    page.locator("#language-toggle").click()
    expect(page.locator("#session-status")).to_contain_text("bricht sie weder ab")
    page.locator("#nav-analysis").click()
    expect(page.locator("#session-status")).to_be_hidden()
    pending[0].fulfill(json=_output("heuristic-hu", [NODULE]))
    expect(page.locator("#run-analysis")).to_be_enabled()
    page.locator("#nav-about").click()
    expect(page.locator("#session-status")).to_be_hidden()
    page.locator("#nav-analysis").click()
    expect(page.locator("#study-select")).to_have_value(selected)
    expect(page.locator("#download-html")).to_have_attribute("href", "/mock/heuristic-hu.html")
    assert len(pending) == 1
    assert page.evaluate("sessionStorage.length") == 0
    assert page.evaluate(f"Object.keys(localStorage).every(key => {ALLOWED_STORAGE}.includes(key))")
    stored = page.evaluate("JSON.stringify(Object.values(localStorage))")
    assert "phantom" not in stored
    assert "Synthetic mocked model output" not in stored


def test_ux06_hover_grace_escape_and_tab_help(ui_page: Page) -> None:
    page = ui_page
    page.clock.pause_at(page.evaluate("Date.now() / 1000 + 1"))
    tooltip = page.get_by_role("tooltip")
    theme = page.locator("#theme-toggle")
    theme.hover()
    page.clock.fast_forward(649)
    expect(tooltip).to_be_hidden()
    page.clock.fast_forward(1)
    expect(tooltip).to_be_visible()
    trigger = theme.bounding_box()
    assert trigger is not None
    # Pointer travel through the gap keeps the tooltip during the 180 ms grace period.
    page.mouse.move(trigger["x"] + 4, trigger["y"] + trigger["height"] + 3)
    page.clock.fast_forward(150)
    expect(tooltip).to_be_visible()
    box = tooltip.bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.clock.fast_forward(2000)
    expect(tooltip).to_be_visible()
    expect(tooltip).to_contain_text("light and dark")
    page.mouse.move(*_neutral(page))
    page.clock.fast_forward(170)
    expect(tooltip).to_be_visible()
    page.clock.fast_forward(20)
    expect(tooltip).to_be_hidden()
    # Escape dismisses without moving focus; pointer jitter on the same trigger stays dismissed.
    theme.hover()
    page.clock.fast_forward(650)
    expect(tooltip).to_be_visible()
    focused_before = page.evaluate("document.activeElement.id")
    page.keyboard.press("Escape")
    expect(tooltip).to_be_hidden()
    assert page.evaluate("document.activeElement.id") == focused_before
    page.mouse.move(trigger["x"] + 6, trigger["y"] + 6)
    page.clock.fast_forward(1000)
    expect(tooltip).to_be_hidden()
    page.mouse.move(*_neutral(page))
    theme.hover()
    page.clock.fast_forward(650)
    expect(tooltip).to_be_visible()


def test_ux06_tab_between_controls_exposes_own_help(ui_page: Page) -> None:
    page = ui_page
    page.clock.pause_at(page.evaluate("Date.now() / 1000 + 1"))
    tooltip = page.get_by_role("tooltip")
    theme = page.locator("#theme-toggle")
    # Tab between two controls: each exposes its own help, never a stale description.
    language = page.locator("#language-toggle")
    language.focus()
    page.clock.fast_forward(650)
    expect(tooltip).to_contain_text("English and German")
    page.keyboard.press("Tab")
    expect(theme).to_be_focused()
    page.clock.fast_forward(650)
    expect(tooltip).to_contain_text("light and dark")
    expect(tooltip).not_to_contain_text("English and German")
    expect(theme).to_have_accessible_description(tooltip.inner_text())
    page.keyboard.press("Shift+Tab")
    page.clock.fast_forward(650)
    expect(tooltip).to_contain_text("English and German")
    expect(language).to_have_accessible_description(tooltip.inner_text())


def test_ux07_model_and_target_changes_mark_previous_result(ui_page: Page) -> None:
    page = ui_page
    models = [
        {"id": "heuristic-hu", "adapter": "heuristic", "available": True, "recommended": True},
        {"id": "medgemma1.5-q4", "adapter": "ollama", "available": True, "recommended": True},
    ]
    _inventory(page, models)
    _demo(page)
    requests: list[str] = []

    def respond(route: Route) -> None:
        requests.append(route.request.post_data_json["model_id"])
        route.fulfill(json=_output("heuristic-hu", [NODULE]))

    page.route("**/api/analyze", respond)
    page.locator("#run-analysis").click()
    expect(page.locator("#result-context")).to_contain_text("Model: heuristic-hu")
    expect(page.locator("#previous-settings")).to_be_hidden()
    context = page.locator("#result-context").inner_text()
    marker = page.locator("#previous-settings")
    page.locator("#model-select").select_option("medgemma1.5-q4")
    expect(marker).to_be_visible()
    expect(page.locator("#result-context")).to_have_text(context)
    expect(page.locator("#metric-model")).to_have_text("heuristic-hu")
    expect(page.locator("#download-html")).to_have_attribute("href", "/mock/heuristic-hu.html")
    page.locator("#image-count").fill("8")
    expect(marker).to_be_visible()
    page.locator("#image-count").fill("4")
    page.locator("#model-select").select_option("heuristic-hu")
    expect(marker).to_be_hidden()
    expect(page.locator("#result-context")).to_have_text(context)
    page.locator("#language-toggle").click()
    page.locator("#model-select").select_option("medgemma1.5-q4")
    expect(marker).to_contain_text("früheren Einstellungen")
    assert requests == ["heuristic-hu"]


def test_ux08_comparison_names_translate_and_identifiers_stay(ui_page: Page) -> None:
    page = ui_page
    models = [
        {"id": "heuristic-hu", "adapter": "heuristic", "available": True, "recommended": True},
        {"id": "medgemma1.5-q4", "adapter": "ollama", "available": True, "recommended": True},
    ]
    _inventory(page, models)
    _demo(page)
    unknown = {"label": "<i>odd_label</i>", "present": True, "confidence": 0.6}

    def respond(route: Route) -> None:
        model = route.request.post_data_json["model_id"]
        route.fulfill(
            json=_output(model, [NODULE, unknown] if model != "heuristic-hu" else [NODULE])
        )

    page.route("**/api/analyze", respond)
    page.route(
        "**/api/compare",
        lambda route: route.fulfill(json={"downloads": {"html": "/mock/comparison.html"}}),
    )
    page.locator("#compare-models").check()
    page.locator("#run-analysis").click()
    expect(page.locator("#comparison-download")).to_be_visible()
    table = page.locator("#comparison-findings-body")
    nodule = table.locator("tr").filter(has_text="pulmonary_nodule")
    odd = table.locator("tr").filter(has_text="<i>odd_label</i>")
    expect(nodule.locator("td").first).to_contain_text("Pulmonary nodule")
    scores = [cell.inner_text() for cell in nodule.locator("td").all()[1:]]
    assert scores == ["Present · 0.80", "Present · 0.80"]
    expect(odd.locator("td").nth(2)).to_have_text("Present · 0.60")
    expect(table.locator("i")).to_have_count(0)
    page.locator("#language-toggle").click()
    expect(nodule.locator("td").first).to_contain_text("Lungenrundherd")
    expect(nodule.locator("code")).to_have_text("pulmonary_nodule")
    assert [cell.inner_text() for cell in nodule.locator("td").all()[1:]] == [
        "Vorhanden · 0.80",
        "Vorhanden · 0.80",
    ]
    expect(odd.locator("code")).to_have_text("<i>odd_label</i>")
    page.locator("#language-toggle").click()
    expect(nodule.locator("td").first).to_contain_text("Pulmonary nodule")
    assert [cell.inner_text() for cell in nodule.locator("td").all()[1:]] == scores
    expect(page.locator("#findings-body")).to_contain_text("Pulmonary nodule")
