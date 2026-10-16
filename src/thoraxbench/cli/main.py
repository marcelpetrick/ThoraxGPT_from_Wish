# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Typer application: the ``thoraxbench`` entry point."""

from pathlib import Path
from typing import Annotated

import typer

from thoraxbench import __version__
from thoraxbench.cli.acquire import acquire
from thoraxbench.cli.benchmark import benchmark
from thoraxbench.cli.compare import benchmark_export, compare
from thoraxbench.cli.coverage import coverage
from thoraxbench.cli.privacy import privacy_app
from thoraxbench.config import get_settings
from thoraxbench.splits import Phase
from thoraxbench.study_access import guard_study_input

DISCLAIMER = (
    "Research use only. Self-made experimental research tool; not medical advice from a "
    "qualified healthcare professional, a diagnosis, or a medical device. Findings may be "
    "incorrect, incomplete or misleading. Do not use for diagnosis or treatment decisions."
)

app = typer.Typer(
    name="thoraxbench",
    help="ThoraxBench Local — research-only thoracic-CT AI benchmark. Not medical advice.",
    no_args_is_help=True,
)
app.command()(benchmark)
app.command()(benchmark_export)
app.command()(compare)
app.command()(acquire)
app.command()(coverage)
app.add_typer(privacy_app)


def _redact(value: object) -> str:
    """Replace absolute paths in CLI messages (Vision §29)."""
    from thoraxbench.privacy import settings_redactor  # noqa: PLC0415 - imports pydicom

    return settings_redactor(get_settings()).redact(str(value))


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"thoraxbench {__version__}\n{DISCLAIMER}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """ThoraxBench Local command-line interface."""
    typer.echo(DISCLAIMER, err=True)


@app.command()
def info() -> None:
    """Print the intended-use statement."""
    typer.echo("ThoraxBench Local is a research system. Outputs are experimental predictions.")


@app.command()
def analyze(
    study_dir: Annotated[Path, typer.Argument(help="Folder with the DICOM study.")],
    *,
    model: Annotated[str, typer.Option(help="Model id from configs/models.")] = "heuristic-hu",
    prompt: Annotated[str | None, typer.Option(help="Prompt id (P0-P4).")] = None,
    strategy: Annotated[str | None, typer.Option(help="Sampling strategy id.")] = None,
    n_images: Annotated[int | None, typer.Option("--n", min=1, help="Number of slices.")] = None,
    output: Annotated[Path | None, typer.Option(help="Write the result JSON here.")] = None,
    report: Annotated[Path | None, typer.Option(help="Write the Markdown report here.")] = None,
    html: Annotated[
        Path | None, typer.Option(help="Write an embedded-image HTML report under data/results/.")
    ] = None,
) -> None:
    """Analyse one local DICOM study with one local model; print the clinical report."""
    from thoraxbench.analysis import analyze_study  # noqa: PLC0415 - keep CLI start fast
    from thoraxbench.reports import render_study_report  # noqa: PLC0415
    from thoraxbench.reports.html_report import (  # noqa: PLC0415 - report only
        render_html_report,
        require_results_path,
    )
    from thoraxbench.study import load_study_dir  # noqa: PLC0415

    try:
        settings = get_settings()
        if html:
            require_results_path(html, settings)
        dataset, case_id = guard_study_input(study_dir, settings)
        study = load_study_dir(study_dir, dataset=dataset, case_id=case_id)
        overrides: dict[str, object] = {}
        if strategy:
            overrides["strategy"] = strategy
        if n_images is not None:
            overrides["n"] = n_images
        result = analyze_study(study, model, settings, prompt_id=prompt, view_overrides=overrides)
        markdown = render_study_report(result)
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        if report:
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(markdown, encoding="utf-8")
        if html:
            html.parent.mkdir(parents=True, exist_ok=True)
            html.write_text(render_html_report(result, study), encoding="utf-8")
        typer.echo(markdown)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        typer.echo(f"Analysis failed: {_redact(exc)}\n{DISCLAIMER}", err=True)
        raise typer.Exit(1) from exc
    if result.report.abstain or result.raw_error is not None:
        raise typer.Exit(1)


@app.command("demo-data")
def demo_data(
    out_dir: Annotated[Path, typer.Argument(help="Where to write the synthetic DICOM study.")],
    nodule_mm: Annotated[float, typer.Option(min=0, help="Nodule diameter (0 = none).")] = 12.0,
    effusion: Annotated[bool, typer.Option(help="Add a right pleural effusion.")] = True,
    emphysema: Annotated[bool, typer.Option(help="Add emphysema.")] = False,
) -> None:
    """Write a synthetic chest-CT phantom (no patient data) to try the pipeline."""
    from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series  # noqa: PLC0415

    spec = PhantomSpec(nodule_radius_mm=nodule_mm / 2, effusion=effusion, emphysema=emphysema)
    try:
        write_dicom_series(make_phantom(spec), out_dir, spec.spacing_mm)
    except OSError as exc:
        typer.echo(f"Cannot write demo data: {exc}\n{DISCLAIMER}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"synthetic phantom written to {out_dir}")


@app.command()
def index(
    dataset: Annotated[str, typer.Argument(help="Approved downloaded dataset id.")],
    limit: Annotated[
        int | None, typer.Option(min=1, help="Index at most N development patients.")
    ] = None,
) -> None:
    """Index development studies and reference labels after the patient split is frozen."""
    from thoraxbench.index import build_index  # noqa: PLC0415 - index only

    try:
        entries = build_index(
            dataset, get_settings(), progress=lambda m: typer.echo(_redact(m)), limit=limit
        )
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        typer.echo(f"Cannot build index: {_redact(exc)}\n{DISCLAIMER}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"{len(entries)} development case(s) indexed")


@app.command()
def split(
    dataset: Annotated[str, typer.Argument(help="Approved downloaded dataset id.")],
) -> None:
    """Freeze a random patient-level 80% development / 20% sealed holdout split."""
    from thoraxbench.splits.pilot import create_pilot_split  # noqa: PLC0415 - split only

    try:
        result = create_pilot_split(dataset, get_settings())
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        typer.echo(f"Cannot create split: {_redact(exc)}\n{DISCLAIMER}", err=True)
        raise typer.Exit(1) from exc
    counts = result.patients
    development = counts[Phase.CALIBRATION.value] + counts[Phase.INTERNAL_TEST.value]
    typer.echo(
        f"Frozen {dataset}: {development} development patients, "
        f"{counts[Phase.SEALED.value]} sealed holdout patients."
    )


@app.command()
def models() -> None:
    """List configured models and whether they are available locally."""
    from thoraxbench.adapters.base import list_model_configs  # noqa: PLC0415
    from thoraxbench.adapters.factory import load_model  # noqa: PLC0415

    settings = get_settings()
    for cfg in list_model_configs(settings.configs_dir / "models"):
        try:
            ok = load_model(cfg.id, settings).available()
        except Exception:
            ok = False
        typer.echo(
            f"{'✓' if ok else '✗'} {cfg.id:24} {cfg.adapter:12} {cfg.tag or cfg.service or ''}"
        )


@app.command()
def datasets() -> None:
    """List registered data sources and their license status."""
    from thoraxbench.registry import load_registry  # noqa: PLC0415

    for entry in load_registry(get_settings().configs_dir / "datasets").values():
        typer.echo(f"{entry.status.value:24} {entry.id:26} {entry.license}")


@app.command()
def serve(
    port: Annotated[
        int, typer.Option(min=1024, max=65535, help="Local web interface port.")
    ] = 8000,
) -> None:
    """Open the research review interface on this computer's loopback network."""
    import uvicorn  # noqa: PLC0415 - web dependencies are loaded only for serve

    from thoraxbench.api.app import create_app  # noqa: PLC0415 - web startup only

    typer.echo(f"ThoraxBench Local: http://127.0.0.1:{port}\n{DISCLAIMER}")
    uvicorn.run(create_app(), host="127.0.0.1", port=port, proxy_headers=False)
