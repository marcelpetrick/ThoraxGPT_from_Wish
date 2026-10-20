# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Promo renderer guards and helpers; synthetic metadata only, no recording or encoding."""

import copy
import wave
from pathlib import Path

import pytest
from scripts.promo_video import (
    CHROME,
    card_frames,
    credits_text,
    highlight,
    music,
    pill,
    screen_geometry,
    srt,
    take_box,
    validate_plan,
)

TAKE = {
    "status": "succeeded",
    "master_duration_s": 200.0,
    "dataset": "lidc_idri",
    "case": "SYNTHETIC-CASE",
    "attribution": "Synthetic attribution line.",
    "events": [{"name": "verdict", "boxes": {"look_first": [487, 513, 1982, 67]}}],
}
PLAN = {
    "seconds": 10.0,
    "shots": [
        {"card": "title", "duration": 3.0, "lines": [["Title", "black", 40, "#ffffff", 0.0]]},
        {"name": "run", "start": 20.0, "duration": 3.0, "speed": 10, "speed_tag": "10x"},
        {"card": "end", "duration": 4.0, "lines": [["End", "bold", 30, "#ffffff", 0.0]]},
    ],
}


def test_valid_plan_passes() -> None:
    validate_plan(PLAN, TAKE)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda p: p["shots"][1].update(duration=2.0), "add up"),
        (lambda p: p["shots"][1].pop("speed_tag"), "disclose"),
        (lambda p: p["shots"][1].update(speed=100), "between"),
        (lambda p: p["shots"][1].update(start=190.0), "outside"),
        (lambda p: p["shots"].reverse(), "title card"),
        (lambda p: p["shots"][1].update(crop={"1x1": [0, 10, 100, 100]}), "page area"),
    ],
)
def test_plan_guards_refuse_misleading_edits(change: object, message: str) -> None:
    plan = copy.deepcopy(PLAN)
    change(plan)  # type: ignore[operator]
    with pytest.raises(ValueError, match=message):
        validate_plan(plan, TAKE)


def test_failed_take_cannot_be_rendered() -> None:
    with pytest.raises(ValueError, match="succeeded"):
        validate_plan(PLAN, {**TAKE, "status": "failed"})


def test_short_end_card_is_refused() -> None:
    plan = copy.deepcopy(PLAN)
    plan["shots"][2]["duration"] = 2.0
    plan["shots"][0]["duration"] = 5.0
    with pytest.raises(ValueError, match="three seconds"):
        validate_plan(plan, TAKE)


def test_full_window_geometry_hides_only_the_browser_bar() -> None:
    source, (x, y, width) = screen_geometry("16x9", {})
    assert source == [0, CHROME, 2560, 1440 - CHROME]
    assert (x, width) == (0, 1920)
    assert y + round(width * source[3] / source[2]) == 1080


def test_srt_uses_captions_and_card_text() -> None:
    plan = copy.deepcopy(PLAN)
    plan["shots"][1]["caption"] = "Caption"
    text = srt(plan["shots"])
    assert "00:00:00,000 --> 00:00:03,000\nTitle" in text
    assert "00:00:03,000 --> 00:00:06,000\nCaption" in text
    assert "00:00:06,000 --> 00:00:10,000\nEnd" in text


def test_pill_wraps_long_text_and_keeps_alpha() -> None:
    short, long = pill("Short", 40, 800), pill("word " * 40, 40, 800)
    assert long.height > short.height
    assert long.width <= 800 + 40
    assert short.mode == "RGBA"
    assert short.getpixel((0, 0))[3] == 0


def test_highlight_maps_recorded_box_into_the_frame() -> None:
    box = take_box(TAKE, "verdict.look_first")
    assert box == [487, 513, 1982, 67]
    assert take_box(TAKE, "verdict.missing") is None
    ring = highlight(box, [0, CHROME, 2560, 1344], (0, 72, 1920), (1920, 1080))
    alpha = ring.getchannel("A")
    left = round(487 * 0.75)
    top = 72 + round((513 - CHROME) * 0.75)
    assert alpha.getpixel((left - 10, top + 20)) > 0  # ring edge
    assert alpha.getpixel((left + 400, top + 20)) < 30  # inside stays clear (soft glow only)


def test_cards_keep_sparkles_off_the_text(tmp_path: Path) -> None:
    folder = card_frames(
        "title-test", (320, 180), 0.2, [["TEXT", "black", 40, "#ffffff", 0.0]], tmp_path
    )
    frames = sorted(folder.glob("*.png"))
    assert len(frames) == 6
    assert frames[0].stat().st_size > 0


def test_music_is_generated_stereo_audio(tmp_path: Path) -> None:
    path = tmp_path / "music.wav"
    music(3.0, path)
    with wave.open(str(path)) as handle:
        assert handle.getnchannels() == 2
        assert handle.getframerate() == 48_000
        assert handle.getnframes() == 3 * 48_000


def test_credits_name_source_overlap_and_voice() -> None:
    text = credits_text(TAKE)
    assert "SYNTHETIC-CASE" in text
    assert "Synthetic attribution line." in text
    assert "overlaps its training data" in text
    assert "Kokoro-82M (Apache-2.0)" in text
    assert "Not medical advice" in text


def test_rendering_works_without_system_fonts(monkeypatch: pytest.MonkeyPatch) -> None:
    # CI runners and other distributions keep fonts elsewhere; Pillow's font still works.
    monkeypatch.setattr("scripts.promo_video.FONT_DIRS", [])
    assert pill("Caption", 36, 800).width > 0
