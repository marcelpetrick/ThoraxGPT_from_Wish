# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Experiment configuration parsing, variant resolution and report rendering."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from thoraxbench.benchmark import (
    CaseOutcome,
    CaseStatus,
    DatasetSummary,
    ExperimentConfig,
    ExperimentResult,
    RunResult,
    load_experiment,
    render_markdown,
)
from thoraxbench.benchmark.runner import _combine
from thoraxbench.config import REPO_ROOT
from thoraxbench.provenance import RunProvenance
from thoraxbench.splits.guard import config_sha256

BASE: dict[str, Any] = {
    "id": "T1",
    "model": "heuristic-hu",
    "datasets": ["lidc_idri"],
    "labels": ["pulmonary_nodule"],
}


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "exp.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "path", sorted((REPO_ROOT / "configs" / "experiments").glob("*.yaml")), ids=lambda p: p.name
)
def test_repository_experiments_validate(path: Path) -> None:
    loaded = load_experiment(path)
    assert loaded.file_sha256 == config_sha256(path)
    assert loaded.config.split == "development"
    assert path.read_text(encoding="utf-8").startswith("# SPDX-License-Identifier:")
    assert loaded.config.runs()


def test_repository_has_e001_to_e004() -> None:
    ids = {
        load_experiment(p).config.id for p in (REPO_ROOT / "configs" / "experiments").glob("*.yaml")
    }
    assert {"E000", "E001", "E002", "E003", "E004"} <= ids


def test_base_run_and_defaults(tmp_path: Path) -> None:
    loaded = load_experiment(_write(tmp_path, BASE))
    cfg = loaded.config
    assert cfg.phases == ["calibration", "internal_test"]
    assert cfg.n_boot == 1000
    (run,) = cfg.runs()
    assert run.to_dict() == {
        "variant": "base",
        "model": "heuristic-hu",
        "prompt": None,
        "view_overrides": {},
    }
    assert len(loaded.canonical_sha256) == 64


def test_variants_inherit_and_override() -> None:
    cfg = ExperimentConfig.model_validate(
        BASE
        | {
            "prompt": "P3",
            "view_overrides": {"strategy": "anatomy", "n": 24},
            "variants": [
                {"id": "a", "view_overrides": {"n": 8}},
                {"id": "b", "model": "medgemma1.5-q8", "prompt": "P0"},
            ],
        }
    )
    a, b = cfg.runs()
    assert (a.model, a.prompt, a.view_overrides) == (
        "heuristic-hu",
        "P3",
        {"strategy": "anatomy", "n": 8},
    )
    assert (b.model, b.prompt, b.view_overrides) == (
        "medgemma1.5-q8",
        "P0",
        {"strategy": "anatomy", "n": 24},
    )


@pytest.mark.parametrize(
    ("extra", "match"),
    [
        ({"variants": [{"id": "x"}, {"id": "x"}]}, "variant ids must be unique"),
        ({"thresholds": {"pulmonary_mass": 0.4}}, "thresholds for unscored labels"),
        ({"datasets": ["lidc_idri", "lidc_idri"]}, "datasets must be unique"),
        ({"split": "sealed"}, "split"),
        ({"phases": ["sealed"]}, "phases"),
        ({"id": "../escape"}, "id"),
        ({"labels": []}, "labels"),
        ({"unknown_key": 1}, "unknown_key"),
        ({"n_boot": -1}, "n_boot"),
    ],
)
def test_invalid_configs_rejected(extra: dict[str, Any], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        ExperimentConfig.model_validate(BASE | extra)


def test_non_mapping_yaml_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be a YAML mapping"):
        load_experiment(_write(tmp_path, ["not", "a", "mapping"]))


def test_combine_hashes() -> None:
    assert _combine([None, None]) is None
    assert _combine(["a", None, "a"]) == "a"
    combined = _combine(["b", "a"])
    assert combined is not None
    assert len(combined) == 64
    assert combined == _combine(["a", "b"])


def _result(cases: list[CaseOutcome], metrics: dict[str, Any]) -> ExperimentResult:
    run = RunResult(
        spec={"variant": "base", "model": "m", "prompt": None, "view_overrides": {}},
        provenance=RunProvenance(config_hash="c"),
        status_counts={"scored": 1, "failed": 1},
        phase_counts={},
        metrics=metrics,
        runtime_s=0.5,
        cases=cases,
    )
    return ExperimentResult(
        experiment_id="T1",
        title="",
        description="",
        vision_ref="",
        config_path="exp.yaml",
        config_sha256="c",
        config_canonical_sha256="d",
        config={},
        split="development",
        started_at="2026-10-15T00:00:00+00:00",
        runtime_s=1.0,
        limit_per_dataset=None,
        datasets=[
            DatasetSummary(
                dataset="lidc_idri",
                development_cases=2,
                selected_cases=2,
                indexed_development_cases=2,
                not_indexed=0,
                index_entries_outside_development=0,
                index_sha256="i",
                split_manifest_sha256=None,
                dataset_manifest_sha256=None,
            )
        ],
        runs=[run],
    )


def test_render_markdown_handles_missing_values() -> None:
    label = {
        "label": "pulmonary_nodule",
        "n": 1,
        "n_positive": 1,
        "auroc": None,
        "counts": None,
        "ci95": {"sensitivity": [0.25, 1.0]},
        "notes": [],
        "sensitivity": 1.0,
    }
    metrics = {
        "task_a": {
            "macro_f1": None,
            "micro_f1": None,
            "macro_auroc": None,
            "per_label": {"pulmonary_nodule": label},
        },
        "task_b": {"pulmonary_nodule": {"n": 1, "brier": 0.1, "ece": None, "nll": None}},
        "task_e": {
            "label_agreement": None,
            "agreements": 0,
            "contradictions": 0,
            "omissions": 0,
            "hallucinated_positives": 0,
            "reference_labels": 0,
        },
        "task_g": {
            "abstention_rate": None,
            "high_confidence_error_rate": None,
            "high_confidence_decisions": 0,
            "false_reassurance_rate": None,
            "fabricated_measurement_rate": None,
        },
    }
    cases = [
        CaseOutcome(
            dataset="lidc_idri",
            case_id="P1",
            phase="calibration",
            status=CaseStatus.SCORED,
            y_true={"pulmonary_nodule": True, "pulmonary_mass": None},
            positive_labels=["pulmonary_nodule"],
        ),
        CaseOutcome(
            dataset="lidc_idri", case_id="P2", status=CaseStatus.FAILED, error="bad | pipe"
        ),
    ]
    text = render_markdown(_result(cases, metrics))
    assert "Research use only" in text
    assert "not clinical accuracy" in text
    assert "[0.250, 1.000]" in text
    assert "n/a" in text
    assert "pulmonary_nodule=True" in text
    assert "bad / pipe" in text
    assert "| lidc_idri | P2 | - | failed | - | - |" in text
    assert "Benchmark T1: untitled" in text
