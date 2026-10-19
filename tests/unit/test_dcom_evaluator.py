# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""The operator's single-file diagnostic never prints identifying header values."""

import importlib.util
import json
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

import pydicom
import pytest
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dcom_evaluator.py"
spec = importlib.util.spec_from_file_location("dcom_evaluator", SCRIPT)
assert spec is not None
assert spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def run(path: Path, *options: str) -> tuple[int, dict[str, Any], str]:
    process = subprocess.run(  # noqa: S603 - fixed interpreter/script, synthetic test paths only
        [sys.executable, str(SCRIPT), str(path), *options],
        check=False,
        capture_output=True,
        text=True,
    )
    return process.returncode, json.loads(process.stdout), process.stderr


def test_valid_extensionless_header_omits_identity_and_never_loads_pixels(
    phantom_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = next(phantom_dir.glob("*.dcm"))
    dataset = pydicom.dcmread(source)
    dataset.PatientName = "PRIVATE^PERSON"
    dataset.PatientID = "SECRET-ID-123"
    dataset.InstitutionName = "SECRET-HOSPITAL"
    file = tmp_path / "SECRET-FILENAME"
    dataset.save_as(file, enforce_file_format=True)
    original = pydicom.dcmread
    reads = []

    def read(*args: Any, **kwargs: Any) -> Any:
        assert kwargs.get("stop_before_pixels") is True
        reads.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(pydicom, "dcmread", read)
    result = module.evaluate(file)
    assert len(reads) == 1
    assert result["status"] == "header_readable"
    assert result["technical"]["Rows"] > 0
    assert result["technical"]["transfer_syntax_uid"]
    serialized = json.dumps(result)
    for secret in ("PRIVATE", "SECRET", str(file), str(dataset.SOPInstanceUID)):
        assert secret not in serialized
    code, output, stderr = run(file)
    assert code == 0
    assert output["status"] == "header_readable"
    assert stderr == ""


def test_malformed_tag_reports_vr_and_lengths_without_its_value(
    phantom_dir: Path, tmp_path: Path
) -> None:
    source = next(phantom_dir.glob("*.dcm"))
    dataset = pydicom.dcmread(source)
    del dataset.PatientID
    file = tmp_path / "private-input"
    dataset.save_as(file, enforce_file_format=True)
    # Place malformed header before PixelData, using a header-only file.
    del dataset.PixelData
    dataset.save_as(file, enforce_file_format=True)
    with file.open("ab") as stream:
        stream.write(struct.pack("<HH2sH", 0x0010, 0x0020, b"US", 1) + b"\x01")
    code, result, stderr = run(file)
    assert code == 2
    assert result["status"] == "header_errors"
    error = result["header"]["conversion_errors"][0]
    assert error["tag"] == "(0010,0020)"
    assert error["keyword"] == "PatientID"
    assert error["vr"] == "US"
    assert error["dictionary_vr"] == "LO"
    assert error["declared_length"] == error["available_value_bytes"] == 1
    assert error["required_byte_multiple"] == 2
    assert error["exception_type"] == "BytesLengthException"
    assert "private-input" not in json.dumps(result)
    assert stderr == ""


@pytest.mark.parametrize("missing", [False, True])
def test_unreadable_input_has_safe_json_error(tmp_path: Path, missing: bool) -> None:
    file = tmp_path / "SECRET-PATH"
    if not missing:
        file.write_text("SECRET-NOT-DICOM")
    code, result, stderr = run(file)
    assert code == 2
    assert result["status"] == "read_error"
    assert "SECRET" not in json.dumps(result) + stderr


def test_nested_and_unknown_tags_and_bounds_do_not_expose_values() -> None:
    dataset = Dataset()
    dataset.add_new((0x7776, 0x0001), "LO", "SECRET")
    nested = Dataset()
    nested.PatientName = "SECRET^NAME"
    dataset.ReferencedStudySequence = Sequence([nested])
    result = module.inspect_header(dataset)
    assert result["elements_checked"] == 3
    assert result["errors"] == 0
    assert "SECRET" not in json.dumps(result)
    assert module.numeric(float("nan")) is None
    assert module.numeric("SECRET") is None
    assert module.numeric([1, float("inf")]) is None


def test_pixel_decode_is_explicit_and_only_shape_is_printed(phantom_dir: Path) -> None:
    file = next(phantom_dir.glob("*.dcm"))
    code, result, stderr = run(file, "--check-pixels")
    assert code == 0
    assert result["pixels"]["decoded"] is True
    assert len(result["pixels"]["shape"]) == 2
    assert "pixels" not in result["pixels"]
    assert stderr == ""


def test_argument_error_does_not_echo_extra_identifying_arguments(tmp_path: Path) -> None:
    process = subprocess.run(  # noqa: S603 - fixed script and synthetic secret argument
        [sys.executable, str(SCRIPT), str(tmp_path / "SECRET-PATH"), "SECRET-PATIENT"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 2
    assert "SECRET" not in process.stdout + process.stderr
    assert "quoted file path" in process.stderr


def test_copied_sealed_header_is_refused_before_pixel_read(
    phantom_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from thoraxbench.config import Settings
    from thoraxbench.splits import CaseRecord, Phase, make_split, save_split

    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    split = make_split(
        [CaseRecord(dataset="toy", patient_id=f"P{i}", case_id=f"P{i}") for i in range(10)], "toy"
    )
    save_split(split, settings.data_dir, settings.manifests_dir)
    dataset = pydicom.dcmread(next(phantom_dir.glob("*.dcm")))
    dataset.PatientID = split.cases(Phase.SEALED)[0]
    copy = tmp_path / "copied-study-file"
    dataset.save_as(copy, enforce_file_format=True)
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    original = pydicom.dcmread

    def read(*args: Any, **kwargs: Any) -> Any:
        assert kwargs.get("stop_before_pixels") is True
        return original(*args, **kwargs)

    monkeypatch.setattr(pydicom, "dcmread", read)
    result = module.evaluate(copy, check_pixels=True)
    assert result["status"] == "read_error"
    assert result["error"]["exception_type"] == "SealedAccessError"
    assert "pixels" not in result
    assert dataset.PatientID not in json.dumps(result)


def test_known_sealed_path_is_refused_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from thoraxbench.config import Settings

    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    result = module.evaluate(settings.data_path("sealed", "never-read-file"))
    assert result["status"] == "read_error"
    assert result["error"]["exception_type"] == "SealedAccessError"
    assert "file_size_bytes" not in result


def test_bounded_incomplete_inspection_cannot_enable_pixels(
    phantom_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module, "MAX_ELEMENTS", 1)
    result = module.evaluate(next(phantom_dir.glob("*.dcm")), check_pixels=True)
    assert result["header"]["truncated"] is True
    assert result["status"] == "header_incomplete"
    assert result["pixels"]["decoded"] is False
    assert result["pixels"]["exception_type"] == "HeaderValidationError"


def test_scan_groups_malformed_lengths_and_ephemeral_planes(
    phantom_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from thoraxbench.config import Settings

    monkeypatch.setattr(
        module, "get_settings", lambda: Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    )
    folder = tmp_path / "scan"
    folder.mkdir()
    dataset = pydicom.dcmread(next(phantom_dir.glob("*.dcm")))
    dataset.PatientID = "PRIVATE-PATIENT"
    dataset.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    uid = str(dataset.SeriesInstanceUID)
    dataset.save_as(folder / "axial", enforce_file_format=True)
    dataset.ImageOrientationPatient = [1, 0, 0, 0, 0, 1]
    dataset.save_as(folder / "coronal", enforce_file_format=True)
    del dataset.PatientID
    del dataset.PixelData
    for index in range(2):
        path = folder / f"malformed-{index}"
        dataset.save_as(path, enforce_file_format=True)
        with path.open("ab") as stream:
            stream.write(struct.pack("<HH2sH", 0x0010, 0x0020, b"US", 1) + b"\x01")
    (folder / "README").write_text("PRIVATE-NOT-DICOM")
    original = pydicom.dcmread

    def headers_only(*args: Any, **kwargs: Any) -> Any:
        assert kwargs.get("stop_before_pixels") is True
        return original(*args, **kwargs)

    monkeypatch.setattr(pydicom, "dcmread", headers_only)
    result = module.scan_headers(folder)
    assert result["counts"]["scanned"] == 5
    assert result["counts"]["readable"] == 2
    assert result["counts"]["header_errors"] == 2
    assert result["counts"]["non_dicom"] == 1
    group = result["error_groups"][0]
    assert group["count"] == 2
    assert group["vr"] == "US"
    assert group["declared_length"] == group["available_value_bytes"] == 1
    assert group["required_byte_multiple"] == 2
    assert group["exception_type"] == "BytesLengthException"
    assert {entry["orientation"] for entry in result["series"]} == {"axial", "coronal"}
    assert all(isinstance(entry["series"], int) for entry in result["series"])
    assert {entry["series"] for entry in result["series"]} == {1}
    assert "PRIVATE" not in json.dumps(result)
    assert uid not in json.dumps(result)
    assert str(folder) not in json.dumps(result)


def test_scan_bounds_skips_symlinks_and_never_opens_protected_paths(
    phantom_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from thoraxbench.config import Settings

    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    folder = tmp_path / "scan"
    folder.mkdir()
    (folder / "alias").symlink_to(phantom_dir, target_is_directory=True)
    (folder / "file-alias").symlink_to(next(phantom_dir.glob("*.dcm")))
    assert module.scan_headers(folder)["counts"]["symlinks_skipped"] == 2
    (folder / "one").write_text("junk")
    (folder / "two").write_text("junk")
    result = module.scan_headers(folder, max_files=1)
    assert result["truncated"] is True
    assert result["counts"]["scanned"] == 1
    protected = module.scan_headers(settings.data_path("sealed", "never-open"))
    assert protected["status"] == "read_error"
    assert protected["counts"]["scanned"] == 0
    assert protected["error"]["exception_type"] == "SealedAccessError"
    (folder / "protected-alias").symlink_to(settings.data_path("sealed"), target_is_directory=True)
    result = module.scan_headers(folder)
    assert result["counts"]["protected_paths"] == 1


def test_scan_refuses_copied_sealed_patient(
    phantom_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from thoraxbench.config import Settings
    from thoraxbench.splits import CaseRecord, Phase, make_split, save_split

    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    split = make_split(
        [CaseRecord(dataset="toy", patient_id=f"P{i}", case_id=f"P{i}") for i in range(10)], "toy"
    )
    save_split(split, settings.data_dir, settings.manifests_dir)
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    folder = tmp_path / "copied"
    folder.mkdir()
    dataset = pydicom.dcmread(next(phantom_dir.glob("*.dcm")))
    dataset.PatientID = split.cases(Phase.SEALED)[0]
    dataset.save_as(folder / "copy", enforce_file_format=True)
    result = module.scan_headers(folder)
    assert result["status"] == "read_error"
    assert result["counts"]["readable"] == 0
    assert result["error"]["exception_type"] == "SealedAccessError"
    assert dataset.PatientID not in json.dumps(result)


def test_scan_cli_conflicting_options_and_missing_dependencies_are_safe(tmp_path: Path) -> None:
    process = subprocess.run(  # noqa: S603 - fixed script and synthetic arguments
        [sys.executable, str(SCRIPT), str(tmp_path / "SECRET"), "--scan-headers", "--check-pixels"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 2
    assert "SECRET" not in process.stdout + process.stderr
    process = subprocess.run(  # noqa: S603 - fixed interpreter/script, synthetic path
        [sys.executable, "-S", str(SCRIPT), str(tmp_path / "SECRET")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 2
    assert "uv run" in process.stderr
    assert "Traceback" not in process.stderr
    assert "SECRET" not in process.stderr


def test_scan_metadata_is_collected_once_and_progress_has_only_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from unittest.mock import Mock

    from thoraxbench.config import Settings

    monkeypatch.setattr(
        module, "get_settings", lambda: Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    )
    folder = tmp_path / "scan"
    folder.mkdir()
    for number in range(100):
        (folder / f"SECRET-{number}").write_text("junk")
    original = module.importlib.metadata.version
    version = Mock(wraps=original)
    monkeypatch.setattr(module.importlib.metadata, "version", version)
    result = module.scan_headers(folder, progress=True)
    assert version.call_count == 6
    output = capsys.readouterr()
    assert output.out == ""
    assert "SECRET" not in output.err
    assert json.loads(output.err)["scanned"] == 100
    assert result["counts"]["non_dicom"] == 100
    assert module.scan_headers(folder, max_files=0)["status"] == "read_error"
    timed = module.scan_headers(folder, max_seconds=1e-100)
    assert timed["truncated"] is True
    assert timed["counts"]["scanned"] == 0


def test_import_check_uses_app_loader_without_models_or_identifiers(
    phantom_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from thoraxbench.config import Settings

    monkeypatch.setattr(
        module, "get_settings", lambda: Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    )
    result = module.evaluate_import(phantom_dir, progress=True)
    assert result["status"] == "succeeded"
    assert result["selected_slices"] >= 20
    assert len(result["spacing_mm"]) == 3
    assert isinstance(result["qc_adequate"], bool)
    assert isinstance(result["qc_warning_count"], int)
    assert "PHANTOM" not in json.dumps(result)
    assert str(phantom_dir) not in json.dumps(result)
    assert "selected_series" not in json.dumps(result)

    events = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert [event["stage"] for event in events[:4]] == [
        "folder_check",
        "study",
        "source_recheck",
        "done",
    ]
    assert events[-1]["event"] == "import_finished"
    assert str(phantom_dir) not in json.dumps(events)


def test_import_check_pixel_corruption_is_fatal(
    phantom_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from thoraxbench.config import Settings

    monkeypatch.setattr(
        module, "get_settings", lambda: Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    )
    folder = tmp_path / "corrupt"
    shutil.copytree(phantom_dir, folder)
    for file in folder.glob("*.dcm"):
        dataset = pydicom.dcmread(file)
        if "LOCALIZER" not in dataset.get("ImageType", []):
            dataset.PixelData = bytes(2)
            dataset.save_as(file, enforce_file_format=True)
            break
    result = module.evaluate_import(folder)
    assert result["status"] == "failed"
    assert result["error"]["code"] == "dicom_read_error"
    assert result["error"]["exception_type"] == "DicomPixelError"


def test_import_check_source_change_and_guard_refusal_are_safe(
    phantom_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from thoraxbench.config import Settings

    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    original = module.load_study_dir

    def mutate(*args: Any, **kwargs: Any) -> Any:
        study = original(*args, **kwargs)
        (phantom_dir / "source-change").write_text("changed")
        return study

    monkeypatch.setattr(module, "load_study_dir", mutate)
    result = module.evaluate_import(phantom_dir)
    assert result["error"]["code"] == "source_changed"
    (phantom_dir / "source-change").unlink()
    protected = module.evaluate_import(settings.data_path("sealed", "SECRET"))
    assert protected["error"]["code"] == "sealed_input"
    assert "SECRET" not in json.dumps(protected)


def test_import_cli_requires_explicit_folder_mode_and_respects_scan_bounds(
    phantom_dir: Path, tmp_path: Path
) -> None:
    code, result, stderr = run(phantom_dir, "--scan-headers", "--check-import")
    assert code == 0
    assert result["import"]["status"] == "succeeded"
    assert result["pixels_requested"] is True
    assert stderr == ""
    code, result, stderr = run(phantom_dir, "--scan-headers", "--check-import", "--max-files", "1")
    assert code == 2
    assert result["import"]["status"] == "not_run"
    assert result["import"]["reason"] == "scan_not_complete"
    process = subprocess.run(  # noqa: S603 - fixed script and synthetic arguments
        [sys.executable, str(SCRIPT), str(tmp_path / "SECRET"), "--check-import"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 2
    assert "SECRET" not in process.stderr


def test_scan_counts_mistyped_private_value_as_readable(
    phantom_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pydicom.uid import ImplicitVRLittleEndian

    from thoraxbench.config import Settings

    monkeypatch.setattr(
        module, "get_settings", lambda: Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    )
    folder = tmp_path / "vendor"
    folder.mkdir()
    dataset = pydicom.dcmread(next(phantom_dir.glob("*.dcm")))
    dataset.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
    dataset.add_new(0x01F10010, "LO", "ELSCINT1")
    dataset.add_new(0x01F11026, "UN", b"0.984 ")
    path = folder / "slice"
    dataset.save_as(path, implicit_vr=True, little_endian=True, enforce_file_format=True)
    result = module.scan_headers(folder)
    assert result["counts"]["readable"] == 1
    assert result["counts"]["header_errors"] == 0
    assert result["counts"]["private_values_raw"] == 1
    group = result["error_groups"][0]
    assert group["tag"] == "(01F1,1026)"
    assert group["exception_type"] == "BytesLengthException"
    assert "ELSCINT1" not in json.dumps(result)
    single = module.evaluate(path)
    assert single["status"] == "header_readable"
    assert single["header"]["private_errors"] == 1
