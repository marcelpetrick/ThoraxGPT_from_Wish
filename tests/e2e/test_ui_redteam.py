# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""UI red-team regressions (2026-10-19): synthetic studies and mocked folder jobs only."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.test_local_folder_ui import FolderAPI

pytestmark = pytest.mark.e2e


def german_dark(page: Page) -> None:
    page.locator("#language-toggle").click()
    page.locator("#theme-toggle").click()


@pytest.mark.parametrize("german", [False, True])
def test_failed_open_clears_visible_selection_so_previous_study_can_be_rechosen(
    ui_page: Page, german: bool
) -> None:
    page = ui_page
    api = FolderAPI(page)
    api.include_demo = True
    page.reload()
    if german:
        german_dark(page)
    expect(page.locator("#study-select option:checked")).to_have_text("phantom")
    expect(page.locator("#run-analysis")).to_be_enabled()
    page.locator("#local-folder-path").fill("/synthetic/broken")
    page.locator("#open-local-folder").click()
    api.finish("failed")
    page.clock.fast_forward(1100)
    # The old study must not look selected or ready while analysis is blocked.
    expect(page.locator("#study-select option:checked")).to_have_text(
        "Studie auswählen…" if german else "Choose a study…"
    )
    for badge in ["#study-phase", "#study-qc", "#study-slices"]:
        expect(page.locator(badge)).to_have_text("—")
    expect(page.locator("#run-analysis")).to_be_disabled()
    expect(page.locator("#run-blocked-reason")).to_contain_text(
        "letzte Ordner wurde nicht geöffnet" if german else "last folder did not open"
    )
    page.locator("#study-search").fill("phan")
    expect(page.locator("#study-select option:checked")).to_contain_text(
        "Studie auswählen" if german else "Choose a study"
    )
    expect(page.locator("#run-analysis")).to_be_disabled()
    # Re-choosing the previously selected study is now an actual selection change.
    page.locator("#study-select").select_option(label="phantom")
    expect(page.locator("#ct-image")).to_be_visible()
    expect(page.locator("#run-analysis")).to_be_enabled()
    expect(page.locator("#run-blocked-reason")).to_be_hidden()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not api.errors


@pytest.mark.parametrize("german", [False, True])
def test_rejected_folder_message_is_translated_marked_invalid_and_focused(
    ui_page: Page, german: bool
) -> None:
    page = ui_page
    if german:
        german_dark(page)
    path = page.locator("#local-folder-path")
    path.fill("/nonexistent-synthetic-redteam/study")
    page.locator("#open-local-folder").click()
    expect(page.locator("#local-folder-notice")).to_contain_text(
        "nicht zugelassen" if german else "not permitted (for example a protected holdout path)"
    )
    assert "Local folder is unavailable" not in page.locator("#local-folder-notice").inner_text()
    expect(path).to_have_attribute("aria-invalid", "true")
    expect(path).to_have_attribute("aria-errormessage", "local-folder-notice")
    expect(path).to_be_focused()
    expect(path).to_have_value("/nonexistent-synthetic-redteam/study")
    path.press("End")
    path.type("x")
    expect(path).not_to_have_attribute("aria-invalid", "true")
    path.fill("relative/path")
    path.press("Enter")
    expect(page.locator("#local-folder-notice")).to_contain_text(
        "absoluten lokalen Ordnerpfad" if german else "absolute local folder path"
    )
    expect(path).to_have_attribute("aria-invalid", "true")
    expect(page.locator("#run-analysis")).to_be_disabled()


def test_disabled_run_names_the_first_blocking_reason(ui_page: Page) -> None:
    page = ui_page
    api = FolderAPI(page)
    reason = page.locator("#run-blocked-reason")
    expect(page.locator("#run-analysis")).to_be_disabled()
    expect(reason).to_have_text("Run is unavailable: select a study first.")
    expect(reason).to_have_attribute("role", "status")
    api.include_demo = True
    page.locator("#refresh-studies").click()
    expect(page.locator("#ct-image")).to_be_visible()
    expect(page.locator("#run-analysis")).to_be_enabled()
    expect(reason).to_be_hidden()
    unavailable = page.evaluate(
        "[...document.querySelectorAll('#model-select option')]"
        ".map((option) => option.value).filter((id) => id !== 'heuristic-hu')"
    )
    page.locator("#model-select").select_option(unavailable[0])
    expect(page.locator("#run-analysis")).to_be_disabled()
    expect(reason).to_contain_text("selected model is not available locally")
    page.locator("#language-toggle").click()
    expect(reason).to_contain_text("Modell ist lokal nicht verfügbar")
    page.locator("#language-toggle").click()
    page.locator("#model-select").select_option("heuristic-hu")
    expect(reason).to_be_hidden()
    api.study["qc_adequate"] = False
    page.locator("#local-folder-path").fill("/synthetic/limited")
    page.locator("#open-local-folder").click()
    expect(reason).to_contain_text("last folder did not open")
    api.finish()
    page.clock.fast_forward(1100)
    expect(page.locator("#study-qc")).to_have_text("QC limited")
    expect(reason).to_have_text("Run is unavailable: Input QC is limited for this local study.")
    # Opening a folder is a study registration, not a model result.
    expect(page.locator("#job-notice-link")).to_have_text("Open study")
    expect(page.locator("#job-notice-text")).not_to_contain_text("· —")
    page.locator("#nav-jobs").click()
    expect(page.locator('tr[data-job="synthetic-folder-job"] a[data-job-link]')).to_have_text(
        "Open study"
    )
    assert not api.errors
