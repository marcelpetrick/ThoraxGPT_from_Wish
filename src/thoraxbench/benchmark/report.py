# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Append-only benchmark reports under ``data/results/benchmark/<id>/<run>/`` (Vision §25)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from thoraxbench.benchmark.runner import ExperimentResult, RunResult
from thoraxbench.config import Settings
from thoraxbench.reports.html_report import require_results_path


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _ci(metric: dict[str, Any], name: str) -> str:
    interval = metric.get("ci95", {}).get(name)
    return f"[{interval[0]:.3f}, {interval[1]:.3f}]" if interval else "n/a"


def _label_rows(run: RunResult) -> list[str]:
    rows = [
        "| Label | n | Positives | AUROC (95 % CI) | Sensitivity (95 % CI) | "
        "Specificity (95 % CI) | F1 (95 % CI) | TP/FP/TN/FN | Notes |",
        "|---|---:|---:|---|---|---|---|---|---|",
    ]
    for label, m in run.metrics["task_a"]["per_label"].items():
        counts = m.get("counts")
        cm = f"{counts['tp']}/{counts['fp']}/{counts['tn']}/{counts['fn']}" if counts else "n/a"
        rows.append(
            f"| `{label}` | {m['n']} | {m['n_positive']} | "
            f"{_fmt(m['auroc'])} {_ci(m, 'auroc')} | "
            f"{_fmt(m.get('sensitivity'))} {_ci(m, 'sensitivity')} | "
            f"{_fmt(m.get('specificity'))} {_ci(m, 'specificity')} | "
            f"{_fmt(m.get('f1'))} {_ci(m, 'f1')} | {cm} | {'; '.join(m['notes']) or '-'} |"
        )
    return rows


def _calibration_rows(run: RunResult) -> list[str]:
    rows = ["| Label | n | Brier | ECE | NLL |", "|---|---:|---:|---:|---:|"]
    for label, m in run.metrics["task_b"].items():
        rows.append(
            f"| `{label}` | {m['n']} | {_fmt(m['brier'])} | {_fmt(m['ece'])} | {_fmt(m['nll'])} |"
        )
    return rows


def _case_rows(run: RunResult) -> list[str]:
    rows = [
        "| Dataset | Case | Phase | Status | Reference | Predicted present | Detail |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in run.cases:
        ref = ", ".join(f"{k}={_fmt(v)}" for k, v in c.y_true.items() if v is not None) or "-"
        detail = c.error or "; ".join(c.parse_warnings) or "-"
        rows.append(
            f"| {c.dataset} | {c.case_id} | {c.phase or '-'} | {c.status.value} | {ref} | "
            f"{', '.join(c.positive_labels) or '-'} | {detail.replace('|', '/')} |"
        )
    return rows


def _run_section(run: RunResult) -> list[str]:
    spec = run.spec
    prov = run.provenance
    a = run.metrics["task_a"]
    e = run.metrics["task_e"]
    g = run.metrics["task_g"]
    counts = ", ".join(f"{k} {v}" for k, v in run.status_counts.items())
    return [
        f"## Run `{spec['variant']}` — model `{spec['model']}`",
        "",
        f"* Prompt: `{spec['prompt'] or 'model default'}`; view overrides: "
        f"`{spec['view_overrides'] or {}}`",
        f"* Case status: {counts}",
        f"* Runtime (analysis only): {run.runtime_s:.1f} s",
        f"* Provenance fingerprint: `{prov.fingerprint()}`",
        f"* Prompt hash: `{_fmt(prov.prompt_hash)}`; preprocess hash: "
        f"`{_fmt(prov.preprocess_hash)}`; model hash: `{_fmt(prov.model_hash)}`",
        f"* Git commit: `{_fmt(prov.git_commit)}` (dirty: {_fmt(prov.git_dirty)})",
        "",
        "### Task A — study-level labels (scored cases only)",
        "",
        f"Macro F1 {_fmt(a['macro_f1'])}, micro F1 {_fmt(a['micro_f1'])}, "
        f"macro AUROC {_fmt(a['macro_auroc'])}. CIs: patient-level bootstrap.",
        "",
        *_label_rows(run),
        "",
        "### Task B — calibration of raw scores (no calibrator fitted)",
        "",
        *_calibration_rows(run),
        "",
        "### Task E / G — factuality and abstention",
        "",
        f"* Label agreement {_fmt(e['label_agreement'])}: {e['agreements']} agreements, "
        f"{e['contradictions']} contradictions, {e['omissions']} omissions, "
        f"{e['hallucinated_positives']} hallucinated positives over "
        f"{e['reference_labels']} known reference labels.",
        f"* Abstention rate {_fmt(g['abstention_rate'])}; high-confidence error rate "
        f"{_fmt(g['high_confidence_error_rate'])} ({g['high_confidence_decisions']} decisions); "
        f"false reassurance rate {_fmt(g['false_reassurance_rate'])}; fabricated measurement "
        f"rate {_fmt(g['fabricated_measurement_rate'])}.",
        "",
        "### Cases",
        "",
        *_case_rows(run),
        "",
    ]


def render_markdown(result: ExperimentResult) -> str:
    """Render the Markdown benchmark report."""
    lines = [
        f"# Benchmark {result.experiment_id}: {result.title or 'untitled'}",
        "",
        f"> {result.disclaimer}",
        "",
        f"**Framing.** {result.framing}",
        "",
        f"* Purpose: {result.description or '-'}",
        f"* Vision reference: {result.vision_ref or '-'}",
        f"* Config: `{result.config_path}` (file SHA-256 `{result.config_sha256}`)",
        f"* Split: {result.split} only (sealed holdout untouched)",
        f"* Started: {result.started_at}; total runtime {result.runtime_s:.1f} s",
        f"* Case limit per dataset: {_fmt(result.limit_per_dataset)}",
        "",
        "## Datasets",
        "",
        "| Dataset | Development cases | Selected | Indexed | Not indexed | "
        "Index entries outside development (ignored) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    lines += [
        f"| {d.dataset} | {d.development_cases} | {d.selected_cases} | "
        f"{d.indexed_development_cases} | {d.not_indexed} | "
        f"{d.index_entries_outside_development} |"
        for d in result.datasets
    ]
    lines += ["", *[f"* {note}" for note in result.notes], ""]
    for run in result.runs:
        lines += _run_section(run)
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(result: ExperimentResult, settings: Settings) -> tuple[Path, Path]:
    """Write a unique timestamp/config-hash/UUID run directory; preserve prior outputs."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    run_id = f"{stamp}-{result.config_sha256[:12]}-{uuid4().hex}"
    out = settings.data_path("results", "benchmark", result.experiment_id, run_id)
    json_path, md_path = out / "result.json", out / "report.md"
    require_results_path(json_path, settings)
    require_results_path(md_path, settings)
    out.mkdir(parents=True, exist_ok=False)
    require_results_path(json_path, settings)
    with json_path.open("x", encoding="utf-8") as output:
        output.write(result.model_dump_json(indent=1) + "\n")
    require_results_path(md_path, settings)
    with md_path.open("x", encoding="utf-8") as output:
        output.write(render_markdown(result))
    return json_path, md_path
