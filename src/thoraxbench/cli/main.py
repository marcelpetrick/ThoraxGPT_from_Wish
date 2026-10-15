# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Typer application: the ``thoraxbench`` entry point."""

import hashlib
from pathlib import Path
from typing import Annotated

import typer

from thoraxbench import __version__
from thoraxbench.config import Settings, get_settings
from thoraxbench.splits import CaseGuard, Phase, SealedAccessError
from thoraxbench.splits.split import SplitManifest

DISCLAIMER = "Research use only. Experimental output; not medical advice or a diagnosis."

app = typer.Typer(
    name="thoraxbench",
    help="ThoraxBench Local — research-only thoracic-CT AI benchmark. Not medical advice.",
    no_args_is_help=True,
)


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


def _guard_study_input(path: Path, settings: Settings) -> tuple[str, str]:
    """Check paths and header identities before any pixel data is loaded.

    Registered raw inputs require their frozen development split. Public patient hashes
    also block copied sealed patients in otherwise ad hoc folders; sealed IDs stay unread.
    """
    import pydicom  # noqa: PLC0415 - DICOM is needed only for analysis
    from pydicom.errors import InvalidDicomError  # noqa: PLC0415

    resolved = path.resolve()
    sealed = settings.data_path("sealed").resolve()
    raw = settings.data_path("raw").resolve()
    guards: dict[str, CaseGuard] = {}

    def check_path(candidate: Path) -> tuple[str, str] | None:
        target = candidate.resolve()
        if target.is_relative_to(sealed):
            raise SealedAccessError("sealed input is forbidden for analyze")
        if not target.is_relative_to(raw):
            return None
        parts = target.relative_to(raw).parts
        if len(parts) < 2:
            raise SealedAccessError("select a single development patient directory")
        dataset, patient = parts[:2]
        if dataset not in guards:
            guards[dataset] = CaseGuard.load(settings.data_dir, settings.manifests_dir, dataset)
        guards[dataset].check(patient, Phase.DEVELOPMENT)
        return dataset, patient

    identity = check_path(resolved)
    if not resolved.is_dir():
        raise ValueError(f"study directory does not exist: {path}")
    files = sorted(candidate for candidate in resolved.rglob("*") if candidate.is_file())
    for candidate in files:
        check_path(candidate)
    manifests = [
        SplitManifest.model_validate_json(candidate.read_text(encoding="utf-8"))
        for candidate in sorted((settings.manifests_dir / "splits").glob("*.json"))
    ]
    for candidate in files:
        try:
            header = pydicom.dcmread(
                candidate, stop_before_pixels=True, specific_tags=["PatientID"]
            )
        except InvalidDicomError, EOFError:
            continue
        patient = str(header.get("PatientID", ""))
        candidate_identity = check_path(candidate)
        if candidate_identity is not None and patient != candidate_identity[1]:
            raise SealedAccessError("DICOM patient identity does not match development folder")
        for manifest in manifests:
            digest = hashlib.sha256(f"{manifest.salt}:{patient}".encode()).hexdigest()
            if digest in manifest.patient_hashes.get(Phase.SEALED.value, []):
                raise SealedAccessError("DICOM patient belongs to sealed validation")
    return identity or ("adhoc", resolved.name)


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
) -> None:
    """Analyse one local DICOM study with one local model; print the clinical report."""
    from thoraxbench.analysis import analyze_study  # noqa: PLC0415 - keep CLI start fast
    from thoraxbench.reports import render_study_report  # noqa: PLC0415
    from thoraxbench.study import load_study_dir  # noqa: PLC0415

    try:
        settings = get_settings()
        dataset, case_id = _guard_study_input(study_dir, settings)
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
        typer.echo(markdown)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        typer.echo(f"Analysis failed: {exc}\n{DISCLAIMER}", err=True)
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
        entries = build_index(dataset, get_settings(), progress=typer.echo, limit=limit)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        typer.echo(f"Cannot build index: {exc}\n{DISCLAIMER}", err=True)
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
        typer.echo(f"Cannot create split: {exc}\n{DISCLAIMER}", err=True)
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
