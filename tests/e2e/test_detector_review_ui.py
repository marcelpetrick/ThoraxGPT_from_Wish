# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Synthetic sourced-candidate review in both UI languages/themes, using a scripted model."""

import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

from tests.detector_stub import install_stub
from tests.e2e.conftest import browser_page, serve
from thoraxbench.config import Settings

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize(("language", "theme"), [("en", "light"), ("de", "dark")])
def test_candidate_previews_and_slice_navigation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str, theme: str
) -> None:
    install_stub(monkeypatch)
    settings = Settings(data_dir=tmp_path / "data", ollama_url="http://127.0.0.1:1")
    with serve(settings) as address, browser_page(address) as page:
        if language == "de":
            page.locator("#language-toggle").click()
        if theme == "dark":
            page.locator("#theme-toggle").click()
        page.locator("#create-demo").click()
        expect(page.locator("#study-select")).not_to_have_value("")
        page.locator("#model-select").select_option("monai-lung-nodule")
        expect(page.locator("#image-count")).to_be_disabled()
        page.locator("#run-analysis").click()
        expect(page.locator("#candidate-panel")).to_be_visible(timeout=30_000)
        expect(page.locator("#candidate-body tr")).to_have_count(1)
        expect(page.locator("#candidate-previews img")).to_have_count(2)
        page.wait_for_function(
            "() => [...document.querySelectorAll('#candidate-previews img')]"
            ".every(i => i.complete && i.naturalWidth === 256)"
        )
        expect(page.locator("#candidate-body")).to_contain_text(
            "Detektor" if language == "de" else "Detector"
        )
        page.locator("#study-search").fill("missing-source-filter")
        expect(page.locator("#study-select")).to_have_value("")
        page.locator("#candidate-body button").click()
        expect(page.locator("#slice-slider")).to_have_value("22")
        expect(page.locator("#ct-image")).to_have_attribute(
            "src",
            re.compile(r"/slice/22\.png"),
        )
        button = page.locator("#candidate-body button")
        button.focus()
        expect(page.get_by_role("tooltip")).to_be_visible()
        expect(page.get_by_role("tooltip")).not_to_have_text("")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
