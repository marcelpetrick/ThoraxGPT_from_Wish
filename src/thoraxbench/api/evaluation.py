# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Read-only Evaluation view over stored development benchmark invocations.

Nothing here starts inference, writes files, re-renders images or reads raw studies. Every
completed invocation passes :func:`thoraxbench.benchmark.cohort.load_completed_run`, which
re-checks the current development split guard before any case artifact is read. Rows whose
phase is not a development phase are skipped and counted, never shown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thoraxbench.analysis import DISCLAIMER, AnalysisResult
from thoraxbench.benchmark.checkpoint import BenchmarkStore
from thoraxbench.benchmark.cohort import CompletedRun, load_completed_run
from thoraxbench.benchmark.compare import comparison_details, setups
from thoraxbench.benchmark.runner import CaseOutcome
from thoraxbench.config import Settings
from thoraxbench.provenance import sha256_of_obj
from thoraxbench.reports.html_report import require_results_path

SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}")
DEVELOPMENT_PHASES = frozenset({"calibration", "internal_test"})
# Engine wording from thoraxbench.analysis._check_image_evidence; a unit test pins it.
REFERENCES_REMOVED = "invalid or duplicate image references removed"
UNSUPPORTED_POSITIVE = "positive has no valid attached-image evidence"
MAX_COMPARED_RUNS = 8
FRAMING = (
    "Stored development-split results only. This view never starts inference and never "
    "reads sealed cases. Scores are uncalibrated pipeline measurements, not clinical "
    "accuracy; abstentions and failures stay explicit."
)


class EvaluationError(Exception):
    """A refused or unavailable request, with an HTTP status and a fixed safe message."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class _Loaded:
    source: CompletedRun
    rows: list[dict[str, Any]]
    units: dict[str, dict[str, Any]]
    skipped: int


def _component(value: str) -> str:
    if SAFE_COMPONENT.fullmatch(value) is None:
        raise EvaluationError(422, "Invalid experiment, run, variant, dataset or case identifier")
    return value


def presence(probability: float | None) -> str:
    """Return the display presence code for an implied presence probability."""
    if probability is None:
        return "unavailable"
    return "present" if probability >= 0.5 else "absent"


def evidence_verdict(analysis: AnalysisResult | None) -> str:  # noqa: PLR0911 - ordered verdicts
    """Classify the evidence-reference check of one stored case; never infer locations.

    Valid one-based references are bounds-checked numbers, not proof of visual correctness.
    The HU baseline sends no model images; its references are zero-based source slices.
    """
    if analysis is None:
        return "not_run"
    report = analysis.report
    if report.abstain or analysis.raw_error is not None:
        return "abstained"
    count = analysis.perf.n_images or 0
    if count == 0:
        return "source_slices_only"
    if any(UNSUPPORTED_POSITIVE in warning for warning in report.parse_warnings):
        return "unsupported_positive_removed"
    if any(REFERENCES_REMOVED in warning for warning in report.parse_warnings):
        return "invalid_references_removed"
    positives = [
        finding
        for finding in report.findings
        if (probability := finding.presence_probability()) is not None and probability >= 0.5
    ]
    if not positives:
        return "no_positive_findings"
    if all(
        finding.evidence_images and all(1 <= item <= count for item in finding.evidence_images)
        for finding in positives
    ):
        return "valid_references"
    return "missing_references"


def _metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    task_a, task_e, task_g = (metrics.get(key) or {} for key in ("task_a", "task_e", "task_g"))
    return {
        "n_scored": metrics.get("n_scored"),
        "macro_f1": task_a.get("macro_f1"),
        "macro_auroc": task_a.get("macro_auroc"),
        "prediction_coverage": task_e.get("prediction_coverage"),
        "abstention_rate": task_g.get("abstention_rate"),
    }


def _row(
    variant: str, model: str, case: CaseOutcome, analysis: AnalysisResult | None
) -> dict[str, Any]:
    return {
        "variant": variant,
        "model": model,
        "dataset": case.dataset,
        "case_id": case.case_id,
        "phase": case.phase,
        "status": case.status.value,
        "reference": dict(case.y_true),
        "prediction": dict(case.y_score),
        "positive_labels": list(case.positive_labels),
        "warnings": list(case.parse_warnings),
        "error": case.error,
        "evidence": evidence_verdict(analysis),
        "sent_images": analysis.perf.n_images if analysis is not None else None,
    }


class Evaluation:
    """Validate and summarize stored invocations below ``data/results/benchmark``."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: dict[Path, tuple[tuple[int, int], _Loaded]] = {}

    @property
    def root(self) -> Path:
        """Return the ignored benchmark results directory."""
        return self.settings.data_path("results", "benchmark")

    def _folder(self, experiment: str, run: str) -> Path:
        folder = self.root / _component(experiment) / _component(run)
        try:
            require_results_path(folder / "manifest.json", self.settings)
        except ValueError as exc:
            raise EvaluationError(404, "Unknown benchmark run") from exc
        if (
            (self.root / experiment).is_symlink()
            or folder.is_symlink()
            or not folder.is_dir()
            or not folder.resolve().is_relative_to(self.root.resolve())
        ):
            raise EvaluationError(404, "Unknown benchmark run")
        return folder

    def _load(self, folder: Path) -> _Loaded:
        checkpoint = folder / "checkpoint.json"
        try:
            stat = checkpoint.stat()
        except OSError as exc:
            raise EvaluationError(409, "Run has no checkpoint; legacy runs cannot open") from exc
        key = (stat.st_mtime_ns, stat.st_size)
        cached = self._cache.get(folder)
        if cached is not None and cached[0] == key:
            return cached[1]
        try:
            source = load_completed_run(folder, self.settings)
        except PermissionError as exc:
            raise EvaluationError(
                403, "Refused: the stored selection fails the current development split guard"
            ) from exc
        except (ValueError, OSError) as exc:
            raise EvaluationError(
                409, "Only complete, integrity-checked development runs can open"
            ) from exc
        store = BenchmarkStore(folder, self.settings)
        store.state = source.checkpoint
        rows: list[dict[str, Any]] = []
        units: dict[str, dict[str, Any]] = {}
        skipped = 0
        for run in source.result.runs:
            variant, model = run.spec["variant"], run.spec["model"]
            for case in run.cases:
                if case.phase not in DEVELOPMENT_PHASES:
                    skipped += 1
                    continue
                unit_key = sha256_of_obj([case.dataset, case.case_id, variant])
                payload = store.load_unit(unit_key) or {}
                analysis = (
                    AnalysisResult.model_validate(payload["analysis"])
                    if payload.get("analysis") is not None
                    else None
                )
                rows.append(_row(variant, model, case, analysis))
                units[f"{variant}\0{case.dataset}\0{case.case_id}"] = payload
        loaded = _Loaded(source, rows, units, skipped)
        if len(self._cache) >= 16:
            self._cache.pop(next(iter(self._cache)))
        self._cache[folder] = (key, loaded)
        return loaded

    def _summary(self, folder: Path, loaded: _Loaded) -> dict[str, Any]:
        result = loaded.source.result
        variants = [
            {
                "variant": run.spec["variant"],
                "model": run.spec["model"],
                "prompt": loaded.source.identity["models"][run.spec["variant"]]["prompt"],
                "cases": len(run.cases),
                "status_counts": dict(run.status_counts),
                "metrics": _metrics(run.metrics),
            }
            for run in result.runs
        ]
        totals: dict[str, int] = {}
        for item in variants:
            for status, count in item["status_counts"].items():
                totals[status] = totals.get(status, 0) + count
        return {
            "experiment": folder.parent.name,
            "run": folder.name,
            "state": "complete",
            "experiment_id": result.experiment_id,
            "title": result.title,
            "config_sha256": result.config_sha256,
            "started_at": result.started_at,
            "runtime_s": result.runtime_s,
            "split": result.split,
            "phases": list(result.config.get("phases", [])),
            "labels": list(result.config.get("labels", [])),
            "datasets": [item.dataset for item in result.datasets],
            "variants": variants,
            "status_counts": totals,
            "skipped_non_development": loaded.skipped,
        }

    def _unopened(self, folder: Path, error: EvaluationError) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "experiment": folder.parent.name,
            "run": folder.name,
            "state": "refused" if error.status == 403 else "unavailable",
            "detail": error.message,
            "config_sha256": None,
            "started_at": None,
            "variants": [],
            "status_counts": {},
            "completed_units": None,
        }
        parts = folder.name.split("-")
        if len(parts) >= 3 and re.fullmatch(r"[0-9a-f]{12}", parts[1]):
            entry["config_sha256"] = parts[1]
        try:
            checkpoint = BenchmarkStore(folder, self.settings).read_checkpoint()
        except OSError, ValueError:
            return entry
        entry["started_at"] = checkpoint.started_at
        entry["completed_units"] = len(checkpoint.units)
        if checkpoint.status == "running":
            entry["state"] = "incomplete"
            entry["detail"] = "Run is incomplete; only completed runs can open"
        return entry

    def runs(self) -> dict[str, Any]:
        """List every invocation folder; unopenable ones keep an explicit reason."""
        entries: list[dict[str, Any]] = []
        ignored = 0
        root = self.root
        experiments = sorted(root.iterdir()) if root.is_dir() and not root.is_symlink() else []
        for experiment in experiments:
            if (
                experiment.is_symlink()
                or not experiment.is_dir()
                or not SAFE_COMPONENT.fullmatch(experiment.name)
            ):
                ignored += 1
                continue
            for folder in sorted(experiment.iterdir()):
                if (
                    folder.is_symlink()
                    or not folder.is_dir()
                    or not SAFE_COMPONENT.fullmatch(folder.name)
                ):
                    ignored += 1
                    continue
                try:
                    entries.append(self._summary(folder, self._load(folder)))
                except EvaluationError as error:
                    entries.append(self._unopened(folder, error))
        entries.sort(key=lambda item: item["started_at"] or "", reverse=True)
        return {
            "runs": entries,
            "ignored_entries": ignored,
            "framing": FRAMING,
            "disclaimer": DISCLAIMER,
        }

    def run(self, experiment: str, run: str) -> dict[str, Any]:
        """Return one completed run's summary and its per-case development rows."""
        folder = self._folder(experiment, run)
        loaded = self._load(folder)
        return self._summary(folder, loaded) | {
            "cases": loaded.rows,
            "framing": FRAMING,
            "disclaimer": DISCLAIMER,
        }

    def case(
        self, experiment: str, run: str, variant: str, dataset: str, case_id: str
    ) -> dict[str, Any]:
        """Return one stored case/variant unit: response, parsed report and evidence check."""
        folder = self._folder(experiment, run)
        loaded = self._load(folder)
        key = f"{_component(variant)}\0{_component(dataset)}\0{_component(case_id)}"
        if key not in loaded.units:
            raise EvaluationError(404, "Unknown or non-development case")
        payload = loaded.units[key]
        row = next(
            item
            for item in loaded.rows
            if (item["variant"], item["dataset"], item["case_id"]) == (variant, dataset, case_id)
        )
        raw = payload.get("analysis")
        analysis = AnalysisResult.model_validate(raw) if raw is not None else None
        spec = payload.get("resolved_spec") or {}
        detail: dict[str, Any] = row | {
            "experiment": experiment,
            "run": run,
            "prompt": spec.get("prompt"),
            "view": spec.get("view"),
            "view_params": spec.get("view_params") or {},
            "requested_labels": (payload.get("request") or {}).get("labels", []),
            "images": {
                "stored": bool(isinstance(raw, dict) and raw.get("prepared_images")),
                "sent_count": analysis.perf.n_images if analysis is not None else None,
                "captions": list(analysis.image_captions) if analysis is not None else [],
                "source_slice_indices": list(analysis.slice_indices) if analysis else [],
            },
            "findings": [],
            "response": None,
            "disclaimer": DISCLAIMER,
        }
        if analysis is not None:
            count = analysis.perf.n_images or 0
            detail["findings"] = [
                {
                    "label": finding.label,
                    "presence": presence(finding.presence_probability()),
                    "score": finding.presence_probability(),
                    "evidence_images": list(finding.evidence_images),
                    "evidence_kind": "model_images" if count else "source_slices",
                    "in_range": all(1 <= item <= count for item in finding.evidence_images)
                    if count
                    else None,
                }
                for finding in analysis.report.findings
            ]
            detail["response"] = {
                "raw_text": analysis.raw_text,
                "raw_error": analysis.raw_error,
                "parsed": analysis.report.model_dump(mode="json"),
                "context_sent": analysis.context,
                "engine_s": analysis.perf.total_s,
            }
        return detail

    def compare(self, selected: list[str]) -> dict[str, Any]:
        """Compare stored setups with the existing descriptive comparison; no ranking."""
        if not 1 <= len(selected) <= MAX_COMPARED_RUNS or len(set(selected)) != len(selected):
            raise EvaluationError(422, "Select one to eight distinct runs")
        sources: list[CompletedRun] = []
        names: list[tuple[str, str]] = []
        for item in selected:
            experiment, separator, run = item.partition("/")
            if not separator:
                raise EvaluationError(422, "Use experiment/run identifiers")
            sources.append(self._load(self._folder(experiment, run)).source)
            names.append((experiment, run))
        items = setups(sources)
        return {
            "setups": [
                {
                    "id": item.id,
                    "experiment": names[sources.index(item.source)][0],
                    "run": names[sources.index(item.source)][1],
                    "variant": item.run.spec["variant"],
                    "model": item.run.spec["model"],
                    "status_counts": dict(item.run.status_counts),
                    "metrics": _metrics(item.run.metrics),
                }
                for item in items
            ],
            "comparisons": comparison_details(items),
            "framing": FRAMING,
            "disclaimer": DISCLAIMER,
        }
