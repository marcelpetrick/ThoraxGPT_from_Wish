# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Synthetic detector review, exports and manual setup; no network or real weights."""

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.detector_stub import install_stub
from thoraxbench.api.app import create_app
from thoraxbench.config import Settings

pytestmark = pytest.mark.integration


def _finished(client: TestClient, identifier: str) -> dict[str, Any]:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{identifier}").json()
        if job["finished"]:
            return dict(job)
        time.sleep(0.05)
    pytest.fail("synthetic detector job did not finish")


def test_detector_review_and_offline_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_stub(monkeypatch)
    settings = Settings(data_dir=tmp_path / "data", ollama_url="http://127.0.0.1:1")
    with TestClient(create_app(settings)) as client:
        model = next(
            m for m in client.get("/api/models").json()["models"] if m["id"] == "monai-lung-nodule"
        )
        assert model["available"]
        assert not model["download_supported"]
        assert any("--extra detector" in step for step in model["setup_steps"])
        assert (
            client.post(
                "/api/models/monai-lung-nodule/pull", json={"terms_acknowledged": True}
            ).status_code
            == 422
        )
        assert client.post("/api/demo").status_code == 200
        response = client.post(
            "/api/jobs",
            json={
                "kind": "analysis",
                "dataset": "demo",
                "case_id": "phantom",
                "model_id": "monai-lung-nodule",
            },
        )
        assert response.status_code == 200, response.text
        job = _finished(client, response.json()["job"]["id"])
        assert job["status"] == "succeeded"
        body = job["result"]
        review = body["candidate_review"]
        assert (review["previewed"], review["total"], review["illustrative"]) == (1, 1, True)
        (candidate,) = review["candidates"]
        assert candidate["slice_index"] == 22
        assert candidate["source"] == "detector"
        assert [p["plane"] for p in candidate["previews"]] == ["axial", "coronal"]
        assert all(
            p["data_url"].startswith("data:image/png;base64,") for p in candidate["previews"]
        )
        html = client.get(body["downloads"]["html"]).text
        assert "data:image/png;base64," in html
        assert "not input to the detector or verified by a VLM" in html
        assert "Source: detector" in html
        assert 'id="candidate-1-axial"' in html
        assert "Localised candidates (research reference)" in body["markdown"]
        assert "Scripted synthetic detector output" in html


def test_installed_optional_detector_licenses_are_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    from email.message import Message
    from importlib import metadata

    from thoraxbench.api.licenses import runtime_libraries

    def package(name: str) -> Message:
        if name not in {"thoraxbench", "monai", "torch", "torchvision"}:
            raise metadata.PackageNotFoundError(name)
        record = Message()
        record["Name"] = name
        record["Version"] = "test-version"
        record["License-Expression"] = "Apache-2.0" if name == "monai" else "BSD-3-Clause"
        return record

    monkeypatch.setattr(metadata, "metadata", package)
    records = runtime_libraries()
    assert [row["name"] for row in records] == ["monai", "torch", "torchvision"]
    assert records[0]["license"] == "Apache-2.0"


def test_detector_cancel_waits_for_running_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from threading import Event

    from tests.detector_stub import scripted_result
    from thoraxbench.api import app as api

    install_stub(monkeypatch)
    entered, release = Event(), Event()

    def blocking(*args: Any, **kwargs: Any) -> Any:
        kwargs["on_stage"]("inference")
        entered.set()
        assert release.wait(20)
        return scripted_result(*args, **kwargs)

    monkeypatch.setattr(api, "analyze_study", blocking)
    settings = Settings(data_dir=tmp_path / "data", ollama_url="http://127.0.0.1:1")
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/demo").status_code == 200
        job = client.post(
            "/api/jobs",
            json={
                "kind": "analysis",
                "dataset": "demo",
                "case_id": "phantom",
                "model_id": "monai-lung-nodule",
            },
        ).json()["job"]
        try:
            assert entered.wait(10)
            cancelled = client.post(f"/api/jobs/{job['id']}/cancel").json()
            assert cancelled["status"] == "cancelling"
            assert cancelled["cancel_stage"] == "inference"
            assert not cancelled["finished"]
        finally:
            release.set()
        completed = _finished(client, job["id"])
        assert completed["status"] == "cancelled"
        assert completed["result"] is None
