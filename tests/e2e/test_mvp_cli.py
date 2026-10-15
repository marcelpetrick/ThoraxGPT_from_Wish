# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Synthetic, offline exercises of the runnable MVP and its sealed-data boundary."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from thoraxbench import analysis
from thoraxbench.cli import main as cli
from thoraxbench.config import Settings
from thoraxbench.splits import CaseRecord, Phase, make_split, save_split
from thoraxbench.study import load_study_dir
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series

runner = CliRunner()


@pytest.fixture
def phantom(tmp_path: Path) -> Path:
    spec = PhantomSpec(nodule_radius_mm=6)
    return write_dicom_series(make_phantom(spec), tmp_path / "phantom", spec.spacing_mm)


def test_demo_and_analysis_write_nested_artifacts(tmp_path: Path) -> None:
    phantom = tmp_path / "phantom"
    demo = runner.invoke(cli.app, ["demo-data", str(phantom), "--no-effusion"])
    assert demo.exit_code == 0, demo.output
    assert "Research use only" in demo.output
    output, report = tmp_path / "artifacts" / "findings.json", tmp_path / "reports" / "study.md"
    result = runner.invoke(
        cli.app,
        ["analyze", str(phantom), "--n", "2", "--output", str(output), "--report", str(report)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text())
    assert payload["model_id"] == "heuristic-hu"
    assert payload["patient_id"] == "PHANTOM-0001"
    assert payload["report"]["abstain"] is False
    assert payload["provenance"]
    assert "not medical advice" in payload["disclaimer"]
    assert "Pulmonary nodule" in report.read_text()


@pytest.mark.parametrize("value", ["0", "-1"])
def test_nonpositive_image_count_rejected(tmp_path: Path, value: str) -> None:
    result = runner.invoke(cli.app, ["analyze", str(tmp_path), "--n", value])
    assert result.exit_code == 2


@pytest.mark.parametrize("kind", ["missing", "empty", "file"])
def test_bad_input_is_actionable(tmp_path: Path, kind: str) -> None:
    target = tmp_path / kind
    if kind == "empty":
        target.mkdir()
    elif kind == "file":
        target.write_text("not a directory")
    result = runner.invoke(cli.app, ["analyze", str(target)])
    assert result.exit_code == 1
    assert "Analysis failed" in result.output
    assert "Research use only" in result.output


def test_unknown_model_is_actionable(phantom: Path) -> None:
    result = runner.invoke(cli.app, ["analyze", str(phantom), "--model", "missing-model"])
    assert result.exit_code == 1
    assert "Analysis failed" in result.output


def test_failed_model_preserves_artifacts(
    phantom: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = analysis.analyze_study(load_study_dir(phantom), "heuristic-hu", Settings())
    result.raw_error = "local model unavailable"
    result.report.abstain = True
    monkeypatch.setattr(analysis, "analyze_study", lambda *_args, **_kwargs: result)
    output, report = tmp_path / "failed.json", tmp_path / "failed.md"
    invocation = runner.invoke(
        cli.app, ["analyze", str(phantom), "--output", str(output), "--report", str(report)]
    )
    assert invocation.exit_code == 1
    assert json.loads(output.read_text())["raw_error"] == "local model unavailable"
    assert report.exists()


def _split(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Settings, str, str]:
    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    split = make_split(
        [CaseRecord(dataset="demo", patient_id=f"P-{i}", case_id=f"P-{i}") for i in range(5)],
        "demo",
    )
    save_split(split, settings.data_dir, settings.manifests_dir)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    return settings, split.cases(Phase.DEVELOPMENT)[0], split.cases(Phase.SEALED)[0]


def test_raw_input_requires_existing_development_split(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    path = settings.data_path("raw", "demo", "P-1")
    path.mkdir(parents=True)
    invocation = runner.invoke(cli.app, ["analyze", str(path)])
    assert invocation.exit_code == 1
    assert "Analysis failed" in invocation.output


def test_sealed_path_and_symlink_rejected_before_header_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pydicom

    settings, _, _ = _split(tmp_path, monkeypatch)
    sealed = settings.data_path("sealed", "study")
    sealed.mkdir()
    (sealed / "secret.dcm").write_bytes(b"unreadable sealed sentinel")
    monkeypatch.setattr(pydicom, "dcmread", lambda *_args, **_kwargs: pytest.fail("sealed read"))
    for target in [sealed, tmp_path / "alias"]:
        if target != sealed:
            target.symlink_to(sealed, target_is_directory=True)
        result = runner.invoke(cli.app, ["analyze", str(target)])
        assert result.exit_code == 1
        assert "sealed input is forbidden" in result.output
    adhoc = tmp_path / "adhoc"
    adhoc.mkdir()
    (adhoc / "linked.dcm").symlink_to(sealed / "secret.dcm")
    assert runner.invoke(cli.app, ["analyze", str(adhoc)]).exit_code == 1


def test_copied_sealed_patient_blocked_by_public_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, sealed_patient = _split(tmp_path, monkeypatch)
    spec = PhantomSpec()
    path = write_dicom_series(
        make_phantom(spec), tmp_path / "copy", spec.spacing_mm, patient_id=sealed_patient
    )
    monkeypatch.setattr(
        "thoraxbench.study.load_study_dir", lambda *_args, **_kwargs: pytest.fail("pixel load")
    )
    result = runner.invoke(cli.app, ["analyze", str(path)])
    assert result.exit_code == 1
    assert "belongs to sealed validation" in result.output


def test_raw_patient_header_must_match_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, patient, _ = _split(tmp_path, monkeypatch)
    spec = PhantomSpec()
    path = write_dicom_series(
        make_phantom(spec), settings.data_path("raw", "demo", patient), spec.spacing_mm
    )
    result = runner.invoke(cli.app, ["analyze", str(path)])
    assert result.exit_code == 1
    assert "identity does not match" in result.output


def test_raw_development_patient_passes_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, patient, _ = _split(tmp_path, monkeypatch)
    spec = PhantomSpec()
    path = write_dicom_series(
        make_phantom(spec),
        settings.data_path("raw", "demo", patient),
        spec.spacing_mm,
        patient_id=patient,
    )
    assert cli.guard_study_input(path, settings) == ("demo", patient)


def test_inventory_commands_are_research_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "thoraxbench.adapters.factory.load_model",
        lambda *_args: Mock(available=lambda: True),
    )
    models = runner.invoke(cli.app, ["models"])
    assert models.exit_code == 0
    assert "heuristic-hu" in models.output
    assert "Research use only" in models.output

    def unavailable(*_args: object) -> None:
        raise ValueError("not configured")

    monkeypatch.setattr("thoraxbench.adapters.factory.load_model", unavailable)
    assert runner.invoke(cli.app, ["models"]).exit_code == 0
    datasets = runner.invoke(cli.app, ["datasets"])
    assert datasets.exit_code == 0
    assert "lidc_idri" in datasets.output
    assert "Research use only" in datasets.output
    assert "index" in runner.invoke(cli.app, ["--help"]).output
    assert "split" in runner.invoke(cli.app, ["--help"]).output


def test_demo_write_error_is_actionable(tmp_path: Path) -> None:
    target = tmp_path / "file"
    target.write_text("occupied")
    result = runner.invoke(cli.app, ["demo-data", str(target)])
    assert result.exit_code == 1
    assert "Cannot write demo data" in result.output


def test_analysis_stdout_without_files(phantom: Path) -> None:
    result = runner.invoke(cli.app, ["analyze", str(phantom), "--strategy", "S1"])
    assert result.exit_code == 0, result.output
    assert "research report" in result.output


def test_raw_dataset_root_cannot_be_analyzed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    path = settings.data_path("raw", "demo")
    path.mkdir(parents=True)
    result = runner.invoke(cli.app, ["analyze", str(path)])
    assert result.exit_code == 1
    assert "single development patient" in result.output


def test_split_freezes_random_patient_holdout_without_reading_dicom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pydicom

    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    registry = settings.configs_dir / "datasets"
    registry.mkdir(parents=True)
    source = Settings().configs_dir / "datasets" / "lidc_idri.yaml"
    (registry / source.name).write_text(source.read_text())
    for number in range(10):
        patient = settings.data_path("raw", "lidc_idri", f"SYNTHETIC-{number:02}")
        patient.mkdir(parents=True)
        (patient / "unused.dcm").write_bytes(b"directory-only split; never read")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(pydicom, "dcmread", lambda *_args, **_kwargs: pytest.fail("DICOM read"))
    invocation = runner.invoke(cli.app, ["split", "lidc_idri"])
    assert invocation.exit_code == 0, invocation.output
    assert "8 development patients" in invocation.output
    assert "2 sealed holdout patients" in invocation.output
    assert "SYNTHETIC-" not in invocation.output
    development_path = settings.data_path("splits", "lidc_idri.json")
    frozen_development = development_path.read_bytes()
    manifest_path = settings.manifests_dir / "splits" / "lidc_idri.json"
    manifest = json.loads(manifest_path.read_text())
    assert len(manifest["patient_hashes"]["sealed"]) == 2
    repeated = runner.invoke(cli.app, ["split", "lidc_idri"])
    assert repeated.exit_code == 1
    assert "Cannot create split" in repeated.output
    assert development_path.read_bytes() == frozen_development


def test_index_passes_limit_and_progress_and_handles_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from thoraxbench.index import build_index

    mock = Mock(spec=build_index, return_value=[Mock()])
    monkeypatch.setattr("thoraxbench.index.build_index", mock)
    invocation = runner.invoke(cli.app, ["index", "lidc_idri", "--limit", "1"])
    assert invocation.exit_code == 0, invocation.output
    assert "1 development case(s) indexed" in invocation.output
    assert mock.call_args.args[0] == "lidc_idri"
    assert mock.call_args.kwargs["limit"] == 1
    mock.call_args.kwargs["progress"](f"skip P-1: {Path.home()}/cases/P-1")
    assert capsys.readouterr().out == "skip P-1: [home]/P-1\n"
    mock.side_effect = ValueError("freeze a split first")
    failed = runner.invoke(cli.app, ["index", "lidc_idri"])
    assert failed.exit_code == 1
    assert "Cannot build index: freeze a split first" in failed.output
    assert mock.call_args.kwargs["limit"] is None
    assert runner.invoke(cli.app, ["index", "lidc_idri", "--limit", "0"]).exit_code == 2


def test_html_export_is_confined_to_results_before_loading(
    phantom: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    html_path = settings.data_path("results", "demo", "report.html")
    invocation = runner.invoke(cli.app, ["analyze", str(phantom), "--html", str(html_path)])
    assert invocation.exit_code == 0, invocation.output
    html = html_path.read_text()
    assert "data:image/png;base64," in html
    assert "not medical advice" in html
    outside = tmp_path / "public.html"
    monkeypatch.setattr(
        "thoraxbench.study.load_study_dir", lambda *_args, **_kwargs: pytest.fail("study read")
    )
    rejected = runner.invoke(cli.app, ["analyze", str(phantom), "--html", str(outside)])
    assert rejected.exit_code == 1
    assert "results" in rejected.output
    assert not outside.exists()
