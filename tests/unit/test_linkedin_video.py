# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Recorder planning/guard tests use only synthetic metadata; no medical pixels or GPU."""

import copy
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from scripts.linkedin_video import (
    MODEL,
    default_plan,
    focus_crop,
    guard_case_request,
    hash_file,
    local_url,
    master_path,
    output_root,
    parser,
    preflight,
    private_library,
    srt,
    stop_process,
    validate_plan,
    verify_result,
    x11_environment,
)

from thoraxbench.splits import Phase


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost",
        "http://lan:8000",
        "http://user@localhost",
        "http://127.0.0.1/a",
        "http://localhost/?a=1",
    ],
)
def test_remote_and_credential_urls_are_refused(url: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        local_url(url)


def test_local_and_detector_only_arguments() -> None:
    assert local_url("http://127.0.0.1:8001/") == "http://127.0.0.1:8001"
    args = parser().parse_args(
        [
            "capture",
            "--url",
            "http://localhost:8001",
            "--dataset",
            "lidc_idri",
            "--case",
            "SYNTHETIC",
        ]
    )
    assert args.model == MODEL
    assert not args.allow_real_calibration
    with pytest.raises(SystemExit):
        parser().parse_args(["capture", "--model", "heuristic-hu"])


def test_output_symlink_escape_is_refused(tmp_path: Path) -> None:
    (tmp_path / "data/results").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "data/results/linkedin").symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        output_root(tmp_path)


def test_calibration_registry_and_explicit_consent_are_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "configs/datasets/lidc_idri.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("status: approved\n")
    loader = Mock()
    monkeypatch.setattr("scripts.linkedin_video.CaseGuard.load", loader)
    with pytest.raises(ValueError, match="acknowledgement"):
        preflight(tmp_path, "lidc_idri", "SYNTHETIC", MODEL, False)
    preflight(tmp_path, "lidc_idri", "SYNTHETIC", MODEL, True)
    loader.return_value.check.assert_called_once_with("SYNTHETIC", Phase.CALIBRATION)
    loader.return_value.check.side_effect = ValueError("sealed or internal-test")
    with pytest.raises(ValueError, match="sealed or internal"):
        preflight(tmp_path, "lidc_idri", "SYNTHETIC", MODEL, True)
    config.write_text("status: pending_access\n")
    with pytest.raises(ValueError, match="not approved"):
        preflight(tmp_path, "lidc_idri", "SYNTHETIC", MODEL, True)


def synthetic_take() -> dict:
    phases = ["study", "viewer", "setup", "running", "findings", "candidates", "report", "about"]
    return {
        "status": "succeeded",
        "recording_wall_s": 90,
        "width": 2560,
        "height": 1440,
        "job": {"elapsed_s": 23.5},
        "events": [
            {"name": phase, "start": index * 10, "end": index * 10 + 9}
            for index, phase in enumerate(phases)
        ],
    }


def test_both_cuts_are_thirty_seconds_and_wait_edits_are_disclosed() -> None:
    take = synthetic_take()
    plan = default_plan(take)
    validate_plan(plan, take)
    for clips in plan["cuts"].values():
        assert sum(clip["duration"] for clip in clips) + plan["endcard_seconds"] == 30
        assert any("Wait shortened" in clip["caption"] for clip in clips)
        assert "00:00:30,000" in srt(clips)
    assert "23.5 seconds" in plan["cuts"]["A"][2]["caption"]


@pytest.mark.parametrize("change", ["failed", "nan", "outside", "crop", "duration"])
def test_unsafe_or_misleading_cut_plans_are_refused(change: str) -> None:
    take = synthetic_take()
    plan = copy.deepcopy(default_plan(take))
    clip = plan["cuts"]["A"][0]
    if change == "failed":
        take["status"] = "failed"
    elif change == "nan":
        clip["start"] = float("nan")
    elif change == "outside":
        clip["start"] = 10000
    elif change == "crop":
        clip["crop"] = [2500, 0, 1000, 1000]
    else:
        clip["duration"] = 4
    with pytest.raises(ValueError, match=r"take|Excerpt|Crop|excerpts"):
        validate_plan(plan, take)


def test_readable_crop_is_even_and_bounded() -> None:
    assert focus_crop({"x": 2501, "y": -100}, 2560, 1440) == [1160, 0, 1400, 1100]


def test_private_library_and_case_route_allow_only_selected_calibration() -> None:
    chosen = {"dataset": "lidc_idri", "case_id": "SYNTHETIC", "phase": "calibration"}
    route = Mock()
    route.fetch.return_value.json.return_value = {
        "studies": [chosen, {"dataset": "lidc_idri", "case_id": "OTHER", "phase": "internal_test"}]
    }
    private_library(route, "lidc_idri", "SYNTHETIC")
    assert route.fulfill.call_args.kwargs["json"]["studies"] == [chosen]
    route.request.url = "http://localhost/api/studies/lidc_idri/OTHER/slice/0.png"
    guard_case_request(route, "lidc_idri", "SYNTHETIC")
    route.abort.assert_called_once_with("blockedbyclient")
    route.request.url = "http://localhost/api/studies/lidc_idri/SYNTHETIC/slice/0.png"
    guard_case_request(route, "lidc_idri", "SYNTHETIC")
    route.continue_.assert_called_once()


def test_process_shutdown_kills_and_reaps_on_timeout() -> None:
    process = Mock()
    process.poll.return_value = None
    process.wait.side_effect = [subprocess.TimeoutExpired("synthetic", 10), 0]
    stop_process(process)
    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    assert process.wait.call_count == 2


def test_preserved_master_hash_and_symlink_guard(tmp_path: Path) -> None:
    folder = tmp_path / "take"
    folder.mkdir()
    master = folder / "master.mp4"
    master.write_bytes(b"synthetic fixture, not patient pixels")
    digest = hash_file(master)
    assert master_path(folder, digest) == master
    master.write_bytes(b"changed")
    with pytest.raises(ValueError, match="integrity"):
        master_path(folder, digest)
    master.unlink()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"synthetic")
    master.symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        master_path(folder, hash_file(outside))


@pytest.mark.parametrize(
    "change", ["valid", "model", "abstain", "error", "source", "dirty", "commit"]
)
def test_real_result_identity_guard(change: str) -> None:
    result = {
        "result": {
            "model_id": MODEL,
            "raw_error": None,
            "report": {"abstain": False, "findings": [{"source": "detector"}]},
            "provenance": {"git_commit": "synthetic-source", "git_dirty": False},
        }
    }
    value = result["result"]
    if change == "model":
        value["model_id"] = "heuristic-hu"
    elif change == "abstain":
        value["report"]["abstain"] = True
    elif change == "error":
        value["raw_error"] = "synthetic failure"
    elif change == "source":
        value["report"]["findings"][0]["source"] = "model"
    elif change == "dirty":
        value["provenance"]["git_dirty"] = True
    elif change == "commit":
        value["provenance"]["git_commit"] = "different"
    if change == "valid":
        verify_result(result, "synthetic-source")
    else:
        with pytest.raises(ValueError, match=r"detector|identity"):
            verify_result(result, "synthetic-source")


def test_capture_cannot_inherit_personal_wayland_display(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "personal-wayland")
    monkeypatch.setenv("WAYLAND_SOCKET", "42")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    env = x11_environment(":91")
    assert env["DISPLAY"] == ":91"
    assert env["XDG_SESSION_TYPE"] == "x11"
    assert "WAYLAND_DISPLAY" not in env
    assert "WAYLAND_SOCKET" not in env
