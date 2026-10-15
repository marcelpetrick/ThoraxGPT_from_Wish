# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""``thoraxbench privacy``: DICOM de-identification audit (Vision §29)."""

from pathlib import Path
from typing import Annotated

import typer

from thoraxbench.config import get_settings
from thoraxbench.study_access import guard_study_input

PRIVACY_DISCLAIMER = (
    "Research use only. This audit checks DICOM header attributes against a subset of the "
    "DICOM PS3.15 Basic Profile. It does not inspect pixel data and does not prove that a "
    "study is anonymous."
)

privacy_app = typer.Typer(
    name="privacy", help="Privacy checks for local DICOM studies.", no_args_is_help=True
)


@privacy_app.command("audit")
def audit(
    study_dir: Annotated[Path, typer.Argument(help="Folder with the DICOM study.")],
    *,
    as_json: Annotated[bool, typer.Option("--json", help="Print the audit as JSON.")] = False,
    strict: Annotated[
        bool, typer.Option(help="Exit with code 1 when a 'fail' attribute is found.")
    ] = False,
) -> None:
    """Audit DICOM headers for identifiers; print tag keywords and counts, never values."""
    from thoraxbench.privacy import audit_study_dir, settings_redactor  # noqa: PLC0415 - pydicom

    settings = get_settings()
    redactor = settings_redactor(settings)
    try:
        dataset, case_id = guard_study_input(study_dir, settings)
        pseudonyms = None if dataset == "adhoc" else {case_id}
        report = audit_study_dir(study_dir.resolve(), pseudonyms=pseudonyms)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        typer.echo(f"Privacy audit failed: {redactor.redact(str(exc))}", err=True)
        raise typer.Exit(1) from exc
    if as_json:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(report.summary())
    typer.echo(PRIVACY_DISCLAIMER, err=True)
    if strict and not report.passed:
        raise typer.Exit(1)
