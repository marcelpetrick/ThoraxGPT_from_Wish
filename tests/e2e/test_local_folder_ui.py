# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Synthetic local-folder UI contract: no uploads, real paths, patient pixels or inference."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Page, Route, expect

pytestmark = pytest.mark.e2e


class FolderAPI:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.posts: list[dict[str, str]] = []
        self.folder_queries: list[str | None] = []
        self.include_demo = False
        self.job: dict | None = None
        self.errors: list[str] = []
        self.trace: list[tuple] = []
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.study = {
            "dataset": "local",
            "case_id": "opaque-synthetic-local",
            "n_slices": 64,
            "phase": "local",
            "qc_adequate": True,
        }
        page.request.post(page.url.rstrip("/") + "/api/demo")
        self.png = page.request.get(
            page.url.rstrip("/") + "/api/studies/demo/phantom/slice/22.png"
        ).body()
        page.route("**/api/local-folders*", self.folders)
        page.route("**/api/local-studies", self.submit)
        page.route(re.compile(r".*/api/jobs(?:/.*)?$"), self.jobs)
        page.route("**/api/studies", self.studies)
        page.route(
            "**/api/studies/local/**",
            lambda route: route.fulfill(body=self.png, content_type="image/png"),
        )
        page.reload()
        expect(page.locator("#folder-dropzone")).to_be_visible()

    def folders(self, route: Route) -> None:
        path = parse_qs(urlsplit(route.request.url).query).get("path", [None])[0]
        self.folder_queries.append(path)
        if path == "/denied":
            route.fulfill(status=403, json={"detail": "Synthetic access denied"})
            return
        current = path or "/demo"
        route.fulfill(
            json={
                "path": current,
                "parent": "/" if current != "/" else None,
                "folders": [{"name": "study A", "path": current.rstrip("/") + "/study A"}],
                "truncated": False,
                "disclaimer": "Synthetic research fixture",
            }
        )

    def submit(self, route: Route) -> None:
        self.posts.append(route.request.post_data_json)
        self.job = {
            "id": "synthetic-folder-job",
            "kind": "study-import",
            "dataset": "local",
            "case_id": self.study["case_id"],
            "models": [],
            "steps": [],
            "status": "running",
            "stage": "loading",
            "finished": False,
            "elapsed_s": 1.2,
            "result": None,
            "result_available": False,
            "queued_at": None,
            "started_at": None,
            "queue_position": None,
            "error": None,
        }
        route.fulfill(status=202, json={"job": self.job, "created": True})

    def jobs(self, route: Route) -> None:
        path = urlsplit(route.request.url).path
        self.trace.append(("jobs", path, self.job["status"] if self.job else None))
        if path.endswith("/cancel") and self.job:
            self.finish("cancelled")
        if path == "/api/jobs":
            route.fulfill(json={"jobs": [self.job] if self.job else [], "downloads": []})
        elif self.job:
            route.fulfill(json=self.job)
        else:
            route.fulfill(status=404, json={"detail": "Unknown job"})

    def studies(self, route: Route) -> None:
        local = self.job and self.job["status"] == "succeeded"
        self.trace.append(("studies", bool(local)))
        route.fulfill(
            json={
                "studies": ([self.study] if local else [])
                + (
                    [
                        {
                            "dataset": "demo",
                            "case_id": "phantom",
                            "n_slices": 64,
                            "phase": "synthetic",
                            "qc_adequate": True,
                        }
                    ]
                    if self.include_demo
                    else []
                ),
                "libraries": [],
            }
        )

    def finish(self, status: str = "succeeded") -> None:
        assert self.job is not None
        self.job.update(
            status=status,
            stage="done",
            finished=True,
            result={"study": self.study} if status == "succeeded" else None,
            result_available=status == "succeeded",
            error="Synthetic read failure" if status == "failed" else None,
        )


def drop(page: Page, text: str = "", mime: str = "text/plain", files: bool = False) -> None:
    transfer = page.evaluate_handle(
        "([text,mime,files]) => {const transfer = new DataTransfer(); "
        "if (files) transfer.items.add(new File(['synthetic'], 'study')); "
        "else transfer.setData(mime,text); return transfer;}",
        [text, mime, files],
    )
    page.locator("#folder-dropzone").dispatch_event("drop", {"dataTransfer": transfer})
    transfer.dispose()


@pytest.mark.parametrize("german", [False, True])
def test_local_import_survives_navigation_reload_and_opens_only_viewer(
    ui_page: Page, german: bool
) -> None:
    page = ui_page
    api = FolderAPI(page)
    page.set_viewport_size({"width": 390, "height": 844})
    if german:
        page.locator("#language-toggle").click()
        page.locator("#theme-toggle").click()
    page.locator("#folder-dropzone").focus()
    page.locator("#folder-dropzone").press("Enter")
    expect(page.locator("#local-folder-path")).to_be_focused()
    drop(page, "# local file\nfile:///demo/study%20A", "text/uri-list")
    expect(page.locator("#local-folder-notice")).to_contain_text(
        "eingereiht" if german else "queued"
    )
    assert api.posts == [{"path": "/demo/study A"}]
    expect(page.locator("#local-folder-path")).to_have_value("")
    expect(page.locator("#request-forecast")).to_contain_text(
        "keine Inferenz" if german else "no inference"
    )
    page.locator("#nav-about").click()
    page.reload()
    page.clock.fast_forward(1100)
    expect(page.locator("#job-bar")).to_be_visible()
    expect(page.locator("#job-follow-status")).to_contain_text(
        "Lokalen Ordner öffnen" if german else "Open local folder"
    )
    page.clock.resume()
    api.finish()
    page.clock.fast_forward(1100)
    page.locator("#nav-analysis").click()
    expect(page.locator("#study-phase")).to_contain_text(
        "Serversitzung" if german else "server session"
    )
    assert not api.errors
    expect(page.locator("#library-counts")).to_contain_text(
        "0 Entwicklungsstudien" if german else "0 development studies"
    )
    expect(page.locator("#ct-image")).to_be_visible()
    expect(page.locator("#results-content")).to_be_hidden()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert "/demo/study A" not in page.evaluate("JSON.stringify(localStorage)")


@pytest.mark.parametrize(
    ("value", "mime"),
    [
        ("/one\n/two", "text/plain"),
        ("relative/path", "text/plain"),
        ("file://remote/share", "text/uri-list"),
        ("file:///tmp/a%00b", "text/uri-list"),
        ("file:///a\nfile:///b", "text/uri-list"),
    ],
)
def test_invalid_drops_never_submit(ui_page: Page, value: str, mime: str) -> None:
    api = FolderAPI(ui_page)
    drop(ui_page, value, mime)
    expect(ui_page.locator("#local-folder-notice")).to_contain_text("absolute local folder path")
    assert api.posts == []


def test_browser_hidden_folder_paths_offer_browse_without_upload(ui_page: Page) -> None:
    api = FolderAPI(ui_page)
    drop(ui_page, files=True)
    expect(ui_page.locator("#local-folder-notice")).to_contain_text("browser hid")
    expect(ui_page.locator("#browse-local-folders")).to_be_focused()
    assert api.posts == []


@pytest.mark.parametrize("german", [False, True])
def test_browse_dialog_keyboard_errors_and_focus_restore(ui_page: Page, german: bool) -> None:
    page = ui_page
    api = FolderAPI(page)
    if german:
        page.locator("#language-toggle").click()
        page.locator("#theme-toggle").click()
    page.locator("#browse-local-folders").click()
    expect(page.locator("#folder-browser")).to_be_visible()
    expect(page.locator("#folder-browser-path")).to_be_focused()
    expect(page.locator("#folder-browser-path")).to_have_value("/demo")
    page.locator("#folder-browser-list button").first.click()
    expect(page.locator("#folder-browser-path")).to_have_value("/demo/study A")
    page.locator("#folder-parent").click()
    expect(page.locator("#folder-browser-path")).to_have_value("/")
    page.locator("#folder-browser-path").fill("/denied")
    page.locator("#folder-browser-path").press("Enter")
    expect(page.locator("#folder-browser-notice")).to_contain_text("Synthetic access denied")
    expect(page.locator("#folder-browser-select")).to_be_disabled()
    page.locator("#folder-browser").press("Escape")
    expect(page.locator("#folder-browser")).to_be_hidden()
    expect(page.locator("#browse-local-folders")).to_be_focused()
    expect(page.locator("#folder-browser-path")).to_have_value("")
    page.locator("#browse-local-folders").click()
    expect(page.locator("#folder-browser-select")).to_be_enabled()
    page.locator("#folder-browser-select").click()
    expect(page.locator("#folder-browser")).to_be_hidden()
    expect(page.locator("#local-folder-notice")).to_contain_text(
        "eingereiht" if german else "queued"
    )
    assert api.posts == [{"path": "/demo"}]


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_import_failure_and_cancellation_do_not_render_predictions(
    ui_page: Page, status: str
) -> None:
    page = ui_page
    api = FolderAPI(page)
    page.locator("#local-folder-path").fill("/demo/study A")
    page.locator("#local-folder-form").evaluate("form => form.requestSubmit()")
    expect(page.locator("#local-folder-notice")).to_contain_text("queued")
    api.finish(status)
    page.clock.fast_forward(1100)
    expect(page.locator("#local-folder-notice")).to_contain_text(
        "Synthetic read failure" if status == "failed" else "cancelled"
    )
    expect(page.locator("#results-content")).to_be_hidden()


def test_completion_waits_for_initial_model_inventory_without_losing_new_study(
    ui_page: Page,
) -> None:
    page = ui_page
    pending: list[Route] = []

    def hold_models(route: Route) -> None:
        pending.append(route)

    page.route("**/api/models", hold_models)
    api = FolderAPI(page)
    page.locator("#local-folder-path").fill("/demo/study A")
    page.locator("#open-local-folder").click()
    expect(page.locator("#local-folder-notice")).to_contain_text("queued")
    api.finish()
    page.clock.fast_forward(1100)
    expect(page.locator("#job-follow-status")).to_contain_text("Succeeded")
    assert pending
    pending[-1].fulfill(
        json={
            "models": [
                {
                    "id": "heuristic-hu",
                    "adapter": "heuristic",
                    "available": True,
                    "recommended": True,
                }
            ]
        }
    )
    expect(page.locator("#study-phase")).to_contain_text("server session")
    expect(page.locator("#study-select option:checked")).to_contain_text("Local study")
    expect(page.locator("#dataset-filter")).to_have_value("local")
    assert not api.errors


def test_rejected_folder_keeps_path_for_correction(ui_page: Page) -> None:
    page = ui_page
    api = FolderAPI(page)
    page.route(
        "**/api/local-studies",
        lambda route: route.fulfill(status=403, json={"detail": "Synthetic access denied"}),
    )
    page.locator("#local-folder-path").fill("/demo/correct me")
    page.locator("#open-local-folder").click()
    expect(page.locator("#local-folder-notice")).to_contain_text("Synthetic access denied")
    expect(page.locator("#local-folder-path")).to_have_value("/demo/correct me")
    assert api.job is None


def test_explicit_open_import_result_reselects_it_after_another_study(ui_page: Page) -> None:
    page = ui_page
    api = FolderAPI(page)
    api.include_demo = True
    page.locator("#local-folder-path").fill("/demo/study A")
    page.locator("#open-local-folder").click()
    expect(page.locator("#local-folder-notice")).to_contain_text("queued")
    api.finish()
    page.clock.fast_forward(1100)
    expect(page.locator("#study-phase")).to_contain_text("server session")
    page.locator("#dataset-filter").select_option("")
    page.locator("#study-select").select_option(label="phantom")
    expect(page.locator("#study-phase")).to_contain_text("Synthetic")
    page.locator("#nav-jobs").click()
    page.clock.fast_forward(1100)
    page.locator('tr[data-job="synthetic-folder-job"] a[data-job-link]').click()
    expect(page.locator("#study-select option:checked")).to_contain_text("Local study")
    expect(page.locator("#dataset-filter")).to_have_value("local")
    expect(page.locator("#study-phase")).to_contain_text("server session")
    expect(page.locator("#results-content")).to_be_hidden()
