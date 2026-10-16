# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Synthetic, metadata-only offline cohort export and comparison acceptance."""

import csv
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from typer.testing import CliRunner

from thoraxbench.adapters.base import load_model_config
from thoraxbench.analysis import AnalysisResult
from thoraxbench.benchmark.checkpoint import BenchmarkStore
from thoraxbench.benchmark.cohort import load_completed_run
from thoraxbench.benchmark.compare import comparison_details, setups
from thoraxbench.benchmark.config import ExperimentConfig
from thoraxbench.benchmark.exports import _csv, case_rows, export_completed_runs
from thoraxbench.benchmark.runner import (
    CaseOutcome,
    CaseStatus,
    DatasetSummary,
    ExperimentResult,
    RunResult,
)
from thoraxbench.cli import compare as cli_compare
from thoraxbench.cli.main import app
from thoraxbench.config import REPO_ROOT, Settings
from thoraxbench.perf import PerfRecord
from thoraxbench.provenance import RunProvenance, sha256_of_file, sha256_of_obj
from thoraxbench.schemas import AnalysisRequest, Finding, FindingsReport
from thoraxbench.splits import (
    CaseGuard,
    CaseRecord,
    Phase,
    SealedAccessError,
    make_split,
    save_split,
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = Settings(repo_root=repo, data_dir=tmp_path / "data")
    split = make_split(
        [
            CaseRecord(dataset="lidc_idri", case_id=f"DEV_A{i:03}", patient_id=f"DEV_A{i:03}")
            for i in range(8)
        ],
        "lidc_idri",
    )
    save_split(split, config.data_dir, config.manifests_dir)
    return config


def _completed(settings: Settings, *, overrides: dict[str, Any] | None = None) -> Path:
    cfg = ExperimentConfig(
        id="EXPORT",
        model="heuristic-hu",
        datasets=["lidc_idri"],
        labels=["pulmonary_nodule", "pulmonary_mass"],
        n_boot=0,
        view_overrides=overrides or {},
    )
    guard = CaseGuard.load(settings.data_dir, settings.manifests_dir, "lidc_idri")
    selected = guard.cases(Phase.DEVELOPMENT)[:4]
    model = load_model_config("heuristic-hu", REPO_ROOT / "configs" / "models")
    spec = cfg.runs()[0].to_dict()
    summary = DatasetSummary(
        dataset="lidc_idri",
        development_cases=len(guard.cases(Phase.DEVELOPMENT)),
        selected_cases=4,
        indexed_development_cases=3,
        not_indexed=1,
        index_entries_outside_development=0,
        index_sha256="index",
        split_manifest_sha256="split",
        dataset_manifest_sha256=None,
    )
    provenance = RunProvenance(
        model_id="heuristic-hu",
        scoring_hash="scoring-v1",
        ground_truth_hash="references-v1",
        prompt_hash="prompt",
        preprocess_hash=sha256_of_obj(cfg.view_overrides),
    )
    identity = {
        "schema_version": 1,
        "config": cfg.model_dump(mode="json"),
        "experiment_file": "filehash",
        "experiment_canonical": sha256_of_obj(cfg.model_dump(mode="json")),
        "limit": None,
        "source_hash": "packagehash",
        "development_splits": {"lidc_idri": "split-hash"},
        "runtime_models": {"heuristic-hu": {"adapter": "heuristic", "identity": "source-hashed"}},
        "models": {"base": {"model": model.model_dump(mode="json"), "prompt": "P3"}},
        "datasets": [summary.model_dump(mode="json")],
        "selected": [
            {
                "dataset": "lidc_idri",
                "case_id": case,
                "phase": guard.phase_of(case).value,
                "entry": None if index == 3 else sha256_of_obj(case),
                "input": None
                if index == 3
                else {"sha256": sha256_of_obj(["bytes", case]), "error": None},
            }
            for index, case in enumerate(selected)
        ],
    }
    folder = settings.data_path("results", "benchmark", "EXPORT", uuid4().hex)
    folder.mkdir(parents=True)
    store = BenchmarkStore(folder, settings)
    store.initialize(identity, resume=False)
    cases = []
    for index, case_id in enumerate(selected):
        truth = {"pulmonary_nodule": index != 1, "pulmonary_mass": None} if index != 3 else {}
        analysis = None
        report = None
        if index < 2:
            report = FindingsReport(
                findings=[Finding(label="pulmonary_nodule", present=True, confidence=0.8)],
                abstain=index == 1,
                parse_warnings=["PRIVATE_MODEL_WARNING"],
            )
            analysis = AnalysisResult(
                dataset="lidc_idri",
                case_id=case_id,
                patient_id=case_id,
                series_uid=f"1.2.{index}",
                model_id="heuristic-hu",
                request=AnalysisRequest(labels=cfg.labels, prompt_id="P3"),
                report=report,
                raw_text="DO_NOT_EXPORT_RAW_PROVIDER_TEXT",
                raw_meta={"private": "DO_NOT_EXPORT_RAW_PROVIDER_TEXT"},
                perf=PerfRecord(total_s=0.1),
                provenance=provenance,
            )
        status = [
            CaseStatus.SCORED,
            CaseStatus.ABSTAINED,
            CaseStatus.FAILED,
            CaseStatus.NOT_INDEXED,
        ][index]
        outcome = CaseOutcome(
            dataset="lidc_idri",
            case_id=case_id,
            patient_id=case_id if index != 3 else None,
            phase=guard.phase_of(case_id).value,
            status=status,
            y_true=truth,
            y_score={label: report.label_probability(label) for label in cfg.labels}
            if status == CaseStatus.SCORED
            else {},
            positive_labels=["pulmonary_nodule"] if status == CaseStatus.SCORED else [],
            parse_warnings=report.parse_warnings if report else [],
            runtime_s=0.1 if analysis else None,
            fingerprint=provenance.fingerprint() if analysis else None,
            error="PRIVATE_MODEL_ERROR" if index == 2 else None,
            report=report,
        )
        cases.append(outcome)
        key = sha256_of_obj(["lidc_idri", case_id, "base"])
        store.save_unit(
            key,
            {
                "unit": key,
                "schema_version": 1,
                "runtime_identity_error": None,
                "outcome": outcome.model_dump(mode="json"),
                "report": report.model_dump(mode="json") if report else None,
                "analysis": analysis.model_dump(mode="json") if analysis else None,
                "resolved_spec": spec
                | {
                    "prompt": "P3",
                    "view": model.view,
                    "view_params": model.view_params | cfg.view_overrides,
                },
                "request": AnalysisRequest(labels=cfg.labels, prompt_id="P3").model_dump(
                    mode="json"
                ),
            },
            0.1,
        )
    counts = dict(Counter(c.status.value for c in cases))
    run = RunResult(
        spec=spec,
        provenance=provenance,
        status_counts=counts,
        phase_counts={},
        metrics={
            "n_scored": 1,
            "task_a": {
                "macro_f1": 0.5,
                "macro_auroc": None,
                "per_label": {
                    "pulmonary_nodule": {"tp": 1, "fp": 0, "fn": 1, "notes": ['=HYPERLINK("bad")']}
                },
            },
            "task_e": {
                "available_predictions": 1,
                "reference_labels": 2,
                "prediction_coverage": 0.5,
            },
            "task_g": {
                "abstention_rate": 0.5,
                "false_reassurance_studies": 0,
                "false_reassurance_eligible_studies": 1,
            },
            "unsafe_text": '<script>alert("metadata")</script>',
        },
        runtime_s=0.2,
        cases=cases,
    )
    result = ExperimentResult(
        experiment_id=cfg.id,
        title="Synthetic export fixture",
        description="",
        vision_ref="",
        config_path="fixture.yaml",
        config_sha256="filehash",
        config_canonical_sha256=identity["experiment_canonical"],
        config=cfg.model_dump(mode="json"),
        split="development",
        started_at="2026-10-16T00:00:00+00:00",
        runtime_s=0.5,
        limit_per_dataset=None,
        datasets=[summary],
        runs=[run],
    )
    store.finish(result.model_dump_json(), "Synthetic research-only report")
    return folder


def test_cohort_export_is_offline_pseudonymous_and_preserves_source(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _completed(settings)
    original = {
        str(path.relative_to(source)): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(httpx, "Client", Mock(side_effect=AssertionError("network access")))
    outputs = export_completed_runs([source], settings)
    html = outputs["html"].read_text()
    assert "Cohort review" in html
    assert "Case processing (s)" in html
    assert "separate from engine-stage timing" in html
    assert "case_processing_s" in outputs["metrics_csv"].read_text()
    assert "analysis_stages_s" not in outputs["metrics_csv"].read_text()
    assert "Development split only" in html
    assert "prediction" in html.lower()
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<img" not in html
    assert "http://" not in html
    assert "not directly comparable" in html
    assert "not anonymous" in html
    assert "PRIVATE_MODEL_" not in html
    assert "DO_NOT_EXPORT_RAW" not in html
    for case_id in CaseGuard.load(settings.data_dir, settings.manifests_dir, "lidc_idri").cases(
        Phase.DEVELOPMENT
    ):
        assert case_id not in html
        assert case_id not in outputs["cases_csv"].read_text()
    assert {
        str(path.relative_to(source)): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    } == original
    manifest = json.loads(outputs["manifest"].read_text())
    for kind, record in manifest["outputs"].items():
        assert sha256_of_file(outputs[kind]) == record["sha256"]
    rows = list(csv.DictReader(io.StringIO(outputs["cases_csv"].read_text())))
    assert len(rows) == 8
    assert {row["status"] for row in rows} == {"scored", "abstained", "failed", "not_indexed"}
    assert all(row["presence_score"] == "" for row in rows if row["status"] != "scored")
    assert outputs["metrics_csv"].read_text().count("Research use only") > 1
    second = export_completed_runs([source], settings)
    assert second["html"].parent != outputs["html"].parent


def test_comparison_separates_source_cohort_from_prepared_view(settings: Settings) -> None:
    first = load_completed_run(_completed(settings), settings)
    second = load_completed_run(_completed(settings, overrides={"n": 2}), settings)
    pairs = comparison_details(setups([first, second]))
    assert pairs[0]["comparable"]
    assert pairs[0]["experimental_factors"]["model_or_prompt_or_view"]
    assert pairs[0]["experimental_factors"]["prepared_input_definition"]
    assert pairs[0]["paired_available_predictions"] == {"pulmonary_mass": 0, "pulmonary_nodule": 1}
    second.result.runs[0].provenance.scoring_hash = "different-scoring"
    assert not comparison_details(setups([first, second]))[0]["comparable"]
    second.result.runs[0].provenance.scoring_hash = None
    assert (
        "scoring source identity unavailable"
        in comparison_details(setups([first, second]))[0]["differences"]
    )
    second.result.runs[0].provenance.ground_truth_hash = None
    second.identity["selected"][0]["input"] = {"sha256": None}
    second.identity["models"]["base"]["model"]["adapter"] = "ollama"
    pairs = comparison_details(setups([first, second]))
    assert "selected source-input identity unavailable" in pairs[0]["differences"]
    assert "actual model weight identity unavailable" in pairs[0]["differences"]
    assert case_rows(setups([first]))[0][2].startswith("case-")


@pytest.mark.parametrize(
    "value", ["=1+2", "+SUM(1,2)", "-1+2", "@SUM(1)", "\t=cmd", " \r\n=bad", "\ufeff=bad"]
)
def test_csv_formula_injection_is_neutralized(value: str) -> None:
    parsed = list(csv.reader(io.StringIO(_csv(["cell"], [[value]]))))
    assert parsed[1][0] == "'" + value


def test_exports_reject_legacy_partial_corrupt_and_escaping_sources(
    settings: Settings, tmp_path: Path
) -> None:
    legacy = settings.data_path("results", "benchmark", "legacy")
    legacy.mkdir(parents=True)
    (legacy / "result.json").write_text("{}")
    with pytest.raises(ValueError, match="legacy"):
        export_completed_runs([legacy], settings)
    source = _completed(settings)
    with pytest.raises(ValueError, match="distinct"):
        export_completed_runs([source, source], settings)
    with pytest.raises(ValueError, match="completed invocation"):
        export_completed_runs([tmp_path], settings)
    with pytest.raises(ValueError, match="source invocations"):
        export_completed_runs([source], settings, output_dir=source / "exports")
    outside = tmp_path / "outside"
    outside.mkdir()
    escaped = settings.data_path("results", "escaped")
    escaped.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="ignored data/results"):
        export_completed_runs([source], settings, output_dir=escaped)
    (source / "result.json").write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        export_completed_runs([source], settings)


def test_current_development_guard_precedes_artifact_reads(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _completed(settings)
    monkeypatch.setattr(
        CaseGuard, "check", Mock(side_effect=SealedAccessError("sealed or unknown"))
    )
    monkeypatch.setattr(
        BenchmarkStore, "verify", Mock(side_effect=AssertionError("artifact read before guard"))
    )
    with pytest.raises(SealedAccessError):
        load_completed_run(source, settings)


def test_cli_compare_and_single_export(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_compare, "get_settings", lambda: settings)
    first, second = _completed(settings), _completed(settings, overrides={"n": 2})
    one = CliRunner().invoke(app, ["benchmark-export", str(first)])
    assert one.exit_code == 0, one.output
    assert "metrics_csv:" in one.output
    compared = CliRunner().invoke(app, ["compare", str(first), str(second)])
    assert compared.exit_code == 0, compared.output
    assert "No model ranking" in compared.output
    invalid = CliRunner().invoke(app, ["compare", str(first)])
    assert invalid.exit_code == 2
    failed = CliRunner().invoke(
        app, ["benchmark-export", str(first), "--output-dir", str(settings.repo_root)]
    )
    assert failed.exit_code == 1


def _rewrite(
    folder: Path,
    *,
    identity_change: Any = None,
    checkpoint_change: Any = None,
    result_change: Any = None,
    unit_change: Any = None,
) -> None:
    identity = json.loads((folder / "manifest.json").read_text())["payload"]
    checkpoint = json.loads((folder / "checkpoint.json").read_text())["payload"]
    if identity_change:
        identity_change(identity)
    if result_change:
        result_file = folder / checkpoint["outputs"]["json"]["file"]
        result = json.loads(result_file.read_text())
        result_change(result)
        result_file.write_text(json.dumps(result))
        checkpoint["outputs"]["json"]["sha256"] = sha256_of_file(result_file)
    if unit_change:
        record = next(
            item
            for item in checkpoint["units"].values()
            if json.loads((folder / item["file"]).read_text())["outcome"]["status"] == "scored"
        )
        unit_file = folder / record["file"]
        unit = json.loads(unit_file.read_text())
        unit_change(unit)
        unit_file.write_text(json.dumps(unit))
        record["sha256"] = sha256_of_file(unit_file)
    checkpoint["identity_sha256"] = sha256_of_obj(identity)
    if checkpoint_change:
        checkpoint_change(checkpoint)
    for name, payload in [("manifest.json", identity), ("checkpoint.json", checkpoint)]:
        (folder / name).write_text(
            json.dumps({"payload": payload, "sha256": sha256_of_obj(payload)})
        )


@pytest.mark.parametrize("location", ["config", "selection"])
def test_unsafe_dataset_is_rejected_before_any_guard_read(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, location: str
) -> None:
    source = _completed(settings)

    def unsafe(identity: dict[str, Any]) -> None:
        if location == "config":
            identity["config"]["datasets"] = ["../sealed/lidc_idri"]
            identity["experiment_canonical"] = sha256_of_obj(identity["config"])
        else:
            identity["selected"][0]["dataset"] = "../sealed/lidc_idri"

    _rewrite(source, identity_change=unsafe)
    monkeypatch.setattr(
        CaseGuard, "load", Mock(side_effect=AssertionError("guard attempted unsafe read"))
    )
    with pytest.raises(ValueError, match="Invalid dataset identifier"):
        load_completed_run(source, settings)


@pytest.mark.parametrize(
    "fault",
    [
        "version",
        "canonical",
        "duplicate_selection",
        "selection_dataset",
        "phase",
        "running",
        "missing_output",
        "identity_hash",
        "missing_unit",
        "result_identity",
        "duplicate_case",
        "case_phase",
        "outcome",
        "unit_version",
        "setup",
        "labels",
        "prompt",
        "missing_analysis",
        "analysis_identity",
        "availability",
    ],
)
def test_semantic_corruption_is_rejected_after_checksum_verification(
    settings: Settings, fault: str
) -> None:
    source = _completed(settings)

    def manifest(value: dict[str, Any]) -> None:
        if fault == "version":
            value["schema_version"] = 2
        if fault == "canonical":
            value["experiment_canonical"] = "wrong"
        if fault == "duplicate_selection":
            value["selected"].append(value["selected"][0])
        if fault == "selection_dataset":
            value["selected"][0]["dataset"] = "unknown"
        if fault == "phase":
            value["selected"][0]["phase"] = "sealed"

    def checkpoint(value: dict[str, Any]) -> None:
        if fault == "running":
            value["status"] = "running"
        if fault == "missing_output":
            value["outputs"].pop("markdown")
        if fault == "identity_hash":
            value["identity_sha256"] = "wrong"
        if fault == "missing_unit":
            value["units"].pop(next(iter(value["units"])))

    def result(value: dict[str, Any]) -> None:
        cases = value["runs"][0]["cases"]
        if fault == "result_identity":
            value["config_sha256"] = "wrong"
        if fault == "duplicate_case":
            cases[1] = cases[0]
        if fault == "case_phase":
            cases[0]["phase"] = "sealed"
        if fault == "outcome":
            cases[0]["error"] = "changed"

    def unit(value: dict[str, Any]) -> None:
        if fault == "unit_version":
            value["schema_version"] = 2
        if fault == "setup":
            value["resolved_spec"]["prompt"] = "P4"
        if fault == "labels":
            value["request"]["labels"] = []
        if fault == "prompt":
            value["request"]["prompt_id"] = "P4"
        if fault == "missing_analysis":
            value["analysis"] = None
        if fault == "analysis_identity":
            value["analysis"]["case_id"] = "other"
        if fault == "availability":
            value["analysis"]["report"]["abstain"] = True
            value["report"]["abstain"] = True

    _rewrite(
        source,
        identity_change=manifest,
        checkpoint_change=checkpoint,
        result_change=result,
        unit_change=unit,
    )
    with pytest.raises(
        ValueError,
        match=r"Unsupported|mismatch|Invalid|invalid|phase|completed|differ|accounting|exactly|missing",
    ):
        load_completed_run(source, settings)


def test_malformed_envelopes_and_case_symlink_escapes_are_refused(
    settings: Settings, tmp_path: Path
) -> None:
    source = _completed(settings)
    (source / "manifest.json").write_text("[]")
    with pytest.raises(ValueError, match="manifest envelope"):
        load_completed_run(source, settings)
    source = _completed(settings)
    content = json.loads((source / "manifest.json").read_text())
    content["sha256"] = "corrupt"
    (source / "manifest.json").write_text(json.dumps(content))
    with pytest.raises(ValueError, match="checksum"):
        load_completed_run(source, settings)
    source = _completed(settings)
    _rewrite(source, identity_change=lambda value: value.update(selected=7))
    with pytest.raises(ValueError, match="Malformed"):
        load_completed_run(source, settings)
    source = _completed(settings)
    unit = next((source / "cases").glob("*.json"))
    outside = tmp_path / "private.json"
    outside.write_bytes(unit.read_bytes())
    unit.unlink()
    unit.symlink_to(outside)
    with pytest.raises(ValueError, match="ignored data/results"):
        load_completed_run(source, settings)


def test_export_bounds_are_checked_before_outputs(settings: Settings) -> None:
    from thoraxbench.benchmark.exports import write_cohort_exports

    with pytest.raises(ValueError, match="one to eight"):
        write_cohort_exports([], settings)
    source = load_completed_run(_completed(settings), settings)
    source.result.runs *= 65
    with pytest.raises(ValueError, match="64 experiment variants"):
        write_cohort_exports([source], settings)
    with pytest.raises(ValueError, match="one to eight"):
        export_completed_runs([Path(str(index)) for index in range(9)], settings)


@pytest.mark.parametrize("value", ["\x00=bad", "\v+bad", "\f@bad"])
def test_csv_control_prefixed_formulas_are_neutralized(value: str) -> None:
    assert list(csv.reader(io.StringIO(_csv(["cell"], [[value]]))))[1][0] == "'" + value


@pytest.mark.parametrize(
    "changed",
    [
        "configured_tag",
        "runtime_weights",
        "actual_weights",
        "default_prompt",
        "prompt_file",
        "actual_prompt",
        "configured_view",
        "view_parameters",
    ],
)
def test_equal_run_specs_still_expose_resolved_experimental_changes(
    settings: Settings, changed: str
) -> None:
    first = load_completed_run(_completed(settings), settings)
    second = load_completed_run(_completed(settings), settings)
    assert first.result.runs[0].spec == second.result.runs[0].spec
    resolved = second.identity["models"]["base"]
    if changed == "configured_tag":
        resolved["model"]["tag"] = "changed:tag"
    if changed == "runtime_weights":
        second.identity["runtime_models"]["heuristic-hu"]["digest"] = "changed-digest"
    if changed == "actual_weights":
        second.result.runs[0].provenance.model_hash = "changed-actual-digest"
    if changed == "default_prompt":
        resolved["prompt"] = "P4"
    if changed == "prompt_file":
        resolved["prompt_file"] = "changed-prompt-filehash"
    if changed == "actual_prompt":
        second.result.runs[0].provenance.prompt_hash = "changed-prompt-hash"
    if changed == "configured_view":
        resolved["model"]["view"] = "changed-view"
    if changed == "view_parameters":
        resolved["model"]["view_params"]["n"] = 2
    pair = comparison_details(setups([first, second]))[0]
    assert pair["comparable"]
    assert pair["experimental_factors"]["model_or_prompt_or_view"]
    assert not pair["experimental_factors"]["source_study_inputs"]
    assert pair["experimental_factors"]["prepared_input_definition"] is (
        changed in {"configured_view", "view_parameters"}
    )


def test_variant_renaming_and_source_data_changes_are_separate_factors(settings: Settings) -> None:
    first = load_completed_run(_completed(settings), settings)
    second = load_completed_run(_completed(settings), settings)
    second.result.runs[0].spec["variant"] = "renamed"
    second.identity["models"]["renamed"] = second.identity["models"].pop("base")
    pair = comparison_details(setups([first, second]))[0]
    assert not pair["experimental_factors"]["model_or_prompt_or_view"]
    second.identity["selected"][0]["input"]["sha256"] = "changed-source-data"
    pair = comparison_details(setups([first, second]))[0]
    assert not pair["comparable"]
    assert pair["experimental_factors"]["source_study_inputs"]
    assert not pair["experimental_factors"]["prepared_input_definition"]
