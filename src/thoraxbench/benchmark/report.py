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


def _overlap(run: RunResult) -> str:
    overlap = run.metrics.get("possible_training_overlap") or {}
    return "; ".join(f"{ds}={value}" for ds, value in overlap.items()) or "n/a"


def _label_rows(run: RunResult) -> list[str]:
    rows = [
        "| Label | n | Positives | AUROC (95 % CI) | Sensitivity (95 % CI) | "
        "Specificity (95 % CI) | F1 (95 % CI) | TP/FP/TN/FN | possible_training_overlap "
        "| Notes |",
        "|---|---:|---:|---|---|---|---|---|---|---|",
    ]
    overlap = _overlap(run)
    for label, m in run.metrics["task_a"]["per_label"].items():
        counts = m.get("counts")
        cm = f"{counts['tp']}/{counts['fp']}/{counts['tn']}/{counts['fn']}" if counts else "n/a"
        rows.append(
            f"| `{label}` | {m['n']} | {m['n_positive']} | "
            f"{_fmt(m['auroc'])} {_ci(m, 'auroc')} | "
            f"{_fmt(m.get('sensitivity'))} {_ci(m, 'sensitivity')} | "
            f"{_fmt(m.get('specificity'))} {_ci(m, 'specificity')} | "
            f"{_fmt(m.get('f1'))} {_ci(m, 'f1')} | {cm} | {overlap} | "
            f"{'; '.join(m['notes']) or '-'} |"
        )
    return rows


def _dataset_rows(run: RunResult) -> list[str]:
    rows = [
        "| Dataset | possible_training_overlap | Cases | Scored | Label | n | Positives "
        "| AUROC (95 % CI) | Sensitivity (95 % CI) | Specificity (95 % CI) | Notes |",
        "|---|---|---:|---:|---|---:|---:|---|---|---|---|",
    ]
    for dataset, d in (run.metrics.get("per_dataset") or {}).items():
        for label, m in d["task_a"]["per_label"].items():
            rows.append(
                f"| {dataset} | {d['possible_training_overlap']} | {d['n_cases']} | "
                f"{d['n_scored']} | `{label}` | {m['n']} | {m['n_positive']} | "
                f"{_fmt(m['auroc'])} {_ci(m, 'auroc')} | "
                f"{_fmt(m.get('sensitivity'))} {_ci(m, 'sensitivity')} | "
                f"{_fmt(m.get('specificity'))} {_ci(m, 'specificity')} | "
                f"{'; '.join(m['notes']) or '-'} |"
            )
    return rows


def _task_c_rows(run: RunResult) -> list[str]:
    rates = ("0.125", "0.25", "0.5", "1.0", "2.0", "4.0", "8.0")
    rows = [
        "| Dataset | possible_training_overlap | Rule | Scans | Lesions | "
        + " | ".join(f"Sens @{r} FP" for r in rates)
        + " | CPM | Sensitivity (all candidates) | FP/scan (all candidates) |",
        "|---|---|---|---:|---:|" + "---:|" * len(rates) + "---:|---:|---:|",
    ]
    groups = [("pooled", _overlap(run), run.metrics.get("task_c"))] + [
        (dataset, d["possible_training_overlap"], d.get("task_c"))
        for dataset, d in (run.metrics.get("per_dataset") or {}).items()
    ]
    for name, overlap, task in groups:
        if not task:
            continue
        for rule in ("all_readers", "luna16_style"):
            c = task[rule]
            rows.append(
                f"| {name} | {overlap} | {rule} | {c['n_scans']} | {c['n_lesions']} | "
                + " | ".join(_fmt(c["froc_at"].get(r)) for r in rates)
                + f" | {_fmt(c['froc_average'])} | {_fmt(c['sensitivity'])} | "
                f"{_fmt(c['fp_per_scan'])} |"
            )
    return rows


def _calibration_rows(run: RunResult) -> list[str]:
    rows = ["| Label | n | Brier | ECE | NLL |", "|---|---:|---:|---:|---:|"]
    for label, m in run.metrics["task_b"].items():
        rows.append(
            f"| `{label}` | {m['n']} | {_fmt(m['brier'])} | {_fmt(m['ece'])} | {_fmt(m['nll'])} |"
        )
    return rows


def _fitted_calibration_rows(run: RunResult) -> list[str]:
    fit = run.metrics.get("calibration", {})
    rows = [
        "### Calibration fit / internal-test application",
        "",
        f"Status: {fit.get('status', 'not recorded')}. {fit.get('reason') or ''}",
    ]
    if fit.get("status") != "applied":
        return [*rows, ""]
    rows += [
        "Fit: calibration phase only. Apply: internal_test only. Raw 0.5 baseline stays available.",
        "",
        "| Label | Fit n | Fit positives | Fitted threshold | Method | Notes |",
        "|---|---:|---:|---:|---|---|",
    ]
    for label, item in fit["per_label"].items():
        rows.append(
            f"| {label} | {item['fit_n']} | {item['fit_positives']} | "
            f"{_fmt(item['fitted_threshold'])} | {fit['method']} | "
            f"{'; '.join(item['notes']) or '-'} |"
        )
    rows += [
        "",
        "Full fitted parameters and raw/fitted internal-test metrics are retained in result.json.",
        "",
    ]
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
        f"* possible_training_overlap: {_overlap(run)}",
        "",
        "### Task A — study-level labels (scored cases only)",
        "",
        f"Macro F1 {_fmt(a['macro_f1'])}, micro F1 {_fmt(a['micro_f1'])}, "
        f"macro AUROC {_fmt(a['macro_auroc'])}. CIs: patient-level bootstrap.",
        "",
        *_label_rows(run),
        "",
        "### Task B — calibration of raw scores",
        "",
        *_calibration_rows(run),
        "",
        *_fitted_calibration_rows(run),
        "",
        "### Per dataset — study level (scored cases only)",
        "",
        *_dataset_rows(run),
        "",
        *(
            [
                "### Task C — lesion level (FROC; scored, localising cases only)",
                "",
                *_task_c_rows(run),
                "",
            ]
            if run.metrics.get("task_c")
            else []
        ),
        "### Task E / G — factuality and abstention",
        "",
        f"* Label agreement {_fmt(e['label_agreement'])}: {e['agreements']} agreements, "
        f"{e['contradictions']} contradictions, {e['omissions']} omissions, "
        f"{e['hallucinated_positives']} hallucinated positives over "
        f"{e['reference_labels']} known reference labels.",
        f"* Available label predictions: {_fmt(e.get('available_predictions'))}; "
        f"prediction coverage {_fmt(e.get('prediction_coverage'))}.",
        f"* Abstention rate {_fmt(g['abstention_rate'])}; high-confidence error rate "
        f"{_fmt(g['high_confidence_error_rate'])} ({g['high_confidence_decisions']} decisions); "
        f"false reassurance rate {_fmt(g['false_reassurance_rate'])}; fabricated measurement "
        f"rate {_fmt(g['fabricated_measurement_rate'])}.",
        f"* False reassurance: {_fmt(g.get('false_reassurance_studies'))} over "
        f"{_fmt(g.get('false_reassurance_eligible_studies'))} eligible studies.",
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
    base = settings.data_path("results", "benchmark", result.experiment_id)
    require_results_path(base / "preflight", settings)
    if result.output_dir is not None:
        from thoraxbench.benchmark.checkpoint import BenchmarkStore  # noqa: PLC0415

        if not result.output_dir.resolve().is_relative_to(base.resolve()):
            raise ValueError("Invocation directory differs from the experiment")
        store = BenchmarkStore(result.output_dir, settings)
        store.state = store.read_checkpoint()
        if store.state.status != "complete":
            raise ValueError("Benchmark invocation has not completed")
        return store.verify(store.state.outputs["json"]), store.verify(
            store.state.outputs["markdown"]
        )
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
