# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Record an explicitly authorized calibration tour, then render two local 30-second drafts."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import math
import os
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Route, sync_playwright

from thoraxbench.splits import CaseGuard, Phase

PROJECT = "github.com/marcelpetrick/ThoraxGPT_from_Wish"
MODEL = "monai-lung-nodule"
CAUTION = "RESEARCH ONLY - NOT DIAGNOSIS | Selected calibration | LIDC overlap"
ATTRIBUTION = (
    "LIDC-IDRI / The Cancer Imaging Archive (TCIA), CC BY 3.0. "
    "Armato III et al. (2015), Data From LIDC-IDRI, doi:10.7937/K9/TCIA.2015.LO9QL9SX. "
    "Armato et al., Medical Physics 38(2):915-931 (2011), doi:10.1118/1.3528204. "
    "The authors acknowledge the National Cancer Institute and the Foundation for the "
    "National Institutes of Health, and their critical role in the creation of the free "
    "publicly available LIDC/IDRI Database used in this study. "
    "https://www.cancerimagingarchive.net/collection/lidc-idri/ "
    "https://creativecommons.org/licenses/by/3.0/ "
    "Presentation changes: windowed CT renders, UI recording, cropped excerpts and captions. "
    "No endorsement by TCIA or dataset contributors is implied."
)


def local_url(value: str) -> str:
    """Reject remote targets and credentials before any browser connection."""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use a credential-free loopback HTTP URL without a path")
    _ = parsed.port
    return value.rstrip("/")


def save(path: Path, value: object) -> None:
    """Atomically checkpoint metadata; never overwrite a different take."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def output_root(repo: Path) -> Path:
    """Keep all real frames beneath the repository's ignored local output directory."""
    root = repo.resolve() / "data" / "results" / "linkedin"
    if not root.resolve().is_relative_to(repo.resolve() / "data" / "results"):
        raise ValueError("Video output symlink escapes ignored results")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def preflight(repo: Path, dataset: str, case: str, model: str, allowed: bool) -> dict[str, Any]:
    """Read registry and split metadata only; never read patient pixels here."""
    if not allowed or dataset != "lidc_idri" or model != MODEL:
        raise ValueError(
            "Explicit real-calibration acknowledgement, LIDC-IDRI and detector required"
        )
    registry = yaml.safe_load((repo / "configs" / "datasets" / f"{dataset}.yaml").read_text())
    if not str(registry.get("status", "")).startswith("approved"):
        raise ValueError("Dataset registry is not approved")
    CaseGuard.load(repo / "data", repo / "manifests", dataset).check(case, Phase.CALIBRATION)
    return dict(registry)


@contextlib.contextmanager
def display(width: int, height: int) -> Iterator[str]:
    """Own a separate X server; never capture the person's desktop."""
    number = next(n for n in range(90, 200) if not Path(f"/tmp/.X11-unix/X{n}").exists())
    target = f":{number}"
    process = subprocess.Popen(
        ["Xvfb", target, "-screen", "0", f"{width}x{height}x24", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if Path(f"/tmp/.X11-unix/X{number}").exists():
                yield target
                return
            if process.poll() is not None:
                raise RuntimeError("Isolated Xvfb failed to start")
            time.sleep(0.05)
        raise RuntimeError("Isolated Xvfb startup timed out")
    finally:
        stop_process(process)


def stop_process(process: subprocess.Popen[bytes], interrupt: bool = False) -> None:
    """Close only our child, and reap it even when graceful shutdown times out."""
    if process.poll() is None:
        process.send_signal(2) if interrupt else process.terminate()
        try:
            process.wait(timeout=30 if interrupt else 10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def private_library(route: Route, dataset: str, case: str) -> None:
    """Narrow visible metadata, preserving the actual chosen-case server response."""
    response = route.fetch()
    payload = response.json()
    payload["studies"] = [
        row
        for row in payload["studies"]
        if row["dataset"] == dataset
        and row["case_id"] == case
        and row.get("phase") == "calibration"
    ]
    route.fulfill(response=response, json=payload)


def guard_case_request(route: Route, dataset: str, case: str) -> None:
    path = unquote(urlsplit(route.request.url).path)
    if path.startswith(f"/api/studies/{dataset}/{case}/"):
        route.continue_()
    else:
        route.abort("blockedbyclient")


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def master_path(folder: Path, expected_hash: str) -> Path:
    path = folder / "master.mp4"
    if not path.is_file() or not path.resolve().is_relative_to(folder.resolve()):
        raise ValueError("Master is missing or escapes its take")
    if not expected_hash or hash_file(path) != expected_hash:
        raise ValueError("Preserved master integrity check failed")
    return path


def verify_result(payload: dict[str, Any], commit: str) -> None:
    result = payload.get("result", {})
    report = result.get("report", {})
    provenance = result.get("provenance", {})
    findings = report.get("findings", [])
    if (
        result.get("model_id") != MODEL
        or result.get("raw_error")
        or report.get("abstain") is not False
        or not findings
        or any(finding.get("source") != "detector" for finding in findings)
    ):
        raise ValueError("Take requires actual successful detector-sourced output")
    if provenance.get("git_commit") != commit or provenance.get("git_dirty") is not False:
        raise ValueError("Result source identity differs from clean take source")


def x11_environment(target: str) -> dict[str, str]:
    """Keep Chromium on our Xvfb display even inside a Wayland desktop session."""
    return {
        key: value
        for key, value in os.environ.items()
        if key not in {"WAYLAND_DISPLAY", "WAYLAND_SOCKET"}
    } | {"DISPLAY": target, "XDG_SESSION_TYPE": "x11"}


def capture(args: argparse.Namespace) -> Path:  # noqa: PLR0912, PLR0915 - linear UI recording procedure
    repo, url = args.repo.resolve(), local_url(args.url)
    registry = preflight(repo, args.dataset, args.case, args.model, args.allow_real_calibration)
    if (args.width, args.height) not in {(2560, 1440), (3840, 2160)}:
        raise ValueError("Use 2560x1440 or 3840x2160 capture dimensions")
    if subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"]).strip():
        raise ValueError("Capture requires a clean committed checkout")
    root = output_root(repo)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    folder = root / f"{stamp}-{uuid.uuid4().hex}"
    folder.mkdir()
    print(f"Preserved take: {folder}", flush=True)
    if shutil.disk_usage(folder).free < 2_000_000_000:
        raise ValueError("Need at least 2 GB free for original and drafts")
    take: dict[str, Any] = {
        "recorder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "schema_version": 1,
        "status": "recording",
        "dataset": args.dataset,
        "case": args.case,
        "phase": "calibration",
        "model": args.model,
        "selected_case": True,
        "training_overlap": "yes",
        "attribution": ATTRIBUTION,
        "registry": registry,
        "events": [],
        "width": args.width,
        "height": args.height,
        "commit": subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip(),
    }
    save(folder / "take.json", take)
    master = folder / "master.mp4"
    with (
        display(args.width, args.height) as target,
        sync_playwright() as playwright,
        contextlib.ExitStack() as cleanup,
    ):

        def unfinished() -> None:
            if take["status"] == "recording":
                take["status"], take["error"] = (
                    "failed",
                    "Capture interrupted before finalization",
                )
                save(folder / "take.json", take)

        cleanup.callback(unfinished)
        executable = args.chromium or playwright.chromium.executable_path
        if not Path(executable).is_file():
            candidates = sorted(
                (Path.home() / ".cache/ms-playwright").glob("chromium-*/chrome-linux*/chrome")
            )
            executable = str(candidates[-1]) if candidates else executable
        browser = playwright.chromium.launch(
            downloads_path=str(folder / "downloads"),
            executable_path=str(executable),
            headless=False,
            env=x11_environment(target),
            args=[
                "--ozone-platform=x11",
                "--disable-gpu",
                "--kiosk",
                f"--window-size={args.width},{args.height}",
            ],
        )
        cleanup.callback(browser.close)
        context = browser.new_context(
            viewport={"width": args.width, "height": args.height}, locale="en-US"
        )
        context.route(
            "**/api/studies", lambda route: private_library(route, args.dataset, args.case)
        )
        context.route(
            "**/api/studies/**",
            lambda route: guard_case_request(route, args.dataset, args.case),
        )
        take["library_narrowed_for_privacy"] = True
        page = context.new_page()
        page.set_default_timeout(30_000)
        page.goto(url)
        # Browser display zoom only. This changes presentation, never model inputs/results.
        page.evaluate("document.documentElement.style.zoom = '1.5'")
        log = (folder / "capture.log").open("wb")
        cleanup.callback(log.close)
        recorder = subprocess.Popen(
            [
                "ffmpeg",
                "-nostdin",
                "-n",
                "-f",
                "x11grab",
                "-draw_mouse",
                "0",
                "-video_size",
                f"{args.width}x{args.height}",
                "-framerate",
                "30",
                "-i",
                target,
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "16",
                "-threads",
                "2",
                "-pix_fmt",
                "yuv420p",
                str(master),
            ],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
        )
        cleanup.callback(stop_process, recorder, True)
        started = time.monotonic()

        @contextlib.contextmanager
        def shot(name: str) -> Iterator[None]:
            event: dict[str, Any] = {"name": name, "start": time.monotonic() - started}
            take["events"].append(event)
            save(folder / "take.json", take)
            try:
                yield
                page.wait_for_timeout(6000)
            finally:
                pages = context.pages
                active = pages[-1] if pages else None
                focus = {
                    "study": "#viewer-heading",
                    "viewer": "#ct-image",
                    "setup": "#run-analysis",
                    "running": "#jobs-body",
                    "findings": "#results-heading",
                    "candidates": "#candidate-previews",
                    "report": "#candidates",
                    "about": "#about-page",
                }.get(name)
                if focus and active is not None:
                    locator = active.locator(focus)
                    if locator.count():
                        box = locator.bounding_box()
                        if box:
                            event["crop"] = focus_crop(box, args.width, args.height)
                event["end"] = time.monotonic() - started
                save(folder / "take.json", take)

        try:
            page.wait_for_timeout(1200)
            if recorder.poll() is not None:
                raise RuntimeError("ffmpeg capture failed before inference; inspect capture.log")
            if any(
                not item["finished"] for item in page.request.get(url + "/api/jobs").json()["jobs"]
            ):
                raise ValueError("Capture requires an idle processing queue")
            available = page.request.get(url + "/api/studies").json()["studies"]
            selected = next(
                (
                    row
                    for row in available
                    if row["dataset"] == args.dataset and row["case_id"] == args.case
                ),
                None,
            )
            if selected is None or selected.get("phase") != "calibration":
                raise ValueError("Server does not expose this case as calibration")
            with shot("study"):
                page.locator("#dataset-filter").select_option(args.dataset)
                page.locator("#study-select").select_option(value="0")
                page.locator("#slice-slider").fill("54")
                page.locator("#slice-slider").dispatch_event("input")
            with shot("viewer"):
                for window in ("lung", "mediastinum", "bone", "lung"):
                    page.locator("#window-select").select_option(window)
                    page.wait_for_timeout(1000)
                page.locator("#window-select").focus()
            with shot("setup"):
                page.locator("#model-select").select_option(MODEL)
                page.locator("#open-model-setup").click()
                page.wait_for_timeout(2500)
                page.locator("#model-setup > summary").click()
                page.locator("#run-analysis").scroll_into_view_if_needed()
            with shot("running"):
                with page.expect_response(
                    lambda response: (
                        urlsplit(response.url).path == "/api/jobs"
                        and response.request.method == "POST"
                    )
                ) as submitted:
                    page.locator("#run-analysis").click()
                take["job_id"] = submitted.value.json()["job"]["id"]
                page.locator("#nav-jobs").click()
                deadline = time.monotonic() + args.timeout
                while time.monotonic() < deadline:
                    job = page.request.get(url + "/api/jobs/" + take["job_id"]).json()
                    if job.get("finished"):
                        break
                    page.wait_for_timeout(1000)
                else:
                    raise TimeoutError("Live job exceeded capture timeout; retain failed take")
                take["job"] = {key: value for key, value in job.items() if key != "result"}
                if job["status"] != "succeeded":
                    raise RuntimeError("Live detector did not succeed; retain this failure")
            with shot("findings"):
                page.locator(f'tr[data-job="{take["job_id"]}"] a').click()
                page.locator("#results-heading").scroll_into_view_if_needed()
            with shot("candidates"):
                page.locator("#candidate-heading").scroll_into_view_if_needed()
                page.locator("#candidate-body button").first.click()
                page.wait_for_timeout(2000)
                page.locator("#candidate-previews").scroll_into_view_if_needed()
            with shot("report"):
                with page.expect_popup() as opened:
                    page.locator("#open-html").click()
                report = opened.value
                report.wait_for_load_state()
                report.locator("#candidates").scroll_into_view_if_needed()
                report.wait_for_function(
                    "[...document.images].every(image => image.complete && image.naturalWidth > 0)"
                )
                report.wait_for_timeout(6000)
            report.close()
            with page.expect_download() as downloaded:
                page.locator("#download-html").click()
            downloaded.value.save_as(folder / "offline-report.html")
            with shot("evaluation"):
                page.locator("#nav-evaluation").click()
            with shot("about"):
                page.locator("#nav-about").click()
                page.locator("#language-toggle").click()
                page.locator("#theme-toggle").click()
                page.wait_for_timeout(2500)
                page.locator("#language-toggle").click()
                page.locator("#theme-toggle").click()
            with shot("manual"):
                manual = context.new_page()
                manual.goto((repo / "docs" / "manual.html").as_uri())
                manual.wait_for_timeout(6000)
            manual.close()
            result = job.get("result", {})
            take["result_id"] = result.get("id")
            take["provenance"] = result.get("result", {}).get("provenance", {})
            metadata = result.get("result", {}).get("raw_meta", {})
            take["detector"] = {
                key: metadata.get(key)
                for key in (
                    "detector",
                    "weights_sha256",
                    "bundle_revision",
                    "model_identity",
                    "n_candidates",
                )
            }
            verify_result(result, take["commit"])
            take["status"] = "finalizing"
        except Exception as exc:
            take["status"], take["error"] = "failed", str(exc)
            with contextlib.suppress(PlaywrightError):
                page.wait_for_timeout(5000)
            raise
        finally:
            take["recording_wall_s"] = time.monotonic() - started
            save(folder / "take.json", take)

    try:
        probe = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(master),
                ]
            )
        )
        stream = probe["streams"][0]
        if (
            recorder.returncode not in {0, 255}
            or stream["width"] != args.width
            or stream["height"] != args.height
            or stream["r_frame_rate"] != "30/1"
            or abs(float(probe["format"]["duration"]) - take["recording_wall_s"]) > 3
        ):
            raise ValueError("Original recording is incomplete or has unexpected dimensions/timing")
        take["master_probe"] = probe
        take["status"] = "succeeded"
    except Exception as exc:
        take["status"], take["error"] = "failed", str(exc)
        save(folder / "take.json", take)
        raise
    take["master_sha256"] = hash_file(master)
    save(folder / "take.json", take)
    save(folder / "cut-plan.json", default_plan(take))
    return folder


def focus_crop(box: dict[str, float], width: int, height: int) -> list[int]:
    """Keep a readable detail, with bounded even pixel coordinates for H.264."""
    crop_width, crop_height = min(1400, width), min(1100, height)
    x = max(0, min(width - crop_width, round(box["x"] - 30)))
    y = max(0, min(height - crop_height, round(box["y"] - 60)))
    return [x // 2 * 2, y // 2 * 2, crop_width, crop_height]


def default_plan(take: dict[str, Any]) -> dict[str, Any]:
    """Editable five 5-second excerpts plus a 5-second project/credit end card."""
    elapsed = float(take.get("job", {}).get("elapsed_s", 0))
    labels = {
        "study": "ThoraxBench Local: inspect a selected public calibration study",
        "viewer": (f"Browse CT slices. Wait shortened; actual processing {elapsed:.1f} seconds"),
        "setup": "Local MONAI detector; scores are uncalibrated",
        "running": f"Wait shortened; actual processing {elapsed:.1f} seconds",
        "findings": "Review detector candidates, not a medical diagnosis",
        "candidates": "Candidate crops illustrate detector proposals; no VLM verification",
        "report": "Open the actual image-and-text report in a new tab",
        "about": "English / German, light / dark; open-source contributions welcome",
    }
    events = {event["name"]: event for event in take["events"]}
    plans = {}
    for name, phases in {
        "A": ["study", "setup", "running", "findings", "report"],
        "B": ["viewer", "findings", "candidates", "report", "about"],
    }.items():
        plans[name] = [
            {
                "event": phase,
                "start": events[phase]["start"] + 1
                if phase == "running"
                else events[phase]["end"] - 5,
                "crop": events[phase].get("crop"),
                "duration": 5,
                "caption": labels[phase],
            }
            for phase in phases
        ]
    return {"version": 1, "cuts": plans, "endcard_seconds": 5}


def validate_plan(plan: dict[str, Any], take: dict[str, Any]) -> None:
    """Refuse misleading or out-of-range edits; original remains untouched."""
    if take.get("status") != "succeeded":
        raise ValueError("A failed take cannot be rendered as a successful workflow")
    if set(plan["cuts"]) != {"A", "B"} or plan["endcard_seconds"] != 5:
        raise ValueError("Require two cuts and a five-second end card")
    for clips in plan["cuts"].values():
        if len(clips) != 5 or sum(clip["duration"] for clip in clips) != 25:
            raise ValueError("Require five excerpts totaling 25 seconds")
        for clip in clips:
            if (
                not all(math.isfinite(float(clip[field])) for field in ("start", "duration"))
                or clip["duration"] <= 0
                or clip["start"] < 0
                or clip["start"] + clip["duration"] > take["recording_wall_s"]
            ):
                raise ValueError("Excerpt lies outside the preserved master")
            overview = clip.get("crop")
            focus = clip.get("focus_crop")
            for rect in (overview, focus):
                if rect is not None:
                    validate_rectangle(rect, take["width"], take["height"])
            if "return_to_overview" in clip and type(clip["return_to_overview"]) is not bool:
                raise ValueError("return_to_overview must be a boolean")
            if focus is not None:
                whole = overview or [0, 0, take["width"], take["height"]]
                if (
                    focus[0] < whole[0]
                    or focus[1] < whole[1]
                    or focus[0] + focus[2] > whole[0] + whole[2]
                    or focus[1] + focus[3] > whole[1] + whole[3]
                ):
                    raise ValueError("Focus must be fully contained in overview crop")


def validate_rectangle(rect: object, width: int, height: int) -> None:
    """Use recorded pixels only; reject malformed/empty rectangles explicitly."""
    if (
        not isinstance(rect, list)
        or len(rect) != 4
        or any(type(value) is not int for value in rect)
        or rect[0] < 0
        or rect[1] < 0
        or rect[2] <= 0
        or rect[3] <= 0
        or rect[0] + rect[2] > width
        or rect[1] + rect[3] > height
    ):
        raise ValueError("Crop lies outside the recorded frame")


def framing_geometry(
    overview: list[int], focus: list[int], content_height: int
) -> dict[str, float]:
    """Contain complete endpoints in one aspect-correct camera canvas without stretching."""
    divisor = math.gcd(1080, content_height)
    ratio_w, ratio_h = 1080 // divisor, content_height // divisor
    units = math.ceil(max(overview[2] / ratio_w, overview[3] / ratio_h) / 2) * 2
    canvas_w, canvas_h = units * ratio_w, units * ratio_h
    pad_x, pad_y = (canvas_w - overview[2]) // 2, (canvas_h - overview[3]) // 2
    center_x = focus[0] - overview[0] + pad_x + focus[2] / 2
    center_y = focus[1] - overview[1] + pad_y + focus[3] / 2
    # A capped zoom keeps extra context rather than cutting a small requested focus.
    zoom = min(8.0, canvas_w / focus[2], canvas_h / focus[3])
    return {
        "width": canvas_w,
        "height": canvas_h,
        "zoom": zoom,
        "center_x": center_x,
        "center_y": center_y,
    }


def framing_filter(clip: dict[str, Any], take: dict[str, Any], height: int) -> str:
    """One output frame per source frame; smooth camera movement never changes the wait."""
    overview = clip.get("crop") or [0, 0, take["width"], take["height"]]
    crop = f"crop={overview[2]}:{overview[3]}:{overview[0]}:{overview[1]},"
    content = height - 320
    focus = clip.get("focus_crop")
    if focus is None:
        return crop + f"scale=1080:{content}:force_original_aspect_ratio=decrease,"
    geometry = framing_geometry(overview, focus, content)
    frames = max(1, round(clip["duration"] * 30) - 1)
    phase = f"clip((on/{frames}-.12)/.36,0,1)"
    if clip.get("return_to_overview", False):
        phase = f"min({phase},clip((.88-on/{frames})/.36,0,1))"
    ease = f"(({phase})*({phase})*(3-2*({phase})))"
    zoom = f"1/(1+(1/{geometry['zoom']:.12g}-1)*{ease})"
    x = f"max(0,min(iw-iw/zoom,iw/2+({geometry['center_x']:.12g}-iw/2)*{ease}-iw/(2*zoom)))"
    y = f"max(0,min(ih-ih/zoom,ih/2+({geometry['center_y']:.12g}-ih/2)*{ease}-ih/(2*zoom)))"
    return (
        crop + "fps=30," + f"pad={geometry['width']:.0f}:{geometry['height']:.0f}:"
        "(ow-iw)/2:(oh-ih)/2:color=0x102e3b,setsar=1,"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d=1:s=1080x{content}:fps=30,"
    )


def filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def srt(clips: list[dict[str, Any]]) -> str:
    def stamp(seconds: float) -> str:
        milliseconds = round(seconds * 1000)
        return (
            f"{milliseconds // 3600000:02}:{milliseconds // 60000 % 60:02}:"
            f"{milliseconds // 1000 % 60:02},{milliseconds % 1000:03}"
        )

    out, start = [], 0.0
    for index, clip in enumerate([*clips, {"caption": PROJECT, "duration": 5}], 1):
        end = start + clip["duration"]
        out.append(f"{index}\n{stamp(start)} --> {stamp(end)}\n{clip['caption']}\n")
        start = end
    return "\n".join(out)


def render(args: argparse.Namespace) -> Path:
    folder = args.take.resolve()
    if not folder.is_relative_to(output_root(args.repo)):
        raise ValueError("Take must remain under ignored LinkedIn results")
    take = json.loads((folder / "take.json").read_text())
    plan = json.loads((args.plan or folder / "cut-plan.json").read_text())
    validate_plan(plan, take)
    original = master_path(folder, take.get("master_sha256", ""))
    destination = folder / f"render-{uuid.uuid4().hex}"
    destination.mkdir()
    save(destination / "cut-plan.json", plan)
    (destination / "credits.txt").write_text(
        ATTRIBUTION
        + "\nRegistry citation: "
        + take.get("registry", {}).get("citation", "Synthetic fixture; no medical data")
        + "\n"
        + CAUTION
        + "\nSelf-made experimental tool; may be wrong or incomplete. "
        "Not medical advice or a basis for diagnosis/treatment decisions.\n" + PROJECT
    )
    font = "/usr/share/fonts/TTF/DejaVuSans.ttf"
    if not Path(font).exists():
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    for pilot, height in (("A", 1080), ("B", 1350)):
        endcard = Image.new("RGB", (1080, height), "#123d4b")
        draw = ImageDraw.Draw(endcard)
        for y, text in [
            (70, "ThoraxBench Local"),
            (130, "Marcel Petrick"),
            (220, "Self-made experimental tool"),
            (280, "May be wrong or incomplete"),
            (340, "Not medical advice"),
            (400, "No diagnosis/treatment decisions"),
            (490, "Selected calibration example"),
            (550, "LIDC training overlap: yes"),
            (height - 420, "github.com/marcelpetrick/"),
            (height - 370, "ThoraxGPT_from_Wish"),
            (height - 270, "LIDC-IDRI / TCIA - Armato et al. (2015)"),
            (height - 210, "doi:10.7937/K9/TCIA.2015.LO9QL9SX"),
            (height - 150, "CC BY 3.0"),
            (height - 90, "creativecommons.org/licenses/by/3.0/"),
        ]:
            draw.text((70, y), text, font=ImageFont.truetype(font, 36), fill="white")
        card = destination / f"{pilot}-end.png"
        endcard.save(card)
        clips = plan["cuts"][pilot]
        chains = ["[0:v]split=5" + "".join(f"[s{i}]" for i in range(5))]
        caution = destination / "caution.txt"
        caution.write_text(CAUTION)
        for index, clip in enumerate(clips):
            caption = destination / f"{pilot}-{index}.txt"
            # Two balanced lines, with no model text interpolated into ffmpeg syntax.
            import textwrap  # noqa: PLC0415 - caption formatting only

            caption.write_text("\n".join(textwrap.wrap(clip["caption"], 42)))
            framing = framing_filter(clip, take, height)
            # Reserve header and caption bands even for tall square-cut crops.
            chains.append(
                f"[s{index}]trim=start={clip['start']}:duration={clip['duration']},"
                f"setpts=PTS-STARTPTS,{framing}pad=1080:{height}:"
                f"(ow-iw)/2:80+({height - 320}-ih)/2:color=0x102e3b,setsar=1,fps=30,"
                f"drawtext=fontfile='{filter_path(Path(font))}':"
                f"textfile='{filter_path(caution)}':fontcolor=white:fontsize=22:x=30:y=28,"
                f"drawtext=fontfile='{filter_path(Path(font))}':"
                f"textfile='{filter_path(caption)}':fontcolor=white:fontsize=38:"
                f"x=(w-text_w)/2:y=h-150[v{index}]"
            )
        chains.append("[1:v]trim=duration=5,setpts=PTS-STARTPTS,fps=30,setsar=1,format=yuv420p[v5]")
        chains.append("".join(f"[v{i}]" for i in range(6)) + "concat=n=6:v=1:a=0[out]")
        output = destination / f"pilot-{pilot}.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-n",
                "-i",
                str(original),
                "-loop",
                "1",
                "-i",
                str(card),
                "-filter_complex",
                ";".join(chains),
                "-map",
                "[out]",
                "-t",
                "30",
                "-frames:v",
                "900",
                "-an",
                "-c:v",
                "libx264",
                "-crf",
                "17",
                "-preset",
                "medium",
                "-threads",
                "2",
                "-filter_complex_threads",
                "1",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output),
            ],
            check=True,
        )
        (destination / f"pilot-{pilot}.srt").write_text(srt(clips))
        shutil.copyfile(card, destination / f"pilot-{pilot}-thumbnail.png")
        info = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(output),
                ]
            )
        )
        stream = info["streams"][0]
        if (
            stream.get("codec_name") != "h264"
            or stream.get("pix_fmt") != "yuv420p"
            or stream.get("r_frame_rate") != "30/1"
            or stream["width"] != 1080
            or stream["height"] != height
            or stream.get("nb_frames") != "900"
            or abs(float(info["format"]["duration"]) - 30) > 0.01
        ):
            raise RuntimeError("Rendered output failed exact thirty-second validation")
        save(destination / f"pilot-{pilot}-verification.json", info)
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-n",
                "-i",
                str(output),
                "-vf",
                "fps=1/5,scale=360:-1,tile=3x2",
                "-frames:v",
                "1",
                str(destination / f"pilot-{pilot}-contact-sheet.png"),
            ],
            check=True,
        )
    return destination


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repo", type=Path, default=Path.cwd())
    commands = result.add_subparsers(dest="command", required=True)
    record = commands.add_parser("capture")
    record.add_argument("--url", required=True)
    record.add_argument("--dataset", required=True)
    record.add_argument("--case", required=True)
    record.add_argument("--model", choices=[MODEL], default=MODEL)
    record.add_argument("--allow-real-calibration", action="store_true")
    record.add_argument("--width", type=int, choices=[2560, 3840], default=2560)
    record.add_argument("--height", type=int, choices=[1440, 2160], default=1440)
    record.add_argument("--timeout", type=float, default=900)
    record.add_argument("--chromium", type=Path)
    encode = commands.add_parser("render")
    encode.add_argument("--take", type=Path, required=True)
    encode.add_argument("--plan", type=Path)
    return result


if __name__ == "__main__":
    options = parser().parse_args()
    print(capture(options) if options.command == "capture" else render(options))
