# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Development-split benchmark runner (WP8): index → analysis → parse → score → report.

The runner iterates over the **development** cases of each dataset's frozen split, opens
each indexed study through the guarded :func:`thoraxbench.index.open_study`, runs every
configured model setup with :func:`thoraxbench.analysis.analyze_study`, and scores the
parsed findings against the indexed reference labels with :mod:`thoraxbench.scoring`.

Sealed cases are never requested: the guard is loaded without a freeze record, and index
entries that are not in the development split are counted (never opened, never scored, IDs
never reported). A :class:`~thoraxbench.splits.SealedAccessError` aborts the whole run.
Failures and abstentions stay explicit per case and are excluded from the label metrics.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from thoraxbench.adapters.base import load_model_config
from thoraxbench.analysis import DISCLAIMER, AnalysisResult, analyze_study
from thoraxbench.benchmark.checkpoint import BenchmarkStore, runtime_identity
from thoraxbench.benchmark.config import LoadedExperiment, RunSpec
from thoraxbench.config import Settings
from thoraxbench.index import IndexEntry, index_path, load_index, open_study
from thoraxbench.privacy import settings_redactor
from thoraxbench.provenance import (
    RunProvenance,
    git_state,
    scoring_source_hash,
    sha256_of_file,
    sha256_of_obj,
)
from thoraxbench.schemas import AnalysisRequest, FindingsReport
from thoraxbench.scoring import CaseRecord as ScoreRecord
from thoraxbench.scoring import task_a, task_b, task_e, task_g
from thoraxbench.splits import CaseGuard, Phase, SealedAccessError
from thoraxbench.study import Study
from thoraxbench.study_access import guard_study_input

FRAMING = (
    "Development-split pipeline measurement. Scores compare parsed outputs with the indexed "
    "reference labels of development cases only; they are not clinical accuracy and not a "
    "sealed-holdout result. A deterministic HU heuristic measures the pipeline, not a model."
)
TASK_C_NOTE = "Task C (lesion localisation) is not scored: no millimetre lesion centres."
RECOVERABLE = (OSError, ValueError, RuntimeError, KeyError)

Analyzer = Callable[..., AnalysisResult]


class CaseStatus(StrEnum):
    """Outcome of one case for one model setup."""

    SCORED = "scored"
    ABSTAINED = "abstained"
    FAILED = "failed"
    NOT_INDEXED = "not_indexed"


class CaseOutcome(BaseModel):
    """Per-case record kept in the result file (no images, no raw model text)."""

    dataset: str
    case_id: str
    patient_id: str | None = None
    phase: str | None = None
    status: CaseStatus
    y_true: dict[str, bool | None] = Field(default_factory=dict)
    y_score: dict[str, float | None] = Field(default_factory=dict)
    positive_labels: list[str] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    runtime_s: float | None = None
    stages_s: dict[str, float] = Field(default_factory=dict)
    fingerprint: str | None = None
    report: FindingsReport | None = Field(default=None, exclude=True, repr=False)


class DatasetSummary(BaseModel):
    """Per-dataset case accounting (counts only; no sealed identifiers)."""

    dataset: str
    development_cases: int
    selected_cases: int
    indexed_development_cases: int
    not_indexed: int
    index_entries_outside_development: int
    index_sha256: str
    split_manifest_sha256: str | None
    dataset_manifest_sha256: str | None


class RunResult(BaseModel):
    """Results of one model setup over all selected cases."""

    spec: dict[str, Any]
    provenance: RunProvenance
    status_counts: dict[str, int]
    phase_counts: dict[str, dict[str, int]]
    metrics: dict[str, Any]
    runtime_s: float
    cases: list[CaseOutcome]


class ExperimentResult(BaseModel):
    """Everything the benchmark writes for one experiment execution."""

    output_dir: Path | None = Field(default=None, exclude=True, repr=False)
    experiment_id: str
    title: str
    description: str
    vision_ref: str
    config_path: str
    config_sha256: str
    config_canonical_sha256: str
    config: dict[str, Any]
    split: str
    started_at: str
    runtime_s: float
    limit_per_dataset: int | None
    datasets: list[DatasetSummary]
    runs: list[RunResult]
    framing: str = FRAMING
    notes: list[str] = Field(default_factory=lambda: [TASK_C_NOTE])
    disclaimer: str = DISCLAIMER


def _optional_hash(path: Path) -> str | None:
    return sha256_of_file(path) if path.is_file() else None


def _combine(values: list[str | None]) -> str | None:
    known = sorted({v for v in values if v is not None})
    if not known:
        return None
    return known[0] if len(known) == 1 else sha256_of_obj(known)


class _Case:
    """A selected development case with its index entry (``None`` if not indexed)."""

    def __init__(self, dataset: str, case_id: str, phase: Phase, entry: IndexEntry | None) -> None:
        self.dataset = dataset
        self.case_id = case_id
        self.phase = phase
        self.entry = entry


def _select(
    dataset: str, settings: Settings, limit: int | None, phases: list[str]
) -> tuple[list[_Case], DatasetSummary]:
    guard = CaseGuard.load(settings.data_dir, settings.manifests_dir, dataset)
    index = load_index(dataset, settings)
    development = guard.cases(Phase.DEVELOPMENT)
    outside = sum(1 for case_id in index if guard.phase_of(case_id) is None)
    wanted = {Phase(p) for p in phases}
    chosen = [c for c in development if guard.phase_of(c) in wanted][:limit]
    cases: list[_Case] = []
    for case_id in chosen:
        guard.check(case_id, Phase.DEVELOPMENT)
        phase = guard.phase_of(case_id)
        assert phase is not None  # noqa: S101 - checked development cases have a phase
        cases.append(_Case(dataset, case_id, phase, index.get(case_id)))
    summary = DatasetSummary(
        dataset=dataset,
        development_cases=len(development),
        selected_cases=len(chosen),
        indexed_development_cases=sum(1 for c in development if c in index),
        not_indexed=sum(1 for c in cases if c.entry is None),
        index_entries_outside_development=outside,
        index_sha256=sha256_of_file(index_path(settings, dataset)),
        split_manifest_sha256=_optional_hash(settings.manifests_dir / "splits" / f"{dataset}.json"),
        dataset_manifest_sha256=_optional_hash(
            settings.manifests_dir / "datasets" / f"{dataset}.json"
        ),
    )
    return cases, summary


def _base_outcome(case: _Case, labels: list[str]) -> dict[str, Any]:
    entry = case.entry
    return {
        "dataset": case.dataset,
        "case_id": case.case_id,
        "patient_id": entry.patient_id if entry else None,
        "phase": case.phase.value,
        "y_true": {lb: entry.reference.labels.get(lb) for lb in labels} if entry else {},
    }


def _from_result(base: dict[str, Any], result: AnalysisResult, labels: list[str]) -> CaseOutcome:
    report = result.report
    abstained = report.abstain or result.raw_error is not None
    return CaseOutcome(
        **base,
        status=CaseStatus.ABSTAINED if abstained else CaseStatus.SCORED,
        y_score={} if abstained else {lb: report.label_probability(lb) for lb in labels},
        positive_labels=[] if abstained else sorted(report.positive_labels()),
        parse_warnings=list(report.parse_warnings),
        error=result.raw_error,
        runtime_s=result.perf.total_s,
        stages_s=dict(result.perf.stages_s),
        fingerprint=result.provenance.fingerprint(),
        report=report,
    )


def _score(cases: list[CaseOutcome], loaded: LoadedExperiment) -> dict[str, Any]:
    cfg = loaded.config

    def record(c: CaseOutcome) -> ScoreRecord:
        return ScoreRecord(
            case_id=f"{c.dataset}:{c.case_id}",
            patient_id=f"{c.dataset}:{c.patient_id}",
            y_true=dict(c.y_true),
            y_score=dict(c.y_score),
            report=c.report,
        )

    scored = [record(c) for c in cases if c.status is CaseStatus.SCORED]
    answered = [record(c) for c in cases if c.status in {CaseStatus.SCORED, CaseStatus.ABSTAINED}]
    return {
        "n_scored": len(scored),
        "task_a": task_a(
            scored, cfg.labels, thresholds=cfg.thresholds, n_boot=cfg.n_boot, seed=cfg.seed
        ).to_dict(),
        "task_b": {k: v.to_dict() for k, v in task_b(scored, cfg.labels).items()},
        "task_e": task_e(scored).to_dict(),
        "task_g": task_g(answered),
    }


def _provenance(
    spec: RunSpec,
    loaded: LoadedExperiment,
    settings: Settings,
    summaries: list[DatasetSummary],
    per_case: list[RunProvenance],
) -> RunProvenance:
    return RunProvenance.collect(
        settings.repo_root,
        model_id=spec.model,
        model_hash=_combine([p.model_hash for p in per_case]),
        config_hash=loaded.file_sha256,
        prompt_hash=_combine([p.prompt_hash for p in per_case]),
        preprocess_hash=_combine([p.preprocess_hash for p in per_case]),
        seed=loaded.config.seed,
        scoring_hash=scoring_source_hash(),
        ground_truth_hash=sha256_of_obj({s.dataset: s.index_sha256 for s in summaries}),
        dataset_manifest_hash=sha256_of_obj(
            {s.dataset: [s.dataset_manifest_sha256, s.index_sha256] for s in summaries}
        ),
        split_manifest_hash=sha256_of_obj({s.dataset: s.split_manifest_sha256 for s in summaries}),
    )


def _input_identity(case: _Case, settings: Settings) -> dict[str, str | None] | None:
    if case.entry is None:
        return None
    folder = settings.data_dir / case.entry.path
    try:
        dataset, patient = guard_study_input(folder, settings)
        if (dataset, patient) != (case.dataset, case.entry.patient_id):
            raise SealedAccessError("Indexed study identity differs from guarded development input")
        return {
            "sha256": sha256_of_obj(
                {
                    sha256_of_obj(str(path.relative_to(folder))): sha256_of_file(path)
                    for path in sorted(folder.rglob("*"))
                    if path.is_file()
                }
            ),
            "error": None,
        }
    except SealedAccessError:
        raise
    except (OSError, ValueError) as exc:
        return {"sha256": None, "error": type(exc).__name__}


def _resume_identity(
    loaded: LoadedExperiment,
    settings: Settings,
    limit: int | None,
    selections: list[tuple[list[_Case], DatasetSummary]],
) -> dict[str, Any]:
    package = Path(__file__).resolve().parents[1]
    source_hash = sha256_of_obj(
        {
            str(path.relative_to(package)): sha256_of_file(path)
            for path in sorted(package.rglob("*"))
            if path.is_file() and path.suffix in {".py", ".yaml"}
        }
    )
    models: dict[str, Any] = {}
    runtime: dict[str, Any] = {}
    for spec in loaded.config.runs():
        model = load_model_config(spec.model, settings.configs_dir / "models")
        prompt = spec.prompt or model.prompt or "P3"
        models[spec.variant] = {
            "spec": spec.to_dict(),
            "model": model.model_dump(mode="json"),
            "model_file": sha256_of_file(settings.configs_dir / "models" / f"{spec.model}.yaml"),
            "prompt": prompt,
            "prompt_file": sha256_of_file(settings.configs_dir / "prompts" / f"{prompt}.yaml"),
        }
        if spec.model not in runtime:
            runtime[spec.model] = runtime_identity(model, settings)
    return {
        "schema_version": 1,
        "experiment_file": loaded.file_sha256,
        "experiment_canonical": loaded.canonical_sha256,
        "config": loaded.config.model_dump(mode="json"),
        "limit": limit,
        "models": models,
        "runtime_models": runtime,
        "source_hash": source_hash,
        "git_commit": git_state(settings.repo_root)[0],
        "dependencies": _optional_hash(package.parents[1] / "uv.lock"),
        "datasets": [summary.model_dump(mode="json") for _, summary in selections],
        "development_splits": {
            summary.dataset: sha256_of_file(settings.data_path("splits", f"{summary.dataset}.json"))
            for _, summary in selections
        },
        "registry": {
            summary.dataset: _optional_hash(
                settings.configs_dir / "datasets" / f"{summary.dataset}.yaml"
            )
            for _, summary in selections
        },
        "selected": [
            {
                "dataset": case.dataset,
                "case_id": case.case_id,
                "phase": case.phase.value,
                "entry": sha256_of_obj(case.entry.model_dump(mode="json")) if case.entry else None,
                "input": _input_identity(case, settings),
            }
            for cases, _ in selections
            for case in cases
        ],
    }


def _unit_key(case: _Case, spec: RunSpec) -> str:
    return sha256_of_obj([case.dataset, case.case_id, spec.variant])


def _resolved_spec(spec: RunSpec, model: dict[str, Any]) -> dict[str, Any]:
    return spec.to_dict() | {
        "prompt": model["prompt"],
        "view": model["model"]["view"],
        "view_params": {**model["model"]["view_params"], **spec.view_overrides},
    }


def run_experiment(
    loaded: LoadedExperiment,
    settings: Settings,
    *,
    limit: int | None = None,
    resume: Path | None = None,
    progress: Callable[[str], None] = lambda _msg: None,
    analyze: Analyzer = analyze_study,
    open_case: Callable[[IndexEntry, Settings], Study] = open_study,
) -> ExperimentResult:
    """Run/resume a guarded development invocation with durable terminal case artifacts.

    The explicit resume directory must match configuration, source, weights and input bytes.
    Failed, abstained and not-indexed units are terminal; retries need a new invocation.
    No sealed records are read. Persistence failures abort before any subsequent inference.
    """
    from thoraxbench.reports.html_report import require_results_path  # noqa: PLC0415

    invocation_started = time.perf_counter()
    cfg = loaded.config
    if sha256_of_file(loaded.path) != loaded.file_sha256:
        raise ValueError("Experiment identity mismatch: file changed after loading")
    if limit is not None and limit < 1:
        raise ValueError("Benchmark limit must be positive")
    base = settings.data_path("results", "benchmark", cfg.id)
    require_results_path(base / "preflight", settings)
    selections = [_select(ds, settings, limit, list(cfg.phases)) for ds in cfg.datasets]
    identity = _resume_identity(loaded, settings, limit, selections)
    if resume is None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        folder = base / f"{stamp}-{loaded.file_sha256[:12]}-{uuid4().hex}"
        require_results_path(folder / "manifest.json", settings)
        folder.mkdir(parents=True, exist_ok=False)
    else:
        folder = resume
        require_results_path(folder / "manifest.json", settings)
        if not folder.is_dir() or not folder.resolve().is_relative_to(base.resolve()):
            raise ValueError("Resume requires an existing invocation directory for this experiment")
    store = BenchmarkStore(folder, settings)
    with store.locked():
        store.initialize(identity, resume=resume is not None)
        progress(f"Invocation: {folder}")
        if store.state.status == "complete":
            expected = {
                _unit_key(case, spec)
                for cases, _ in selections
                for case in cases
                for spec in cfg.runs()
            }
            if set(store.state.units) != expected or set(store.state.outputs) != {
                "json",
                "markdown",
            }:
                raise ValueError("Completed checkpoint has incomplete unit/output accounting")
            result = ExperimentResult.model_validate_json(
                store.verify(store.state.outputs["json"]).read_text()
            )
            result.output_dir = folder
            return result
        return _execute(
            loaded, settings, selections, store, progress, analyze, open_case, invocation_started
        )


def _restore_unit(
    saved: dict[str, Any],
    base: dict[str, Any],
    spec: RunSpec,
    labels: list[str],
    model: dict[str, Any],
) -> tuple[CaseOutcome, RunProvenance | None]:
    try:
        if saved.get("runtime_identity_error"):
            raise ValueError("Case result came from a changed runtime model")
        request = AnalysisRequest(labels=list(labels), prompt_id=model["prompt"]).model_dump(
            mode="json"
        )
        if (
            saved["schema_version"] != 1
            or saved["resolved_spec"] != _resolved_spec(spec, model)
            or saved["request"] != request
        ):
            raise ValueError("Case artifact request/setup mismatch")
        outcome = CaseOutcome.model_validate(saved["outcome"])
        if any(getattr(outcome, key) != value for key, value in base.items()):
            raise ValueError("Case artifact selected identity mismatch")
        outcome.report = (
            FindingsReport.model_validate(saved["report"]) if saved["report"] is not None else None
        )
        if saved["analysis"] is None:
            if (
                outcome.status not in {CaseStatus.FAILED, CaseStatus.NOT_INDEXED}
                or outcome.report is not None
            ):
                raise ValueError("Case artifact is missing its analysis")
            return outcome, None
        restored = AnalysisResult.model_validate(saved["analysis"])
        expected = _from_result(base, restored, labels)
        if (
            restored.model_id != spec.model
            or restored.dataset != base["dataset"]
            or restored.case_id != base["case_id"]
            or restored.request.model_dump(mode="json") != request
            or expected.model_dump(mode="json") != outcome.model_dump(mode="json")
            or restored.report != outcome.report
        ):
            raise ValueError("Case artifact analysis/outcome mismatch")
        return outcome, restored.provenance
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid checkpointed case artifact") from exc


def _execute(  # noqa: PLR0912, PLR0915, PLR0917 - one ordered checkpoint transaction
    loaded: LoadedExperiment,
    settings: Settings,
    selections: list[tuple[list[_Case], DatasetSummary]],
    store: BenchmarkStore,
    progress: Callable[[str], None],
    analyze: Analyzer,
    open_case: Callable[[IndexEntry, Settings], Study],
    invocation_started: float,
) -> ExperimentResult:
    prior_runtime = store.state.active_runtime_s
    cfg, specs = loaded.config, loaded.config.runs()
    summaries = [summary for _, summary in selections]
    outcomes: dict[str, list[CaseOutcome]] = {s.variant: [] for s in specs}
    provenances: dict[str, list[RunProvenance]] = {s.variant: [] for s in specs}
    runtimes: dict[str, float] = dict.fromkeys(outcomes, 0.0)
    expected = {
        _unit_key(case, spec) for cases, _ in selections for case in cases for spec in specs
    }
    if set(store.state.units) - expected:
        raise ValueError("Checkpoint contains unexpected selected units")
    for cases, _ in selections:
        for case in cases:
            CaseGuard.load(settings.data_dir, settings.manifests_dir, case.dataset).check(
                case.case_id, Phase.DEVELOPMENT
            )
            base = _base_outcome(case, cfg.labels)
            study: Study | None = None
            load_error: str | None = None
            opened = False
            input_identity = next(
                value["input"]
                for value in store.identity["selected"]
                if (value["dataset"], value["case_id"]) == (case.dataset, case.case_id)
            )
            for spec in specs:
                key = _unit_key(case, spec)
                saved = store.load_unit(key)
                if saved is not None:
                    outcome, provenance = _restore_unit(
                        saved,
                        base,
                        spec,
                        cfg.labels,
                        store.identity["models"][spec.variant],
                    )
                    if provenance is not None:
                        provenances[spec.variant].append(provenance)
                    runtimes[spec.variant] += store.state.units[key].elapsed_s
                else:
                    if not opened and case.entry is not None:
                        opened = True
                        if not input_identity or input_identity["sha256"] is None:
                            load_error = "Study input identity could not be verified"
                        else:
                            try:
                                study = open_case(case.entry, settings)
                            except SealedAccessError:
                                raise
                            except RECOVERABLE as exc:
                                load_error = settings_redactor(settings).redact(
                                    f"study load failed: {exc}"
                                )
                    t_case = time.perf_counter()
                    analysis: AnalysisResult | None = None
                    if case.entry is None:
                        outcome = CaseOutcome(
                            **base,
                            status=CaseStatus.NOT_INDEXED,
                            error="development case missing from the index",
                        )
                    else:
                        evaluated = _run_case(
                            study, load_error, base, spec, settings, analyze, cfg.labels
                        )
                        if isinstance(evaluated, AnalysisResult):
                            analysis = evaluated
                            outcome = _from_result(base, analysis, cfg.labels)
                            provenances[spec.variant].append(analysis.provenance)
                        else:
                            outcome = evaluated
                    elapsed = time.perf_counter() - t_case
                    runtimes[spec.variant] += elapsed
                    chosen_prompt = store.identity["models"][spec.variant]["prompt"]
                    expected_digest = store.identity["runtime_models"][spec.model].get("digest")
                    actual_digest = analysis.provenance.model_hash if analysis else None
                    runtime_error = (
                        "Runtime model digest changed during this invocation"
                        if expected_digest and actual_digest and expected_digest != actual_digest
                        else None
                    )
                    if runtime_error:
                        outcome = outcome.model_copy(
                            update={
                                "status": CaseStatus.FAILED,
                                "y_score": {},
                                "positive_labels": [],
                                "error": runtime_error,
                            }
                        )
                    store.state.active_runtime_s = (
                        prior_runtime + time.perf_counter() - invocation_started
                    )
                    store.save_unit(
                        key,
                        {
                            "schema_version": 1,
                            "unit": key,
                            "resolved_spec": _resolved_spec(
                                spec, store.identity["models"][spec.variant]
                            ),
                            "request": AnalysisRequest(
                                labels=list(cfg.labels), prompt_id=chosen_prompt
                            ).model_dump(mode="json"),
                            "outcome": outcome.model_dump(mode="json"),
                            "report": outcome.report.model_dump(mode="json")
                            if outcome.report
                            else None,
                            "analysis": analysis.model_dump(mode="json") if analysis else None,
                            "runtime_identity_error": runtime_error,
                        },
                        elapsed,
                    )
                    if runtime_error:
                        raise RuntimeError(runtime_error)
                outcomes[spec.variant].append(outcome)
                progress(f"{case.dataset}/{case.case_id} [{spec.variant}]: {outcome.status.value}")
    runs = [
        RunResult(
            spec=spec.to_dict(),
            provenance=_provenance(spec, loaded, settings, summaries, provenances[spec.variant]),
            status_counts=_counts(outcomes[spec.variant]),
            phase_counts=_phase_counts(outcomes[spec.variant]),
            metrics=_score(outcomes[spec.variant], loaded),
            runtime_s=runtimes[spec.variant],
            cases=outcomes[spec.variant],
        )
        for spec in specs
    ]
    result = ExperimentResult(
        output_dir=store.folder,
        experiment_id=cfg.id,
        title=cfg.title,
        description=cfg.description,
        vision_ref=cfg.vision_ref,
        config_path=str(loaded.path),
        config_sha256=loaded.file_sha256,
        config_canonical_sha256=loaded.canonical_sha256,
        config=cfg.model_dump(mode="json"),
        split=cfg.split,
        started_at=store.state.started_at,
        runtime_s=prior_runtime + time.perf_counter() - invocation_started,
        limit_per_dataset=store.identity["limit"],
        datasets=summaries,
        runs=runs,
    )
    from thoraxbench.benchmark.report import render_markdown  # noqa: PLC0415 - report imports schema

    store.state.active_runtime_s = result.runtime_s
    store.finish(result.model_dump_json(indent=1) + "\n", render_markdown(result))
    return result


def _run_case(  # noqa: PLR0917 - private helper of the case loop
    study: Study | None,
    load_error: str | None,
    base: dict[str, Any],
    spec: RunSpec,
    settings: Settings,
    analyze: Analyzer,
    labels: list[str],
) -> AnalysisResult | CaseOutcome:
    if study is None:
        return CaseOutcome(**base, status=CaseStatus.FAILED, error=load_error)
    try:
        model_config = load_model_config(spec.model, settings.configs_dir / "models")
        chosen_prompt = spec.prompt or model_config.prompt or "P3"
        return analyze(
            study,
            spec.model,
            settings,
            request=AnalysisRequest(labels=list(labels), prompt_id=chosen_prompt),
            prompt_id=chosen_prompt,
            view_overrides=dict(spec.view_overrides),
        )
    except SealedAccessError:
        raise
    except RECOVERABLE as exc:
        return CaseOutcome(
            **base,
            status=CaseStatus.FAILED,
            error=settings_redactor(settings, study.identifiers).redact(
                f"{type(exc).__name__}: {exc}"
            ),
        )


def _counts(cases: list[CaseOutcome]) -> dict[str, int]:
    counts = Counter(c.status.value for c in cases)
    return {s.value: counts.get(s.value, 0) for s in CaseStatus}


def _phase_counts(cases: list[CaseOutcome]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for c in cases:
        bucket = out.setdefault(c.phase or "unknown", {s.value: 0 for s in CaseStatus})
        bucket[c.status.value] += 1
    return out
