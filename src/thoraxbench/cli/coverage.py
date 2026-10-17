# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""``thoraxbench coverage``: reference-lesion coverage of sampled inputs (no model, no pixels)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from thoraxbench.analysis import DISCLAIMER
from thoraxbench.config import get_settings
from thoraxbench.privacy import settings_redactor

NOTE = (
    "Calibration-phase index geometry only; covered means on a prepared image or slab, "
    "not visible to or detected by a model."
)


def coverage(
    dataset: Annotated[str, typer.Argument(help="Indexed dataset id with lesion labels.")] = (
        "lidc_idri"
    ),
    *,
    output: Annotated[
        Path | None,
        typer.Option(help="Also write aggregate JSON here (must stay under data/results)."),
    ] = None,
    target: Annotated[
        float, typer.Option(min=0.0, max=1.0, help="Lesion-coverage target for the pick.")
    ] = 0.9,
) -> None:
    """Measure the fraction of calibration reference lesions on prepared images per setting."""
    from thoraxbench.benchmark.coverage import (  # noqa: PLC0415 - keep CLI start fast
        COVERAGE_VERSION,
        DEFAULT_NUM_CTX,
        default_grid,
        measure,
        phase_entries,
        render_table,
        smallest_sufficient,
    )
    from thoraxbench.reports.html_report import require_results_path  # noqa: PLC0415

    settings = get_settings()
    try:
        if output is not None:
            require_results_path(output, settings)
        entries = phase_entries(dataset, settings)
        rows = [measure(entries, setting) for setting in default_grid()]
    except (OSError, ValueError, KeyError, PermissionError) as exc:
        message = settings_redactor(settings).redact(str(exc))
        typer.echo(f"Coverage failed: {message}\n{DISCLAIMER}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"{dataset}: {len(entries)} calibration studies. {NOTE}")
    typer.echo(render_table(rows))
    pick = smallest_sufficient(rows, target=target)
    typer.echo(
        f"Smallest fitting setting with >= {target:.0%} lesion coverage: "
        + (f"`{pick.setting.name}`" if pick else "none")
    )
    if output is not None:
        payload = {
            "coverage_version": COVERAGE_VERSION,
            "dataset": dataset,
            "phase": "calibration",
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "n_studies": len(entries),
            "num_ctx": DEFAULT_NUM_CTX,
            "target": target,
            "pick": pick.setting.name if pick else None,
            "rows": [row.to_dict() for row in rows],
            "note": NOTE,
            "disclaimer": DISCLAIMER,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        typer.echo(f"Aggregate JSON: {output}")
    typer.echo(DISCLAIMER)
