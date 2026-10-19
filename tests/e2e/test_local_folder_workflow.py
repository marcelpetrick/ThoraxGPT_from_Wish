# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Real local-folder -> viewer -> engine -> offline HTML, using synthetic DICOM only."""

from __future__ import annotations

import json
import time
from pathlib import Path
from shutil import copyfile
from typing import Any
from urllib.parse import urljoin

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def _complete(page: Page, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = page.request.get(urljoin(page.url, f"/api/jobs/{job_id}")).json()
        if job["finished"]:
            assert job["status"] == "succeeded", job
            page.clock.run_for(1_500)
            return dict(job)
        time.sleep(0.05)
    pytest.fail("Synthetic folder/analysis job did not finish")


def expect_ready_to_run(page: Page) -> None:
    """An enabled Run button shows no blocking reason."""
    expect(page.locator("#run-analysis")).to_be_enabled()
    expect(page.locator("#run-blocked-reason")).to_be_hidden()


def expect_local_result_label(page: Page, case_id: str, language: str) -> None:
    """Local results name the study as the selector does, not as a raw session UUID."""
    label = ("Lokale Studie " if language == "de" else "Local study ") + case_id[:8]
    expect(page.locator("#result-context")).to_contain_text(label)
    assert case_id not in page.locator("#result-context").inner_text()


@pytest.mark.parametrize(("language", "theme"), [("en", "light"), ("de", "dark")])
def test_local_folder_to_real_analysis_and_image_report(
    ui_page: Page, phantom_dir: Path, tmp_path: Path, language: str, theme: str
) -> None:
    page = ui_page
    extensionless = tmp_path / "extensionless-ct"
    extensionless.mkdir()
    for index, source in enumerate(sorted(phantom_dir.rglob("*.dcm"))):
        copyfile(source, extensionless / f"slice_{index:04d}")
    (extensionless / "notes").write_text("Scanner export; not DICOM")
    phantom_dir = extensionless
    if language == "de":
        page.locator("#language-toggle").click()
    if theme == "dark":
        page.locator("#theme-toggle").click()
    page.locator("#local-folder-path").fill(str(phantom_dir))
    with page.expect_response("**/api/local-studies") as submitted:
        page.locator("#open-local-folder").click()
    response = submitted.value
    assert response.status == 202
    queued = response.json()["job"]
    assert queued["kind"] == "study-import"
    registered = _complete(page, queued["id"])
    opened = registered["result"]["study"]
    assert opened["phase"] == "local"
    assert str(phantom_dir) not in json.dumps(registered)
    expect(page.locator("#study-select option:checked")).to_contain_text(opened["case_id"][:8])
    expect(page.locator("#dataset-filter")).to_have_value("local")
    expect(page.locator("#slice-slider")).to_be_enabled()
    page.wait_for_function(
        "() => { const image = document.querySelector('img[src*=\"/slice/\"]'); "
        "return image && image.complete && image.naturalWidth > 0; }"
    )
    # Opening a folder must not silently start a model.
    jobs = page.request.get(urljoin(page.url, "/api/jobs")).json()["jobs"]
    assert not any(
        job["kind"] == "analysis" and job["case_id"] == opened["case_id"] for job in jobs
    )
    page.locator("#model-select").select_option("heuristic-hu")
    expect_ready_to_run(page)
    with page.expect_response("**/api/jobs") as submitted:
        page.locator("#run-analysis").click()
    analyzed = _complete(page, submitted.value.json()["job"]["id"])
    assert analyzed["result"]["result"]["report"]["abstain"] is False
    expect(page.locator("#download-html")).to_have_attribute("aria-disabled", "false")
    expect_local_result_label(page, opened["case_id"], language)
    with page.expect_download() as downloaded:
        page.locator("#download-html").click()
    target = tmp_path / "folder-report.html"
    downloaded.value.save_as(target)
    report = target.read_text()
    assert "data:image/png;base64," in report
    assert "Research use only" in report
    assert opened["case_id"] in report
    assert str(phantom_dir) not in report
    with page.expect_popup() as popup:
        page.locator("#open-html").click()
    expect(popup.value.locator("body")).to_contain_text("Research use only")
    popup.value.close()
    stored = page.evaluate("JSON.stringify({...localStorage})")
    assert str(phantom_dir) not in stored


def test_empty_folder_real_failure_can_export_trace(ui_page: Page, tmp_path: Path) -> None:
    page = ui_page
    folder = tmp_path / "empty-private-folder"
    folder.mkdir()
    page.locator("#local-folder-path").fill(str(folder))
    with page.expect_response("**/api/local-studies") as submitted:
        page.locator("#open-local-folder").click()
    identifier = submitted.value.json()["job"]["id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = page.request.get(urljoin(page.url, f"/api/jobs/{identifier}")).json()
        if job["finished"]:
            break
        time.sleep(0.05)
    assert job["status"] == "failed"
    page.clock.run_for(1500)
    expect(page.locator("#run-analysis")).to_be_disabled()
    page.locator("#local-folder-debug").click()
    expect(page.locator("#job-debug-dialog")).to_be_visible()
    expect(page.locator("#job-debug-trace")).to_contain_text(job["diagnostic"]["trace_id"])
    with page.expect_download() as downloaded:
        page.locator("#job-debug-download").click()
    target = tmp_path / "failure.json"
    downloaded.value.save_as(target)
    result = json.loads(target.read_text())
    assert result["diagnostic"]["code"] == "no_dicom_files"
    assert str(folder) not in target.read_text()

    page.locator("#job-debug-close").click()
    page.locator("#create-demo").click()
    expect(page.locator("#ct-image")).to_be_visible()
    expect(page.locator("#run-analysis")).to_be_enabled()
