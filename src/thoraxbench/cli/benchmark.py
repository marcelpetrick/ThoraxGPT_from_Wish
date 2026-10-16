# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""``thoraxbench benchmark``: run a frozen experiment config on the development split."""

from pathlib import Path
from typing import Annotated

import typer

from thoraxbench.config import get_settings

UNSEAL_REFUSAL = (
    "Sealed evaluation is not implemented. --unseal requires a frozen experiment config and "
    "a reviewed sealed-evaluation workflow; the sealed holdout stays untouched. "
    "Run without --unseal to benchmark the development split."
)
FAILURE_NOTE = "Research use only; benchmark outputs are not medical advice."


def benchmark(
    experiment: Annotated[Path, typer.Argument(help="Experiment YAML (configs/experiments/).")],
    *,
    limit: Annotated[
        int | None,
        typer.Option(min=1, help="Use at most N development cases per dataset (quick runs)."),
    ] = None,
    unseal: Annotated[
        bool,
        typer.Option("--unseal", help="Sealed-holdout evaluation (not implemented; refused)."),
    ] = False,
) -> None:
    """Score a model setup against indexed reference labels of development cases."""
    if unseal:
        typer.echo(UNSEAL_REFUSAL, err=True)
        raise typer.Exit(2)
    from thoraxbench.benchmark import (  # noqa: PLC0415 - keep CLI start fast
        load_experiment,
        run_experiment,
        write_outputs,
    )
    from thoraxbench.reports.html_report import require_results_path  # noqa: PLC0415 - export gate

    try:
        settings = get_settings()
        loaded = load_experiment(experiment)
        require_results_path(settings.data_path("results", "benchmark", loaded.config.id), settings)
        result = run_experiment(loaded, settings, limit=limit, progress=typer.echo)
        json_path, md_path = write_outputs(result, settings)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        typer.echo(f"Benchmark failed: {exc}\n{FAILURE_NOTE}", err=True)
        raise typer.Exit(1) from exc
    for run in result.runs:
        counts = ", ".join(f"{k} {v}" for k, v in run.status_counts.items())
        typer.echo(f"{result.experiment_id} [{run.spec['variant']}]: {counts}")
    typer.echo(f"Results: {json_path}\nReport: {md_path}")
    typer.echo(f"Config SHA-256: {result.config_sha256}\n{result.framing}")
