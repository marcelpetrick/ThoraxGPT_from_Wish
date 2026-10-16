# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Read-only Evaluation API over synthetic, checkpointed benchmark runs in temporary dirs."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from thoraxbench.analysis import AnalysisResult, _check_image_evidence
from thoraxbench.api.app import create_app
from thoraxbench.api.evaluation import (
    REFERENCES_REMOVED,
    UNSUPPORTED_POSITIVE,
    Evaluation,
    evidence_verdict,
    presence,
)
from thoraxbench.benchmark import cohort
from thoraxbench.benchmark.checkpoint import BenchmarkStore, Checkpoint
from thoraxbench.config import Settings
from thoraxbench.schemas import Finding, FindingsReport
from thoraxbench.splits import SealedAccessError
from thoraxbench.synthetic_runs import SCRIPTED_NOTE, SEALED, SyntheticBenchmarks
from thoraxbench.synthetic_runs import build_synthetic_benchmarks as build

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory: pytest.TempPathFactory) -> SyntheticBenchmarks:
    return build(tmp_path_factory.mktemp("evaluation") / "root", ollama_url="http://127.0.0.1:1")


@pytest.fixture
def client(synthetic: SyntheticBenchmarks) -> TestClient:
    return TestClient(create_app(synthetic.settings))


def _ids(synthetic: SyntheticBenchmarks) -> list[tuple[str, str]]:
    return [(folder.parent.name, folder.name) for folder in synthetic.runs]


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(str(path.relative_to(root)).encode())
        if path.is_file() and not path.is_symlink():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def test_runs_list_summarizes_completed_runs(
    client: TestClient, synthetic: SyntheticBenchmarks
) -> None:
    body = client.get("/api/evaluation/runs").json()
    assert "never starts inference" in body["framing"]
    assert "not medical advice" in body["disclaimer"].lower()
    runs = {item["experiment"]: item for item in body["runs"]}
    assert set(runs) == {"SYNTH-E000", "SYNTH-E001"}
    vision = runs["SYNTH-E001"]
    assert vision["state"] == "complete"
    assert vision["run"] == synthetic.runs[1].name
    assert len(vision["config_sha256"]) == 64
    assert vision["started_at"].startswith(str(datetime.now(UTC).year))
    assert [item["variant"] for item in vision["variants"]] == ["q4-p2", "q8-p2"]
    assert vision["variants"][1]["status_counts"] == {
        "scored": 2,
        "abstained": 1,
        "failed": 1,
        "not_indexed": 1,
    }
    assert vision["status_counts"]["scored"] == 5
    assert vision["variants"][0]["prompt"] == "P2"
    assert runs["SYNTH-E000"]["variants"][0]["model"] == "heuristic-hu"
    assert body["runs"][0]["started_at"] >= body["runs"][1]["started_at"]
    assert SEALED not in json.dumps(body)


def test_run_cases_and_evidence_verdicts(
    client: TestClient, synthetic: SyntheticBenchmarks
) -> None:
    (baseline, vision) = _ids(synthetic)
    body = client.get(f"/api/evaluation/runs/{vision[0]}/{vision[1]}").json()
    rows = {(row["variant"], row["case_id"]): row for row in body["cases"]}
    assert len(rows) == 10
    assert body["skipped_non_development"] == 0
    assert rows["q4-p2", "SYNTH-P1"]["evidence"] == "valid_references"
    assert rows["q4-p2", "SYNTH-P1"]["sent_images"] == 4
    assert rows["q4-p2", "SYNTH-P1"]["reference"]["pulmonary_nodule"] is True
    assert rows["q4-p2", "SYNTH-P1"]["prediction"]["pulmonary_nodule"] == pytest.approx(0.82)
    assert rows["q4-p2", "SYNTH-P2"]["status"] == "abstained"
    assert rows["q4-p2", "SYNTH-P2"]["evidence"] == "abstained"
    assert rows["q4-p2", "SYNTH-P3"]["evidence"] == "unsupported_positive_removed"
    assert any(REFERENCES_REMOVED in item for item in rows["q4-p2", "SYNTH-P3"]["warnings"])
    assert rows["q4-p2", "SYNTH-P4"]["evidence"] == "no_positive_findings"
    assert rows["q8-p2", "SYNTH-P4"]["status"] == "failed"
    assert rows["q8-p2", "SYNTH-P4"]["evidence"] == "not_run"
    assert "no model ran" in rows["q8-p2", "SYNTH-P4"]["error"]
    assert rows["q4-p2", "SYNTH-P5"]["status"] == "not_indexed"
    assert {row["phase"] for row in body["cases"]} <= {"calibration", "internal_test"}
    heuristic = client.get(f"/api/evaluation/runs/{baseline[0]}/{baseline[1]}").json()
    assert {row["evidence"] for row in heuristic["cases"]} == {"source_slices_only", "not_run"}
    assert SEALED not in json.dumps(body) + json.dumps(heuristic)


def test_case_detail_returns_stored_response_without_identifiers(
    client: TestClient, synthetic: SyntheticBenchmarks
) -> None:
    (baseline, vision) = _ids(synthetic)
    base = f"/api/evaluation/runs/{vision[0]}/{vision[1]}/cases"
    detail = client.get(f"{base}/q4-p2/lidc_idri/SYNTH-P3").json()
    assert detail["prompt"] == "P2"
    assert detail["requested_labels"] == ["pulmonary_nodule", "pulmonary_mass"]
    assert detail["images"] == {
        "stored": False,
        "sent_count": 4,
        "captions": [
            f"Image {n}: synthetic axial slice {n * 8} (lung window)" for n in range(1, 5)
        ],
        "source_slice_indices": [8, 16, 24, 32],
    }
    assert SCRIPTED_NOTE in detail["response"]["raw_text"]
    assert (
        '"evidence_images": [\n        2,\n        2,\n        7\n      ]'
        in (detail["response"]["raw_text"])
    )
    findings = {item["label"]: item for item in detail["findings"]}
    assert findings["pulmonary_nodule"]["evidence_images"] == [2]
    assert findings["pulmonary_nodule"]["in_range"] is True
    assert findings["pulmonary_nodule"]["evidence_kind"] == "model_images"
    assert findings["pulmonary_mass"]["presence"] == "unavailable"
    assert detail["response"]["parsed"]["findings"][1]["present"] is None
    serialized = json.dumps(detail)
    assert "patient_id" not in serialized
    assert "series_uid" not in serialized
    failed = client.get(f"{base}/q8-p2/lidc_idri/SYNTH-P4").json()
    assert failed["response"] is None
    assert failed["images"]["sent_count"] is None
    heuristic = client.get(
        f"/api/evaluation/runs/{baseline[0]}/{baseline[1]}/cases/base/lidc_idri/SYNTH-P1"
    ).json()
    assert heuristic["images"]["sent_count"] == 0
    assert all(item["evidence_kind"] == "source_slices" for item in heuristic["findings"])
    assert all(item["in_range"] is None for item in heuristic["findings"])
    assert client.get(f"{base}/q4-p2/lidc_idri/{SEALED}").status_code == 404
    assert client.get(f"{base}/missing/lidc_idri/SYNTH-P1").status_code == 404


def test_compare_uses_existing_descriptive_comparison(
    client: TestClient, synthetic: SyntheticBenchmarks
) -> None:
    (baseline, vision) = _ids(synthetic)
    one = client.get("/api/evaluation/compare", params={"run": "/".join(vision)}).json()
    assert [item["variant"] for item in one["setups"]] == ["q4-p2", "q8-p2"]
    (pair,) = one["comparisons"]
    assert (pair["left"], pair["right"]) == ("S1", "S2")
    assert pair["experimental_factors"]["model_or_prompt_or_view"] is True
    assert "actual model weight identity unavailable" in pair["differences"]
    both = client.get(
        "/api/evaluation/compare", params=[("run", "/".join(baseline)), ("run", "/".join(vision))]
    ).json()
    assert [item["id"] for item in both["setups"]] == ["S1", "S2", "S3"]
    assert len(both["comparisons"]) == 3
    assert "not clinical accuracy" in both["framing"]
    assert client.get("/api/evaluation/compare").status_code == 422
    duplicate = [("run", "/".join(vision))] * 2
    assert client.get("/api/evaluation/compare", params=duplicate).status_code == 422
    assert client.get("/api/evaluation/compare", params={"run": "nosep"}).status_code == 422
    unknown = {"run": "SYNTH-E001/absent"}
    assert client.get("/api/evaluation/compare", params=unknown).status_code == 404
    many = [("run", f"SYNTH-E001/run{index}") for index in range(9)]
    assert client.get("/api/evaluation/compare", params=many).status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/api/evaluation/runs/../SYNTH-E001",
        "/api/evaluation/runs/SYNTH-E001/..",
        "/api/evaluation/runs/SYNTH-E001/%2E%2E",
        "/api/evaluation/runs/.hidden/run",
        "/api/evaluation/runs/SYNTH-E001/run%2F..",
        "/api/evaluation/runs/SYNTH-E001/x/cases/q4-p2/lidc_idri/..",
    ],
)
def test_traversal_components_are_refused(client: TestClient, path: str) -> None:
    response = client.get(path)
    # Dot segments may be normalized to the runs list; they never reach a run or case.
    assert response.status_code in {404, 422} or set(response.json()) == {
        "runs",
        "ignored_entries",
        "framing",
        "disclaimer",
    }


def test_symlinks_incomplete_and_legacy_runs_stay_closed(
    synthetic: SyntheticBenchmarks, tmp_path: Path
) -> None:
    settings = synthetic.settings
    root = settings.data_path("results", "benchmark")
    outside = tmp_path / "outside"
    shutil.copytree(synthetic.runs[1], outside / "copied")
    (root / "LINKED").symlink_to(outside, target_is_directory=True)
    (root / "SYNTH-E001" / "linked-run").symlink_to(outside / "copied", target_is_directory=True)
    legacy = root / "LEGACY" / "20250101T000000Z-legacy"
    legacy.mkdir(parents=True)
    (legacy / "result.json").write_text("{}", encoding="utf-8")
    running = root / "PARTIAL" / "20991231T000000.000000Z-0123456789ab-feed"
    running.mkdir(parents=True)
    store = BenchmarkStore(running, settings)
    store.state = Checkpoint(identity_sha256="synthetic", started_at="2099-12-31T00:00:00+00:00")
    store.save()
    try:
        client = TestClient(create_app(settings))
        body = client.get("/api/evaluation/runs").json()
        listed = {(item["experiment"], item["run"]): item for item in body["runs"]}
        assert body["ignored_entries"] == 2
        assert all(experiment != "LINKED" for experiment, _ in listed)
        assert ("SYNTH-E001", "linked-run") not in listed
        assert listed["LEGACY", legacy.name]["state"] == "unavailable"
        partial = listed["PARTIAL", running.name]
        assert (partial["state"], partial["completed_units"]) == ("incomplete", 0)
        assert partial["config_sha256"] == "0123456789ab"
        assert client.get("/api/evaluation/runs/LINKED/copied").status_code == 404
        assert client.get("/api/evaluation/runs/SYNTH-E001/linked-run").status_code == 404
        assert client.get(f"/api/evaluation/runs/LEGACY/{legacy.name}").status_code == 409
        assert client.get(f"/api/evaluation/runs/PARTIAL/{running.name}").status_code == 409
    finally:
        (root / "LINKED").unlink()
        (root / "SYNTH-E001" / "linked-run").unlink()
        shutil.rmtree(root / "LEGACY")
        shutil.rmtree(root / "PARTIAL")


def test_guard_refusal_is_explicit(
    synthetic: SyntheticBenchmarks, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise SealedAccessError("synthetic refusal")

    monkeypatch.setattr(cohort.CaseGuard, "check", refuse)
    client = TestClient(create_app(synthetic.settings))
    body = client.get("/api/evaluation/runs").json()
    assert {item["state"] for item in body["runs"]} == {"refused"}
    assert all("development split guard" in item["detail"] for item in body["runs"])
    (experiment, run) = _ids(synthetic)[0]
    response = client.get(f"/api/evaluation/runs/{experiment}/{run}")
    assert response.status_code == 403
    assert "synthetic refusal" not in response.text


def test_evaluation_is_read_only_and_cached(synthetic: SyntheticBenchmarks) -> None:
    before = _tree_digest(synthetic.settings.data_dir)
    client = TestClient(create_app(synthetic.settings))
    (baseline, vision) = _ids(synthetic)
    for path in [
        "/api/evaluation/runs",
        f"/api/evaluation/runs/{vision[0]}/{vision[1]}",
        f"/api/evaluation/runs/{vision[0]}/{vision[1]}/cases/q4-p2/lidc_idri/SYNTH-P1",
        f"/api/evaluation/compare?run={baseline[0]}/{baseline[1]}&run={vision[0]}/{vision[1]}",
    ]:
        assert client.get(path).status_code == 200
    assert _tree_digest(synthetic.settings.data_dir) == before
    service = Evaluation(synthetic.settings)
    first = service.run(*vision)
    assert service.run(*vision) == first


def test_non_development_rows_are_skipped_and_counted(
    synthetic: SyntheticBenchmarks, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = cohort.load_completed_run

    def tampered(folder: Path, settings: Settings) -> cohort.CompletedRun:
        source = original(folder, settings)
        source.result.runs[0].cases[0].phase = "sealed"
        return source

    monkeypatch.setattr("thoraxbench.api.evaluation.load_completed_run", tampered)
    body = Evaluation(synthetic.settings).run(*_ids(synthetic)[1])
    assert body["skipped_non_development"] == 1
    assert len(body["cases"]) == 9


def _analysis(report: FindingsReport, images: int, *, error: str | None = None) -> AnalysisResult:
    return AnalysisResult.model_validate(
        {
            "dataset": "synthetic",
            "case_id": "c",
            "patient_id": "p",
            "series_uid": "1",
            "model_id": "m",
            "request": {},
            "report": report.model_dump(),
            "raw_text": "",
            "raw_error": error,
            "perf": {"total_s": 0.0, "n_images": images},
            "provenance": {"model_id": "m"},
        }
    )


def test_evidence_verdict_matches_engine_wording() -> None:
    report = FindingsReport(
        findings=[
            Finding(label="a", present=True, confidence=0.9, evidence_images=[1, 9]),
            Finding(label="b", present=True, confidence=0.8),
        ]
    )
    _check_image_evidence(report, 3, required=True)
    assert any(REFERENCES_REMOVED in item for item in report.parse_warnings)
    assert any(UNSUPPORTED_POSITIVE in item for item in report.parse_warnings)
    assert evidence_verdict(_analysis(report, 3)) == "unsupported_positive_removed"
    removed = FindingsReport(
        findings=[Finding(label="a", present=True, confidence=0.9, evidence_images=[1, 1])]
    )
    _check_image_evidence(removed, 3, required=False)
    assert evidence_verdict(_analysis(removed, 3)) == "invalid_references_removed"
    missing = FindingsReport(findings=[Finding(label="a", present=True, confidence=0.9)])
    assert evidence_verdict(_analysis(missing, 3)) == "missing_references"
    assert evidence_verdict(_analysis(missing, 3, error="boom")) == "abstained"
    assert evidence_verdict(_analysis(missing, 0)) == "source_slices_only"
    assert evidence_verdict(None) == "not_run"
    assert (presence(None), presence(0.5), presence(0.49)) == ("unavailable", "present", "absent")


def test_missing_results_directory_lists_nothing(tmp_path: Path) -> None:
    settings = Settings(repo_root=tmp_path / "repo", data_dir=tmp_path / "data")
    assert Evaluation(settings).runs()["runs"] == []
    with pytest.raises(Exception, match="Unknown benchmark run"):
        Evaluation(settings).run("SYNTH-E000", "absent")


def test_builder_refuses_the_repository_checkout() -> None:
    from thoraxbench.config import REPO_ROOT

    with pytest.raises(ValueError, match="outside the repository"):
        build(REPO_ROOT / "data" / "never-created")
