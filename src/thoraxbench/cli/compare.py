# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Offline benchmark export/compare commands; never execute inference."""

from pathlib import Path
from typing import Annotated

import typer

from thoraxbench.analysis import DISCLAIMER
from thoraxbench.benchmark.exports import export_completed_runs
from thoraxbench.config import get_settings
from thoraxbench.privacy import settings_redactor


def _export(folders: list[Path], output_dir: Path | None) -> None:
    settings = get_settings()
    try:
        outputs = export_completed_runs(folders, settings, output_dir=output_dir)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        typer.echo(
            f"Export failed: {settings_redactor(settings).redact(str(exc))}\n{DISCLAIMER}", err=True
        )
        raise typer.Exit(1) from exc
    for kind, path in outputs.items():
        typer.echo(f"{kind}: {path}")
    typer.echo(
        "Stored development results only. No model ranking or clinical validity is established."
    )


def benchmark_export(
    invocation: Annotated[
        Path, typer.Argument(help="Completed checkpointed development invocation directory.")
    ],
    *,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            help="Parent under ignored data/results; a fresh export subdirectory is created."
        ),
    ] = None,
) -> None:
    """Export saved cohort metrics, pseudonymous cases and provenance as offline HTML/CSV."""
    _export([invocation], output_dir)


def compare(
    invocations: Annotated[
        list[Path],
        typer.Argument(help="Two to eight distinct completed development invocation directories."),
    ],
    *,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            help="Parent directory under ignored data/results; source invocations remain unchanged."
        ),
    ] = None,
) -> None:
    """Compare stored cohort results with explicit provenance and denominator differences."""
    if not 2 <= len(invocations) <= 8:
        typer.echo(
            "Compare requires two to eight distinct completed invocation directories.\n"
            f"{DISCLAIMER}",
            err=True,
        )
        raise typer.Exit(2)
    _export(invocations, output_dir)
