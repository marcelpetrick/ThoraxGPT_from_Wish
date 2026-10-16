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

from pydantic import BaseModel, Field

from thoraxbench.adapters.base import load_model_config
from thoraxbench.analysis import DISCLAIMER, AnalysisResult, analyze_study
from thoraxbench.benchmark.config import LoadedExperiment, RunSpec
from thoraxbench.config import Settings
from thoraxbench.index import IndexEntry, index_path, load_index, open_study
from thoraxbench.provenance import RunProvenance, sha256_of_file, sha256_of_obj
from thoraxbench.schemas import AnalysisRequest, FindingsReport
from thoraxbench.scoring import CaseRecord as ScoreRecord
from thoraxbench.scoring import task_a, task_b, task_e, task_g
from thoraxbench.splits import CaseGuard, Phase, SealedAccessError
from thoraxbench.study import Study

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
        dataset_manifest_hash=sha256_of_obj(
            {s.dataset: [s.dataset_manifest_sha256, s.index_sha256] for s in summaries}
        ),
        split_manifest_hash=sha256_of_obj({s.dataset: s.split_manifest_sha256 for s in summaries}),
    )


def run_experiment(
    loaded: LoadedExperiment,
    settings: Settings,
    *,
    limit: int | None = None,
    progress: Callable[[str], None] = lambda _msg: None,
    analyze: Analyzer = analyze_study,
    open_case: Callable[[IndexEntry, Settings], Study] = open_study,
) -> ExperimentResult:
    """Run every model setup of *loaded* on the selected development cases and score them.

    Args:
        loaded: Parsed experiment configuration with its file hash.
        settings: Paths and endpoints.
        limit: Use at most this many development cases per dataset (split order, after
            the configured phase filter).
        progress: Receives one line per case and setup.
        analyze: Single-study analysis function (injectable for tests).
        open_case: Guarded study loader (injectable for tests).

    Raises:
        FileNotFoundError: if a split or index is missing.
        SealedAccessError: if any sealed or unknown case would be touched.
    """
    cfg = loaded.config
    started = datetime.now(UTC)
    t0 = time.perf_counter()
    specs = cfg.runs()
    selections = [_select(ds, settings, limit, list(cfg.phases)) for ds in cfg.datasets]
    summaries = [summary for _, summary in selections]
    outcomes: dict[str, list[CaseOutcome]] = {s.variant: [] for s in specs}
    provenances: dict[str, list[RunProvenance]] = {s.variant: [] for s in specs}
    runtimes: dict[str, float] = dict.fromkeys(outcomes, 0.0)
    for cases, _ in selections:
        for case in cases:
            base = _base_outcome(case, cfg.labels)
            if case.entry is None:
                for spec in specs:
                    outcomes[spec.variant].append(
                        CaseOutcome(
                            **base,
                            status=CaseStatus.NOT_INDEXED,
                            error="development case missing from the index",
                        )
                    )
                progress(f"{case.dataset}/{case.case_id}: not indexed")
                continue
            try:
                study: Study | None = open_case(case.entry, settings)
                load_error = None
            except SealedAccessError:
                raise
            except RECOVERABLE as exc:
                study, load_error = None, f"study load failed: {exc}"
            for spec in specs:
                t_case = time.perf_counter()
                outcome = _run_case(study, load_error, base, spec, settings, analyze, cfg.labels)
                runtimes[spec.variant] += time.perf_counter() - t_case
                if isinstance(outcome, AnalysisResult):
                    provenances[spec.variant].append(outcome.provenance)
                    outcome = _from_result(base, outcome, cfg.labels)
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
    return ExperimentResult(
        experiment_id=cfg.id,
        title=cfg.title,
        description=cfg.description,
        vision_ref=cfg.vision_ref,
        config_path=str(loaded.path),
        config_sha256=loaded.file_sha256,
        config_canonical_sha256=loaded.canonical_sha256,
        config=cfg.model_dump(mode="json"),
        split=cfg.split,
        started_at=started.isoformat(timespec="seconds"),
        runtime_s=time.perf_counter() - t0,
        limit_per_dataset=limit,
        datasets=summaries,
        runs=runs,
    )


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
        return CaseOutcome(**base, status=CaseStatus.FAILED, error=f"{type(exc).__name__}: {exc}")


def _counts(cases: list[CaseOutcome]) -> dict[str, int]:
    counts = Counter(c.status.value for c in cases)
    return {s.value: counts.get(s.value, 0) for s in CaseStatus}


def _phase_counts(cases: list[CaseOutcome]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for c in cases:
        bucket = out.setdefault(c.phase or "unknown", {s.value: 0 for s in CaseStatus})
        bucket[c.status.value] += 1
    return out
