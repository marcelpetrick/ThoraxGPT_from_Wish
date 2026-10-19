# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Failed synthetic folder jobs have downloadable, privacy-bounded debug information."""

import time
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from thoraxbench.api.app import create_app
from thoraxbench.config import Settings


def test_empty_folder_failure_explains_input_and_exports_a_matching_trace(tmp_path: Path) -> None:
    private = tmp_path / "PRIVATE-PATIENT"
    private.mkdir()
    with TestClient(create_app(Settings(data_dir=tmp_path / "data"))) as client:
        submitted = client.post("/api/local-studies", json={"path": str(private)})
        assert submitted.status_code == 202
        identifier = submitted.json()["job"]["id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = client.get(f"/api/jobs/{identifier}").json()
            if job["finished"]:
                break
            time.sleep(0.01)
        assert job["status"] == "failed"
        assert job["diagnostic"]["code"] == "no_dicom_files"
        assert job["diagnostic"]["stage"] == "study"
        assert job["diagnostic"]["discovery"]["files_scanned"] == 0
        exported = client.get(f"/api/jobs/{identifier}/diagnostics")
        assert exported.status_code == 200
        assert exported.headers["content-disposition"].startswith("attachment;")
        assert exported.json()["diagnostic"]["trace_id"] == job["diagnostic"]["trace_id"]
        assert "PRIVATE-PATIENT" not in exported.text
        assert str(private) not in exported.text
        assert "Research use only" in exported.text
        assert client.get(f"/api/jobs/{uuid4()}/diagnostics").status_code == 404


def test_successful_folder_with_bad_header_exports_warning_trace(tmp_path: Path) -> None:
    import struct

    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

    from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series

    folder = tmp_path / "PRIVATE-PATIENT"
    spec = PhantomSpec(shape=(32, 64, 64))
    write_dicom_series(make_phantom(spec), folder, spec.spacing_mm, include_scout=False)
    bad = folder / "PRIVATE-FILENAME"
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    FileDataset(str(bad), {}, file_meta=meta, preamble=b"\0" * 128).save_as(
        bad, enforce_file_format=True
    )
    with bad.open("ab") as stream:
        stream.write(struct.pack("<HH2sH", 0x0010, 0x0020, b"US", 1) + b"\x01")
    with TestClient(create_app(Settings(data_dir=tmp_path / "data"))) as client:
        submitted = client.post("/api/local-studies", json={"path": str(folder)})
        identifier = submitted.json()["job"]["id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = client.get(f"/api/jobs/{identifier}").json()
            if job["finished"]:
                break
            time.sleep(0.01)
        assert job["status"] == "succeeded", job
        assert job["diagnostic"]["severity"] == "warning"
        assert job["diagnostic"]["header_error_types"] == {"BytesLengthException": 1}
        assert job["result"]["discovery"]["headers_unreadable"] == 1
        exported = client.get(f"/api/jobs/{identifier}/diagnostics")
        assert exported.status_code == 200
        assert "PRIVATE-PATIENT" not in exported.text
        assert "PRIVATE-FILENAME" not in exported.text
        assert exported.json()["diagnostic"]["trace_id"] == job["diagnostic"]["trace_id"]
