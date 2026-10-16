# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Benchmark runner and CLI over a synthetic, split-guarded, indexed data directory."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import yaml
from typer.testing import CliRunner

import thoraxbench.benchmark.runner as benchmark_runner
import thoraxbench.cli.benchmark as cli_benchmark
import thoraxbench.splits.guard as guard_module
from thoraxbench.adapters.base import load_model_config
from thoraxbench.analysis import AnalysisResult, analyze_study
from thoraxbench.benchmark import CaseStatus, load_experiment, run_experiment, write_outputs
from thoraxbench.cli.main import app
from thoraxbench.config import REPO_ROOT, Settings
from thoraxbench.dicom import discover_series
from thoraxbench.index import IndexEntry, build_index, index_path, open_study
from thoraxbench.schemas import AnalysisRequest
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
    assert len(messages) == 4
    assert messages[0].startswith("Invocation: ")
    json_path, md_path = write_outputs(result, settings)
    assert json_path.parent.parent == settings.data_path("results", "benchmark", "T001")
    assert loaded.file_sha256[:12] in json_path.parent.name
    stored = json.loads(json_path.read_text(encoding="utf-8"))
    assert stored["config_sha256"] == loaded.file_sha256
    assert stored["runs"][0]["cases"][0]["status"] == "scored"
    assert "report" not in stored["runs"][0]["cases"][0]
    assert "not clinical accuracy" in md_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("model_prompt", "variant_prompt", "expected"),
    [(None, None, "P3"), ("P2", None, "P2"), ("P2", "P4", "P4")],
)
def test_requests_use_experiment_labels_and_resolved_prompt(
    tmp_path: Path,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    *,
    model_prompt: str | None,
    variant_prompt: str | None,
    expected: str,
) -> None:
    model = load_model_config("heuristic-hu", settings.configs_dir / "models")
    monkeypatch.setattr(
        benchmark_runner,
        "load_model_config",
        lambda *args: model.model_copy(update={"prompt": model_prompt}),
    )
    observed: list[AnalysisRequest] = []

    def inspect(study: Study, model_id: str, s: Settings, **kwargs: Any) -> AnalysisResult:
        request = kwargs["request"]
        assert isinstance(request, AnalysisRequest)
        assert request.labels == ["pulmonary_nodule"]
        assert request.prompt_id == expected
        assert kwargs["prompt_id"] == expected
        observed.append(request)
        return analyze_study(study, model_id, s, **kwargs)

    variants = [{"id": "configured", "prompt": variant_prompt}]
    loaded = load_experiment(_experiment(tmp_path, labels=["pulmonary_nodule"], variants=variants))
    result = run_experiment(loaded, settings, limit=1, analyze=inspect)
    assert len(observed) == 1
    assert result.runs[0].status_counts["scored"] == 1
    assert loaded.config.labels == ["pulmonary_nodule"]


def test_output_runs_preserve_prior_and_legacy_files(tmp_path: Path, settings: Settings) -> None:
    result = run_experiment(load_experiment(_experiment(tmp_path)), settings, limit=1)
    legacy = settings.data_path("results", "benchmark", result.experiment_id)
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "result.json").write_text("historical result")
    (legacy / "report.md").write_text("historical report")
    first = write_outputs(result, settings)
    original = [path.read_bytes() for path in first]
    assert write_outputs(result, settings) == first
    second = write_outputs(
        run_experiment(load_experiment(_experiment(tmp_path)), settings, limit=1), settings
    )
    assert first[0].parent != second[0].parent
    assert [path.read_bytes() for path in first] == original
    assert (legacy / "result.json").read_text() == "historical result"
    assert (legacy / "report.md").read_text() == "historical report"
    assert all(path.is_file() for path in second)


def test_output_symlink_escape_is_rejected_before_writing(
    tmp_path: Path, settings: Settings
) -> None:
    result = run_experiment(load_experiment(_experiment(tmp_path)), settings, limit=1)
    escaped = tmp_path / "outside"
    escaped.mkdir()
    base = settings.data_path("results", "benchmark")
    base.mkdir(parents=True, exist_ok=True)
    (base / "escape").symlink_to(escaped, target_is_directory=True)
    result.experiment_id = "escape"
    with pytest.raises(ValueError, match="ignored data/results"):
        write_outputs(result, settings)
    assert list(escaped.iterdir()) == []


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


def test_cli_rejects_export_escape_before_inference(
    tmp_path: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    import thoraxbench.benchmark as benchmark_package

    outside = tmp_path / "outside"
    outside.mkdir()
    base = settings.data_path("results", "benchmark")
    base.mkdir(parents=True, exist_ok=True)
    (base / "preflight").symlink_to(outside, target_is_directory=True)
    experiment = _experiment(tmp_path, id="preflight")
    analyze = Mock()
    monkeypatch.setattr(cli_benchmark, "get_settings", lambda: settings)
    monkeypatch.setattr(benchmark_package, "run_experiment", analyze)
    response = CliRunner().invoke(app, ["benchmark", str(experiment)])
    assert response.exit_code == 1
    assert "ignored data/results" in response.output
    analyze.assert_not_called()
    assert list(outside.iterdir()) == []


def _interrupted_run(loaded: Any, settings: Settings) -> Path:
    messages: list[str] = []
    calls = 0

    def interrupt(study: Study, model_id: str, s: Settings, **kwargs: Any) -> AnalysisResult:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        result = analyze_study(study, model_id, s, **kwargs)
        result.raw_text = "synthetic raw response retained exactly"
        return result

    with pytest.raises(KeyboardInterrupt):
        run_experiment(loaded, settings, analyze=interrupt, progress=messages.append)
    return Path(messages[0].removeprefix("Invocation: "))


def test_interruption_resume_preserves_raw_artifacts_and_scoring(
    tmp_path: Path, settings: Settings
) -> None:
    loaded = load_experiment(_experiment(tmp_path))
    folder = _interrupted_run(loaded, settings)
    checkpoint = json.loads((folder / "checkpoint.json").read_text())["payload"]
    assert checkpoint["status"] == "running"
    assert len(checkpoint["units"]) == 1
    record = next(iter(checkpoint["units"].values()))
    artifact_path = folder / record["file"]
    original = artifact_path.read_bytes()
    artifact = json.loads(original)
    assert artifact["analysis"]["raw_text"] == "synthetic raw response retained exactly"
    assert artifact["analysis"]["request"]["labels"] == loaded.config.labels
    assert artifact["analysis"]["provenance"]["preprocess_hash"]
    assert "prepared_images" not in artifact["analysis"]
    assert artifact["report"]["findings"]
    observed: list[str] = []

    def analyze_remaining(
        study: Study, model_id: str, s: Settings, **kwargs: Any
    ) -> AnalysisResult:
        observed.append(study.case_id)
        return analyze_study(study, model_id, s, **kwargs)

    resumed = run_experiment(loaded, settings, resume=folder, analyze=analyze_remaining)
    assert observed == ["P2", "P3"]
    assert artifact_path.read_bytes() == original
    fresh = run_experiment(loaded, settings)
    assert resumed.runs[0].metrics == fresh.runs[0].metrics
    assert resumed.output_dir == folder
    before = {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()}
    completed = run_experiment(
        loaded, settings, resume=folder, analyze=Mock(side_effect=AssertionError)
    )
    assert completed.runs[0].metrics == resumed.runs[0].metrics
    assert {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()} == before


@pytest.mark.parametrize("name", ["checkpoint.json", "manifest.json", "case"])
def test_resume_rejects_corrupt_integrity_records(
    tmp_path: Path, settings: Settings, name: str
) -> None:
    loaded = load_experiment(_experiment(tmp_path))
    folder = _interrupted_run(loaded, settings)
    path = next((folder / "cases").glob("*.json")) if name == "case" else folder / name
    path.write_text("{}")
    with pytest.raises(ValueError, match=r"integrity|checksum"):
        run_experiment(loaded, settings, resume=folder, analyze=Mock(side_effect=AssertionError))


def test_resume_rejects_changed_selection_experiment_source_and_input(
    tmp_path: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = load_experiment(_experiment(tmp_path))
    folder = _interrupted_run(loaded, settings)
    with pytest.raises(ValueError, match="identity mismatch"):
        run_experiment(loaded, settings, resume=folder, limit=1)
    changed = load_experiment(_experiment(tmp_path, labels=["pulmonary_nodule"]))
    with pytest.raises(ValueError, match="identity mismatch"):
        run_experiment(changed, settings, resume=folder)
    _experiment(tmp_path)
    original = benchmark_runner._resume_identity

    def changed_source(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return original(*args, **kwargs) | {"source_hash": "changed"}

    with monkeypatch.context() as context:
        context.setattr(benchmark_runner, "_resume_identity", changed_source)
        with pytest.raises(ValueError, match="identity mismatch"):
            run_experiment(loaded, settings, resume=folder)
    extra = settings.data_path("raw", "lidc_idri", "P1", "changed.txt")
    extra.write_text("changed source input")
    try:
        with pytest.raises(ValueError, match="identity mismatch"):
            run_experiment(loaded, settings, resume=folder)
    finally:
        extra.unlink()


def test_resume_keeps_failed_and_not_indexed_units_terminal(
    tmp_path: Path, settings: Settings, stale_index: Path
) -> None:
    loaded = load_experiment(_experiment(tmp_path))

    def failed(study: Study, model_id: str, s: Settings, **kwargs: Any) -> AnalysisResult:
        raise RuntimeError("synthetic terminal failure")

    result = run_experiment(loaded, settings, analyze=failed)
    assert result.runs[0].status_counts["failed"] == 2
    assert result.runs[0].status_counts["not_indexed"] == 1
    resumed = run_experiment(
        loaded, settings, resume=result.output_dir, analyze=Mock(side_effect=AssertionError)
    )
    assert resumed.runs[0].status_counts == result.runs[0].status_counts


def test_output_failure_stops_before_next_inference_and_initializes_checkpoint(
    tmp_path: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from thoraxbench.benchmark.checkpoint import BenchmarkStore

    loaded = load_experiment(_experiment(tmp_path))
    analyze = Mock(wraps=analyze_study)
    monkeypatch.setattr(BenchmarkStore, "save_unit", Mock(side_effect=OSError("disk full")))
    messages: list[str] = []
    with pytest.raises(OSError, match="disk full"):
        run_experiment(loaded, settings, analyze=analyze, progress=messages.append)
    assert analyze.call_count == 1
    folder = Path(messages[0].removeprefix("Invocation: "))
    assert (folder / "checkpoint.json").is_file()
    assert (folder / "manifest.json").is_file()
    assert not (folder / "result.json").exists()


def test_cli_resume_returns_same_invocation(
    tmp_path: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_benchmark, "get_settings", lambda: settings)
    exp = _experiment(tmp_path)
    first = CliRunner().invoke(app, ["benchmark", str(exp), "--limit", "1"])
    assert first.exit_code == 0, first.output
    invocation = next(
        line.removeprefix("Invocation: ")
        for line in first.output.splitlines()
        if line.startswith("Invocation: ")
    )
    resumed = CliRunner().invoke(
        app, ["benchmark", str(exp), "--limit", "1", "--resume", invocation]
    )
    assert resumed.exit_code == 0, resumed.output
    assert f"Invocation: {invocation}" in resumed.output
    refused = CliRunner().invoke(app, ["benchmark", str(exp), "--resume", invocation, "--unseal"])
    assert refused.exit_code == 2


def test_unverifiable_source_is_failed_without_inference_and_cannot_resume(
    tmp_path: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        benchmark_runner, "guard_study_input", Mock(side_effect=ValueError("unreadable input"))
    )
    analyze = Mock(side_effect=AssertionError)
    loaded = load_experiment(_experiment(tmp_path))
    result = run_experiment(loaded, settings, limit=1, analyze=analyze)
    assert result.runs[0].status_counts["failed"] == 1
    analyze.assert_not_called()
    with pytest.raises(ValueError, match="verified selected input"):
        run_experiment(loaded, settings, limit=1, resume=result.output_dir, analyze=analyze)


def test_runtime_model_change_archives_failure_and_stops_next_case(
    tmp_path: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        benchmark_runner,
        "runtime_identity",
        lambda *args: {"adapter": "heuristic", "digest": "before"},
    )

    def changed(study: Study, model_id: str, s: Settings, **kwargs: Any) -> AnalysisResult:
        result = analyze_study(study, model_id, s, **kwargs)
        result.provenance.model_hash = "after"
        return result

    messages: list[str] = []
    with pytest.raises(RuntimeError, match="digest changed"):
        run_experiment(
            load_experiment(_experiment(tmp_path)),
            settings,
            analyze=changed,
            progress=messages.append,
        )
    folder = Path(messages[0].removeprefix("Invocation: "))
    checkpoint = json.loads((folder / "checkpoint.json").read_text())["payload"]
    assert len(checkpoint["units"]) == 1
    artifact = json.loads(next((folder / "cases").glob("*.json")).read_text())
    assert artifact["analysis"]["provenance"]["model_hash"] == "after"
    assert artifact["outcome"]["status"] == "failed"
    assert artifact["runtime_identity_error"]
    with pytest.raises(ValueError, match="Invalid checkpointed case"):
        run_experiment(load_experiment(_experiment(tmp_path)), settings, resume=folder)


def test_development_guard_runs_before_reusing_completed_result(
    tmp_path: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from thoraxbench.benchmark.checkpoint import BenchmarkStore

    loaded = load_experiment(_experiment(tmp_path))
    result = run_experiment(loaded, settings, limit=1)
    monkeypatch.setattr(
        guard_module.CaseGuard,
        "check",
        Mock(side_effect=SealedAccessError("no longer development")),
    )
    monkeypatch.setattr(
        BenchmarkStore, "verify", Mock(side_effect=AssertionError("artifact read before guard"))
    )
    with pytest.raises(SealedAccessError):
        run_experiment(loaded, settings, limit=1, resume=result.output_dir)


def test_active_runtime_includes_loading_and_resume_excludes_downtime(
    tmp_path: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = load_experiment(_experiment(tmp_path))
    clock = [0.0]
    monkeypatch.setattr(benchmark_runner.time, "perf_counter", lambda: clock[0])

    def slow_open(entry: IndexEntry, s: Settings) -> Study:
        clock[0] += 7.0
        return open_study(entry, s)

    def advance(study: Study, model_id: str, s: Settings, **kwargs: Any) -> AnalysisResult:
        result = analyze_study(study, model_id, s, **kwargs)
        clock[0] += 2.0
        return result

    result = run_experiment(loaded, settings, open_case=slow_open, analyze=advance)
    assert result.runtime_s == 27.0
    assert result.runs[0].runtime_s == 6.0
    checkpoint = json.loads((result.output_dir / "checkpoint.json").read_text())["payload"]
    assert checkpoint["active_runtime_s"] == 27.0

    folder = _interrupted_run(loaded, settings)
    saved = json.loads((folder / "checkpoint.json").read_text())["payload"]
    clock[0] += 1000.0  # Downtime must not appear in resumed active wall time.
    resumed = run_experiment(loaded, settings, resume=folder, open_case=slow_open, analyze=advance)
    assert resumed.runtime_s == saved["active_runtime_s"] + 18.0


def test_failed_case_artifact_redacts_paths_and_known_identifiers(
    tmp_path: Path, settings: Settings
) -> None:
    def fail(study: Study, _model: str, s: Settings, **_kwargs: Any) -> AnalysisResult:
        study.identifiers = frozenset({"Synthetic Secret Name"})
        raise RuntimeError(f"Synthetic Secret Name at {s.data_dir}/private/input.dcm")

    result = run_experiment(load_experiment(_experiment(tmp_path)), settings, limit=1, analyze=fail)
    case = next((result.output_dir / "cases").glob("*.json"))
    text = case.read_text()
    assert "Synthetic Secret Name" not in text
    assert str(settings.data_dir) not in text
    assert "[redacted]" in text
    assert "[data]/private/input.dcm" in text
