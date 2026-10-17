# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Read-only, development-guarded validation of completed benchmark invocations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thoraxbench.analysis import AnalysisResult
from thoraxbench.benchmark.checkpoint import BenchmarkStore, Checkpoint
from thoraxbench.benchmark.config import ExperimentConfig
from thoraxbench.benchmark.runner import CaseOutcome, CaseStatus, ExperimentResult, RunResult
from thoraxbench.config import Settings
from thoraxbench.provenance import sha256_of_file, sha256_of_obj
from thoraxbench.schemas import FindingsReport
from thoraxbench.splits import CaseGuard, Phase


@dataclass(frozen=True)
class CompletedRun:
    """Validated stored research results; no CT images, raw studies or runtime access."""

    folder: Path
    identity: dict[str, Any]
    checkpoint: Checkpoint
    result: ExperimentResult
    source_hashes: dict[str, str]


def _manifest(store: BenchmarkStore) -> dict[str, Any]:
    envelope = json.loads(store.path("manifest.json").read_text(encoding="utf-8"))
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError("Invalid benchmark manifest envelope")
    payload: dict[str, Any] = envelope["payload"]
    if envelope.get("sha256") != sha256_of_obj(payload):
        raise ValueError("Benchmark manifest checksum mismatch")
    return payload


def _guard_selection(identity: dict[str, Any], cfg: ExperimentConfig, settings: Settings) -> None:
    guards: dict[str, CaseGuard] = {}
    seen: set[tuple[str, str]] = set()
    datasets = [*cfg.datasets, *[item["dataset"] for item in identity["selected"]]]
    if any(
        not isinstance(dataset, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", dataset) is None
        for dataset in datasets
    ):
        raise ValueError("Invalid dataset identifier in stored experiment")
    for dataset in cfg.datasets:
        guards[dataset] = CaseGuard.load(settings.data_dir, settings.manifests_dir, dataset)
    for selected in identity["selected"]:
        key = selected["dataset"], selected["case_id"]
        if key in seen or selected["dataset"] not in guards:
            raise ValueError("Invalid or duplicate stored cohort selection")
        seen.add(key)
        guard = guards[selected["dataset"]]
        guard.check(selected["case_id"], Phase.DEVELOPMENT)
        phase = guard.phase_of(selected["case_id"])
        if phase is None or phase.value != selected["phase"] or phase.value not in cfg.phases:
            raise ValueError("Stored cohort phase no longer matches the development split")


def _validate_case(
    store: BenchmarkStore,
    key: str,
    summary: CaseOutcome,
    run: RunResult,
    identity: dict[str, Any],
    *,
    labels: list[str],
) -> None:
    payload = store.load_unit(key)
    if (
        payload is None
        or payload.get("schema_version") != 1
        or payload.get("runtime_identity_error")
    ):
        raise ValueError("Invalid completed benchmark case artifact")
    outcome = CaseOutcome.model_validate(payload["outcome"])
    if outcome.model_dump(mode="json") != summary.model_dump(mode="json"):
        raise ValueError("Case artifact differs from its final result summary")
    model = identity["models"][run.spec["variant"]]
    expected_spec = run.spec | {
        "prompt": model["prompt"],
        "view": model["model"]["view"],
        "view_params": {**model["model"]["view_params"], **run.spec["view_overrides"]},
    }
    if payload["resolved_spec"] != expected_spec or payload["request"]["labels"] != labels:
        raise ValueError("Case artifact setup or requested labels differ from its manifest")
    if payload["request"]["prompt_id"] != model["prompt"]:
        raise ValueError("Case artifact prompt differs from its manifest")
    if payload["analysis"] is None:
        if (
            outcome.status not in {CaseStatus.FAILED, CaseStatus.NOT_INDEXED}
            or payload["report"] is not None
        ):
            raise ValueError("Completed case is missing its analysis")
        return
    analysis = AnalysisResult.model_validate(payload["analysis"])
    report = FindingsReport.model_validate(payload["report"])
    if (
        analysis.report != report
        or analysis.request.model_dump(mode="json") != payload["request"]
        or (analysis.dataset, analysis.case_id, analysis.model_id)
        != (outcome.dataset, outcome.case_id, run.spec["model"])
    ):
        raise ValueError("Case analysis identity/report differs from its outcome")
    abstained = report.abstain or analysis.raw_error is not None
    if (
        (abstained and outcome.y_score)
        or (not abstained and set(outcome.y_score) != set(labels))
        or outcome.status != (CaseStatus.ABSTAINED if abstained else CaseStatus.SCORED)
    ):
        raise ValueError("Case prediction availability differs from its final outcome")


def load_completed_run(  # noqa: PLR0912 - validate the complete stored contract before export
    folder: Path,
    settings: Settings,
) -> CompletedRun:
    """Load only checkpointed development outputs, guarding selection before artifact reads.

    Historical non-checkpointed summaries lack the integrity/cohort contract and are refused.
    Current code, raw studies, model servers and inference are deliberately not consulted.
    """
    root = settings.data_path("results", "benchmark").resolve()
    if not folder.resolve().is_relative_to(root) or not folder.is_dir():
        raise ValueError("Expected a completed invocation under ignored data/results/benchmark")
    store = BenchmarkStore(folder, settings)
    try:
        identity = _manifest(store)
        if identity.get("schema_version") != 1:
            raise ValueError("Unsupported benchmark manifest version")
        cfg = ExperimentConfig.model_validate(identity["config"])
        if identity["experiment_canonical"] != sha256_of_obj(identity["config"]):
            raise ValueError("Stored experiment canonical hash mismatch")
        _guard_selection(identity, cfg, settings)
        store.state = store.read_checkpoint()
        if store.state.status != "complete" or set(store.state.outputs) != {"json", "markdown"}:
            raise ValueError("Only completed checkpointed invocations can be exported")
        if store.state.identity_sha256 != sha256_of_obj(identity):
            raise ValueError("Checkpoint and manifest identity differ")
        expected_keys = {
            sha256_of_obj([item["dataset"], item["case_id"], spec.variant])
            for item in identity["selected"]
            for spec in cfg.runs()
        }
        if set(store.state.units) != expected_keys:
            raise ValueError("Completed invocation has incomplete case accounting")
        result_path = store.verify(store.state.outputs["json"])
        store.verify(store.state.outputs["markdown"])
        result = ExperimentResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        if (
            result.split != "development"
            or result.experiment_id != cfg.id
            or result.config != identity["config"]
            or result.config_sha256 != identity["experiment_file"]
            or result.config_canonical_sha256 != identity["experiment_canonical"]
            or result.limit_per_dataset != identity["limit"]
            or [item.model_dump(mode="json") for item in result.datasets] != identity["datasets"]
            or [item.spec for item in result.runs] != [spec.to_dict() for spec in cfg.runs()]
        ):
            raise ValueError("Final result differs from its checkpoint manifest")
        selection = {(item["dataset"], item["case_id"]): item for item in identity["selected"]}
        for run in result.runs:
            if len(run.cases) != len(selection) or {
                (c.dataset, c.case_id) for c in run.cases
            } != set(selection):
                raise ValueError("Run summary does not contain the selected cohort exactly once")
            for case in run.cases:
                if case.phase != selection[case.dataset, case.case_id]["phase"]:
                    raise ValueError("Case summary phase differs from its selection")
                key = sha256_of_obj([case.dataset, case.case_id, run.spec["variant"]])
                _validate_case(store, key, case, run, identity, labels=cfg.labels)
        return CompletedRun(
            folder,
            identity,
            store.state,
            result,
            {
                "manifest": sha256_of_file(store.path("manifest.json")),
                "checkpoint": sha256_of_file(store.path("checkpoint.json")),
                "result": store.state.outputs["json"].sha256,
            },
        )
    except FileNotFoundError as exc:
        raise ValueError(
            "Missing checkpoint/artifact; legacy and incomplete outputs cannot be exported"
        ) from exc
    except (KeyError, TypeError) as exc:
        raise ValueError("Malformed completed benchmark invocation") from exc
