# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Browser acceptance of the read-only Evaluation section over synthetic benchmark runs."""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest
from playwright.sync_api import Page, Request, Route, expect

from tests.e2e.conftest import browser_page, serve
from thoraxbench.synthetic_runs import SEALED, build_synthetic_benchmarks

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def evaluation_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    built = build_synthetic_benchmarks(
        tmp_path_factory.mktemp("evaluation-ui") / "root", ollama_url="http://127.0.0.1:1"
    )
    legacy = built.settings.data_path("results", "benchmark", "LEGACY", "20250101T000000Z-old")
    legacy.mkdir(parents=True)
    (legacy / "result.json").write_text("{}", encoding="utf-8")
    with serve(built.settings) as address:
        yield address


@pytest.fixture
def eval_page(evaluation_server: str) -> Iterator[Page]:
    with browser_page(evaluation_server) as opened:
        yield opened


def _requests(page: Page) -> list[Request]:
    seen: list[Request] = []
    page.on("request", lambda request: seen.append(request))  # noqa: PLW0108
    return seen


def _open_vision_run(page: Page) -> None:
    page.locator("#nav-evaluation").click()
    expect(page.locator("#evaluation-page")).to_be_visible()
    row = page.locator("#eval-runs-body tr[data-run^='SYNTH-E001/']")
    row.get_by_role("button").click()
    expect(page.locator("#eval-cases-body tr")).to_have_count(10)


def test_runs_cases_detail_and_comparison_are_read_only(eval_page: Page) -> None:
    page = eval_page
    seen = _requests(page)
    _open_vision_run(page)
    runs = page.locator("#eval-runs-body")
    expect(runs.locator("tr")).to_have_count(3)
    legacy = runs.locator("tr[data-run^='LEGACY/']")
    expect(legacy).to_contain_text("Unavailable")
    expect(legacy).to_contain_text("cannot open")
    expect(legacy.get_by_role("checkbox")).to_be_disabled()
    expect(legacy.get_by_role("button")).to_have_count(0)
    vision = runs.locator("tr[data-run^='SYNTH-E001/']")
    expect(vision).to_contain_text("q8-p2 · medgemma1.5-q8")
    expect(vision).to_contain_text("Scored 5 · Abstained 2 · Failed 1 · Not indexed 2")
    expect(page.locator("#eval-run-context")).to_contain_text("Phase: Calibration, Internal test")
    page.locator("#eval-filter-status").select_option("abstained")
    expect(page.locator("#eval-cases-body tr")).to_have_count(2)
    expect(page.locator("#eval-cases-count")).to_have_text("2 / 10 rows visible")
    page.locator("#eval-filter-status").select_option("")
    page.locator("#eval-filter-evidence").select_option("unsupported_positive_removed")
    page.locator("#eval-filter-variant").select_option("q4-p2")
    rows = page.locator("#eval-cases-body tr")
    expect(rows).to_have_count(1)
    expect(rows.first).to_contain_text("Pulmonary nodule: positive")
    expect(rows.first).to_contain_text("Pulmonary mass: unavailable")
    expect(rows.first).to_contain_text("invalid or duplicate image references removed")
    rows.first.get_by_role("button", name="Details").click()
    detail = page.locator("#eval-case")
    expect(detail).to_be_focused()
    expect(page.locator("#eval-images-note")).to_contain_text("not stored")
    expect(page.locator("#eval-images-note")).to_contain_text("sent 4 image(s)")
    expect(page.locator("#eval-captions li")).to_have_count(4)
    expect(detail.locator("img")).to_have_count(0)
    expect(page.locator("#eval-case-verdict")).to_contain_text(
        "Unsupported positive marked unavailable"
    )
    expect(page.locator("#eval-raw")).to_contain_text("<b>not markup</b>")
    expect(page.locator("#eval-raw b, #eval-parsed b")).to_have_count(0)
    expect(page.locator("#eval-evidence-body tr").first).to_contain_text("model images (1-based)")
    page.locator("#eval-runs-body input[type=checkbox]").nth(0).check()
    page.locator("#eval-runs-body input[type=checkbox]").nth(1).check()
    page.locator("#eval-compare").click()
    expect(page.locator("#eval-setups-body tr")).to_have_count(3)
    expect(page.locator("#eval-pairs-body tr")).to_have_count(3)
    expect(page.locator("#eval-comparison")).to_contain_text("does not rank models")
    expect(page.locator("#eval-pairs-body")).to_contain_text("Different or unknown basis")
    assert SEALED not in page.content()
    evaluation = [item for item in seen if "/api/" in item.url]
    assert evaluation
    assert all(item.method == "GET" for item in evaluation)
    assert any("/api/evaluation/compare" in item.url for item in evaluation)
    forbidden = ("/api/analyze", "/api/demo", "/pull", "/api/compare")
    assert not any(marker in item.url for item in evaluation for marker in forbidden)


def test_heuristic_case_explains_source_slices_and_missing_request(eval_page: Page) -> None:
    page = eval_page
    page.locator("#nav-evaluation").click()
    page.locator("#eval-runs-body tr[data-run^='SYNTH-E000/'] button").click()
    case = page.locator("#eval-cases-body tr[data-case='base/lidc_idri/SYNTH-P1']")
    case.get_by_role("button").click()
    expect(page.locator("#eval-images-note")).to_contain_text("sent no images to a model")
    expect(page.locator("#eval-evidence-body")).to_contain_text("source slices (0-based)")
    missing = page.locator("#eval-cases-body tr[data-case='base/lidc_idri/SYNTH-P5']")
    expect(missing).to_contain_text("Not indexed")
    missing.get_by_role("button").click()
    expect(page.locator("#eval-images-note")).to_contain_text("No request was sent")
    expect(page.locator("#eval-raw")).to_have_text("No model response is stored for this case.")


def _check_tooltips(page: Page, root: str) -> None:
    for control in page.locator(f"{root} [data-tip]:not(:disabled)").all():
        if not control.is_visible():
            continue
        control.scroll_into_view_if_needed()
        control.focus()
        page.clock.fast_forward(700)
        expect(page.get_by_role("tooltip")).to_be_visible()
        expect(control).to_have_accessible_description(re.compile(r"\S+"))
        page.keyboard.press("Escape")


def test_german_dark_mobile_labels_tooltips_and_layout(eval_page: Page) -> None:
    page = eval_page
    page.locator("#language-toggle").click()
    page.locator("#theme-toggle").click()
    _open_vision_run(page)
    expect(page.locator("#evaluation-heading")).to_have_text("Auswertung gespeicherter Läufe")
    expect(page.locator("#nav-evaluation")).to_have_text(re.compile("Auswertung"))
    expect(page.locator("#page-crumb")).to_have_text("Auswertung")
    expect(page.locator("#eval-cases-head")).to_contain_text("Referenzlabels")
    expect(page.locator("#eval-cases-body")).to_contain_text("Enthaltung")
    expect(page.locator("#eval-cases-body")).to_contain_text("Bildverweise im gültigen Bereich")
    page.locator("#eval-cases-body tr[data-case='q4-p2/lidc_idri/SYNTH-P1'] button").click()
    expect(page.locator("#eval-images-note")).to_contain_text("nicht gespeichert")
    expect(page.locator("#eval-labels-body")).to_contain_text("Lungenrundherd")
    _check_tooltips(page, "#evaluation-page")
    page.locator("#language-toggle").click()
    expect(page.locator("#eval-images-note")).to_contain_text("not stored")
    expect(page.locator("#eval-cases-body")).to_contain_text("In-range image references")
    page.set_viewport_size({"width": 390, "height": 844})
    for _ in range(2):
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#theme-toggle").click()
        page.locator("#language-toggle").click()


def test_evaluation_navigation_preserves_single_study_session(eval_page: Page) -> None:
    page = eval_page
    page.locator("#create-demo").click()
    expect(page.locator("#run-analysis")).to_be_enabled()
    pending: list[Route] = []
    page.route("**/api/analyze", lambda route: pending.append(route))  # noqa: PLW0108
    page.locator("#run-analysis").click()
    _open_vision_run(page)
    expect(page.locator("#session-status")).to_be_visible()
    page.locator("#eval-cases-body tr[data-case='q8-p2/lidc_idri/SYNTH-P4'] button").click()
    expect(page.locator("#eval-case-warnings")).to_contain_text("scripted synthetic runtime")
    page.locator("#nav-analysis").click()
    expect(page.locator("#run-analysis")).to_be_disabled()
    pending[0].fulfill(json=_mock())
    expect(page.locator("#result-context")).to_contain_text("demo / phantom")
    href = page.locator("#download-html").get_attribute("href")
    page.locator("#nav-evaluation").click()
    expect(page.locator("#session-status")).to_be_hidden()
    expect(page.locator("#eval-case")).to_be_visible()
    expect(page.locator("#eval-case-context")).to_contain_text("SYNTH-P4")
    page.go_back()
    expect(page.locator("#analysis-page")).to_be_visible()
    expect(page.locator("#download-html")).to_have_attribute("href", href or "")
    assert len(pending) == 1


def test_direct_evaluation_url_loads_runs(eval_page: Page, evaluation_server: str) -> None:
    page = eval_page
    page.goto(f"{evaluation_server}/evaluation")
    expect(page.locator("#evaluation-page")).to_be_visible()
    expect(page.locator("#nav-evaluation")).to_have_attribute("aria-current", "page")
    expect(page.locator("#eval-runs-summary")).to_have_text("3 runs")
    page.locator("#eval-refresh").click()
    expect(page.locator("#eval-runs-body tr")).to_have_count(3)


def _mock() -> dict[str, object]:
    return {
        "id": "run-heuristic",
        "result": {
            "model_id": "heuristic-hu",
            "perf": {"total_s": 0.1, "n_images": 0},
            "report": {
                "abstain": False,
                "findings": [{"label": "pulmonary_nodule", "present": True, "confidence": 0.8}],
            },
            "raw_error": None,
        },
        "markdown": "Research use only. Synthetic mocked model output, not medical advice.",
        "downloads": {"html": "/mock/heuristic.html"},
    }
