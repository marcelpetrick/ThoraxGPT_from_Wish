# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""The model selector ranks configured models by evidence-based thorax-review fit."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("german", [False, True])
def test_models_are_grouped_and_prefixed_by_fit(ui_page: Page, german: bool) -> None:
    page = ui_page
    if german:
        page.locator("#language-toggle").click()
    groups = page.locator("#model-select optgroup")
    expect(groups).to_have_count(3)
    expect(groups.nth(0)).to_have_attribute(
        "label", "1️⃣ Thorax-Prüfung: empfohlen" if german else "1️⃣ Thorax review: recommended"
    )
    expect(groups.nth(2)).to_have_attribute(
        "label",
        "3️⃣ Forschungskontrollen (nicht für Befunde)"
        if german
        else "3️⃣ Research controls (not for findings)",
    )
    first = groups.nth(0).locator("option").first
    expect(first).to_contain_text("1️⃣ monai-lung-nodule")
    expect(groups.nth(2).locator("option[value='medgemma1.5-q4']")).to_contain_text("3️⃣")
    page.locator("#model-select").select_option("medgemma1.5-q4")
    expect(page.locator("#model-status")).to_contain_text(
        "Schwache Eignung" if german else "Weak fit"
    )
