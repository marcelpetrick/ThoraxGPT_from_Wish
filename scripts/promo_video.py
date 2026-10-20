# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Record a calm 40-second promo of a real detector review, then render 16:9 and 1:1 cuts.

The tour uses one public, de-identified LIDC-IDRI calibration case (explicit
acknowledgement required), a fresh loopback server whose library is narrowed to that
case, and a real MONAI detector run; nothing is mocked. The render adds title/end cards
with sparkles, a soft highlight, captions, a voice-over and a generated music bed.
See docs/linkedin-promo-2026-10-20.md.

    uv run --extra detector python scripts/promo_video.py capture \
        --dataset lidc_idri --case LIDC-IDRI-0027 --allow-real-calibration
    uv run --extra detector python scripts/promo_video.py render \
        --take data/results/promo/<take> --voice <dir with line-N.wav>
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import math
import random
import subprocess
import time
import uuid
import wave
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from playwright.sync_api import Page, sync_playwright

try:  # Run as `python scripts/promo_video.py` or imported as `scripts.promo_video` in tests.
    from scripts.capture_screenshots import _offline, running_server
    from scripts.linkedin_video import (
        ATTRIBUTION,
        display,
        guard_case_request,
        hash_file,
        preflight,
        private_library,
        save,
        stop_process,
        x11_environment,
    )
except ModuleNotFoundError:  # pragma: no cover - script execution path
    from capture_screenshots import _offline, running_server  # type: ignore[no-redef]
    from linkedin_video import (  # type: ignore[no-redef]
        ATTRIBUTION,
        display,
        guard_case_request,
        hash_file,
        preflight,
        private_library,
        save,
        stop_process,
        x11_environment,
    )

REPO_URL = "https://github.com/marcelpetrick/ThoraxGPT_from_Wish"
PROJECT = "github.com/marcelpetrick/ThoraxGPT_from_Wish"
MODEL = "monai-lung-nodule"
WIDTH, HEIGHT, ZOOM = 2560, 1440, 1.5
CHROME = 96  # Browser tab/address bar height in recorded pixels; never shown.
FPS = 30
BRAND, ACCENT, INK, SOFT = "#0f2f3a", "#2bb3a3", "#ffffff", "#9fd9d1"
FONT_DIRS = [Path("/usr/share/fonts/noto"), Path("/usr/share/fonts/TTF")]
FORMATS = {"16x9": (1920, 1080)}
SAMPLE_RATE = 48_000


def output_root(repo: Path) -> Path:
    root = (repo / "data" / "results" / "promo").resolve()
    if not root.is_relative_to((repo / "data").resolve()):
        raise ValueError("Promo output must stay under the ignored data directory")
    root.mkdir(parents=True, exist_ok=True)
    return root


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    names = {
        "black": ["NotoSans-Black.ttf", "DejaVuSans-Bold.ttf"],
        "bold": ["NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
        "medium": ["NotoSans-Medium.ttf", "DejaVuSans.ttf"],
        "regular": ["NotoSans-Regular.ttf", "DejaVuSans.ttf"],
    }[weight]
    for name in names:
        for folder in FONT_DIRS:
            if (folder / name).exists():
                return ImageFont.truetype(str(folder / name), size)
    raise FileNotFoundError(f"No {weight} font found")


# --------------------------------------------------------------------------- capture


def zoomed(page: Page) -> None:
    # Browser display zoom only; it changes presentation, never inputs or results.
    page.evaluate(f"document.documentElement.style.zoom = '{ZOOM}'")


def scroll_to(page: Page, selector: str, offset: int = 16) -> None:
    """Scroll so *selector* starts just below the top (scrollIntoView fails in kiosk)."""
    page.evaluate(
        "([selector, offset]) => window.scrollTo(0, scrollY + "
        "document.querySelector(selector).getBoundingClientRect().top - offset)",
        [selector, offset],
    )


def glide_to(page: Page, selector: str, offset: int = 16, steps: int = 30) -> None:
    """A calm, visible scroll instead of a jump."""
    start = page.evaluate("scrollY")
    target = page.evaluate(
        "([selector, offset]) => scrollY + "
        "document.querySelector(selector).getBoundingClientRect().top - offset",
        [selector, offset],
    )
    for step in range(1, steps + 1):
        eased = (1 - math.cos(math.pi * step / steps)) / 2
        page.evaluate(f"window.scrollTo(0, {start + (target - start) * eased})")
        page.wait_for_timeout(33)


def show_slice(page: Page, index: int) -> None:
    """Move the slider and wait until that slice is really displayed (no skipped frames)."""
    slider = page.locator("#slice-slider")
    slider.fill(str(index))
    slider.dispatch_event("input")
    page.wait_for_function(
        "index => { const image = document.querySelector('#ct-image');"
        " return !image.hidden && image.complete && image.naturalWidth > 0"
        " && image.src.includes(`/slice/${index}.png`); }",
        arg=index,
    )


def boxes(page: Page, selectors: dict[str, str]) -> dict[str, list[int]]:
    """Recorded pixel rectangles (screen coordinates) for planning crops and highlights."""
    found: dict[str, list[int]] = {}
    for name, selector in selectors.items():
        locator = page.locator(selector).first
        if locator.count() and (box := locator.bounding_box()):
            found[name] = [
                round(box["x"]),
                round(box["y"]) + CHROME,
                round(box["width"]),
                round(box["height"]),
            ]
    return found


def capture(args: argparse.Namespace) -> Path:  # noqa: PLR0912, PLR0915 - linear recording script
    repo = args.repo.resolve()
    registry = preflight(repo, args.dataset, args.case, MODEL, args.allow_real_calibration)
    # The recorded app must match the commit; docs and this script may still be in progress.
    app_paths = ["src", "configs", "pyproject.toml", "uv.lock"]
    if subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain", "--", *app_paths]):
        raise ValueError("Capture requires committed application code and configuration")
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    folder = output_root(repo) / f"{stamp}-{uuid.uuid4().hex[:8]}"
    folder.mkdir()
    print(f"Preserved take: {folder}", flush=True)
    take: dict[str, Any] = {
        "schema_version": 2,
        "status": "recording",
        "dataset": args.dataset,
        "case": args.case,
        "phase": "calibration",
        "selected_case": True,
        "training_overlap": "yes (LUNA16 is derived from LIDC-IDRI)",
        "attribution": ATTRIBUTION,
        "registry_citation": registry.get("citation"),
        "model": MODEL,
        "width": WIDTH,
        "height": HEIGHT,
        "events": [],
        "commit": subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip(),
    }
    save(folder / "take.json", take)
    master = folder / "master.mp4"
    from thoraxbench.config import Settings  # noqa: PLC0415 - after path setup

    # A fresh server process has no session-only local imports; the library is narrowed
    # to the one calibration case in the browser as well.
    data = repo / "data"
    with (
        running_server(data, Settings(data_dir=data, **_offline())) as url,
        display(WIDTH, HEIGHT) as target,
        sync_playwright() as playwright,
        contextlib.ExitStack() as cleanup,
    ):
        api = playwright.request.new_context(base_url=url)
        cleanup.callback(api.dispose)
        browser = playwright.chromium.launch(
            executable_path=str(args.chromium or playwright.chromium.executable_path),
            headless=False,
            env=x11_environment(target),
            args=[
                "--ozone-platform=x11",
                "--disable-gpu",
                "--kiosk",
                "--hide-scrollbars",
                f"--window-size={WIDTH},{HEIGHT}",
            ],
        )
        cleanup.callback(browser.close)
        context = browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT - CHROME},
            locale="en-US",
            color_scheme="light",
        )
        context.route("**/api/studies", lambda r: private_library(r, args.dataset, args.case))
        context.route("**/api/studies/**", lambda r: guard_case_request(r, args.dataset, args.case))
        page = context.new_page()
        page.set_default_timeout(30_000)
        page.goto(url)
        page.evaluate("localStorage.clear()")
        page.reload()
        zoomed(page)
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
                f"{WIDTH}x{HEIGHT}",
                "-framerate",
                str(FPS),
                "-i",
                target,
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "14",
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

        def now() -> float:
            return round(time.monotonic() - started, 3)

        @contextlib.contextmanager
        def scene(
            name: str, active: Callable[[], Page], selectors: dict[str, str]
        ) -> Iterator[dict[str, float]]:
            event: dict[str, Any] = {"name": name, "start": now(), "marks": {}}
            take["events"].append(event)
            try:
                yield event["marks"]
            finally:
                with contextlib.suppress(Exception):
                    event["boxes"] = boxes(active(), selectors)
                event["end"] = now()
                save(folder / "take.json", take)

        try:
            page.wait_for_timeout(1500)
            if recorder.poll() is not None:
                raise RuntimeError("ffmpeg capture failed; inspect capture.log")
            # 1. The public README, rendered by GitHub (title, badges, tagline).
            readme = context.new_page()
            with scene("github", lambda: readme, {"title": "article.markdown-body h1"}) as marks:
                readme.goto(REPO_URL, wait_until="load")
                zoomed(readme)
                readme.bring_to_front()
                for _ in range(100):
                    if readme.evaluate(
                        "[...document.querySelectorAll('article.markdown-body img')]"
                        ".slice(0, 7).every(image => image.complete && image.naturalWidth > 0)"
                    ):
                        break
                    readme.wait_for_timeout(200)
                readme.wait_for_timeout(800)
                for _ in range(40):
                    scroll_to(readme, "article.markdown-body h1", 60)
                    readme.wait_for_timeout(400)
                    top = readme.evaluate(
                        "document.querySelector('article.markdown-body h1')"
                        ".getBoundingClientRect().top"
                    )
                    if 0 <= top < 400:
                        break
                else:
                    raise TimeoutError("README heading did not stay in view")
                take["badge_alts"] = readme.evaluate(
                    "[...document.querySelectorAll('article.markdown-body img')]"
                    ".slice(0, 7).map(image => image.alt)"
                )
                marks["ready"] = now()
                readme.wait_for_timeout(9000)
            readme.close()
            page.bring_to_front()
            # 2. Open the case and scroll calmly through the slices.
            with scene(
                "open", lambda: page, {"viewer": ".viewer-panel", "study": "#study-panel"}
            ) as marks:
                page.locator("#dataset-filter").select_option(args.dataset)
                page.locator("#study-select").select_option(value="0")
                page.locator("#ct-image").wait_for(state="visible")
                scroll_to(page, ".viewer-panel")
                slices = int(page.locator("#slice-slider").get_attribute("max") or "0") + 1
                take["n_slices"] = slices
                low, high = round(slices * 0.30), round(slices * 0.62)
                show_slice(page, low)
                page.wait_for_timeout(1500)
                marks["scroll"] = now()
                for index in range(low, high + 1):
                    show_slice(page, index)
                    page.wait_for_timeout(45)
                marks["scrolled"] = now()
                page.wait_for_timeout(1500)
            # 3. Full thorax review with the detector; the page stays on the analysis view.
            with scene(
                "review",
                lambda: page,
                {"panel": "#model-panel", "progress": "#full-review-progress"},
            ) as marks:
                page.locator("#model-select").select_option(MODEL)
                glide_to(page, "#model-panel", 40)
                page.wait_for_timeout(1500)
                with page.expect_response(
                    lambda response: (
                        response.url.endswith("/api/jobs") and response.request.method == "POST"
                    )
                ) as submitted:
                    page.locator("#run-full-review").click()
                job_id = submitted.value.json()["job"]["id"]
                take["job_id"] = job_id
                marks["clicked"] = now()
                # Show the start beside the button, then watch the run over the CT image.
                page.wait_for_timeout(3000)
                glide_to(page, ".viewer-panel", 16, steps=40)
                marks["watching"] = now()
                deadline = time.monotonic() + args.timeout
                while True:
                    job = api.get(f"/api/jobs/{job_id}").json()
                    if job.get("finished"):
                        break
                    if time.monotonic() > deadline:
                        raise TimeoutError("Detector review exceeded the capture timeout")
                    page.wait_for_timeout(1000)
                marks["finished"] = now()
                take["job"] = {key: value for key, value in job.items() if key != "result"}
                if job["status"] != "succeeded":
                    raise RuntimeError(f"Full review did not succeed: {job['status']}")
                page.wait_for_timeout(2000)
            # 4. Where to look, then jump to the first place.
            with scene(
                "verdict",
                lambda: page,
                {
                    "panel": "#full-review-panel",
                    "outcome": "#full-review-outcome",
                    "look_first": "#full-review-look li",
                    "look": "#full-review-look-section",
                },
            ) as marks:
                page.locator("#full-review-panel").wait_for(state="visible")
                glide_to(page, "#full-review-panel", 24, steps=45)
                marks["shown"] = now()
                page.wait_for_timeout(5000)
            with scene(
                "jump", lambda: page, {"viewer": ".viewer-panel", "image": "#ct-image"}
            ) as marks:
                page.locator("#full-review-look li button").first.click()
                page.wait_for_timeout(300)
                scroll_to(page, ".viewer-panel")
                marks["jumped"] = now()
                page.wait_for_timeout(5000)
                take["shown_slice"] = page.locator("#slice-counter").inner_text()
            # 5. The offline report.
            with page.expect_popup() as opened:
                scroll_to(page, "#full-review-panel", 24)
                page.locator("#full-review-open").click()
            report = opened.value
            with scene("report", lambda: report, {"body": "body"}) as marks:
                report.wait_for_load_state()
                zoomed(report)
                report.bring_to_front()
                report.wait_for_function(
                    "[...document.images].every(image => image.complete && image.naturalWidth > 0)"
                )
                marks["loaded"] = now()
                report.wait_for_timeout(2500)
                marks["scroll"] = now()
                for _ in range(90):
                    report.mouse.wheel(0, 9)
                    report.wait_for_timeout(33)
                report.wait_for_timeout(2500)
            report.close()
            result = api.get(f"/api/jobs/{job_id}").json().get("result") or {}
            summary = result.get("summary", {})
            take["result"] = {
                "verdict": summary.get("verdict"),
                "look_here": summary.get("look_here"),
                "detector": summary.get("detector"),
                "total_s": summary.get("timing", {}).get("total_s"),
            }
            take["status"] = "finalizing"
        except Exception as exc:
            take["status"], take["error"] = "failed", str(exc)
            raise
        finally:
            take["recording_wall_s"] = now()
            save(folder / "take.json", take)
            stop_process(recorder, True)
    probe = json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(master)]
        )
    )
    stream = probe["streams"][0]
    if (stream["width"], stream["height"], stream["r_frame_rate"]) != (WIDTH, HEIGHT, "30/1"):
        take["status"] = "failed"
        save(folder / "take.json", take)
        raise ValueError("Master has unexpected dimensions or frame rate")
    take["master_duration_s"] = float(probe["format"]["duration"])
    take["master_sha256"] = hash_file(master)
    take["status"] = "succeeded"
    save(folder / "take.json", take)
    return folder


# --------------------------------------------------------------------------- render


def frames(seconds: float) -> int:
    return round(seconds * FPS)


def validate_plan(plan: dict[str, Any], take: dict[str, Any]) -> None:
    """Refuse plans that misrepresent the take or miss the exact length."""
    if take.get("status") != "succeeded":
        raise ValueError("Only a succeeded take can be rendered")
    shots = plan["shots"]
    if sum(frames(shot["duration"]) for shot in shots) != frames(plan["seconds"]):
        raise ValueError("Shot durations do not add up to the planned length")
    if shots[0].get("card") != "title" or shots[-1].get("card") != "end":
        raise ValueError("Start with the title card and end with the end card")
    if shots[-1]["duration"] < 3:
        raise ValueError("The project URL needs at least three seconds on screen")
    for shot in shots:
        if "card" in shot:
            continue
        speed = float(shot.get("speed", 1.0))
        if not (math.isfinite(speed) and 1.0 <= speed <= 60.0):
            raise ValueError("Speed must be between 1x and 60x")
        if speed > 1.0 and not shot.get("speed_tag"):
            raise ValueError("A sped-up shot must disclose it with a speed_tag")
        end = shot["start"] + shot["duration"] * speed
        if shot["start"] < 0 or end > take["master_duration_s"]:
            raise ValueError(f"Shot {shot.get('name')} lies outside the master")
        for rect in shot.get("crop", {}).values():
            x, y, w, h = rect
            if x < 0 or y < CHROME or w <= 0 or h <= 0 or x + w > WIDTH or y + h > HEIGHT:
                raise ValueError(f"Crop {rect} leaves the recorded page area")


def pill(text: str, size: int, width: int, *, tag: bool = False) -> Image.Image:
    """A soft rounded caption pill (RGBA) with a shadow, sized to its text."""
    face = font("medium" if tag else "bold", size)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines = [""]
    for word in text.split():
        trial = f"{lines[-1]} {word}".strip()
        if probe.textlength(trial, font=face) <= width - 2 * size:
            lines[-1] = trial
        else:
            lines.append(word)
    body = "\n".join(lines)
    spacing = round(size * 0.3)
    box = probe.multiline_textbbox((0, 0), body, font=face, spacing=spacing, align="center")
    pad_x, pad_y = round(size * 0.9), round(size * 0.55)
    w = math.ceil(box[2] - box[0]) + 2 * pad_x
    h = math.ceil(box[3] - box[1]) + 2 * pad_y
    radius = h // 2 if tag else 22
    image = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [20, 24, 20 + w, 24 + h], radius=radius, fill=(0, 0, 0, 90)
    )
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([20, 20, 20 + w, 20 + h], radius=radius, fill=(15, 47, 58, 228))
    draw.multiline_text(
        (20 + w / 2, 20 + pad_y - box[1]),
        body,
        font=face,
        fill=SOFT if tag else INK,
        align="center",
        anchor="ma",
        spacing=spacing,
    )
    return image


def sparkle(draw: ImageDraw.ImageDraw, x: float, y: float, r: float, alpha: int) -> None:
    """A four-point star with a soft core."""
    if r < 1 or alpha <= 0:
        return
    colour = (255, 255, 255, alpha)
    thin = max(1.0, r / 7)
    draw.polygon([(x, y - r), (x + thin, y), (x, y + r), (x - thin, y)], fill=colour)
    draw.polygon([(x - r, y), (x, y - thin), (x + r, y), (x, y + thin)], fill=colour)
    core = r / 4
    draw.ellipse([x - core, y - core, x + core, y + core], fill=(220, 255, 248, alpha))


def card_frames(
    kind: str, size: tuple[int, int], seconds: float, lines: list[list[Any]], folder: Path
) -> Path:
    """Render a card as a PNG sequence: gradient, gentle zoom, staggered text, sparkles.

    Each line is ``[text, weight, size, colour, delay_seconds]``.
    """
    width, height = size
    count = frames(seconds)
    rng = random.Random(7 if kind.startswith("title") else 11)
    stars = [
        (rng.uniform(0.04, 0.96), rng.uniform(0.06, 0.94), rng.uniform(9, 26), rng.uniform(0, 1))
        for _ in range(60)
    ]
    top, bottom = np.array([18, 63, 78]), np.array([10, 33, 42])
    ramp = np.linspace(0, 1, height)[:, None, None]
    gradient = (top * (1 - ramp) + bottom * ramp).astype(np.uint8)
    background = Image.fromarray(np.repeat(gradient, width, axis=1), "RGB").convert("RGBA")
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [width * 0.15, height * 0.1, width * 0.85, height * 0.9], fill=(43, 179, 163, 60)
    )
    background.alpha_composite(glow.filter(ImageFilter.GaussianBlur(min(size) // 6)))
    faces = [(text, font(weight, px), colour, delay) for text, weight, px, colour, delay in lines]
    probe = ImageDraw.Draw(background)
    heights = [probe.textbbox((0, 0), text, font=face)[3] for text, face, _, _ in faces]
    gap = round(height * 0.03)
    y0 = (height - sum(heights) - gap * (len(faces) - 1)) // 2
    # Sparkles frame the text; none may land on a letter.
    half = max(probe.textlength(text, font=face) for text, face, _, _ in faces) / 2 + 60
    y_end = y0 + sum(heights) + gap * len(faces) + 40
    stars = [
        star
        for star in stars
        if not (abs(star[0] * width - width / 2) < half and y0 - 60 < star[1] * height < y_end)
    ]
    out = folder / f"card-{kind}"
    out.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        t = index / FPS
        frame = background.copy()
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        y = y0
        for (text, face, colour, delay), line_h in zip(faces, heights, strict=True):
            fade = max(0.0, min(1.0, (t - delay) / 0.6))
            rise = (1 - fade) * 18
            rgb = Image.new("RGB", (1, 1), colour).getpixel((0, 0))
            draw.text(
                (width / 2, y + rise), text, font=face, fill=(*rgb, round(255 * fade)), anchor="ma"
            )
            y += line_h + gap
        frame.alpha_composite(layer)
        twinkle = Image.new("RGBA", size, (0, 0, 0, 0))
        tdraw = ImageDraw.Draw(twinkle)
        for sx, sy, radius, phase in stars:
            level = max(0.0, math.sin(2 * math.pi * (t / 2.2 + phase)))
            sparkle(tdraw, sx * width, sy * height, radius * level, round(210 * level))
        frame.alpha_composite(twinkle.filter(ImageFilter.GaussianBlur(3)))
        frame.alpha_composite(twinkle)
        # A static light dither hides gradient banding; a fixed pattern stays cheap to encode.
        noise = np.random.default_rng(0).integers(-2, 3, (height, width, 1), dtype=np.int16)
        pixels = np.asarray(frame.convert("RGB"), dtype=np.int16) + noise
        frame = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
        # A slow push-in keeps the card alive.
        scale = 1 + 0.035 * index / max(1, count - 1)
        grown = frame.resize((round(width * scale), round(height * scale)), Image.LANCZOS)
        left, upper = (grown.width - width) // 2, (grown.height - height) // 2
        grown.crop((left, upper, left + width, upper + height)).convert("RGB").save(
            out / f"{index:04d}.png"
        )
    return out


def screen_geometry(fmt: str, shot: dict[str, Any]) -> tuple[list[int], tuple[int, int, int]]:
    """Source rectangle and (x, y, width) of the screen inside the output frame."""
    width, height = FORMATS[fmt]
    if fmt == "16x9":
        # The whole page area, scaled under a slim wordmark band.
        page_h = HEIGHT - CHROME
        return [0, CHROME, WIDTH, page_h], (0, height - round(width * page_h / WIDTH), width)
    return shot["crop"]["1x1"], (0, 0, width)


def music(seconds: float, path: Path) -> None:
    """A warm, generated ambient pad (no third-party recording): slow chords and a soft bell."""
    t = np.arange(round(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    chords = [  # Cmaj9, Am9, Fmaj7, G6 in a gentle low-mid voicing (Hz).
        [130.81, 196.00, 246.94, 293.66, 329.63],
        [110.00, 164.81, 196.00, 246.94, 261.63],
        [87.31, 174.61, 220.00, 261.63, 329.63],
        [98.00, 146.83, 196.00, 246.94, 329.63],
    ]
    span = seconds / len(chords)
    signal = np.zeros_like(t)
    for index, chord in enumerate(chords):
        start, end = index * span, (index + 1) * span
        envelope = np.clip((t - start + 1.2) / 1.6, 0, 1) * np.clip((end + 1.2 - t) / 1.6, 0, 1)
        for note in chord:
            for detune in (-0.15, 0.15):
                signal += envelope * np.sin(2 * np.pi * (note + detune) * t) / (len(chord) * 2)
    bell = np.zeros_like(t)
    rng = np.random.default_rng(3)
    for start in np.arange(1.0, seconds - 2, 2.5):
        chord = chords[min(len(chords) - 1, int(start // span))]
        note = rng.choice(chord) * 4
        ring = np.where(t >= start, np.exp(-(t - start) * 2.2), 0.0)
        bell += 0.08 * ring * np.sin(2 * np.pi * note * (t - start))
    mix = signal * 0.5 + bell
    fade = np.clip(t / 1.5, 0, 1) * np.clip((seconds - t) / 2.0, 0, 1)
    mix = (mix * fade) / max(1e-9, float(np.max(np.abs(mix)))) * 0.6
    stereo = np.stack([mix, np.roll(mix, 240)], axis=1)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes((stereo * 32767).astype("<i2").tobytes())


def take_box(take: dict[str, Any], name: str) -> list[int] | None:
    scene_name, _, key = name.partition(".")
    for event in take["events"]:
        if event["name"] == scene_name:
            box = event.get("boxes", {}).get(key)
            return list(box) if box else None
    return None


def highlight(
    box: list[int], source: list[int], placement: tuple[int, int, int], size: tuple[int, int]
) -> Image.Image:
    """A soft glowing ring around *box* (recorded pixels) mapped into the output frame."""
    sx, sy, sw = placement
    scale = sw / source[2]
    x0 = sx + (box[0] - source[0]) * scale - 10
    y0 = sy + (box[1] - source[1]) * scale - 8
    x1 = sx + (box[0] + box[2] - source[0]) * scale + 10
    y1 = sy + (box[1] + box[3] - source[1]) * scale + 8
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle(
        [x0, y0, x1, y1], radius=14, outline=(43, 179, 163, 200), width=10
    )
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(8)))
    ImageDraw.Draw(image).rounded_rectangle(
        [x0, y0, x1, y1], radius=14, outline=(43, 179, 163, 255), width=3
    )
    sparkle(ImageDraw.Draw(image), x1 - 4, y0 + 2, 16, 230)
    return image


def screen_chain(
    shot: dict[str, Any], index: int, fmt: str, count: int
) -> tuple[str, list[int], tuple[int, int, int]]:
    """Trim (optionally sped up), crop the page area, gentle push-in, place in the frame."""
    width, height = FORMATS[fmt]
    speed = float(shot.get("speed", 1.0))
    source, (sx, sy, sw) = screen_geometry(fmt, shot)
    sh = round(sw * source[3] / source[2])
    push = float(shot.get("push", 0.03))
    zoom = f"1+{push}*on/{max(1, count - 1)}"
    chain = (
        f"[0:v]trim=start={shot['start']}:duration={shot['duration'] * speed:.4f},"
        f"setpts=(PTS-STARTPTS)/{speed},fps={FPS},"
        f"crop={source[2]}:{source[3]}:{source[0]}:{source[1]},"
        f"scale={sw * 2}:{sh * 2}:flags=lanczos,"
        f"zoompan=z='{zoom}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={sw}x{sh}:fps={FPS},"
        f"pad={width}:{height}:{sx}:{sy}:color={BRAND},setsar=1,format=rgba[s{index}]"
    )
    return chain, source, (sx, sy, sw)


def overlays_for(
    shot: dict[str, Any],
    take: dict[str, Any],
    fmt: str,
    source: list[int],
    placement: tuple[int, int, int],
) -> list[tuple[Image.Image, int, int, float]]:
    """Wordmark band (16:9), caption pill, speed tag and the optional highlight ring."""
    width, height = FORMATS[fmt]
    _, sy, _ = placement
    result: list[tuple[Image.Image, int, int, float]] = []
    if fmt == "16x9":
        band = Image.new("RGBA", (width, sy), (0, 0, 0, 0))
        draw = ImageDraw.Draw(band)
        draw.text((36, sy // 2), "ThoraxBench Local", font=font("black", 30), fill=INK, anchor="lm")
        draw.text(
            (width - 36, sy // 2),
            "public CT example · real detector run",
            font=font("regular", 22),
            fill=SOFT,
            anchor="rm",
        )
        result.append((band, 0, 0, 0.0))
    caption = pill(shot["caption"], 40 if fmt == "16x9" else 36, round(width * 0.8))
    result.append((caption, (width - caption.width) // 2, height - caption.height - 26, 0.35))
    if shot.get("speed_tag"):
        tag = pill(shot["speed_tag"], 24, width // 2, tag=True)
        # Below the app's job bar, so the tag never covers the queue chip.
        result.append((tag, width - tag.width - 16, (sy if fmt == "16x9" else 0) + 70, 0.2))
    if shot.get("highlight") and (box := take_box(take, shot["highlight"])):
        ring = highlight(box, source, placement, (width, height))
        result.append((ring, 0, 0, float(shot.get("highlight_at", 1.0))))
    return result


def audio_chains(
    voice_inputs: list[tuple[int, float]], first_stream: int, seconds: float
) -> list[str]:
    """Voice lines at their offsets over the ducked music bed, loudness-normalised."""
    music_stream = first_stream
    chains, labels = [], []
    for position, (line, at) in enumerate(voice_inputs, start=first_stream + 1):
        delay = round(at * 1000)
        chains.append(
            f"[{position}:a]aresample={SAMPLE_RATE},aformat=channel_layouts=stereo,"
            f"adelay={delay}|{delay},apad[l{line}]"
        )
        labels.append(f"[l{line}]")
    chains.append(
        "".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=longest,"
        f"atrim=0:{seconds},asplit=2[voice][key]"
    )
    chains.append(
        f"[{music_stream}:a]volume=0.32[bed];"
        "[bed][key]sidechaincompress=threshold=0.03:ratio=6:attack=40:release=500[ducked]"
    )
    chains.append(
        "[voice][ducked]amix=inputs=2:normalize=0:duration=first,"
        f"atrim=0:{seconds},loudnorm=I=-16:TP=-1.5:LRA=11,aresample={SAMPLE_RATE}[audio]"
    )
    return chains


def render(args: argparse.Namespace) -> Path:  # noqa: PLR0915 - one filter graph per format
    folder = args.take.resolve()
    if not folder.is_relative_to(output_root(args.repo.resolve())):
        raise ValueError("Take must stay under data/results/promo/")
    take = json.loads((folder / "take.json").read_text())
    plan = json.loads((args.plan or folder / "cut-plan.json").read_text())
    validate_plan(plan, take)
    master = folder / "master.mp4"
    if hash_file(master) != take["master_sha256"]:
        raise ValueError("Master changed since capture")
    destination = folder / f"render-{dt.datetime.now(dt.UTC).strftime('%H%M%S')}"
    destination.mkdir()
    save(destination / "cut-plan.json", plan)
    seconds = plan["seconds"]
    music(seconds, destination / "music.wav")
    voice_dir = args.voice.resolve()
    shots = plan["shots"]
    total = frames(seconds)
    for fmt, (width, height) in FORMATS.items():
        inputs: list[str] = ["-i", str(master)]
        streams = 1
        chains: list[str] = []
        labels: list[str] = []
        offset = 0.0
        voice_inputs: list[tuple[int, float]] = []
        for index, shot in enumerate(shots):
            count = frames(shot["duration"])
            fade_out = f"{shot['duration'] - 0.45:.3f}"
            if "card" in shot:
                sequence = card_frames(
                    f"{shot['card']}-{fmt}",
                    (width, height),
                    shot["duration"],
                    shot["lines"],
                    destination,
                )
                inputs += ["-framerate", str(FPS), "-i", str(sequence / "%04d.png")]
                chains.append(
                    f"[{streams}:v]setpts=PTS-STARTPTS,trim=end_frame={count},format=yuv420p,"
                    f"fade=t=in:st=0:d=0.5:color={BRAND},"
                    f"fade=t=out:st={fade_out}:d=0.45:color={BRAND}[v{index}]"
                )
                streams += 1
            else:
                chain, source, placement = screen_chain(shot, index, fmt, count)
                chains.append(chain)
                current = f"s{index}"
                for o_index, (image, ox, oy, delay) in enumerate(
                    overlays_for(shot, take, fmt, source, placement)
                ):
                    still = destination / f"{fmt}-{index}-overlay-{o_index}.png"
                    image.save(still)
                    inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(still)]
                    label = f"o{index}_{o_index}"
                    chains.append(
                        f"[{streams}:v]format=rgba,trim=end_frame={count},"
                        f"fade=t=in:st={delay}:d=0.5:alpha=1[{label}]"
                    )
                    chains.append(f"[{current}][{label}]overlay={ox}:{oy}:shortest=1[c{label}]")
                    current = f"c{label}"
                    streams += 1
                chains.append(
                    f"[{current}]trim=end_frame={count},format=yuv420p,"
                    f"fade=t=in:st=0:d=0.45:color={BRAND},"
                    f"fade=t=out:st={fade_out}:d=0.45:color={BRAND}[v{index}]"
                )
            if shot.get("voice") is not None:
                voice_inputs.append((shot["voice"], offset + float(shot.get("voice_at", 0.4))))
            labels.append(f"[v{index}]")
            offset += count / FPS
        chains.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[video]")
        inputs += ["-i", str(destination / "music.wav")]
        for line, _ in voice_inputs:
            inputs += ["-i", str(voice_dir / f"line-{line}.wav")]
        chains += audio_chains(voice_inputs, streams, seconds)
        output = destination / f"promo-{fmt}.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-n",
                "-loglevel",
                "error",
                *inputs,
                "-filter_complex",
                ";".join(chains),
                "-map",
                "[video]",
                "-map",
                "[audio]",
                "-frames:v",
                str(total),
                "-c:v",
                "libx264",
                "-crf",
                "17",
                "-preset",
                "slow",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-ar",
                str(SAMPLE_RATE),
                "-t",
                str(seconds),
                "-movflags",
                "+faststart",
                str(output),
            ],
            check=True,
        )
        verify(output, (width, height), total, destination / f"promo-{fmt}-verification.json")
        (destination / f"promo-{fmt}.srt").write_text(srt(shots))
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-n",
                "-loglevel",
                "error",
                "-i",
                str(output),
                "-vf",
                "fps=1/2,scale=384:-1,tile=5x4",
                "-frames:v",
                "1",
                "-update",
                "1",
                str(destination / f"promo-{fmt}-contact-sheet.png"),
            ],
            check=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-n",
                "-loglevel",
                "error",
                "-ss",
                str(plan["thumbnail_s"]),
                "-i",
                str(output),
                "-frames:v",
                "1",
                "-update",
                "1",
                str(destination / f"promo-{fmt}-thumbnail.png"),
            ],
            check=True,
        )
    (destination / "credits.txt").write_text(credits_text(take))
    return destination


def verify(output: Path, size: tuple[int, int], total: int, record: Path) -> None:
    info = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-count_frames",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(output),
            ]
        )
    )
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if (
        video.get("codec_name") != "h264"
        or video.get("pix_fmt") != "yuv420p"
        or video.get("r_frame_rate") != f"{FPS}/1"
        or (video["width"], video["height"]) != size
        or video.get("nb_read_frames") != str(total)
        or audio is None
        or audio.get("codec_name") != "aac"
    ):
        raise RuntimeError(f"{output.name} failed validation")
    save(record, info)


def srt(shots: list[dict[str, Any]]) -> str:
    def stamp(value: float) -> str:
        ms = round(value * 1000)
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"

    out, start = [], 0.0
    for number, shot in enumerate(shots, 1):
        end = start + frames(shot["duration"]) / FPS
        text = shot.get("caption") or " ".join(str(line[0]) for line in shot.get("lines", []))
        out.append(f"{number}\n{stamp(start)} --> {stamp(end)}\n{text}\n")
        start = end
    return "\n".join(out)


def credits_text(take: dict[str, Any]) -> str:
    return "\n".join(
        [
            "ThoraxBench Local promo - " + PROJECT,
            f"CT: {take['dataset']} / {take['case']} (selected public calibration example).",
            take["attribution"],
            "The MONAI detector's LUNA16 training data is derived from LIDC-IDRI, so this "
            "example overlaps its training data; it is not accuracy evidence.",
            "Voice: Kokoro-82M (Apache-2.0), voice af_heart. Music: generated for this video.",
            "Self-made experimental research tool; may be wrong or incomplete. "
            "Not medical advice or a basis for diagnosis or treatment decisions.",
        ]
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repo", type=Path, default=Path.cwd())
    commands = result.add_subparsers(dest="command", required=True)
    record = commands.add_parser("capture")
    record.add_argument("--dataset", required=True)
    record.add_argument("--case", required=True)
    record.add_argument("--allow-real-calibration", action="store_true")
    record.add_argument("--timeout", type=float, default=900)
    record.add_argument("--chromium", type=Path)
    encode = commands.add_parser("render")
    encode.add_argument("--take", type=Path, required=True)
    encode.add_argument("--plan", type=Path)
    encode.add_argument("--voice", type=Path, required=True)
    return result


if __name__ == "__main__":
    options = parser().parse_args()
    print(capture(options) if options.command == "capture" else render(options))
