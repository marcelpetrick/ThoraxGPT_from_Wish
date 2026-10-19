# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Malformed deferred header values never reach pixels or break valid study loading."""

import struct
from pathlib import Path
from unittest.mock import Mock

import pydicom
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.errors import BytesLengthException
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

from thoraxbench.config import Settings
from thoraxbench.dicom.discovery import discover_series
from thoraxbench.dicom.headers import read_header
from thoraxbench.privacy import audit_files, identifier_values
from thoraxbench.splits import CaseRecord, Phase, make_split, save_split
from thoraxbench.study import StudyLoadError, load_study_dir
from thoraxbench.study_access import guard_study_input
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series


def malformed(path: Path, tag: tuple[int, int] = (0x0010, 0x0020)) -> Path:
    """Write actual explicit-VR US bytes with illegal odd length, not a mock exception."""
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    dataset = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.save_as(path, enforce_file_format=True)
    with path.open("ab") as stream:
        stream.write(struct.pack("<HH2sH", *tag, b"US", 1) + b"\x01")
    return path


def phantom(path: Path, patient: str = "SYNTHETIC-ONLY") -> Path:
    """Write extensionless valid synthetic CT files."""
    spec = PhantomSpec(shape=(32, 64, 64))
    write_dicom_series(
        make_phantom(spec), path, spec.spacing_mm, patient_id=patient, include_scout=False
    )
    (path / "README.txt").unlink()
    for file in path.glob("*.dcm"):
        file.rename(file.with_suffix(""))
    return path


def test_real_lazy_bytes_length_exception_is_contained(tmp_path: Path) -> None:
    path = malformed(tmp_path / "malformed")
    dataset = pydicom.dcmread(path, stop_before_pixels=True)
    with pytest.raises(BytesLengthException):
        dataset.get("PatientID")
    assert read_header(path) is None
    stats: dict[str, int] = {}
    assert discover_series(tmp_path, stats) == []
    assert stats == {
        "files_scanned": 1,
        "headers_readable": 0,
        "headers_unreadable": 1,
        "non_dicom_files": 0,
    }
    assert identifier_values([path]) == frozenset()
    audit = audit_files([path])
    assert audit.files_scanned == 0
    assert audit.files_skipped == 1


def test_good_extensionless_ct_skips_bad_headers_and_junk_with_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = phantom(tmp_path / "study")
    malformed(folder / "bad-patient-id")
    malformed(folder / "bad-patient-name", (0x0010, 0x0010))
    (folder / "readme").write_text("ordinary non-DICOM file")
    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    assert guard_study_input(folder, settings) == ("adhoc", "study")
    original = pydicom.dcmread
    pixel_reads = []

    def checked(path: Path, **kwargs: object) -> pydicom.Dataset:
        if not kwargs.get("stop_before_pixels"):
            assert Path(path).name not in {"bad-patient-id", "bad-patient-name", "readme"}
            pixel_reads.append(path)
        return original(path, **kwargs)

    monkeypatch.setattr(pydicom, "dcmread", checked)
    study = load_study_dir(folder)
    assert study.volume.shape[0] == 32
    assert len(pixel_reads) == 32
    assert study.selection["discovery"] == {
        "files_scanned": 35,
        "headers_readable": 32,
        "headers_unreadable": 2,
        "non_dicom_files": 1,
    }
    assert study.selection["header_error_types"] == {"BytesLengthException": 2}
    assert study.selection["warnings"] == ["2 unreadable DICOM header file(s) skipped"]
    assert study.selection["warnings"][0] in study.qc.warnings


def test_all_malformed_and_readable_non_ct_fail_with_safe_diagnostics(tmp_path: Path) -> None:
    malformed(tmp_path / "broken")
    with pytest.raises(StudyLoadError) as failure:
        load_study_dir(tmp_path)
    error = failure.value
    assert error.discovery == {
        "files_scanned": 1,
        "headers_readable": 0,
        "headers_unreadable": 1,
        "non_dicom_files": 0,
    }
    assert error.header_error_types == {"BytesLengthException": 1}
    assert error.selection["n_series"] == 0
    assert str(tmp_path) not in str(error.selection)
    assert "selected_series" not in error.selection
    assert "rejected" not in error.selection
    folder = phantom(tmp_path / "non-ct")
    for file in folder.iterdir():
        dataset = pydicom.dcmread(file)
        dataset.Modality = "MR"
        dataset.save_as(file, enforce_file_format=True)
    with pytest.raises(StudyLoadError) as failure:
        load_study_dir(folder)
    assert failure.value.selection["n_series"] == 1
    assert failure.value.discovery["headers_readable"] == 32


def test_selected_ct_pixel_decode_failure_is_fatal(tmp_path: Path) -> None:
    folder = phantom(tmp_path / "study")
    file = next(folder.iterdir())
    dataset = pydicom.dcmread(file)
    dataset.PixelData = b"\x00\x00"
    dataset.save_as(file, enforce_file_format=True)
    assert len(discover_series(folder)) == 1
    with pytest.raises(ValueError, match="pixel data") as failure:
        load_study_dir(folder)
    assert failure.value.code == "dicom_read_error"
    assert isinstance(failure.value.__cause__, ValueError)


def test_bad_header_does_not_bypass_copied_sealed_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    split = make_split(
        [CaseRecord(dataset="toy", patient_id=f"P{i}", case_id=f"P{i}") for i in range(10)], "toy"
    )
    save_split(split, settings.data_dir, settings.manifests_dir)
    sealed = split.cases(Phase.SEALED)[0]
    folder = phantom(tmp_path / "copied", sealed)
    malformed(folder / "000-malformed")
    original = pydicom.dcmread
    reader = Mock(wraps=original)
    monkeypatch.setattr(pydicom, "dcmread", reader)
    with pytest.raises(PermissionError, match="sealed validation"):
        guard_study_input(folder, settings)
    assert all(call.kwargs.get("stop_before_pixels") is True for call in reader.call_args_list)


def test_ordinary_non_dicom_files_are_counted_without_malformed_warning(tmp_path: Path) -> None:
    folder = phantom(tmp_path / "study")
    (folder / "README.txt").write_text("ordinary study notes")
    (folder / "annotations.xml").write_text("<annotations/>")
    study = load_study_dir(folder)
    assert study.selection["discovery"] == {
        "files_scanned": 34,
        "headers_readable": 32,
        "headers_unreadable": 0,
        "non_dicom_files": 2,
    }
    assert study.selection["warnings"] == []
