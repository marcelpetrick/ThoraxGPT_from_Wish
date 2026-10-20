# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Remaining UI red-team items (2026-10-20): synthetic studies and mocked folder jobs only."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.test_local_folder_ui import FolderAPI

pytestmark = pytest.mark.e2e


def open_folder(page: Page, api: FolderAPI, status: str = "succeeded") -> None:
    page.locator("#local-folder-path").fill("/synthetic/leftovers")
    page.locator("#open-local-folder").click()
    api.finish(status)
    page.clock.fast_forward(1100)


def test_announcer_follows_language_switch(ui_page: Page) -> None:
    page = ui_page
    api = FolderAPI(page)
    open_folder(page, api)
    announcer = page.locator("#job-announcer")
    expect(announcer).to_contain_text("Job finished")
    page.locator("#language-toggle").click()
    expect(announcer).to_contain_text("Auftrag beendet")
    expect(announcer).not_to_contain_text("Job finished")
    assert not api.errors


def test_disabled_downloads_leave_tab_order_and_explain_why(ui_page: Page) -> None:
    page = ui_page
    hint = page.locator("#downloads-hint")
    expect(hint).to_be_visible()
    expect(hint).to_have_text("Downloads become available once a result is shown.")
    for identifier in ["open-html", "download-json", "download-report", "download-html"]:
        link = page.locator(f"#{identifier}")
        expect(link).to_have_attribute("aria-disabled", "true")
        expect(link).to_have_attribute("tabindex", "-1")
    page.locator("#language-toggle").click()
    expect(hint).to_contain_text("sobald ein Ergebnis angezeigt wird")


@pytest.mark.parametrize("german", [False, True])
def test_server_error_text_gets_translated_lead(ui_page: Page, german: bool) -> None:
    page = ui_page
    api = FolderAPI(page)
    if german:
        page.locator("#language-toggle").click()
    open_folder(page, api, "failed")
    page.locator("#nav-jobs").click()
    detail = page.locator('tr[data-job="synthetic-folder-job"] .job-detail')
    if german:
        expect(detail).to_contain_text("Der Auftrag konnte nicht abgeschlossen werden.")
        expect(detail).to_contain_text("Serverdetail (englisch): Synthetic read failure")
    else:
        expect(detail).to_have_text("Synthetic read failure")
    page.locator("#language-toggle").click()
    expect(detail).to_contain_text(
        "Synthetic read failure" if german else "Serverdetail (englisch): Synthetic read failure"
    )
    if not german:
        expect(detail).to_contain_text("Der Auftrag konnte nicht abgeschlossen werden.")
    assert not api.errors


def test_mobile_notice_is_compact_and_jobs_table_stacks(ui_page: Page) -> None:
    page = ui_page
    api = FolderAPI(page)
    open_folder(page, api)
    # The folder form collapses below 700 px, so shrink only after opening.
    page.set_viewport_size({"width": 360, "height": 740})
    notice = page.locator("#job-notice")
    expect(notice).to_be_visible()
    # One compact line that never hides the end of the page.
    assert notice.bounding_box()["height"] <= 56
    expect(notice).to_have_attribute("title", page.locator("#job-notice-text").inner_text())
    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    footer = page.locator("#analysis-page footer, footer").last.bounding_box()
    assert footer["y"] + footer["height"] <= notice.bounding_box()["y"] + 1
    page.locator("#nav-jobs").click()
    row = page.locator('tr[data-job="synthetic-folder-job"]')
    expect(row.locator("td").first).to_have_attribute("data-label", "Kind")
    assert row.evaluate("(element) => getComputedStyle(element).display") == "block"
    wrapper = page.locator("#jobs-table").locator("xpath=..")
    assert wrapper.evaluate("(element) => element.scrollWidth <= element.clientWidth + 1")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not api.errors
