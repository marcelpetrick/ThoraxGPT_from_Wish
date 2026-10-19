# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Actual bounded loading counters over generated DICOM; callbacks may cancel work."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from thoraxbench.api.jobs import JobCancelledError
from thoraxbench.config import Settings
from thoraxbench.dicom import discover_series, load_study, load_volume
from thoraxbench.dicom.progress import emit_progress
from thoraxbench.study import load_study_dir
from thoraxbench.study_access import guard_study_input
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series

Counter = tuple[str, int, int | None]


def phantom(path: Path) -> Path:
    """Create a bounded synthetic study with extensionless image files."""
    spec = PhantomSpec(shape=(52, 64, 64))
    write_dicom_series(make_phantom(spec), path, spec.spacing_mm, include_scout=False)
    (path / "README.txt").unlink()
    for file in path.glob("*.dcm"):
        file.rename(file.with_suffix(""))
    return path


def test_guard_and_loader_emit_safe_actual_bounded_counts(tmp_path: Path) -> None:
    folder = phantom(tmp_path / "input")
    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    counters: list[Counter] = []

    def progress(operation: str, completed: int, total: int | None) -> None:
        counters.append((operation, completed, total))

    guard_study_input(folder, settings, progress=progress)
    assert ("path_check", 52, 52) in counters
    assert ("header_check", 52, 52) in counters
    assert ("header_check", 25, 52) in counters
    assert ("header_check", 50, 52) in counters
    assert len(counters) < 15
    counters.clear()
    study = load_study_dir(folder, progress=progress)
    assert study.volume.shape[0] == 52
    assert ("discovery", 52, 52) in counters
    assert ("pixel_decode", 52, 52) in counters
    assert ("pixel_decode", 25, 52) in counters
    assert ("input_qc", 0, 1) in counters
    assert ("input_qc", 1, 1) in counters
    assert counters.index(("pixel_decode", 52, 52)) < counters.index(("input_qc", 0, 1))
    assert counters.index(("input_qc", 1, 1)) < counters.index(("header_check", 52, 52))
    assert len(counters) < 25
    assert str(folder) not in str(counters)
    assert "PHANTOM" not in str(counters)


def test_callback_cancels_header_guard_before_pixels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = phantom(tmp_path / "input")
    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    import thoraxbench.study_access as access

    reader = Mock(wraps=access.read_header)
    monkeypatch.setattr(access, "read_header", reader)

    def cancelled(operation: str, completed: int, total: int | None) -> None:
        if operation == "header_check" and completed == 25:
            raise JobCancelledError

    with pytest.raises(JobCancelledError):
        guard_study_input(folder, settings, progress=cancelled)
    assert reader.call_count == 25


def test_discovery_can_cancel_after_25_headers(tmp_path: Path) -> None:
    folder = phantom(tmp_path / "input")
    counts: dict[str, int] = {}

    def cancelled(operation: str, completed: int, total: int | None) -> None:
        if operation == "discovery" and completed == 25:
            raise JobCancelledError

    with pytest.raises(JobCancelledError):
        discover_series(folder, counts, progress=cancelled)
    assert counts["files_scanned"] == 25


def test_pixel_decode_counts_only_decoded_images_and_cancels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = phantom(tmp_path / "input")
    series = discover_series(folder)[0]
    from thoraxbench.dicom import volume

    decoder = Mock(wraps=volume._to_hu)
    monkeypatch.setattr(volume, "_to_hu", decoder)

    def cancelled(operation: str, completed: int, total: int | None) -> None:
        if operation == "pixel_decode" and completed == 25:
            raise JobCancelledError

    with pytest.raises(JobCancelledError):
        load_volume(series, progress=cancelled)
    assert decoder.call_count == 25
    with pytest.raises(JobCancelledError):
        load_study(folder, progress=cancelled)


def test_qc_start_is_before_expensive_qc_and_callback_cancellation_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = phantom(tmp_path / "input")
    from thoraxbench.dicom import volume

    qc = Mock(side_effect=AssertionError("QC must not begin after cancellation"))
    monkeypatch.setattr(volume, "lung_voxel_fraction", qc)

    def cancelled(operation: str, completed: int, total: int | None) -> None:
        if operation == "input_qc" and completed == 0:
            raise JobCancelledError

    with pytest.raises(JobCancelledError):
        load_study_dir(folder, progress=cancelled)
    qc.assert_not_called()


def test_empty_discovery_and_optional_callback(tmp_path: Path) -> None:
    counters: list[Counter] = []
    assert (
        discover_series(
            tmp_path,
            progress=lambda operation, completed, total: counters.append(
                (operation, completed, total)
            ),
        )
        == []
    )
    assert counters[-1] == ("discovery", 0, 0)
    callback = Mock()
    for completed in range(52):
        emit_progress(callback, "header_check", completed, 51)
    assert callback.call_count == 4
    emit_progress(None, "header_check", 0, 0)
