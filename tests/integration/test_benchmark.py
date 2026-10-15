# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Benchmark runner and CLI over a synthetic, split-guarded, indexed data directory."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

import thoraxbench.cli.benchmark as cli_benchmark
import thoraxbench.splits.guard as guard_module
from thoraxbench.analysis import AnalysisResult, analyze_study
from thoraxbench.benchmark import CaseStatus, load_experiment, run_experiment, write_outputs
from thoraxbench.cli.main import app
from thoraxbench.config import REPO_ROOT, Settings
from thoraxbench.dicom import discover_series
from thoraxbench.index import IndexEntry, build_index, index_path, open_study
from thoraxbench.splits import CaseRecord, Phase, SealedAccessError, make_split, save_split
from thoraxbench.study import Study, StudyLoadError
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series

pytestmark = pytest.mark.integration

NODULE = """<unblindedReadNodule><noduleID>1</noduleID><roi><imageZposition>0.0</imageZposition>
<inclusion>TRUE</inclusion><edgeMap><xCoord>40</xCoord><yCoord>40</yCoord></edgeMap>
<edgeMap><xCoord>44</xCoord><yCoord>40</yCoord></edgeMap></roi></unblindedReadNodule>"""
XML = '<?xml version="1.0"?><LidcReadMessage xmlns="http://www.nih.gov"><readingSession>{}</readingSession></LidcReadMessage>'
DEV = ("P1", "P2", "P3")


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Three development LIDC-like patients plus one sealed patient, indexed."""
    root = tmp_path_factory.mktemp("bench")
    spec = PhantomSpec(shape=(40, 64, 64), spacing_mm=(5.0, 5.0, 5.0), nodule_radius_mm=8.0)
    hu = make_phantom(spec)
    xml_dir = root / "raw" / "lidc_idri" / "_labels" / "xml_selected"
    xml_dir.mkdir(parents=True)
    for pid in DEV:
        staging = write_dicom_series(
            hu, root / "staging" / pid, spec.spacing_mm, patient_id=pid, include_scout=False
        )
        series = discover_series(staging)[0]
        (root / "raw" / "lidc_idri" / pid).mkdir(parents=True)
        staging.rename(root / "raw" / "lidc_idri" / pid / series.series_uid)
        (xml_dir / f"{series.series_uid}.xml").write_text(XML.format(NODULE if pid == "P1" else ""))
    (root / "raw" / "lidc_idri" / "SEALED").mkdir()
    repo = root / "repo"
    repo.mkdir()
    (repo / "configs").symlink_to(REPO_ROOT / "configs", target_is_directory=True)
    records = [
        CaseRecord(dataset="lidc_idri", patient_id=pid, case_id=pid) for pid in (*DEV, "SEALED")
    ]
    for seed in range(200):
        split = make_split(records, "lidc_idri", salt=f"bench-{seed}")
        if split.cases(Phase.SEALED) == ["SEALED"] and split.cases(Phase.INTERNAL_TEST):
            break
    assert split.cases(Phase.SEALED) == ["SEALED"]
    save_split(split, root, repo / "manifests")
    settings = Settings(repo_root=repo, data_dir=root)
    entries = build_index("lidc_idri", settings)
    assert [e.case_id for e in entries] == list(DEV)
    return root


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(repo_root=data_dir / "repo", data_dir=data_dir)


@pytest.fixture
def stale_index(settings: Settings) -> Iterator[Path]:
    """Index with an extra entry that is not in the development split; restored afterwards."""
    path = index_path(settings, "lidc_idri")
    original = path.read_text(encoding="utf-8")
    data = json.loads(original)
    data.append(data[0] | {"case_id": "SEALED", "patient_id": "SEALED", "path": "raw/x/SEALED"})
    data = [e for e in data if e["case_id"] != "P3"]
    path.write_text(json.dumps(data), encoding="utf-8")
    yield path
    path.write_text(original, encoding="utf-8")


def _experiment(tmp_path: Path, **extra: Any) -> Path:
    data = {
        "id": "T001",
        "title": "synthetic",
        "model": "heuristic-hu",
        "datasets": ["lidc_idri"],
        "labels": ["pulmonary_nodule", "pulmonary_mass"],
        "n_boot": 50,
    } | extra
    path = tmp_path / "T001.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_full_run_scores_and_writes(tmp_path: Path, settings: Settings) -> None:
    loaded = load_experiment(_experiment(tmp_path))
    messages: list[str] = []
    result = run_experiment(loaded, settings, progress=messages.append)
    (run,) = result.runs
    assert run.status_counts == {"scored": 3, "abstained": 0, "failed": 0, "not_indexed": 0}
    assert [c.case_id for c in run.cases] == list(DEV)
    assert {c.patient_id for c in run.cases} == set(DEV)
    truth = {c.case_id: c.y_true["pulmonary_nodule"] for c in run.cases}
    assert truth == {"P1": True, "P2": False, "P3": False}
    assert all(c.y_score["pulmonary_nodule"] is not None for c in run.cases)
    nodule = run.metrics["task_a"]["per_label"]["pulmonary_nodule"]
    assert (nodule["n"], nodule["n_positive"]) == (3, 1)
    assert run.metrics["n_scored"] == 3
    assert run.metrics["task_g"]["abstention_rate"] == 0.0
    assert run.provenance.config_hash == loaded.file_sha256
    assert run.provenance.model_id == "heuristic-hu"
    assert run.provenance.preprocess_hash is not None
    assert run.provenance.split_manifest_hash is not None
    assert sum(sum(v.values()) for v in run.phase_counts.values()) == 3
    (summary,) = result.datasets
    assert (summary.development_cases, summary.selected_cases, summary.not_indexed) == (3, 3, 0)
    assert summary.split_manifest_sha256 is not None
    assert summary.dataset_manifest_sha256 is None
    assert len(messages) == 3
    json_path, md_path = write_outputs(result, settings)
    assert json_path == settings.data_path("results", "benchmark", "T001", "result.json")
    stored = json.loads(json_path.read_text(encoding="utf-8"))
    assert stored["config_sha256"] == loaded.file_sha256
    assert stored["runs"][0]["cases"][0]["status"] == "scored"
    assert "report" not in stored["runs"][0]["cases"][0]
    assert "not clinical accuracy" in md_path.read_text(encoding="utf-8")


def test_outside_entries_ignored_and_missing_reported(
    tmp_path: Path, settings: Settings, stale_index: Path
) -> None:
    opened: list[str] = []

    def guarded_open(entry: IndexEntry, s: Settings) -> Study:
        opened.append(entry.case_id)
        return open_study(entry, s)

    result = run_experiment(
        load_experiment(_experiment(tmp_path)), settings, open_case=guarded_open
    )
    (summary,) = result.datasets
    assert summary.index_entries_outside_development == 1
    assert summary.not_indexed == 1
    assert "SEALED" not in opened
    (run,) = result.runs
    statuses = {c.case_id: c.status for c in run.cases}
    assert statuses["P3"] is CaseStatus.NOT_INDEXED
    assert "SEALED" not in statuses
    assert run.status_counts["not_indexed"] == 1


def test_limit_phases_and_variants(tmp_path: Path, settings: Settings) -> None:
    exp = _experiment(
        tmp_path,
        phases=["internal_test"],
        variants=[{"id": "a"}, {"id": "b", "view_overrides": {"n": 4}}],
    )
    result = run_experiment(load_experiment(exp), settings, limit=1)
    assert [r.spec["variant"] for r in result.runs] == ["a", "b"]
    for run in result.runs:
        assert len(run.cases) == 1
        assert run.cases[0].phase == "internal_test"
    assert result.limit_per_dataset == 1


def test_failures_and_abstentions_are_explicit(tmp_path: Path, settings: Settings) -> None:
    def flaky(study: Study, model_id: str, s: Settings, **kwargs: Any) -> AnalysisResult:
        if study.case_id == "P1":
            raise RuntimeError("model crashed")
        result = analyze_study(study, model_id, s, **kwargs)
        if study.case_id == "P2":
            result.report.abstain = True
        return result

    result = run_experiment(load_experiment(_experiment(tmp_path)), settings, analyze=flaky)
    (run,) = result.runs
    by_id = {c.case_id: c for c in run.cases}
    assert by_id["P1"].status is CaseStatus.FAILED
    assert by_id["P1"].error == "RuntimeError: model crashed"
    assert by_id["P2"].status is CaseStatus.ABSTAINED
    assert by_id["P2"].y_score == {}
    assert by_id["P3"].status is CaseStatus.SCORED
    assert run.metrics["n_scored"] == 1
    assert run.metrics["task_g"]["abstention_rate"] == 0.5


def test_study_load_failure_marks_every_variant(tmp_path: Path, settings: Settings) -> None:
    def broken(entry: IndexEntry, s: Settings) -> Study:
        raise StudyLoadError("no CT series")

    exp = _experiment(tmp_path, variants=[{"id": "a"}, {"id": "b"}])
    result = run_experiment(load_experiment(exp), settings, open_case=broken, limit=1)
    for run in result.runs:
        assert run.cases[0].status is CaseStatus.FAILED
        assert run.cases[0].error == "study load failed: no CT series"
        assert run.metrics["task_a"]["per_label"]["pulmonary_nodule"]["n"] == 0
        assert run.provenance.preprocess_hash is None


def test_sealed_access_aborts(tmp_path: Path, settings: Settings) -> None:
    def sealed_open(entry: IndexEntry, s: Settings) -> Study:
        raise SealedAccessError("sealed")

    def sealed_analyze(*args: Any, **kwargs: Any) -> AnalysisResult:
        raise SealedAccessError("sealed")

    loaded = load_experiment(_experiment(tmp_path))
    with pytest.raises(SealedAccessError):
        run_experiment(loaded, settings, open_case=sealed_open, limit=1)
    with pytest.raises(SealedAccessError):
        run_experiment(loaded, settings, analyze=sealed_analyze, limit=1)


def test_cli_runs_and_refuses_unseal(
    tmp_path: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_benchmark, "get_settings", lambda: settings)
    exp = _experiment(tmp_path)
    runner = CliRunner()
    ok = runner.invoke(app, ["benchmark", str(exp), "--limit", "2"])
    assert ok.exit_code == 0, ok.output
    assert "T001 [base]: scored 2" in ok.output
    assert "Config SHA-256:" in ok.output

    calls: list[object] = []
    monkeypatch.setattr(guard_module.CaseGuard, "load", lambda *a, **k: calls.append(k))
    refused = runner.invoke(app, ["benchmark", str(exp), "--unseal"])
    assert refused.exit_code == 2
    assert "Sealed evaluation is not implemented" in refused.output
    assert calls == []


def test_cli_reports_errors(
    tmp_path: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_benchmark, "get_settings", lambda: settings)
    missing = CliRunner().invoke(app, ["benchmark", str(tmp_path / "missing.yaml")])
    assert missing.exit_code == 1
    assert "Benchmark failed" in missing.output
    no_index = CliRunner().invoke(
        app, ["benchmark", str(_experiment(tmp_path, datasets=["nsclc_radiogenomics"]))]
    )
    assert no_index.exit_code == 1
