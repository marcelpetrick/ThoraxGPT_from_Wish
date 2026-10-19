# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Session folder imports use synthetic pixels and preserve split/header guards."""

import shutil
import time
from pathlib import Path
from threading import Event
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from thoraxbench.api import app as api
from thoraxbench.api import local_studies
from thoraxbench.config import Settings
from thoraxbench.splits import CaseRecord, Phase, make_split, save_split
from thoraxbench.study import Study
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    shutil.copytree(Settings().configs_dir, tmp_path / "configs")
    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    settings.data_dir.mkdir()
    return settings


def phantom(path: Path, patient: str = "PRIVATE-PATIENT") -> Path:
    """Write a small generated CT series, never a real patient study."""
    spec = PhantomSpec(shape=(32, 64, 64))
    write_dicom_series(make_phantom(spec), path, spec.spacing_mm, patient_id=patient)
    return path


def split(settings: Settings) -> tuple[str, str]:
    """Return one development and one sealed synthetic identity."""
    result = make_split(
        [CaseRecord(dataset="toy", patient_id=f"P{i}", case_id=f"P{i}") for i in range(10)],
        dataset="toy",
    )
    save_split(result, settings.data_dir, settings.manifests_dir)
    return result.cases(Phase.DEVELOPMENT)[0], result.cases(Phase.SEALED)[0]


def wait(client: TestClient, job: dict[str, Any]) -> dict[str, Any]:
    """Wait only for local synthetic queue work."""
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        current = client.get(f"/api/jobs/{job['id']}").json()
        if current["finished"]:
            return dict(current)
        time.sleep(0.01)
    pytest.fail("synthetic import job did not finish")


def submit(client: TestClient, path: Path) -> dict[str, Any]:
    """Submit a folder import to the shared queue."""
    response = client.post("/api/local-studies", json={"path": str(path)})
    assert response.status_code == 202, response.text
    return dict(response.json()["job"])


def test_import_slice_analysis_and_private_local_summary(
    settings: Settings, tmp_path: Path
) -> None:
    folder = phantom(tmp_path / "external")
    with TestClient(api.create_app(settings)) as client:
        done = wait(client, submit(client, folder))
        assert done["status"] == "succeeded", done
        summary = done["result"]["study"]
        assert summary["phase"] == "local"
        assert summary["dataset"] == "local"
        assert summary["n_slices"] == 32
        assert done["models"] == []
        assert str(folder) not in str(done)
        assert "PRIVATE-PATIENT" not in str(done)
        listed = client.get("/api/studies").json()
        assert listed["summary"]["local_studies"] == 1
        assert listed["summary"]["development_studies"] == 0
        assert listed["studies"] == [summary]
        key = summary["case_id"]
        assert client.get(f"/api/studies/local/{key}/slice/0.png").content.startswith(b"\x89PNG")
        analyzed = client.post("/api/analyze", json={"dataset": "local", "case_id": key})
        assert analyzed.status_code == 200, analyzed.text
        assert "PRIVATE-PATIENT" not in analyzed.text
        assert str(folder) not in analyzed.text
        assert analyzed.json()["result"]["case_id"] == key
        assert (
            client.post(
                "/api/local-studies",
                json={"path": str(folder)},
                headers={"Origin": "https://evil.example"},
            ).status_code
            == 403
        )


def test_browse_bounded_and_refuses_relative(settings: Settings, tmp_path: Path) -> None:
    folder = tmp_path / "external"
    folder.mkdir()
    for number in range(205):
        (folder / f"folder-{number:03}").mkdir()
    (folder / "file.txt").write_text("not a directory")
    with TestClient(api.create_app(settings)) as client:
        assert client.get("/api/local-folders").json()["path"] == str(settings.data_dir)
        result = client.get("/api/local-folders", params={"path": str(folder)}).json()
        assert len(result["folders"]) == 200
        assert result["truncated"] is True
        assert result["parent"] == str(tmp_path)
        assert "disclaimer" in result
        for endpoint in ("/api/local-folders?path=relative",):
            assert client.get(endpoint).status_code == 403
        assert client.post("/api/local-studies", json={"path": "relative"}).status_code == 403
        assert client.post("/api/local-studies", json={"path": 42}).status_code == 422


def test_raw_browse_filters_before_probing_and_aliases(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    development, sealed = split(settings)
    raw = settings.data_path("raw", "toy")
    (raw / development).mkdir(parents=True)
    (raw / sealed).mkdir()
    (raw / "UNKNOWN").mkdir()
    settings.data_path("raw", "unregistered").mkdir()
    settings.data_path("sealed").mkdir(exist_ok=True)
    (tmp_path / "sealed-alias").symlink_to(settings.data_path("sealed"), target_is_directory=True)
    original = local_studies.os.scandir

    def checked(path: Any) -> Any:
        assert Path(path) not in {raw / sealed, raw / "UNKNOWN", settings.data_path("sealed")}
        return original(path)

    monkeypatch.setattr(local_studies.os, "scandir", checked)
    with TestClient(api.create_app(settings)) as client:
        listed = client.get("/api/local-folders", params={"path": str(raw)}).json()
        assert [entry["name"] for entry in listed["folders"]] == [development]
        assert (
            client.get("/api/local-folders", params={"path": str(raw / sealed)}).status_code == 403
        )
        assert (
            client.post("/api/local-studies", json={"path": str(raw / sealed)}).status_code == 403
        )
        assert (
            client.get(
                "/api/local-folders", params={"path": str(tmp_path / "sealed-alias")}
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/local-folders",
                params={"path": str(settings.data_path("raw", "unregistered"))},
            ).status_code
            == 403
        )
        assert client.post("/api/local-studies", json={"path": str(raw)}).status_code == 403


def test_copied_sealed_headers_fail_before_pixels(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, sealed = split(settings)
    folder = phantom(tmp_path / "copied", sealed)
    loader = Mock(side_effect=AssertionError("pixels must not load"))
    monkeypatch.setattr(api, "load_study_dir", loader)
    with TestClient(api.create_app(settings)) as client:
        done = wait(client, submit(client, folder))
        assert done["status"] == "failed"
        assert str(folder) not in str(done)
        assert sealed not in str(done)
        loader.assert_not_called()
        assert client.get("/api/studies").json()["studies"] == []


def test_invalid_folder_job_fails_cleanly(settings: Settings, tmp_path: Path) -> None:
    folder = tmp_path / "invalid"
    folder.mkdir()
    (folder / "readme.txt").write_text("no dicom")
    with TestClient(api.create_app(settings)) as client:
        done = wait(client, submit(client, folder))
        assert done["status"] == "failed"
        assert "Traceback" not in str(done)
        assert str(folder) not in str(done)


def test_source_mutation_during_load_is_not_registered(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = phantom(tmp_path / "mutating")
    original = api.load_study_dir

    def mutate(*args: Any, **kwargs: Any) -> Study:
        study = original(*args, **kwargs)
        (folder / "changed.txt").write_text("source changed during loading")
        return study

    monkeypatch.setattr(api, "load_study_dir", mutate)
    with TestClient(api.create_app(settings)) as client:
        assert wait(client, submit(client, folder))["status"] == "failed"
        assert client.get("/api/studies").json()["studies"] == []


def test_cached_source_replacement_is_guarded(settings: Settings, tmp_path: Path) -> None:
    folder = phantom(tmp_path / "selected")
    with TestClient(api.create_app(settings)) as client:
        done = wait(client, submit(client, folder))
        key = done["result"]["study"]["case_id"]
        folder.rename(tmp_path / "old")
        target = settings.data_path("sealed", "never-read")
        target.mkdir(parents=True)
        folder.symlink_to(target, target_is_directory=True)
        assert client.get(f"/api/studies/local/{key}/slice/0.png").status_code == 403
        assert (
            client.post("/api/analyze", json={"dataset": "local", "case_id": key}).status_code
            == 403
        )
        assert client.get("/api/studies").json()["studies"] == []


def test_import_uses_shared_queue_and_cancel_boundary(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = phantom(tmp_path / "first"), phantom(tmp_path / "second")
    entered, release = Event(), Event()
    original = api.load_study_dir

    def blocked(*args: Any, **kwargs: Any) -> Study:
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(api, "load_study_dir", blocked)
    with TestClient(api.create_app(settings)) as client:
        running = submit(client, first)
        assert entered.wait(5)
        try:
            queued = submit(client, second)
            assert client.get(f"/api/jobs/{queued['id']}").json()["queue_position"] == 1
            assert client.post(f"/api/jobs/{queued['id']}/cancel").json()["status"] == "cancelled"
            client.post(f"/api/jobs/{running['id']}/cancel")
        finally:
            release.set()
        assert wait(client, running)["status"] == "cancelled"
        assert client.get("/api/studies").json()["studies"] == []


def test_registered_source_identity_and_bounded_session(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    development, _ = split(settings)
    raw = phantom(settings.data_path("raw", "toy", development), development)
    outside = phantom(tmp_path / "outside")
    monkeypatch.setattr(local_studies, "MAX_LOCAL_STUDIES", 2)
    with TestClient(api.create_app(settings)) as client:
        first = wait(client, submit(client, raw))["result"]["study"]
        result = client.post("/api/analyze", json={"dataset": "local", "case_id": first["case_id"]})
        assert result.status_code == 200
        assert result.json()["result"]["dataset"] == "toy"
        assert result.json()["result"]["case_id"] == development
        wait(client, submit(client, outside))
        wait(client, submit(client, outside))
        assert client.get("/api/studies").json()["summary"]["local_studies"] == 2
        assert client.get(f"/api/studies/local/{first['case_id']}/slice/0.png").status_code == 403


def test_cached_headers_are_rechecked_before_pixels(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, sealed = split(settings)
    folder = phantom(tmp_path / "selected")
    with TestClient(api.create_app(settings)) as client:
        key = wait(client, submit(client, folder))["result"]["study"]["case_id"]
        replacement = phantom(tmp_path / "replacement", sealed)
        shutil.rmtree(folder)
        replacement.rename(folder)
        loader = Mock(side_effect=AssertionError("sealed pixels must not load"))
        monkeypatch.setattr(api, "load_study_dir", loader)
        assert client.get(f"/api/studies/local/{key}/slice/0.png").status_code == 403
        loader.assert_not_called()


def test_development_alias_cannot_escape_to_external_source(
    settings: Settings, tmp_path: Path
) -> None:
    development, _ = split(settings)
    outside = phantom(tmp_path / "outside", development)
    alias = settings.data_path("raw", "toy", development)
    alias.parent.mkdir(parents=True)
    alias.symlink_to(outside, target_is_directory=True)
    with TestClient(api.create_app(settings)) as client:
        assert client.post("/api/local-studies", json={"path": str(alias)}).status_code == 403
        assert client.get("/api/local-folders", params={"path": str(alias)}).status_code == 403


def test_changed_source_reloads_and_mutation_during_reload_is_rejected(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = phantom(tmp_path / "selected")
    with TestClient(api.create_app(settings)) as client:
        key = wait(client, submit(client, folder))["result"]["study"]["case_id"]
        marker = folder / "marker.txt"
        marker.write_text("first replacement")
        original = api.load_study_dir
        loader = Mock(wraps=original)
        monkeypatch.setattr(api, "load_study_dir", loader)
        assert client.get(f"/api/studies/local/{key}/slice/0.png").status_code == 200
        assert loader.call_count == 1
        assert client.get(f"/api/studies/local/{key}/slice/0.png").status_code == 200
        assert loader.call_count == 1  # unchanged source reuses pixels after header checks
        marker.write_text("second replacement")

        def mutate(*args: Any, **kwargs: Any) -> Study:
            study = original(*args, **kwargs)
            marker.write_text("changed while reloading")
            return study

        monkeypatch.setattr(api, "load_study_dir", mutate)
        assert client.get(f"/api/studies/local/{key}/slice/0.png").status_code == 403


def test_nested_alias_is_guarded_before_directory_traversal(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = phantom(tmp_path / "selected")
    hidden = settings.data_path("sealed", "sentinel")
    hidden.mkdir(parents=True)
    (folder / "alias").symlink_to(hidden, target_is_directory=True)
    loader = Mock(side_effect=AssertionError("must not load pixels"))
    monkeypatch.setattr(api, "load_study_dir", loader)
    original = Path.iterdir

    def checked(path: Path) -> Any:
        assert path.resolve() != hidden
        return original(path)

    monkeypatch.setattr(Path, "iterdir", checked)
    with TestClient(api.create_app(settings)) as client:
        assert wait(client, submit(client, folder))["status"] == "failed"
        loader.assert_not_called()
