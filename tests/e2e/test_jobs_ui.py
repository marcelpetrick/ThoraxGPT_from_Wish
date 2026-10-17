# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Real queue/browser flow with synthetic DICOM and a held loopback provider."""

from pathlib import Path
from time import sleep

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import browser_page, serve
from tests.e2e.fake_ollama import fake_ollama
from thoraxbench.config import Settings


@pytest.mark.parametrize("german", [False, True])
def test_real_job_survives_navigation_reload_and_can_be_cancelled(
    tmp_path: Path, german: bool
) -> None:
    with fake_ollama(["medgemma1.5:4b-it-q4_K_M"]) as provider:
        settings = Settings(data_dir=tmp_path / "data", ollama_url=provider.url)
        with serve(settings) as address, browser_page(address) as page:
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator("#create-demo").click()
            expect(page.locator("#run-analysis")).to_be_enabled()
            if german:
                page.locator("#language-toggle").click()
                page.locator("#theme-toggle").click()
            page.locator("#model-select").select_option("medgemma1.5-q4")
            page.locator("#run-analysis").click()
            expect(page.locator("#job-bar")).to_be_visible()
            page.locator("#nav-about").click()
            page.reload()
            expect(page.locator("#job-bar")).to_be_visible()
            expect(page.locator("#about-page")).to_be_visible()
            page.locator("#nav-jobs").click()
            expect(page.locator("#jobs-body tr")).to_have_count(1)
            label = "Stoppen" if german else "Stop"
            expect(page.locator("#jobs-body")).to_contain_text(label)
            queued = page.request.post(
                address + "/api/jobs",
                data={"kind": "analysis", "dataset": "demo", "case_id": "phantom"},
            ).json()["job"]
            page.clock.fast_forward(1100)
            queued_row = page.locator(f'tr[data-job="{queued["id"]}"]')
            expect(queued_row).to_contain_text("Wartend" if german else "Queued")
            queued_row.locator("button").click()
            expect(queued_row).to_have_attribute("data-status", "cancelled")
            page.locator('#jobs-body tr[data-status="running"] button').click()
            page.clock.fast_forward(1100)
            expect(page.locator('#jobs-body tr[data-status="cancelled"]')).to_have_count(2)
            expect(page.locator("#job-bar")).to_be_hidden()
            provider.release(8)
            submitted = page.request.post(
                address + "/api/jobs",
                data={"kind": "analysis", "dataset": "demo", "case_id": "phantom"},
            ).json()["job"]
            row = page.locator(f'tr[data-job="{submitted["id"]}"]')
            page.clock.fast_forward(2000)
            expect(row).to_have_attribute("data-status", "succeeded")
            row.locator("a").click()
            expect(page.locator("#metric-model")).to_have_text("heuristic-hu")
            expect(page.locator("#result-context")).to_contain_text("demo / phantom")
            href = page.locator("#download-html").get_attribute("href")
            assert href
            exported = page.request.get(address + href)
            assert exported.ok
            assert "data:image/png;base64," in exported.text()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("german", [False, True])
def test_partial_abstained_comparison_report_opens_in_new_tab(tmp_path: Path, german: bool) -> None:
    with fake_ollama(["medgemma1.5:4b-it-q4_K_M"]) as provider:
        settings = Settings(data_dir=tmp_path / "data", ollama_url=provider.url)
        with serve(settings) as address, browser_page(address) as page:
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator("#create-demo").click()
            expect(page.locator("#run-analysis")).to_be_enabled()
            if german:
                page.locator("#language-toggle").click()
                page.locator("#theme-toggle").click()
            provider.release(8)
            page.request.post(
                address + "/api/jobs",
                data={
                    "kind": "comparison",
                    "dataset": "demo",
                    "case_id": "phantom",
                    "n_images": 1,
                },
            )
            page.locator("#nav-jobs").click()
            page.clock.fast_forward(2000)
            row = page.locator(".job-step").filter(has_text="medgemma1.5-q4")
            opened = row.locator('a[target="_blank"]')
            expect(opened).to_be_visible(timeout=30_000)
            expect(opened).to_contain_text(
                "HTML in neuem Tab öffnen" if german else "Open HTML in new tab"
            )
            assert row.locator("a[download]").count() == 1
            with page.expect_popup() as popup:
                opened.click()
            report = popup.value
            expect(report.get_by_role("heading", name="Abstention", exact=True)).to_be_visible()
            expect(report.get_by_role("img").first).to_be_visible()
            assert (
                report.evaluate("getComputedStyle(document.querySelector('.hero')).backgroundImage")
                != "none"
            )
            report.close()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("german", [False, True])
def test_comparison_stop_uses_running_provider_not_skipped_detector(
    tmp_path: Path, german: bool
) -> None:
    with fake_ollama(["medgemma1.5:4b-it-q4_K_M"]) as provider:
        settings = Settings(data_dir=tmp_path / "data", ollama_url=provider.url)
        with serve(settings) as address, browser_page(address) as page:
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator("#create-demo").click()
            expect(page.locator("#run-analysis")).to_be_enabled()
            if german:
                page.locator("#language-toggle").click()
                page.locator("#theme-toggle").click()
            page.locator("#compare-models").check()
            page.locator("#run-analysis").click()
            page.wait_for_function(
                """async () => {
                    const data = await (await fetch('/api/jobs')).json();
                    return data.jobs.some(job => job.stage === 'inference'
                      && job.steps.some(step => step.model_id === 'monai-lung-nodule'
                        && step.status === 'skipped')
                      && job.steps.some(step => step.model_id === 'medgemma1.5-q4'
                        && step.status === 'running'));
                }"""
            )
            # Stage updates can briefly retain the previous heuristic's inference stage.
            # Wait for the held HTTP call, so cancellation genuinely occurs in Ollama.
            for _ in range(100):
                if provider.chats:
                    break
                sleep(0.05)
            assert provider.chats == 1
            page.clock.fast_forward(1100)
            page.locator("#stop-job").click()
            page.clock.fast_forward(1100)
            expect(page.locator("#job-caveat")).to_be_visible()
            expect(page.locator("#job-caveat")).to_contain_text("Ollama")
            expect(page.locator("#job-caveat")).not_to_contain_text(
                "Detektor" if german else "Detector"
            )
            page.locator("#nav-jobs").click()
            cancelled = page.locator('#jobs-body tr[data-status="cancelled"]')
            expect(cancelled).to_contain_text("Ollama")
            expect(cancelled).to_contain_text("Hintergrund" if german else "background")
