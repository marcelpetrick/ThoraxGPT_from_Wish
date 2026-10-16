# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Local API integration through synthetic studies only; sealed images stay unopened."""

import json
import shutil
from email.message import Message
from importlib import metadata
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from thoraxbench.analysis import AnalysisResult
from thoraxbench.api import app as api
from thoraxbench.api.licenses import runtime_libraries
from thoraxbench.cli import main as cli
from thoraxbench.config import Settings
from thoraxbench.index import IndexEntry
from thoraxbench.schemas import ReferenceLabels
from thoraxbench.splits import CaseRecord, Phase, make_split, save_split
from thoraxbench.study import load_study_dir
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    shutil.copytree(Settings().configs_dir, tmp_path / "configs")
    return Settings(repo_root=tmp_path, data_dir=tmp_path / "data")


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(api.create_app(settings))


def test_demo_slices_analysis_and_downloads(client: TestClient) -> None:
    assert client.get("/api/studies").json()["studies"] == []
    assert client.get("/api/studies/demo/phantom/slice/0.png").status_code == 404
    response = client.post("/api/demo", headers={"Origin": "http://testserver"})
    assert response.status_code == 200
    assert response.json()["studies"] == [
        {
            "dataset": "demo",
            "case_id": "phantom",
            "n_slices": 64,
            "phase": "synthetic",
            "qc_adequate": True,
        }
    ]
    assert client.post("/api/demo").status_code == 200
    for window in ("lung", "mediastinum", "medgemma", "bone", "abdomen"):
        image = client.get(f"/api/studies/demo/phantom/slice/22.png?window={window}")
        assert image.status_code == 200
        assert image.content.startswith(b"\x89PNG")
        assert image.headers["cache-control"] == "no-store"
    assert client.get("/api/studies/demo/phantom/slice/64.png").status_code == 422
    assert client.get("/api/studies/demo/phantom/slice/0.png?window=nope").status_code == 422
    result = client.post("/api/analyze", json={"dataset": "demo", "case_id": "phantom"})
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["result"]["report"]["abstain"] is False
    assert body["presentation"]["educational_only"] is True
    assert any(row["severity"] is not None for row in body["presentation"]["findings"])
    assert "Pulmonary nodule" in body["markdown"]
    assert "not medical advice" in body["markdown"]
    saved = client.get(body["downloads"]["json"])
    assert saved.json() == body["result"]
    assert "attachment" in saved.headers["content-disposition"]
    assert client.get(body["downloads"]["markdown"]).text == body["markdown"]
    html = client.get(body["downloads"]["html"])
    assert html.status_code == 200
    assert html.headers["content-type"].startswith("text/html")
    assert "data:image/png;base64," in html.text
    assert "Source slice index" in html.text
    assert "prepared_images" not in saved.json()
    assert client.get(f"/api/results/{uuid4()}/json").status_code == 404
    assert client.get(f"/api/results/{body['id']}/other").status_code == 404
    assert client.get("/api/results/not-a-uuid/json").status_code == 422


@pytest.mark.parametrize(
    "host", ["remote.example", "192.168.1.2", "localhost:bad", "user@localhost", "localhost/path"]
)
def test_remote_hosts_rejected(client: TestClient, host: str) -> None:
    assert client.get("/api/studies", headers={"host": host}).status_code == 403


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:8000", "[::1]:8000"])
def test_loopback_hosts_allowed(client: TestClient, host: str) -> None:
    assert client.get("/api/studies", headers={"host": host}).status_code == 200


def test_cross_origin_writes_rejected(client: TestClient, settings: Settings) -> None:
    assert client.post("/api/demo", headers={"origin": "https://remote.example"}).status_code == 403
    assert client.post("/api/demo", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert not settings.data_path("demo", "ui").exists()


def test_invalid_analysis_requests(client: TestClient) -> None:
    for extra in (
        {"n_images": 0},
        {"n_images": 17},
        {"model_id": "../../secret"},
        {"dataset": "../../raw"},
    ):
        body = {"dataset": "demo", "case_id": "phantom"} | extra
        assert client.post("/api/analyze", json=body).status_code == 422
    assert (
        client.post(
            "/api/analyze", json={"dataset": "demo", "case_id": "phantom", "model_id": "missing"}
        ).status_code
        == 422
    )
    assert client.get("/api/studies/unknown/case/slice/0.png").status_code == 404


@respx.mock
def test_models_probe_ollama_once_and_never_services(
    client: TestClient, settings: Settings
) -> None:
    respx.route(path="/health").mock(return_value=httpx.Response(503))
    tags = respx.get(f"{settings.ollama_url}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "medgemma1.5:4b-it-q4_K_M"}]})
    )
    response = client.get("/api/models")
    assert tags.call_count == 1
    models = {item["id"]: item for item in response.json()["models"]}
    assert models["medgemma1.5-q4"]["available"]
    assert models["heuristic-hu"]["available"]
    assert models["heuristic-hu"]["recommended"]
    assert models["medgemma1.5-q4"]["recommended"]
    assert not models["ct-clip"]["available"]
    assert not models["ct-clip"]["recommended"]
    tags.mock(side_effect=httpx.ConnectError("down"))
    assert client.get("/api/models").status_code == 200


@pytest.mark.parametrize("payload", [None, [], {"models": None}, {"models": [None, {}, 7]}])
@respx.mock
def test_malformed_model_inventory_is_unavailable(
    client: TestClient, settings: Settings, payload: object
) -> None:
    respx.route(path="/health").mock(return_value=httpx.Response(503))
    respx.get(f"{settings.ollama_url}/api/tags").mock(
        return_value=httpx.Response(200, json=payload)
    )
    response = client.get("/api/models")
    assert response.status_code == 200
    assert not any(
        item["available"] for item in response.json()["models"] if item["adapter"] != "heuristic"
    )


def test_result_outputs_reject_symlink_escape(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    client.post("/api/demo")
    outside = tmp_path / "outside"
    outside.mkdir()
    settings.data_path("results").symlink_to(outside, target_is_directory=True)
    response = client.post("/api/analyze", json={"dataset": "demo", "case_id": "phantom"})
    assert response.status_code == 403
    assert list(outside.iterdir()) == []


def test_download_rechecks_output_path_and_missing_files(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    client.post("/api/demo")
    result = client.post("/api/analyze", json={"dataset": "demo", "case_id": "phantom"}).json()
    path = settings.data_path("results", "ui", result["id"], "report.html")
    path.unlink()
    assert client.get(result["downloads"]["html"]).status_code == 404
    outside = tmp_path / "outside.html"
    outside.write_text("private")
    path.symlink_to(outside)
    assert client.get(result["downloads"]["html"]).status_code == 404


def test_about_reports_installed_runtime_libraries(client: TestClient) -> None:
    data = client.get("/api/about").json()
    assert data["author"] == "Marcel Petrick"
    assert data["email"] == "mail@marcelpetrick.it"
    assert data["license"] == "GPL-3.0-or-later"
    assert "not medical advice" in data["disclaimer"]
    names = {item["name"].lower() for item in data["libraries"]}
    assert {"fastapi", "numpy", "starlette", "pydantic"} <= names
    assert all(item["license"] and item["version"] for item in data["libraries"])


def test_pages_use_shared_template(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Use a tiny template independently of frontend styling/markup changes.
    assets = tmp_path / "assets"
    (assets / "templates").mkdir(parents=True)
    (assets / "templates" / "index.html").write_text("Research use only {{ active_page }}")
    monkeypatch.setattr(api, "ASSETS", assets)
    isolated = TestClient(api.create_app())
    assert isolated.get("/").text == "Research use only analysis"
    assert isolated.get("/about").text == "Research use only about"


def test_only_indexed_development_studies_can_open(settings: Settings) -> None:
    records = [
        CaseRecord(dataset="lidc_idri", patient_id=f"P{i}", case_id=f"P{i}") for i in range(10)
    ]
    split = make_split(records, "lidc_idri")
    save_split(split, settings.data_dir, settings.manifests_dir)
    case = split.cases(Phase.DEVELOPMENT)[0]
    spec = PhantomSpec()
    folder = settings.data_path("raw", "lidc_idri", case)
    write_dicom_series(make_phantom(spec), folder, spec.spacing_mm, patient_id=case)
    study = load_study_dir(folder, dataset="lidc_idri", case_id=case)
    entry = IndexEntry(
        dataset="lidc_idri",
        case_id=case,
        patient_id=case,
        series_uid=study.volume.series_uid,
        path=f"raw/lidc_idri/{case}",
        stratum="all",
        n_slices=64,
        spacing_mm=spec.spacing_mm,
        qc_adequate=True,
        qc_limitations=[],
        reference=ReferenceLabels(
            dataset="lidc_idri", patient_id=case, study_uid=study.volume.study_uid
        ),
        cues=study.cues,
    )
    index = settings.data_path("index", "lidc_idri.json")
    index.parent.mkdir(parents=True)
    index.write_text(json.dumps([entry.model_dump(mode="json")]))
    client = TestClient(api.create_app(settings))
    inventory = client.get("/api/studies").json()
    listed = inventory["studies"]
    assert inventory["summary"]["development_studies"] == 1
    assert next(row for row in inventory["libraries"] if row["dataset"] == "lidc_idri") == {
        "dataset": "lidc_idri",
        "status": "ready",
        "available_studies": 1,
    }
    assert len(listed) == 1
    assert listed[0]["case_id"] == case
    for _ in range(2):
        assert client.get(f"/api/studies/lidc_idri/{case}/slice/0.png").status_code == 200
    # These IDs come from in-memory synthetic split creation, never from sealed file reads.
    sealed = split.cases(Phase.SEALED)[0]
    assert client.get(f"/api/studies/lidc_idri/{sealed}/slice/0.png").status_code == 403
    assert client.get("/api/studies/lidc_idri/missing/slice/0.png").status_code == 403


def test_analysis_setup_failure_is_inspectable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/api/demo")
    monkeypatch.setattr(api, "analyze_study", Mock(side_effect=ValueError("bad config")))
    response = client.post("/api/analyze", json={"dataset": "demo", "case_id": "phantom"})
    assert response.status_code == 422
    assert "configuration" in response.json()["detail"]


def test_demo_rejects_symlink_and_invalid_dicom(settings: Settings, tmp_path: Path) -> None:
    demo = settings.data_path("demo", "ui")
    demo.parent.mkdir(parents=True)
    demo.symlink_to(tmp_path, target_is_directory=True)
    client = TestClient(api.create_app(settings))
    assert client.post("/api/demo").status_code == 404
    demo.unlink()
    demo.mkdir()
    (demo / "bad.txt").write_text("not dicom")
    assert client.post("/api/demo").status_code == 403
    (demo / "bad.txt").unlink()
    demo.rmdir()
    demo.parent.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    demo.parent.symlink_to(outside, target_is_directory=True)
    assert client.post("/api/demo").status_code == 404
    assert not (outside / "ui").exists()


def test_runtime_library_metadata_traversal(monkeypatch: pytest.MonkeyPatch) -> None:
    def package(name: str) -> Message:
        if name == "missing":
            raise metadata.PackageNotFoundError(name)
        info = Message()
        info["Name"], info["Version"] = name, "1.0"
        if name == "thoraxbench":
            for requirement in ("a==1", "b==1", "missing", "ignored; extra == 'test'"):
                info["Requires-Dist"] = requirement
        elif name == "a":
            info["Requires-Dist"] = "b==1"
            info["License-Expression"] = "MIT"
        else:
            info["Classifier"] = "License :: OSI Approved :: BSD License"
        return info

    monkeypatch.setattr(metadata, "metadata", package)
    assert runtime_libraries() == [
        {"name": "a", "version": "1.0", "license": "MIT"},
        {"name": "b", "version": "1.0", "license": "BSD License"},
    ]


def test_cli_serve_binds_only_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    run = Mock()
    monkeypatch.setattr(uvicorn, "run", run)
    result = CliRunner().invoke(cli.app, ["serve", "--port", "8765"])
    assert result.exit_code == 0, result.output
    assert "http://127.0.0.1:8765" in result.output
    assert run.call_args.kwargs == {"host": "127.0.0.1", "port": 8765, "proxy_headers": False}
    assert CliRunner().invoke(cli.app, ["serve", "--host", "192.168.1.2"]).exit_code != 0


def test_comparison_export_includes_completed_abstained_and_skipped_models(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/api/demo")
    first = client.post("/api/analyze", json={"dataset": "demo", "case_id": "phantom"}).json()
    abstained = AnalysisResult.model_validate(first["result"])
    abstained.model_id = "medgemma1.5-q4"
    abstained.report.abstain = True
    abstained.raw_error = "<script>offline</script>"
    monkeypatch.setattr(api, "analyze_study", Mock(return_value=abstained))
    second = client.post("/api/analyze", json={"dataset": "demo", "case_id": "phantom"}).json()
    response = client.post(
        "/api/compare",
        json={
            "result_ids": [first["id"], second["id"]],
            "omissions": [
                {"model_id": "gemma3-4b", "status": "skipped", "detail": "Not installed"}
            ],
        },
    )
    assert response.status_code == 200, response.text
    html = client.get(response.json()["downloads"]["html"]).text
    assert "Findings across models" in html
    assert "not directly comparable" in html
    assert "Unavailable — abstention or model error" in html
    assert "Not installed" in html
    assert "iframe sandbox" in html
    assert "<script>offline</script>" not in html
    assert client.get(f"/api/results/{response.json()['id']}/json").status_code == 404
    single = client.post("/api/compare", json={"result_ids": [first["id"], first["id"]]}).json()
    assert "Only one completed run" in client.get(single["downloads"]["html"]).text
    abstained.case_id = "another-study"
    third = client.post("/api/analyze", json={"dataset": "demo", "case_id": "phantom"}).json()
    assert (
        client.post("/api/compare", json={"result_ids": [first["id"], third["id"]]}).status_code
        == 422
    )


def test_comparison_rejects_invalid_missing_and_escaped_results(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    for payload in (
        {"result_ids": []},
        {"result_ids": ["not-uuid"]},
        {"result_ids": [str(uuid4())] * 9},
    ):
        assert client.post("/api/compare", json=payload).status_code == 422
    assert client.post("/api/compare", json={"result_ids": [str(uuid4())]}).status_code == 404
    client.post("/api/demo")
    result = client.post("/api/analyze", json={"dataset": "demo", "case_id": "phantom"}).json()
    path = settings.data_path("results", "ui", result["id"], "report.html")
    path.unlink()
    path.symlink_to(tmp_path / "outside.html")
    assert client.post("/api/compare", json={"result_ids": [result["id"]]}).status_code == 404


def test_pull_requires_known_configured_ollama_model_and_explicit_terms(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from thoraxbench.api import model_pulls

    monkeypatch.setattr(model_pulls, "Thread", Mock())
    for body in (
        {},
        {"terms_acknowledged": False},
        {"terms_acknowledged": 1},
        {"terms_acknowledged": True, "tag": "arbitrary"},
    ):
        assert client.post("/api/models/gemma3-4b/pull", json=body).status_code == 422
    assert (
        client.post("/api/models/missing/pull", json={"terms_acknowledged": True}).status_code
        == 404
    )
    assert (
        client.post("/api/models/ct-clip/pull", json={"terms_acknowledged": True}).status_code
        == 422
    )
    response = client.post("/api/models/gemma3-4b/pull", json={"terms_acknowledged": True})
    assert response.status_code == 200
    job = response.json()
    assert job["status"] == "queued"
    assert client.get(f"/api/model-pulls/{job['id']}").json() == job
    assert (
        client.post("/api/models/gemma3-4b/pull", json={"terms_acknowledged": True}).status_code
        == 409
    )
    assert client.get(f"/api/model-pulls/{uuid4()}").status_code == 404


@pytest.mark.parametrize(
    ("payload", "available"),
    [({"status": "ok"}, True), ({"status": "loading"}, False), ([], False), (None, False)],
)
@respx.mock
def test_service_inventory_checks_configured_loopback_health(
    client: TestClient, settings: Settings, payload: object, available: bool
) -> None:
    respx.get(f"{settings.ollama_url}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    health = respx.get(f"{settings.service_urls['ct_clip']}/health").mock(
        return_value=httpx.Response(200, json=payload)
    )
    respx.route(path="/health").mock(return_value=httpx.Response(503))
    models = {item["id"]: item for item in client.get("/api/models").json()["models"]}
    assert models["ct-clip"]["available"] is available
    assert health.call_count == 1
    assert not models["ct-clip"]["download_supported"]
    assert models["gemma3-4b"]["download_supported"]
    assert models["gemma3-4b"]["terms_url"]
    assert models["gemma3-4b"]["source_url"].startswith("https://ollama.com/library/")


@respx.mock
def test_service_inventory_and_pull_reject_non_loopback(settings: Settings) -> None:
    settings.service_urls["ct_clip"] = "https://remote.example"
    settings = Settings(
        repo_root=settings.repo_root,
        data_dir=settings.data_dir,
        ollama_url="https://remote.example",
        service_urls=settings.service_urls,
    )
    respx.route(path="/health").mock(return_value=httpx.Response(503))
    client = TestClient(api.create_app(settings))
    models = {item["id"]: item for item in client.get("/api/models").json()["models"]}
    assert not models["ct-clip"]["available"]
    assert (
        client.post("/api/models/gemma3-4b/pull", json={"terms_acknowledged": True}).status_code
        == 422
    )


def test_library_status_explains_missing_and_unavailable_sources(settings: Settings) -> None:
    client = TestClient(api.create_app(settings))
    payload = client.get("/api/studies").json()
    assert payload["summary"] == {
        "total_studies": 0,
        "development_studies": 0,
        "synthetic_studies": 0,
    }
    assert all(row["status"] == "split_required" for row in payload["libraries"])
    split = make_split(
        [CaseRecord(dataset="lidc_idri", patient_id=f"P{i}", case_id=f"P{i}") for i in range(5)],
        "lidc_idri",
    )
    save_split(split, settings.data_dir, settings.manifests_dir)
    payload = client.get("/api/studies").json()
    assert (
        next(row for row in payload["libraries"] if row["dataset"] == "lidc_idri")["status"]
        == "not_indexed"
    )
    index = settings.data_path("index", "lidc_idri.json")
    index.parent.mkdir(parents=True)
    index.write_text("malformed index")
    payload = client.get("/api/studies").json()
    assert (
        next(row for row in payload["libraries"] if row["dataset"] == "lidc_idri")["status"]
        == "unavailable"
    )
    assert str(settings.data_dir) not in json.dumps(payload)
