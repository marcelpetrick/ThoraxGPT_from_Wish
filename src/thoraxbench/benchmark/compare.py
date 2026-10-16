# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Descriptive comparison of stored cohort results; never select a model winner."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

from thoraxbench.benchmark.cohort import CompletedRun
from thoraxbench.benchmark.runner import CaseStatus, RunResult
from thoraxbench.provenance import sha256_of_obj


@dataclass(frozen=True)
class Setup:
    """One experiment variant, with its immutable source invocation."""

    id: str
    source: CompletedRun
    run: RunResult


def setups(sources: list[CompletedRun]) -> list[Setup]:
    """Flatten variants without merging cases, filling predictions or recomputing scores."""
    return [
        Setup(f"S{index}", source, run)
        for index, (source, run) in enumerate(
            ((source, run) for source in sources for run in source.result.runs), start=1
        )
    ]


def _basis(setup: Setup) -> dict[str, Any]:
    identity, cfg = setup.source.identity, setup.source.result.config
    return {
        "selected cases, phases, source inputs and indexed references": sha256_of_obj(
            sorted(identity["selected"], key=lambda item: (item["dataset"], item["case_id"]))
        ),
        "development split identities": identity["development_splits"],
        "dataset manifest identities": {
            item.dataset: item.dataset_manifest_sha256 for item in setup.source.result.datasets
        },
        "requested labels": sorted(cfg["labels"]),
        "decision thresholds": {
            label: cfg["thresholds"].get(label, 0.5) for label in cfg["labels"]
        },
        "bootstrap configuration": {"n_boot": cfg["n_boot"], "seed": cfg["seed"]},
        "scoring source identity": setup.run.provenance.scoring_hash,
        "ground-truth identity": setup.run.provenance.ground_truth_hash,
    }


def _unknowns(setup: Setup) -> list[str]:
    unknown: list[str] = []
    if not setup.run.provenance.scoring_hash:
        unknown.append("scoring source identity unavailable")
    if not setup.run.provenance.ground_truth_hash:
        unknown.append("ground-truth identity unavailable")
    if any(
        item["entry"] is not None and (not item["input"] or not item["input"].get("sha256"))
        for item in setup.source.identity["selected"]
    ):
        unknown.append("selected source-input identity unavailable")
    model = setup.source.identity["models"][setup.run.spec["variant"]]["model"]
    if model["adapter"] != "heuristic" and not setup.run.provenance.model_hash:
        unknown.append("actual model weight identity unavailable")
    return unknown


def _resolved_factors(setup: Setup) -> dict[str, Any]:
    """Separate effective experimental definitions from variant names and source pixels."""
    identity = setup.source.identity
    resolved = identity["models"][setup.run.spec["variant"]]
    model = resolved["model"]
    runtime = identity["runtime_models"].get(setup.run.spec["model"], {})
    return {
        "model": {
            key: value
            for key, value in model.items()
            if key not in {"notes", "license", "tier", "prompt", "view", "view_params"}
        },
        "runtime_weights": runtime.get("digest"),
        "actual_weights": setup.run.provenance.model_hash,
        "prompt": {
            "id": resolved["prompt"],
            "file_hash": resolved.get("prompt_file"),
            "actual_hash": setup.run.provenance.prompt_hash,
        },
        "prepared_definition": {
            "view": model["view"],
            "parameters": {**model["view_params"], **setup.run.spec["view_overrides"]},
            "preprocess_hash": setup.run.provenance.preprocess_hash,
        },
    }


def _source_inputs(setup: Setup) -> list[dict[str, Any]]:
    return sorted(
        [
            {"dataset": item["dataset"], "case_id": item["case_id"], "input": item["input"]}
            for item in setup.source.identity["selected"]
        ],
        key=lambda item: (item["dataset"], item["case_id"]),
    )


def comparison_details(items: list[Setup]) -> list[dict[str, Any]]:
    """List pairwise compatibility and matched available prediction denominators.

    Setup/model/prompt/prepared-view differences are experimental factors. They do not
    change source-cohort identity. Scores are reported verbatim; no ranking is produced.
    """
    comparisons: list[dict[str, Any]] = []
    for left, right in combinations(items, 2):
        a, b = _basis(left), _basis(right)
        left_factors, right_factors = _resolved_factors(left), _resolved_factors(right)
        reasons = [key for key in a if a[key] != b[key]]
        reasons += sorted(set(_unknowns(left) + _unknowns(right)))
        left_cases = {(case.dataset, case.case_id): case for case in left.run.cases}
        right_cases = {(case.dataset, case.case_id): case for case in right.run.cases}
        common = set(left_cases) & set(right_cases)
        labels = sorted(
            set(left.source.result.config["labels"]) & set(right.source.result.config["labels"])
        )
        paired = {
            label: sum(
                left_cases[key].status == right_cases[key].status == CaseStatus.SCORED
                and left_cases[key].y_true.get(label) is not None
                and left_cases[key].y_true.get(label) == right_cases[key].y_true.get(label)
                and left_cases[key].y_score.get(label) is not None
                and right_cases[key].y_score.get(label) is not None
                for key in common
            )
            for label in labels
        }
        comparisons.append(
            {
                "left": left.id,
                "right": right.id,
                "comparable": not reasons,
                "differences": reasons,
                "shared_selected_cases": len(common),
                "paired_available_predictions": paired,
                "experimental_factors": {
                    "model_or_prompt_or_view": left_factors != right_factors,
                    "source_study_inputs": _source_inputs(left) != _source_inputs(right),
                    "prepared_input_definition": left_factors["prepared_definition"]
                    != right_factors["prepared_definition"],
                    "package_source": left.source.identity["source_hash"]
                    != right.source.identity["source_hash"],
                },
            }
        )
    return comparisons
