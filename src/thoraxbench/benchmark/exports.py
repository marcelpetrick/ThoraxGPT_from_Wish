# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Offline cohort tables with provenance, pseudonyms and spreadsheet-safe CSV cells."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any
from uuid import uuid4

from thoraxbench import __version__
from thoraxbench.analysis import DISCLAIMER
from thoraxbench.benchmark.checkpoint import BenchmarkStore
from thoraxbench.benchmark.cohort import CompletedRun, load_completed_run
from thoraxbench.benchmark.compare import Setup, comparison_details, setups
from thoraxbench.config import Settings
from thoraxbench.provenance import git_state, sha256_of_file, sha256_of_obj
from thoraxbench.reports.html_report import REPORT_STYLE, require_results_path


def _flatten(value: Any, prefix: str = "") -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in sorted(value.items()):
            yield from _flatten(item, f"{prefix}.{key}" if prefix else str(key))
    else:
        yield prefix, value


def metric_rows(items: list[Setup]) -> list[list[Any]]:
    """Return stored metrics verbatim and explicitly labeled reference/accounting counts."""
    rows: list[list[Any]] = []
    for setup in items:

        def add(scope: str, label: str, metric: str, value: Any, *, current: Setup = setup) -> None:
            rows.append(
                [
                    current.id,
                    current.source.result.experiment_id,
                    current.run.spec["model"],
                    current.run.spec["variant"],
                    scope,
                    label,
                    metric,
                    value,
                    DISCLAIMER,
                ]
            )

        for status, count in setup.run.status_counts.items():
            add("case accounting", "", status, count)
        add("runtime", "", "case_processing_s", setup.run.runtime_s)
        for label in setup.source.result.config["labels"]:
            known = [
                value for case in setup.run.cases if (value := case.y_true.get(label)) is not None
            ]
            add("selected cohort reference", label, "known_reference_labels", len(known))
            add("selected cohort reference", label, "positive_reference_labels", sum(known))
            add(
                "selected cohort reference",
                label,
                "reference_prevalence",
                sum(known) / len(known) if known else None,
            )
        for name, value in _flatten(setup.run.metrics):
            add("stored score", "", name, value)
    return rows


def case_rows(items: list[Setup]) -> list[list[Any]]:
    """Expose availability with pseudonyms; never export identifiers or free model text."""
    rows: list[list[Any]] = []
    for setup in items:
        for case in setup.run.cases:
            pseudonym = "case-" + sha256_of_obj([case.dataset, case.case_id])[:16]
            for label in setup.source.result.config["labels"]:
                score = case.y_score.get(label)
                rows.append(
                    [
                        setup.id,
                        case.dataset,
                        pseudonym,
                        case.phase,
                        case.status.value,
                        label,
                        case.y_true.get(label),
                        score,
                        score is not None,
                        len(case.parse_warnings),
                        case.error is not None,
                        DISCLAIMER,
                    ]
                )
    return rows


def _display(value: Any) -> str:
    if value is None:
        return "Not available"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _safe_csv(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False)
    if isinstance(value, str) and value.lstrip(
        "\ufeff" + "".join(chr(code) for code in range(33))
    ).startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _csv(headers: list[str], rows: list[list[Any]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows([_safe_csv(value) for value in row] for row in rows)
    return output.getvalue()


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    return (
        '<div class="table-wrap"><table><thead><tr>'
        + "".join(f'<th scope="col">{escape(header)}</th>' for header in headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join(f"<td>{escape(_display(value))}</td>" for value in row) + "</tr>"
            for row in rows
        )
        + "</tbody></table></div>"
    )


def render_cohort_html(items: list[Setup], comparisons: list[dict[str, Any]]) -> str:
    """Render a portable, escaped cohort review without image or network dependencies."""
    overview = []
    definitions = []
    for item in items:
        run, source = item.run, item.source
        overview.append(
            [
                item.id,
                source.result.experiment_id,
                run.spec["model"],
                run.spec["variant"],
                "Unknown; not assessed for this cohort",
                len(run.cases),
                run.status_counts["scored"],
                run.status_counts["abstained"],
                run.status_counts["failed"],
                run.status_counts["not_indexed"],
                run.runtime_s,
            ]
        )
        model = source.identity["models"][run.spec["variant"]]
        definition = {
            "experiment_config_sha256": source.result.config_sha256,
            "invocation_identity_sha256": source.checkpoint.identity_sha256,
            "model": run.spec["model"],
            "model_hash": run.provenance.model_hash,
            "possible_training_overlap": "unknown; no cohort-specific assessment",
            "license": model["model"]["license"],
            "quantization": model["model"].get("quantization"),
            "prompt": model["prompt"],
            "prompt_hash": run.provenance.prompt_hash,
            "view": model["model"]["view"],
            "view_overrides": run.spec["view_overrides"],
            "preprocess_hash": run.provenance.preprocess_hash,
            "source_hash": source.identity["source_hash"],
            "scoring_hash": run.provenance.scoring_hash,
            "ground_truth_hash": run.provenance.ground_truth_hash,
            "labels": source.result.config["labels"],
            "thresholds": source.result.config["thresholds"],
            "phases": source.result.config["phases"],
            "active_invocation_runtime_s": source.result.runtime_s,
            "git_commit": run.provenance.git_commit,
            "thoraxbench_version": run.provenance.thoraxbench_version,
        }
        definitions.append(
            f"<details><summary>{escape(item.id)} · Setup and provenance</summary>"
            f"<pre>{escape(json.dumps(definition, indent=2, ensure_ascii=False))}</pre></details>"
        )
    compare_rows = [
        [
            pair["left"],
            pair["right"],
            "Matched cohort/scoring basis" if pair["comparable"] else "Different or unknown basis",
            "; ".join(pair["differences"]) or "No cohort/scoring mismatch found",
            pair["shared_selected_cases"],
            pair["paired_available_predictions"],
            pair["experimental_factors"],
        ]
        for pair in comparisons
    ]
    metrics = metric_rows(items)
    cases = case_rows(items)
    summary_rows = []
    for item in items:
        a = item.run.metrics.get("task_a", {})
        e = item.run.metrics.get("task_e", {})
        g = item.run.metrics.get("task_g", {})
        summary_rows.append(
            [
                item.id,
                a.get("macro_f1"),
                a.get("macro_auroc"),
                e.get("available_predictions"),
                e.get("reference_labels"),
                e.get("prediction_coverage"),
                g.get("abstention_rate"),
                g.get("false_reassurance_studies"),
                g.get("false_reassurance_eligible_studies"),
            ]
        )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        f"<title>ThoraxBench cohort research review</title><style>{REPORT_STYLE}</style></head>"
        '<body><main class="shell"><header class="hero"><p '
        'class="eyebrow">ThoraxBench Local · Cohort review</p>'
        f"<h1>Stored benchmark results</h1><p>{len(items)} model setup(s). "
        f"Development split only.</p></header>"
        f'<p class="notice">{escape(DISCLAIMER)}</p>'
        '<nav aria-label="Report sections"><a href="#overview">Case accounting</a>'
        '<a href="#comparison">Comparability</a><a href="#scores">Stored metrics</a>'
        '<a href="#cases">Pseudonymous cases</a></nav>'
        '<section class="panel" id="overview"><h2>Case accounting and timing</h2>'
        "<p>Failures, abstentions and missing-index cases remain explicit. "
        "Case processing is recorded benchmark case-wrapper wall time, including configuration, "
        "inference, parsing, provenance/model metadata, input hashing and outcome work. "
        "It excludes study loading, shared invocation input hashing and output persistence. "
        "It is separate from engine-stage timing and is not a speed benchmark. "
        "Invocation wall time and exact setup hashes appear in the provenance details.</p>"
        + _table(
            [
                "Setup",
                "Experiment",
                "Model",
                "Variant",
                "Possible training overlap",
                "Selected",
                "Scored",
                "Abstained",
                "Failed",
                "Not indexed",
                "Case processing (s)",
            ],
            overview,
        )
        + '</section><section class="panel" id="comparison"><h2>Comparability and coverage</h2>'
        "<p>Matched inputs and scoring definitions permit descriptive comparisons only. Different "
        "available-prediction denominators and missing outputs still limit "
        "interpretation. Model/prompt/view "
        "changes are experimental factors; prepared-image differences do not "
        "redefine the source cohort. "
        "Uncalibrated cross-model scores are not directly comparable. "
        "Agreement does not establish correctness. "
        "This report does not rank models or declare a winner.</p>"
        + (
            _table(
                [
                    "Left",
                    "Right",
                    "Basis",
                    "Differences or unknowns",
                    "Shared cases",
                    "Paired available predictions",
                    "Experimental factors",
                ],
                compare_rows,
            )
            if comparisons
            else "<p>One setup is shown; no cross-setup comparison is possible.</p>"
        )
        + '</section><section class="panel" id="scores"><h2>Stored scores and denominators</h2>'
        "<p>Metrics below come from the saved benchmark, without filling "
        "missing predictions or recomputing "
        "scores. Raw-score calibration statistics do not mean a calibrator was "
        "fitted. Reference prevalence "
        "uses known labels in the selected cohort, including failures. "
        "Detailed tables retain CIs, confusion "
        "counts, per-label metrics and unavailable values.</p>"
        + _table(
            [
                "Setup",
                "Macro F1",
                "Macro AUROC",
                "Available labels",
                "Known reference labels",
                "Prediction coverage",
                "Abstention rate",
                "False reassurance studies",
                "Eligible studies",
            ],
            summary_rows,
        )
        + "<details><summary>All stored metrics and reference counts</summary>"
        + _table(
            ["Setup", "Experiment", "Model", "Variant", "Scope", "Label", "Metric", "Value"],
            [row[:-1] for row in metrics],
        )
        + '</details></section><section class="panel" '
        'id="cases"><h2>Pseudonymous case availability</h2>'
        "<p>Case keys are stable unkeyed hashes of dataset/case identifiers. "
        "They remain pseudonymous "
        "research data, not anonymous or automatically publishable. Patient "
        "identifiers, images and raw "
        "model responses are excluded. A blank score indicates an unavailable "
        "prediction; it does not mean "
        "the finding is absent. These records remain under ignored data/results/.</p>"
        + _table(
            [
                "Setup",
                "Dataset",
                "Case key",
                "Phase",
                "Status",
                "Label",
                "Reference",
                "Presence score",
                "Available prediction",
                "Warning count",
                "Error recorded",
            ],
            [row[:-1] for row in cases],
        )
        + '</section><section class="panel"><h2>Setup and provenance</h2>'
        + "".join(definitions)
        + f"</section><footer>{escape(DISCLAIMER)}</footer></main></body></html>"
    )


def write_cohort_exports(
    sources: list[CompletedRun],
    settings: Settings,
    *,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    """Create a fresh output subdirectory, preserving source invocations and earlier exports."""
    if not 1 <= len(sources) <= 8:
        raise ValueError("Export requires one to eight completed invocations")
    items = setups(sources)
    if len(items) > 64:
        raise ValueError("Export supports at most 64 experiment variants")
    parent = output_dir or settings.data_path("results", "benchmark-exports")
    require_results_path(parent / "preflight", settings)
    if any(parent.resolve().is_relative_to(source.folder.resolve()) for source in sources):
        raise ValueError("Export destination must be outside its source invocations")
    name = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid4().hex
    folder = parent / name
    store = BenchmarkStore(folder, settings)
    require_results_path(folder / "manifest.json", settings)
    folder.mkdir(parents=True, exist_ok=False)
    comparisons = comparison_details(items)
    payloads = {
        "html": ("report.html", render_cohort_html(items, comparisons)),
        "metrics_csv": (
            "metrics.csv",
            _csv(
                [
                    "setup",
                    "experiment",
                    "model",
                    "variant",
                    "scope",
                    "label",
                    "metric",
                    "value",
                    "research_disclaimer",
                ],
                metric_rows(items),
            ),
        ),
        "cases_csv": (
            "cases.csv",
            _csv(
                [
                    "setup",
                    "dataset",
                    "case_pseudonym",
                    "phase",
                    "status",
                    "label",
                    "reference",
                    "presence_score",
                    "available_prediction",
                    "warning_count",
                    "error_recorded",
                    "research_disclaimer",
                ],
                case_rows(items),
            ),
        ),
    }
    records = {kind: store.write(name, text) for kind, (name, text) in payloads.items()}
    module = Path(__file__).parent
    commit, dirty = git_state(settings.repo_root)
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "disclaimer": DISCLAIMER,
        "exporter": {
            "version": __version__,
            "git_commit": commit,
            "git_dirty": dirty,
            "style_sha256": sha256_of_obj(REPORT_STYLE),
            "source_sha256": sha256_of_obj(
                {
                    name: sha256_of_file(module / name)
                    for name in ["cohort.py", "compare.py", "exports.py"]
                }
            ),
        },
        "sources": [
            {"identity_sha256": source.checkpoint.identity_sha256, **source.source_hashes}
            for source in sources
        ],
        "setups": [
            {
                "id": item.id,
                "source_index": sources.index(item.source),
                "variant": item.run.spec["variant"],
                "possible_training_overlap": "unknown",
            }
            for item in items
        ],
        "comparisons": comparisons,
        "outputs": {
            kind: {"file": record.file, "sha256": record.sha256} for kind, record in records.items()
        },
        "pseudonyms": "Unkeyed SHA-256(dataset,case_id), first 16 hex "
        "characters; not anonymization.",
    }
    store.write("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return {
        **{kind: store.path(record.file) for kind, record in records.items()},
        "manifest": store.path("manifest.json"),
    }


def export_completed_runs(
    folders: list[Path],
    settings: Settings,
    *,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    """Validate every source before writing; never read raw images or execute a model."""
    if not 1 <= len(folders) <= 8 or len({folder.resolve() for folder in folders}) != len(folders):
        raise ValueError("Provide one to eight distinct completed invocation directories")
    return write_cohort_exports(
        [load_completed_run(folder, settings) for folder in folders],
        settings,
        output_dir=output_dir,
    )
