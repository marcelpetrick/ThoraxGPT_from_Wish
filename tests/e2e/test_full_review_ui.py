# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Full thorax review in the browser: start, measured progress/ETA, stop and outcome.

Synthetic phantom only; the held loopback Ollama stand-in returns scripted, labelled
abstentions, so the outcome comes from the HU cues of the phantom. No model runs.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import browser_page, serve
from tests.e2e.fake_ollama import FakeOllama, fake_ollama
from thoraxbench.config import Settings

Q4 = "medgemma1.5:4b-it-q4_K_M"


def _advance_until(page: Page, condition: Callable[[], bool], steps: int = 300) -> None:
    for _ in range(steps):
        if condition():
            return
        page.clock.fast_forward(1100)
        page.wait_for_timeout(150)
    pytest.fail("browser state did not change")


def _start(page: Page, provider: FakeOllama, german: bool) -> None:
    page.locator("#create-demo").click()
    expect(page.locator("#run-analysis")).to_be_enabled()
    if german:
        page.locator("#language-toggle").click()
    # The HU baseline (default) may start a whole-volume review; unavailable models may not.
    expect(page.locator("#run-full-review")).to_be_enabled()
    page.locator("#model-select").select_option("ct-chat")
    expect(page.locator("#run-full-review")).to_be_disabled()
    expect(page.locator("#full-review-blocked")).to_contain_text(
        "Detektor" if german else "detector"
    )
    page.locator("#model-select").select_option("medgemma1.5-q4")
    expect(page.locator("#run-full-review")).to_be_enabled()
    expect(page.locator("#full-review-blocked")).to_be_hidden()
    page.locator("#run-full-review").click()
    provider.release(2)
    progress = page.locator("#full-review-progress")
    marker = "Bilder übrig" if german else "images left"
    _advance_until(page, lambda: marker in (progress.text_content() or ""))
    text = progress.text_content() or ""
    assert ("s pro Bild" if german else "s per image") in text
    assert ("Min." if german else "min") in text


def test_full_review_shows_eta_and_plain_outcome(tmp_path: Path) -> None:
    with fake_ollama([Q4]) as provider:
        settings = Settings(data_dir=tmp_path / "data", ollama_url=provider.url)
        with serve(settings) as address, browser_page(address) as page:
            _start(page, provider, german=False)
            page.locator("#nav-jobs").click()
            expect(page.locator("#jobs-body")).to_contain_text("Full thorax review")
            expect(page.locator("#jobs-body")).to_contain_text("images left")
            page.locator("#nav-analysis").click()
            provider.release(200)
            panel = page.locator("#full-review-panel")
            _advance_until(page, panel.is_visible)
            # The scripted model abstains and no detector runs: density cues alone are weak.
            expect(page.locator("#full-review-verdict")).to_have_text(
                "This scan could not be assessed"
            )
            expect(page.locator("#full-review-look")).to_contain_text("weak cue")
            expect(page.locator("#full-review-coverage")).to_contain_text("Checked 0 of")
            expect(page.locator("#full-review-look li").first).to_contain_text("Pulmonary nodule")
            expect(page.locator("#full-review-look")).to_contain_text("density (HU) measurement")
            expect(page.locator("#full-review-unanswered")).to_contain_text("Emphysema")
            expect(panel).to_contain_text("not a diagnosis")
            before = page.locator("#slice-slider").input_value()
            page.locator("#full-review-look li button").first.click()
            expect(page.locator("#slice-slider")).not_to_have_value(before)
            href = page.locator("#full-review-open").get_attribute("href")
            assert href
            report = page.request.get(address + href)
            assert report.ok
            assert "Full thorax review" in report.text()
            assert "1.2.826" not in report.text()  # no SeriesInstanceUID in shareable output
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_full_review_stop_keeps_partial_result_in_german(tmp_path: Path) -> None:
    with fake_ollama([Q4]) as provider:
        settings = Settings(data_dir=tmp_path / "data", ollama_url=provider.url)
        with serve(settings) as address, browser_page(address) as page:
            page.set_viewport_size({"width": 390, "height": 844})
            _start(page, provider, german=True)
            page.locator("#stop-job").click()
            panel = page.locator("#full-review-panel")
            _advance_until(page, panel.is_visible)
            expect(page.locator("#notice")).to_contain_text("Teilergebnis")
            expect(page.locator("#full-review-coverage")).to_contain_text("Teilergebnis")
            expect(page.locator("#full-review-verdict")).to_have_text(
                "Diese Aufnahme konnte nicht beurteilt werden"
            )
            expect(page.locator("#full-review-progress")).to_be_hidden()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
