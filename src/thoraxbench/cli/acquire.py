# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""``thoraxbench acquire``: license-, budget- and checksum-gated dataset acquisition."""

from typing import Annotated

import typer

from thoraxbench.config import get_settings

ACQUIRE_DISCLAIMER = (
    "Research use only. Downloaded data stay under data/raw/ (git-ignored); respect the "
    "dataset license and the TCIA Data Usage Policy."
)


def acquire(
    dataset: Annotated[str, typer.Argument(help="Registry id of an approved dataset.")],
    *,
    patients: Annotated[
        int | None,
        typer.Option(min=1, help="Patients to select when no frozen selection exists yet."),
    ] = None,
    modality: Annotated[
        list[str] | None,
        typer.Option(help="Modality for a new selection (repeatable; default CT)."),
    ] = None,
    seed: Annotated[int, typer.Option(help="Seed of the new-selection patient order.")] = 20261015,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print the plan and budget verdict only.")
    ] = False,
    verify: Annotated[
        bool, typer.Option("--verify", help="Re-hash every listed file against _sha256.txt.")
    ] = False,
) -> None:
    """Acquire an approved TCIA dataset into data/raw/ with manifests and checksums."""
    from thoraxbench.acquisition import AcquireOptions, AcquisitionError  # noqa: PLC0415
    from thoraxbench.acquisition import acquire as run_acquire  # noqa: PLC0415
    from thoraxbench.registry import PolicyError  # noqa: PLC0415

    options = AcquireOptions(
        modalities=tuple(m.upper() for m in modality) if modality else ("CT",),
        patients=patients,
        seed=seed,
        dry_run=dry_run,
        verify=verify,
    )
    try:
        report = run_acquire(dataset, get_settings(), options, echo=typer.echo)
    except PolicyError as exc:
        typer.echo(f"Acquisition refused: {exc}\n{ACQUIRE_DISCLAIMER}", err=True)
        raise typer.Exit(2) from exc
    except (OSError, ValueError, KeyError, AcquisitionError) as exc:
        typer.echo(f"Acquisition failed: {exc}\n{ACQUIRE_DISCLAIMER}", err=True)
        raise typer.Exit(1) from exc
    for problem in [*report.errors, *report.checksum_failures]:
        typer.echo(f"  problem: {problem}", err=True)
    if dry_run:
        typer.echo("Dry run: nothing was downloaded or written.")
    if not report.ok:
        raise typer.Exit(1)
