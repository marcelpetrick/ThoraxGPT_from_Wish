# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Source-view readiness and explicit local selection, using synthetic previews only."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, Route, expect

from tests.e2e.test_local_folder_ui import FolderAPI

pytestmark = pytest.mark.e2e


def open_local(page: Page, api: FolderAPI) -> None:
    page.locator("#local-folder-path").fill("/synthetic/selected-ct")
    page.locator("#open-local-folder").click()
    expect(page.locator("#local-folder-notice")).to_contain_text("queued")
    api.finish()
    page.clock.fast_forward(1100)
    expect(page.locator("#dataset-filter")).to_have_value("local")


def test_delayed_source_image_blocks_analysis_until_actual_pixels_arrive(ui_page: Page) -> None:
    page = ui_page
    api = FolderAPI(page)
    pending: list[Route] = []

    def hold_image(route: Route) -> None:
        pending.append(route)

    page.route("**/api/studies/local/**", hold_image)
    open_local(page, api)
    expect(page.locator("#viewer-status")).to_contain_text("Loading the selected DICOM")
    expect(page.locator("#run-analysis")).to_be_disabled()
    expect(page.locator("#ct-image")).to_be_hidden()
    assert pending
    pending[-1].fulfill(body=api.png, content_type="image/png")
    expect(page.locator("#ct-image")).to_be_visible()
    expect(page.locator("#run-analysis")).to_be_enabled()
    assert page.locator("#ct-image").evaluate("image => image.complete && image.naturalWidth > 0")
    assert not api.errors


def test_image_failure_stays_blocked_until_explicit_retry_succeeds(ui_page: Page) -> None:
    page = ui_page
    api = FolderAPI(page)
    page.route("**/api/studies/local/**", lambda route: route.fulfill(status=500, body="failed"))
    open_local(page, api)
    expect(page.locator("#retry-viewer")).to_be_visible()
    expect(page.locator("#run-analysis")).to_be_disabled()
    expect(page.locator("#ct-image")).to_be_hidden()
    page.route(
        "**/api/studies/local/**",
        lambda route: route.fulfill(body=api.png, content_type="image/png"),
    )
    page.locator("#retry-viewer").click()
    expect(page.locator("#ct-image")).to_be_visible()
    expect(page.locator("#run-analysis")).to_be_enabled()
    expect(page.locator("#retry-viewer")).to_be_hidden()
    assert not api.errors


def test_failed_new_folder_cannot_accidentally_analyze_previous_study(ui_page: Page) -> None:
    page = ui_page
    api = FolderAPI(page)
    open_local(page, api)
    expect(page.locator("#run-analysis")).to_be_enabled()
    # Registered A remains in the library even when the unrelated new B cannot open.
    page.route(
        "**/api/studies",
        lambda route: route.fulfill(json={"studies": [api.study], "libraries": []}),
    )
    page.locator("#local-folder-path").fill("/synthetic/broken-new-folder")
    page.locator("#open-local-folder").click()
    expect(page.locator("#run-analysis")).to_be_disabled()
    expect(page.locator("#ct-image")).to_be_hidden()
    api.finish("failed")
    page.clock.fast_forward(1100)
    expect(page.locator("#local-folder-notice")).to_contain_text("Synthetic read failure")
    expect(page.locator("#run-analysis")).to_be_disabled()
    expect(page.locator("#viewer-status")).to_contain_text("Previous images are hidden")
    page.locator("#study-select").select_option("0")
    expect(page.locator("#ct-image")).to_be_visible()
    expect(page.locator("#run-analysis")).to_be_enabled()
    page.locator("#language-toggle").click()
    expect(page.locator("#run-analysis")).to_be_enabled()
    assert not api.errors


def test_local_qc_failure_is_distinct_from_skipped_header_warning(ui_page: Page) -> None:
    page = ui_page
    api = FolderAPI(page)
    api.study["qc_adequate"] = False
    open_local(page, api)
    expect(page.locator("#ct-image")).to_be_visible()
    expect(page.locator("#study-qc")).to_have_text("QC limited")
    expect(page.locator("#viewer-status")).to_contain_text("cannot be analyzed")
    expect(page.locator("#run-analysis")).to_be_disabled()
    assert not api.errors


def test_stale_image_completion_never_replaces_new_selection(ui_page: Page) -> None:
    page = ui_page
    api = FolderAPI(page)
    api.include_demo = True
    pending: list[Route] = []

    def hold_image(route: Route) -> None:
        pending.append(route)

    page.route("**/api/studies/local/**", hold_image)
    open_local(page, api)
    expect(page.locator("#run-analysis")).to_be_disabled()
    assert pending
    page.locator("#dataset-filter").select_option("demo")
    expect(page.locator("#ct-image")).to_be_visible()
    expect(page.locator("#run-analysis")).to_be_enabled()
    selected_src = page.locator("#ct-image").get_attribute("src")
    pending[-1].fulfill(body=api.png, content_type="image/png")
    expect(page.locator("#ct-image")).to_have_attribute("src", selected_src or "")
    expect(page.locator("#study-phase")).to_have_text("Synthetic")
    expect(page.locator("#run-analysis")).to_be_enabled()
    assert not api.errors


@pytest.mark.parametrize("second_status", ["running", "failed"])
def test_late_import_completion_never_unblocks_a_newer_folder(
    ui_page: Page, second_status: str
) -> None:
    page = ui_page
    api = FolderAPI(page)
    page.locator("#local-folder-path").fill("/synthetic/A")
    page.locator("#open-local-folder").click()
    pending: list[Route] = []

    def hold_library(route: Route) -> None:
        pending.append(route)

    page.route("**/api/studies", hold_library)
    api.finish()
    page.clock.fast_forward(1100)
    expect(page.locator("#job-follow-status")).to_contain_text("Succeeded")
    assert pending
    assert api.job is not None
    first = dict(api.job)

    def submit_second(route: Route) -> None:
        api.posts.append(route.request.post_data_json)
        api.job = dict(
            first,
            id="synthetic-B",
            status="running",
            finished=False,
            result=None,
            result_available=False,
            error=None,
        )
        route.fulfill(status=202, json={"job": api.job, "created": True})

    page.route("**/api/local-studies", submit_second)
    page.locator("#local-folder-path").fill("/synthetic/B")
    page.locator("#open-local-folder").click()
    expect(page.locator("#job-follow-status")).to_contain_text("Running")
    if second_status == "failed":
        api.finish("failed")
        page.clock.fast_forward(1100)
        expect(page.locator("#local-folder-notice")).to_contain_text("Synthetic read failure")
    with page.expect_response("**/api/studies"):
        pending[-1].fulfill(json={"studies": [api.study], "libraries": []})
    # Flush the resolved fetch continuation before asserting that it left B untouched.
    page.wait_for_timeout(50)
    expect(page.locator("#run-analysis")).to_be_disabled()
    expect(page.locator("#ct-image")).to_be_hidden()
    expect(page.locator("#viewer-status")).to_contain_text("Previous images are hidden")
    assert api.job is not None
    assert api.job["id"] == "synthetic-B"
    assert not api.errors


def test_search_does_not_unlock_previous_study_after_failed_folder(ui_page: Page) -> None:
    page = ui_page
    api = FolderAPI(page)
    open_local(page, api)
    expect(page.locator("#run-analysis")).to_be_enabled()
    page.locator("#local-folder-path").fill("/synthetic/B")
    page.locator("#open-local-folder").click()
    api.finish("failed")
    page.clock.fast_forward(1100)
    expect(page.locator("#run-analysis")).to_be_disabled()
    page.locator("#study-search").fill("opaque")
    expect(page.locator("#run-analysis")).to_be_disabled()
    expect(page.locator("#ct-image")).to_be_hidden()
    page.locator("#study-select").select_option("0")
    expect(page.locator("#run-analysis")).to_be_enabled()


@pytest.mark.parametrize("selection", ["study", "dataset"])
def test_manual_selection_while_import_runs_prevents_later_auto_selection(
    ui_page: Page, selection: str
) -> None:
    page = ui_page
    api = FolderAPI(page)
    api.include_demo = True
    page.reload()
    expect(page.locator("#study-select option:checked")).to_have_text("phantom")
    page.locator("#local-folder-path").fill("/synthetic/A")
    page.locator("#open-local-folder").click()
    expect(page.locator("#job-follow-status")).to_contain_text("Running")
    if selection == "study":
        page.locator("#study-select").select_option(label="phantom")
    else:
        page.locator("#dataset-filter").select_option("demo")
    expect(page.locator("#run-analysis")).to_be_enabled()
    api.finish()
    page.clock.fast_forward(1100)
    expect(page.locator("#study-select option:checked")).to_have_text("phantom")
    expect(page.locator("#study-phase")).to_have_text("Synthetic")
    expect(page.locator("#run-analysis")).to_be_enabled()
    page.locator("#nav-jobs").click()
    expect(page.locator('tr[data-job="synthetic-folder-job"]')).to_contain_text("Succeeded")
    assert not api.errors


def test_late_submit_response_does_not_override_explicit_study_choice(ui_page: Page) -> None:
    page = ui_page
    api = FolderAPI(page)
    api.include_demo = True
    page.reload()
    expect(page.locator("#study-select option:checked")).to_have_text("phantom")
    pending: list[Route] = []

    def hold_submit(route: Route) -> None:
        pending.append(route)

    page.route("**/api/local-studies", hold_submit)
    page.locator("#local-folder-path").fill("/synthetic/A")
    page.locator("#open-local-folder").click()
    expect(page.locator("#run-analysis")).to_be_disabled()
    assert pending
    page.locator("#study-select").select_option(label="phantom")
    expect(page.locator("#run-analysis")).to_be_enabled()
    with page.expect_response("**/api/local-studies"):
        api.submit(pending[-1])
    page.wait_for_timeout(50)
    expect(page.locator("#request-timer")).to_be_hidden()
    expect(page.locator("#study-select option:checked")).to_have_text("phantom")
    expect(page.locator("#run-analysis")).to_be_enabled()
    assert not api.errors


def test_delayed_refresh_cannot_replace_a_newly_opened_folder(ui_page: Page) -> None:
    page = ui_page
    api = FolderAPI(page)
    open_local(page, api)
    expect(page.locator("#run-analysis")).to_be_enabled()
    first_study = dict(api.study)
    assert api.job is not None
    first_job = dict(api.job)
    pending: list[Route] = []

    def inventory(route: Route) -> None:
        if not pending:
            pending.append(route)
        else:
            route.fulfill(json={"studies": [api.study], "libraries": []})

    page.route("**/api/studies", inventory)
    page.locator("#refresh-studies").click()
    assert pending
    api.study = dict(first_study, case_id="SYNTHETIC-B-opaque")

    def submit_second(route: Route) -> None:
        api.job = dict(
            first_job,
            id="synthetic-B-job",
            case_id=api.study["case_id"],
            status="running",
            finished=False,
            result=None,
            result_available=False,
            error=None,
        )
        route.fulfill(status=202, json={"job": api.job, "created": True})

    page.route("**/api/local-studies", submit_second)
    page.locator("#local-folder-path").fill("/synthetic/B")
    page.locator("#open-local-folder").click()
    api.finish()
    page.clock.fast_forward(1100)
    expect(page.locator("#study-select option:checked")).to_contain_text("SYNTHETI")
    expect(page.locator("#run-analysis")).to_be_enabled()
    with page.expect_response("**/api/studies"):
        pending[0].fulfill(json={"studies": [first_study], "libraries": []})
    page.wait_for_timeout(50)
    expect(page.locator("#study-select option:checked")).to_contain_text("SYNTHETI")
    expect(page.locator("#run-analysis")).to_be_enabled()
    assert not api.errors
