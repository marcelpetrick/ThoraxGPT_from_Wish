# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Capture reproducible documentation screenshots of the local workbench.

The script starts the web UI on a free loopback port with a temporary data root, creates
the synthetic demo phantom, and drives Chromium through Playwright. Ollama and the
optional 3D services point at an unused loopback port, so no real model runs and no
network access happens. Vision-model outputs in the comparison and the download progress
are mocked inside the browser. Only synthetic studies appear; never use patient data.

Usage, from the repository root:

    uv run python scripts/capture_screenshots.py            # write PNGs to docs/assets/
    uv run python scripts/capture_screenshots.py --check    # server/routes only, no browser
    uv run python scripts/capture_screenshots.py --only ui-about --out-dir /tmp/shots

Research use only. Screenshots document a self-made experimental tool; they show no
validated findings and no medical advice.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import os
import socket
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import uvicorn
from playwright.sync_api import (
    Browser,
    Locator,
    Page,
    Playwright,
    Route,
    ViewportSize,
    expect,
    sync_playwright,
)

from thoraxbench.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "docs" / "assets"
# An unused loopback port: every model endpoint is unreachable, so nothing leaves the host.
DEAD_ENDPOINT = "http://127.0.0.1:1"
DESKTOP: ViewportSize = {"width": 1440, "height": 900}
MOBILE: ViewportSize = {"width": 390, "height": 844}
# check_no_medical_data.sh rejects tracked files larger than 2 MB.
MAX_PNG_BYTES = 2_000_000
# Fixed fake browser time keeps timers and request-history estimates deterministic.
FROZEN_TIME = dt.datetime(2026, 1, 15, 9, 0, tzinfo=dt.UTC)
FIXED_ENGINE_S = 0.412
DEMO_SLICE = "22"
DISCLAIMER_EN = "Self-made experimental research tool"
TIMEOUT_MS = 30_000

# Mocked comparison plan: model id -> (outcome, simulated browser wait in ms).
COMPARISON_PLAN: dict[str, tuple[str, int]] = {
    "heuristic-hu": ("real", 1_400),
    "medgemma1.5-q4": ("abstain", 48_200),
    "medgemma1.5-q8": ("findings", 63_500),
    "qwen3-vl-4b-nothink": ("error", 3_100),
}
# A configured research model kept unavailable so the comparison shows an explicit skip.
COMPARISON_SKIPPED = "gemma3-4b"
DOWNLOAD_MODEL = "gemma3-4b"


class CaptureError(RuntimeError):
    """A screenshot precondition failed; the message tells the operator what to fix."""


@dataclass(frozen=True)
class Shot:
    """One documentation screenshot."""

    name: str
    description: str
    capture: Callable[[Browser, str, Path], None]


# --------------------------------------------------------------------------- server


def _offline() -> dict[str, Any]:
    return {
        "ollama_url": DEAD_ENDPOINT,
        "service_urls": dict.fromkeys(Settings().service_urls, DEAD_ENDPOINT),
    }


@contextlib.contextmanager
def running_server(data_dir: Path, settings: Settings | None = None) -> Iterator[str]:
    """Serve the workbench on a free loopback port; yield its base URL."""
    from thoraxbench.api.app import create_app  # noqa: PLC0415 - import after env is final

    settings = settings or Settings(data_dir=data_dir, **_offline())
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    address = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            if not thread.is_alive():
                raise CaptureError("local workbench server stopped during startup")
            if time.monotonic() > deadline:
                raise CaptureError("local workbench server did not start within 15 s")
            time.sleep(0.05)
        yield address
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CaptureError(message)


def check_routes(address: str, data_dir: Path) -> list[str]:
    """Validate every route the screenshots use, without a browser."""
    done: list[str] = []
    leaks = {str(data_dir), str(data_dir.resolve()), socket.gethostname()}
    with httpx.Client(base_url=address, timeout=60.0, trust_env=False) as client:
        for path in ("/", "/about"):
            page = client.get(path)
            _require(page.status_code == 200, f"GET {path} returned {page.status_code}")
            _require(DISCLAIMER_EN in page.text, f"GET {path} lacks the research disclaimer")
            done.append(f"GET {path}: 200 with research disclaimer")
        demo = client.post("/api/demo")
        _require(demo.status_code == 200, f"POST /api/demo returned {demo.status_code}")
        studies = client.get("/api/studies").json()["studies"]
        _require(
            [(s["dataset"], s["case_id"]) for s in studies] == [("demo", "phantom")],
            f"expected only the synthetic demo study, got {studies}",
        )
        done.append("POST /api/demo + GET /api/studies: only synthetic demo/phantom listed")
        image = client.get(f"/api/studies/demo/phantom/slice/{DEMO_SLICE}.png?window=lung")
        _require(
            image.status_code == 200 and image.headers["content-type"] == "image/png",
            f"slice PNG failed: {image.status_code}",
        )
        done.append(f"GET slice {DEMO_SLICE} PNG: {len(image.content)} bytes")
        models = {m["id"]: m for m in client.get("/api/models").json()["models"]}
        available = sorted(k for k, m in models.items() if m["available"])
        _require(available == ["heuristic-hu"], f"unexpected available models: {available}")
        for model_id in (*COMPARISON_PLAN, COMPARISON_SKIPPED):
            _require(model_id in models, f"configured model {model_id} is missing")
            _require(models[model_id]["recommended"], f"{model_id} is not recommended")
        _require(
            bool(models[DOWNLOAD_MODEL]["download_supported"]),
            f"{DOWNLOAD_MODEL} has no download path",
        )
        done.append(f"GET /api/models: {len(models)} configured, only heuristic-hu available")
        analysis = client.post(
            "/api/analyze",
            json={"dataset": "demo", "case_id": "phantom", "model_id": "heuristic-hu"},
        )
        _require(analysis.status_code == 200, f"heuristic analysis returned {analysis.status_code}")
        body = analysis.json()
        findings = body["result"]["report"]["findings"]
        _require(
            any(f["label"] == "pulmonary_nodule" and f["present"] for f in findings),
            "heuristic analysis did not report the synthetic nodule",
        )
        done.append(f"POST /api/analyze heuristic-hu: {len(findings)} findings, nodule present")
        exported = client.get(body["downloads"]["html"])
        _require(exported.status_code == 200, "HTML report download failed")
        visible = analysis.text + client.get("/").text + client.get("/api/about").text
        found = sorted(leak for leak in leaks if leak and leak in visible)
        _require(not found, f"machine-specific values leak into UI responses: {found}")
        done.append("No temporary path or hostname in analysis, page or About responses")
    return done


# --------------------------------------------------------------------------- browser


def find_chromium(playwright: Playwright) -> Path:
    """Locate Chromium; honours PLAYWRIGHT_BROWSERS_PATH, then the e2e cache fallback."""
    default = Path(playwright.chromium.executable_path)
    if default.exists():
        return default
    roots = [Path.home() / ".cache" / "ms-playwright"]
    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if configured and configured != "0":
        roots.insert(0, Path(configured))
    for root in roots:
        candidates = sorted(root.glob("chromium-*/chrome-linux*/chrome"))
        if candidates:
            return candidates[-1]
    raise CaptureError(
        "Chromium not found. Run `uv run playwright install chromium` "
        "or set PLAYWRIGHT_BROWSERS_PATH to an existing browser cache."
    )


def _open(
    browser: Browser, address: str, path: str = "/", viewport: ViewportSize = DESKTOP
) -> Page:
    """Open a fresh context: English, light, defaults only, no stored preferences."""
    context = browser.new_context(
        viewport=viewport,
        device_scale_factor=1,
        locale="en-US",
        timezone_id="UTC",
        color_scheme="light",
        reduced_motion="reduce",
    )
    page = context.new_page()
    page.set_default_timeout(TIMEOUT_MS)
    page.goto(f"{address}{path}")
    expect(page.locator(".research-banner")).to_contain_text(DISCLAIMER_EN)
    return page


def _freeze_clock(page: Page) -> None:
    page.clock.install(time=FROZEN_TIME)
    page.clock.pause_at(FROZEN_TIME + dt.timedelta(seconds=1))


def _create_demo(page: Page) -> None:
    page.locator("#create-demo").click()
    expect(page.locator("#study-select option:checked")).to_have_text("phantom")
    slider = page.locator("#slice-slider")
    expect(slider).to_be_enabled()
    slider.fill(DEMO_SLICE)
    slider.dispatch_event("input")
    _wait_for_slice(page)


def _wait_for_slice(page: Page) -> None:
    expect(page.locator("img[src*='/slice/']")).to_be_visible()
    page.wait_for_function(
        "() => { const image = document.querySelector(\"img[src*='/slice/']\"); "
        "return image && image.complete && image.naturalWidth > 0; }"
    )


def _settle(page: Page) -> None:
    """Remove hover, focus and tooltips so nothing transient lands in the image."""
    size = page.viewport_size or DESKTOP
    page.mouse.move(size["width"] - 1, size["height"] - 1)
    page.keyboard.press("Escape")
    page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
    expect(page.locator("#tooltip")).to_be_hidden()
    page.evaluate("() => document.fonts.ready.then(() => true)")


def _save(target: Page | Locator, path: Path, *, full_page: bool = False) -> None:
    style = "#tooltip{display:none!important}"
    if isinstance(target, Page):
        if full_page and target.viewport_size:
            # Chromium's full_page capture misplaces position:fixed elements (sidebar, skip
            # link); grow the viewport to the document height instead.
            height = int(target.evaluate("document.documentElement.scrollHeight"))
            target.set_viewport_size({"width": target.viewport_size["width"], "height": height})
        target.evaluate("window.scrollTo(0, 0)")
        target.screenshot(path=path, animations="disabled", caret="hide", style=style)
    else:
        target.screenshot(path=path, animations="disabled", caret="hide", style=style)
    size = path.stat().st_size
    if size > MAX_PNG_BYTES:
        raise CaptureError(f"{path.name} is {size} bytes; the data gate allows < 2 MB")
    print(f"  wrote {path} ({size} bytes)")


def _close(page: Page) -> None:
    page.context.close()


def _job_fixture(page: Page, respond: Any, models: list[str] | None = None) -> Any:
    """Use the same labelled job fixture as browser acceptance tests."""
    sys.path.insert(0, str(REPO_ROOT))
    from tests.e2e.mock_jobs import MockJobs  # noqa: PLC0415 - source-tree dev fixture

    return MockJobs(page, respond, models=models)


def _heuristic_output(page: Page) -> dict[str, Any]:
    """Call the real synthetic engine, then disclose a fixed illustrative stage time."""
    response = page.request.post(
        f"{urlsplit(page.url).scheme}://{urlsplit(page.url).netloc}/api/analyze",
        data={"dataset": "demo", "case_id": "phantom", "model_id": "heuristic-hu"},
        timeout=120_000,
    )
    _require(response.ok, "synthetic heuristic analysis failed")
    body: dict[str, Any] = response.json()
    body["result"]["perf"]["total_s"] = FIXED_ENGINE_S
    return body


def _run_heuristic(page: Page, wait_ms: int) -> None:
    """Run real synthetic analysis through a scripted job timing fixture."""
    output = _heuristic_output(page)
    jobs = _job_fixture(page, lambda _model: "hold")
    _freeze_clock(page)
    page.locator("#run-analysis").click()
    expect(page.locator("#job-bar")).to_be_visible()
    jobs.elapsed = wait_ms / 1000
    jobs.finish(output)
    page.clock.fast_forward(1100)
    expect(page.locator("#download-json")).to_have_attribute("aria-disabled", "false")
    expect(page.locator("#metric-time")).to_have_text(f"{FIXED_ENGINE_S:.3f} s")


def _wait_until(page: Page, condition: Callable[[], bool], message: str) -> None:
    deadline = time.monotonic() + TIMEOUT_MS / 1000
    while not condition():
        if time.monotonic() > deadline:
            raise CaptureError(message)
        page.wait_for_timeout(50)


# --------------------------------------------------------------------------- shots


def shot_study_viewer(browser: Browser, address: str, path: Path) -> None:
    """Synthetic phantom loaded, setup panel and viewer at desktop width."""
    page = _open(browser, address)
    _create_demo(page)
    _settle(page)
    _save(page, path)
    _close(page)


def shot_results(browser: Browser, address: str, path: Path) -> None:
    """Real heuristic-hu findings below the research banner, full page."""
    page = _open(browser, address)
    _create_demo(page)
    _run_heuristic(page, wait_ms=1_800)
    expect(page.locator("#findings-table")).to_contain_text("Pulmonary nodule")
    expect(page.locator("#results-content [data-i18n='scoresNotice']")).to_be_visible()
    _settle(page)
    _save(page, path, full_page=True)
    _close(page)


def _mock_output(model_id: str, outcome: str) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    if outcome == "findings":
        findings = [
            {"label": "pulmonary_nodule", "present": True, "confidence": 0.8},
            {"label": "pleural_effusion", "present": False, "confidence": 0.6},
        ]
    return {
        "id": f"mock-{model_id}",
        "result": {
            "model_id": model_id,
            "perf": {"total_s": COMPARISON_PLAN[model_id][1] / 1000 - 0.3},
            "report": {"abstain": outcome == "abstain", "findings": findings},
            "raw_error": "Mocked abstention for documentation" if outcome == "abstain" else None,
        },
        "markdown": "Research use only. Mocked model output for documentation; not medical advice.",
        "downloads": {"html": f"/mock/{model_id}.html"},
    }


def _comparison_inventory(route: Route) -> None:
    response = route.fetch()
    body: dict[str, Any] = response.json()
    for model in body["models"]:
        if model["id"] in COMPARISON_PLAN:
            model["available"] = True
    route.fulfill(response=response, json=body)


def shot_comparison(browser: Browser, address: str, path: Path) -> None:
    """Sequential comparison with labelled scripted abstention, error and skip."""
    page = _open(browser, address)
    page.route("**/api/models", _comparison_inventory)
    page.reload()
    _create_demo(page)
    real = _heuristic_output(page)
    jobs = _job_fixture(page, lambda _model: "hold", [*COMPARISON_PLAN, COMPARISON_SKIPPED])
    jobs.skip(COMPARISON_SKIPPED)
    _freeze_clock(page)
    page.locator("#compare-models").check()
    page.locator("#run-analysis").click()
    expect(page.locator("#job-bar")).to_be_visible()
    for index, (model, (outcome, wait_ms)) in enumerate(COMPARISON_PLAN.items()):
        jobs.elapsed += wait_ms / 1000
        reply = (
            real
            if outcome == "real"
            else ("error", "Mocked service offline (documentation)")
            if outcome == "error"
            else _mock_output(model, outcome)
        )
        jobs.finish_step(jobs.jobs[0], index, reply)
        page.clock.fast_forward(1100)
    expect(page.locator("#comparison-download")).to_be_visible()
    panel = page.locator("#comparison-panel")
    expect(panel).to_contain_text("not directly comparable across model families")
    expect(page.locator(f"#comparison-body tr[data-model='{COMPARISON_SKIPPED}']")).to_contain_text(
        "Skipped"
    )
    expect(page.locator("#comparison-body tr[data-model='qwen3-vl-4b-nothink']")).to_contain_text(
        "Mocked service offline"
    )
    _settle(page)
    _save(panel, path)
    _close(page)


def shot_jobs(browser: Browser, address: str, path: Path) -> None:
    """Labelled scripted running/queued jobs over the synthetic phantom."""
    page = _open(browser, address)
    _create_demo(page)
    jobs = _job_fixture(page, lambda _model: "hold")
    _freeze_clock(page)
    page.locator("#run-analysis").click()
    expect(page.locator("#job-bar")).to_be_visible()
    jobs.elapsed = 75.0
    page.locator("#nav-jobs").click()
    page.clock.fast_forward(1100)
    expect(page.locator("#jobs-body")).to_contain_text("Running")
    _settle(page)
    _save(page, path)
    _close(page)


def shot_model_setup(browser: Browser, address: str, path: Path) -> None:
    """Model availability panel: terms acknowledged, mocked download progress."""
    page = _open(browser, address)
    page.locator("#model-setup > summary").click()
    row = page.locator(f"tr[data-setup-model='{DOWNLOAD_MODEL}']")
    expect(row.get_by_role("button", name="Download model weights")).to_be_disabled()
    page.route(
        f"**/api/models/{DOWNLOAD_MODEL}/pull",
        lambda route: route.fulfill(
            json={
                "id": "00000000-0000-4000-8000-000000000000",
                "model_id": DOWNLOAD_MODEL,
                "status": "running",
                "detail": "pulling layer (mocked for documentation)",
                "completed": 1_048_576_000,
                "total": 3_338_801_804,
            }
        ),
    )
    # The paused clock keeps the poll timer from firing, so the mocked snapshot stays put.
    _freeze_clock(page)
    row.get_by_role("checkbox").check()
    row.get_by_role("button", name="Download model weights").click()
    progress = page.locator("#pull-progress")
    expect(progress).to_contain_text("Active layer bytes")
    _settle(page)
    _save(page.locator("#model-setup"), path)
    _close(page)


def shot_about(browser: Browser, address: str, path: Path) -> None:
    """About page with author, research purpose and dependency licenses."""
    page = _open(browser, address, "/about")
    expect(page.locator("#libraries-table")).to_contain_text("pydantic")
    expect(page.locator("#about-version")).not_to_have_text("—")
    _settle(page)
    _save(page, path, full_page=True)
    _close(page)


def shot_dark_de(browser: Browser, address: str, path: Path) -> None:
    """German interface in dark mode, selected explicitly through the toggles."""
    page = _open(browser, address)
    page.locator("#language-toggle").click()
    page.locator("#theme-toggle").click()
    expect(page.locator("html")).to_have_attribute("lang", "de")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    _create_demo(page)
    _run_heuristic(page, wait_ms=1_800)
    _settle(page)
    _save(page, path)
    _close(page)


def shot_mobile(browser: Browser, address: str, path: Path) -> None:
    """Narrow phone viewport with the synthetic study loaded."""
    page = _open(browser, address, viewport=MOBILE)
    _create_demo(page)
    _require(
        bool(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")),
        "mobile layout overflows horizontally",
    )
    page.evaluate("() => window.scrollTo(0, 0)")
    _settle(page)
    _save(page, path)
    _close(page)


def _evaluation_run(browser: Browser, address: str, viewport: ViewportSize = DESKTOP) -> Page:
    page = _open(browser, address, "/evaluation", viewport)
    row = page.locator("#eval-runs-body tr[data-run^='SYNTH-E001/']")
    row.get_by_role("button").click()
    expect(page.locator("#eval-cases-body tr")).to_have_count(10)
    return page


def shot_evaluation_runs(browser: Browser, address: str, path: Path) -> None:
    """Evaluation: stored synthetic runs and the per-case reference/prediction table."""
    page = _evaluation_run(browser, address)
    expect(page.locator("#eval-runs-body")).to_contain_text("SYNTH-E000")
    _settle(page)
    _save(page, path, full_page=True)
    _close(page)


def shot_evaluation_case(browser: Browser, address: str, path: Path) -> None:
    """Evaluation case detail: evidence check, image information and stored responses."""
    page = _evaluation_run(browser, address)
    page.locator("#eval-cases-body tr[data-case='q4-p2/lidc_idri/SYNTH-P3'] button").click()
    expect(page.locator("#eval-images-note")).to_contain_text("not stored")
    page.locator("#eval-parsed-details").evaluate("element => { element.open = false; }")
    _settle(page)
    _save(page.locator("#eval-case"), path)
    _close(page)


def shot_evaluation_compare(browser: Browser, address: str, path: Path) -> None:
    """Descriptive comparison of the scripted vision variants and the HU baseline."""
    page = _evaluation_run(browser, address)
    for checkbox in page.locator("#eval-runs-body input[type=checkbox]").all():
        checkbox.check()
    page.locator("#eval-compare").click()
    expect(page.locator("#eval-pairs-body tr")).to_have_count(3)
    _settle(page)
    _save(page.locator("#eval-comparison"), path)
    _close(page)


def shot_evaluation_mobile(browser: Browser, address: str, path: Path) -> None:
    """German dark Evaluation at phone width."""
    page = _evaluation_run(browser, address, MOBILE)
    page.locator("#language-toggle").click()
    page.locator("#theme-toggle").click()
    expect(page.locator("#evaluation-heading")).to_have_text("Auswertung gespeicherter Läufe")
    _require(
        bool(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")),
        "mobile Evaluation layout overflows horizontally",
    )
    page.evaluate("() => window.scrollTo(0, 0)")
    _settle(page)
    _save(page, path)
    _close(page)


SHOTS = (
    Shot("ui-jobs", "scripted synthetic job queue and server elapsed", shot_jobs),
    Shot("ui-study-viewer", "synthetic study in the viewer", shot_study_viewer),
    Shot("ui-results", "heuristic-hu findings with disclaimer", shot_results),
    Shot("ui-comparison", "mocked sequential model comparison", shot_comparison),
    Shot("ui-model-setup", "model availability and terms acknowledgement", shot_model_setup),
    Shot("ui-about", "About page", shot_about),
    Shot("ui-dark-de", "German interface, dark mode", shot_dark_de),
    Shot("ui-mobile", "390 px phone layout", shot_mobile),
)
# Served from a separate synthetic benchmark tree (real runner over phantoms).
EVALUATION_SHOTS = (
    Shot("ui-evaluation-runs", "Evaluation runs and case table", shot_evaluation_runs),
    Shot("ui-evaluation-case", "Evaluation case detail", shot_evaluation_case),
    Shot("ui-evaluation-compare", "Evaluation run comparison", shot_evaluation_compare),
    Shot("ui-evaluation-mobile", "Evaluation, German dark, 390 px", shot_evaluation_mobile),
)


def capture(address: str, out_dir: Path, shots: list[Shot], chromium: Path | None) -> None:
    """Launch Chromium once and write every requested screenshot."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        executable = chromium or find_chromium(playwright)
        print(f"Chromium: {executable}")
        browser = playwright.chromium.launch(executable_path=str(executable))
        try:
            for shot in shots:
                print(f"- {shot.name}: {shot.description}")
                shot.capture(browser, address, out_dir / f"{shot.name}.png")
        finally:
            browser.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument(
        "--check",
        action="store_true",
        help="start the server and validate the routes the shots use; launch no browser",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=DEFAULT_OUT, help="PNG directory (docs/assets/)"
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=[shot.name for shot in (*SHOTS, *EVALUATION_SHOTS)],
        help="capture only this shot; repeatable",
    )
    parser.add_argument("--chromium", type=Path, help="explicit Chromium executable")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the check or the capture; return a process exit status."""
    args = parse_args(argv)
    selected = [shot for shot in SHOTS if not args.only or shot.name in args.only]
    evaluation = [shot for shot in EVALUATION_SHOTS if not args.only or shot.name in args.only]
    try:
        with (
            tempfile.TemporaryDirectory(prefix="thoraxbench-shots-") as tmp,
            running_server(Path(tmp) / "demo") as address,
        ):
            print("Local workbench started on a temporary loopback port with synthetic data.")
            if args.check:
                for line in check_routes(address, Path(tmp) / "demo"):
                    print(f"  ok  {line}")
                print("Check passed: routes ready; no browser launched.")
            elif selected:
                capture(address, args.out_dir.resolve(), selected, args.chromium)
            if evaluation and not args.check:
                from thoraxbench.synthetic_runs import (  # noqa: PLC0415 - optional, slower setup
                    build_synthetic_benchmarks,
                )

                built = build_synthetic_benchmarks(Path(tmp) / "evaluation", **_offline())
                print(f"Synthetic benchmark runs: {len(built.runs)} (scripted, no model ran)")
                with running_server(built.settings.data_dir, built.settings) as eval_address:
                    capture(eval_address, args.out_dir.resolve(), evaluation, args.chromium)
            if not args.check:
                print(f"Done: {len(selected) + len(evaluation)} screenshot(s) in {args.out_dir}")
    except CaptureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
