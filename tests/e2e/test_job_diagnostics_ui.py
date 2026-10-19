# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Sanitized diagnostic presentation over synthetic folder jobs, without private inputs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.test_local_folder_ui import FolderAPI

pytestmark = pytest.mark.e2e


def failed_job(page: Page, api: FolderAPI) -> dict:
    page.locator("#folder-dropzone").click()
    page.locator("#local-folder-path").fill("/synthetic/unreadable")
    page.locator("#open-local-folder").click()
    expect(page.locator("#job-bar")).to_be_visible()
    api.finish("failed")
    assert api.job is not None
    diagnostic = {
        "trace_id": "trace-synthetic-42",
        "code": "no_eligible_ct",
        "stage": "folder_check",
        "exception_type": "ValueError",
        "created_at": "2026-10-19T12:00:00Z",
        "causes": ["<img src=x onerror=alert(1)>"],
        "frames": [
            {"file": "src/thoraxbench/dicom/volume.py", "function": "load_study", "line": 25}
        ],
        "discovery": {
            "files_scanned": 12,
            "headers_readable": 7,
            "headers_unreadable": 2,
            "non_dicom_files": 3,
        },
    }
    api.job["diagnostic"] = diagnostic
    bundle = {
        "job_id": api.job["id"],
        "kind": "study-import",
        "status": "failed",
        "diagnostic": diagnostic,
        "disclaimer": "Synthetic research fixture; not medical advice",
    }
    page.route(
        "**/api/jobs/*/diagnostics",
        lambda route: route.fulfill(
            json=bundle, headers={"Content-Disposition": 'attachment; filename="diagnostics.json"'}
        ),
    )
    page.clock.fast_forward(1100)
    return bundle


@pytest.mark.parametrize("german", [False, True])
def test_failed_folder_diagnostics_are_actionable_escaped_and_downloadable(
    ui_page: Page, tmp_path: Path, german: bool
) -> None:
    page = ui_page
    api = FolderAPI(page)
    if german:
        page.locator("#language-toggle").click()
        page.locator("#theme-toggle").click()
    page.set_viewport_size({"width": 390, "height": 844})
    bundle = failed_job(page, api)
    expect(page.locator("#local-folder-notice")).to_contain_text(
        "Keine geeignete CT-Serie" if german else "No eligible CT series"
    )
    expect(page.locator("#local-folder-notice")).to_contain_text("trace-synthetic-42")
    page.locator("#local-folder-debug").click()
    dialog = page.locator("#job-debug-dialog")
    expect(dialog).to_be_visible()
    expect(page.locator("#job-debug-close")).to_be_focused()
    expect(page.locator("#job-debug-trace")).to_have_text("trace-synthetic-42")
    expect(page.locator("#job-debug-discovery")).to_contain_text("12")
    expect(page.locator("#job-debug-stage")).to_have_text(
        "Ordner prüfen" if german else "checking folder"
    )
    page.locator("#job-debug-technical summary").click()
    expect(page.locator("#job-debug-json")).to_contain_text("<img src=x onerror=alert(1)>")
    assert dialog.locator("img").count() == 0
    assert dialog.locator("#tooltip").count() == 1
    page.evaluate("""() => {
        window.debugCopies = [];
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true, value: {writeText: async (text) => window.debugCopies.push(text)}
        });
    }""")
    assert page.evaluate("window.debugCopies.length") == 0
    page.locator("#job-debug-copy").click()
    expect(page.locator("#job-debug-copy-status")).to_contain_text(
        "kopiert" if german else "copied"
    )
    assert json.loads(page.evaluate("window.debugCopies[0]"))["diagnostic"] == bundle["diagnostic"]
    with page.expect_download() as downloaded:
        page.locator("#job-debug-download").click()
    target = tmp_path / "diagnostics.json"
    downloaded.value.save_as(target)
    assert json.loads(target.read_text())["diagnostic"] == bundle["diagnostic"]
    dialog.press("Escape")
    expect(dialog).to_be_hidden()
    expect(page.locator("#local-folder-debug")).to_be_focused()
    expect(page.locator("#job-notice-debug")).to_be_visible()
    page.locator("#job-notice-debug").click()
    expect(dialog).to_be_visible()
    page.locator("#job-debug-close").click()
    expect(page.locator("#job-notice-debug")).to_be_focused()
    page.locator("#nav-jobs").click()
    page.locator('tr[data-job="synthetic-folder-job"] button[data-job-diagnostic]').click()
    expect(dialog).to_be_visible()
    expect(page.locator("#job-debug-class")).to_have_text("ValueError")
    assert "trace-synthetic-42" not in page.evaluate("JSON.stringify(localStorage)")
    assert not api.errors


def test_successful_import_warning_counts_do_not_claim_all_files_were_used(ui_page: Page) -> None:
    page = ui_page
    api = FolderAPI(page)
    page.locator("#local-folder-path").fill("/synthetic/study")
    page.locator("#open-local-folder").click()
    expect(page.locator("#job-bar")).to_be_visible()
    api.finish()
    assert api.job is not None
    api.job["result"]["warnings"] = [{"code": "unreadable_dicom_headers", "count": 2}]
    api.job["diagnostic"] = {
        "trace_id": "synthetic-warning-42",
        "severity": "warning",
        "code": "unreadable_dicom_headers",
        "stage": "folder_check",
        "exception_type": "HeaderWarnings",
        "header_error_types": {"BytesLengthException": 2},
        "causes": [],
        "frames": [],
    }
    api.job["result"]["discovery"] = {
        "files_scanned": 12,
        "headers_readable": 7,
        "headers_unreadable": 2,
        "non_dicom_files": 3,
        "private_values_raw": 40,
    }
    page.clock.fast_forward(1100)
    expect(page.locator("#local-folder-warnings")).to_contain_text(
        "Opened with a warning: 2 file(s)"
    )
    expect(page.locator("#local-folder-warnings")).to_contain_text("Not every scanned file")
    expect(page.locator("#local-folder-discovery")).to_contain_text("Files scanned: 12")
    # Raw vendor-private values are informational: shown with counts, never added to warnings.
    expect(page.locator("#local-folder-discovery")).to_contain_text(
        "Vendor private values kept raw (informational): 40"
    )
    assert "40" not in page.locator("#local-folder-warnings").inner_text()
    expect(page.locator("#job-notice-link")).to_have_text("Open study")
    expect(page.locator("#job-notice-text")).to_contain_text("not a model result")
    expect(page.locator("#local-folder-debug")).to_be_visible()
    expect(page.locator("#run-analysis")).to_be_enabled()
    page.locator("#local-folder-debug").click()
    expect(page.locator("#job-debug-reason")).to_contain_text("Warning only; the import succeeded.")
    expect(page.locator("#job-debug-reason")).to_contain_text("selected CT series opened")
    page.locator("#job-debug-technical summary").click()
    expect(page.locator("#job-debug-json")).to_contain_text("BytesLengthException")
    page.locator("#job-debug-close").click()
    page.locator("#language-toggle").click()
    expect(page.locator("#local-folder-warnings")).to_contain_text("2 Datei(en) mit unlesbarem")
    expect(page.locator("#local-folder-discovery")).to_contain_text("Durchsuchte Dateien: 12")
    expect(page.locator("#local-folder-discovery")).to_contain_text("(Information): 40")
    expect(page.locator("#job-notice-link")).to_have_text("Studie öffnen")
    expect(page.locator("#run-analysis")).to_be_enabled()
    page.locator("#local-folder-debug").click()
    expect(page.locator("#job-debug-reason")).to_contain_text("CT-Serie wurde geöffnet")
    assert not api.errors
