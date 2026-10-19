# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Live operation counts use synthetic job snapshots and never imply overall progress."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, Route, expect

from tests.e2e.test_local_folder_ui import FolderAPI

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("german", [False, True])
def test_import_progress_counts_follow_operations_and_clear_after_cancel(
    ui_page: Page, german: bool
) -> None:
    page = ui_page
    api = FolderAPI(page)
    if german:
        page.locator("#language-toggle").click()
        page.locator("#theme-toggle").click()
    page.locator("#local-folder-path").fill("/synthetic/progress")
    page.locator("#open-local-folder").click()
    expect(page.locator("#job-follow-status")).to_contain_text(
        "Lokalen Ordner öffnen" if german else "Open local folder"
    )
    assert api.job is not None
    progress = page.locator("#folder-job-progress")
    expect(progress).to_be_hidden()
    for operation, completed, total, english, deutsch in [
        (
            "path_check",
            5,
            None,
            "Path check: 5 entries · total unknown",
            "Pfadprüfung: 5 Einträge · Gesamtzahl unbekannt",
        ),
        ("header_check", 2, 20, "Header check: 2 / 20 files", "Headerprüfung: 2 / 20 Dateien"),
        ("discovery", 8, 20, "DICOM discovery: 8 / 20 files", "DICOM-Suche: 8 / 20 Dateien"),
        (
            "pixel_decode",
            12,
            16,
            "Pixel decoding: 12 / 16 files",
            "Pixeldekodierung: 12 / 16 Dateien",
        ),
        ("input_qc", 0, 1, "Input QC: 0 / 1 checks", "Eingabe-QC: 0 / 1 Prüfungen"),
        (
            "source_recheck",
            10,
            20,
            "Source recheck: 10 / 20 entries",
            "Quellen-Nachprüfung: 10 / 20 Einträge",
        ),
    ]:
        api.job["progress"] = {"operation": operation, "completed": completed, "total": total}
        api.job["stage"] = "study"
        api.job["elapsed_s"] = 12.4
        page.clock.fast_forward(1100)
        expect(progress).to_have_text(deutsch if german else english)
        expect(progress).to_have_attribute("role", "status")
        expect(progress).to_have_attribute("aria-live", "polite")
        expect(page.locator("#request-elapsed")).to_have_text(re.compile(r"00:1[2-5]"))
        expect(page.locator("#run-analysis")).to_be_disabled()
        page.locator("#nav-jobs").click()
        row = page.locator('tr[data-job="synthetic-folder-job"]')
        expect(row.locator("[data-import-progress]")).to_have_text(deutsch if german else english)
        expect(row).to_contain_text("Studie laden" if german else "loading study")
        page.locator("#nav-analysis").click()
    page.locator("#nav-jobs").click()
    detail = page.locator('[data-job-progress="synthetic-folder-job"]')
    detail.focus()
    api.job["progress"]["completed"] = 11
    page.clock.fast_forward(1100)
    expect(detail).to_be_focused()
    page.locator("#nav-analysis").click()
    progress.focus()
    page.clock.fast_forward(700)
    expect(page.locator("#tooltip")).to_contain_text(
        "weder Gesamtprozente" if german else "not an overall percentage"
    )

    def stopping(route: Route) -> None:
        assert api.job is not None
        api.job["status"] = "cancelling"
        route.fulfill(json=api.job)

    page.route("**/api/jobs/synthetic-folder-job/cancel", stopping)
    page.locator("#stop-job").click()
    expect(page.locator("#job-caveat")).to_contain_text(
        "sicheren Schrittgrenze" if german else "safe stage boundary"
    )
    expect(progress).to_be_visible()
    api.finish("cancelled")
    page.clock.fast_forward(1100)
    expect(progress).to_be_hidden()
    page.locator("#nav-jobs").click()
    expect(page.locator("[data-import-progress]")).to_have_count(0)
    assert "%" not in page.locator("#jobs-body").inner_text()
    assert not api.errors


def test_invalid_progress_never_displays_untrusted_text(ui_page: Page) -> None:
    page = ui_page
    api = FolderAPI(page)
    page.locator("#local-folder-path").fill("/synthetic/progress")
    page.locator("#open-local-folder").click()
    assert api.job is not None
    for value in [
        {"operation": "/synthetic/never-display-this", "completed": 2, "total": 10},
        {"operation": "header_check", "completed": -1, "total": 10},
        {"operation": "header_check", "completed": "2", "total": 10},
        None,
    ]:
        api.job["progress"] = value
        page.clock.fast_forward(1100)
        expect(page.locator("#folder-job-progress")).to_be_hidden()
        page.locator("#nav-jobs").click()
        expect(page.locator("[data-import-progress]")).to_have_count(0)
        assert "never-display-this" not in page.locator("body").inner_text()
        page.locator("#nav-analysis").click()
    assert "never-display-this" not in page.evaluate("JSON.stringify(localStorage)")
    assert not api.errors
