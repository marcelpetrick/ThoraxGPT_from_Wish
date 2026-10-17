# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""``thoraxbench sanity``: image-path and visual-signal diagnostics (calibration/synthetic)."""

from pathlib import Path
from typing import Annotated

import typer

from thoraxbench.analysis import DISCLAIMER
from thoraxbench.config import get_settings
from thoraxbench.privacy import settings_redactor


def sanity(
    config: Annotated[Path, typer.Argument(help="Sanity YAML (configs/experiments/sanity/).")],
    *,
    limit: Annotated[
        int | None, typer.Option(min=1, help="Use only the first N input groups (pairs/sources).")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option(help="Build and count the inputs; send no request.")
    ] = False,
) -> None:
    """Check whether local VLM answers depend on the attached images (research diagnostic)."""
    from thoraxbench.benchmark.sanity import (  # noqa: PLC0415 - keep CLI start fast
        build_items,
        limit_groups,
        load_sanity,
        run_sanity,
    )
    from thoraxbench.splits import SealedAccessError  # noqa: PLC0415

    settings = get_settings()
    redactor = settings_redactor(settings)
    try:
        loaded = load_sanity(config)
        if dry_run:
            items, counts = build_items(loaded.config, settings)
            items = limit_groups(items, limit)
            images = sum(len(item.images) for item in items)
            typer.echo(
                f"{loaded.config.id}: {len(items)} inputs, {images} images, "
                f"{len(loaded.config.models)} model(s); selection {counts}"
            )
            typer.echo(DISCLAIMER)
            return
        run = run_sanity(
            loaded, settings, limit=limit, progress=lambda m: typer.echo(redactor.redact(m))
        )
    except SealedAccessError as exc:
        typer.echo(f"Refused: {redactor.redact(str(exc))}\n{DISCLAIMER}", err=True)
        raise typer.Exit(2) from exc
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        typer.echo(f"Sanity check failed: {redactor.redact(str(exc))}\n{DISCLAIMER}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(run.markdown)
    typer.echo(f"Artifacts: {redactor.redact(str(run.folder))}")
