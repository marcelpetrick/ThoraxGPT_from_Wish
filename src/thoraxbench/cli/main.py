# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Typer application: the ``thoraxbench`` entry point."""

from typing import Annotated

import typer

from thoraxbench import __version__

app = typer.Typer(
    name="thoraxbench",
    help="ThoraxBench Local — research-only thoracic-CT AI benchmark. Not medical advice.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"thoraxbench {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """ThoraxBench Local command-line interface."""


@app.command()
def info() -> None:
    """Print the intended-use statement."""
    typer.echo("ThoraxBench Local is a research system. Outputs are experimental predictions.")
