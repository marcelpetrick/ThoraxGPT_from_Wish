# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""DICOM de-identification audit and output redaction on synthetic phantoms (Vision §29)."""

import json
from pathlib import Path

import pydicom
import pytest
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from typer.testing import CliRunner

from thoraxbench import analysis
from thoraxbench.analysis import redact_result
from thoraxbench.cli import main as cli
from thoraxbench.cli import privacy as privacy_cli
from thoraxbench.config import Settings
from thoraxbench.dicom import discover_series
from thoraxbench.privacy import (
    ID_PLACEHOLDER,
    Redactor,
    Root,
    audit_dataset,
    audit_files,
    audit_series,
    audit_study_dir,
    identifier_values,
    settings_redactor,
)
from thoraxbench.splits import CaseRecord, Phase, make_split, save_split
from thoraxbench.study import load_study_dir
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series

runner = CliRunner()

FAKE = {
    "PatientBirthDate": "19010203",
    "OtherPatientIDs": ["MRN-998877", "MRN-112233"],
    "InstitutionName": "Fictional General Hospital",
    "ReferringPhysicianName": "Fakedoc^Imaginary",
    "AccessionNumber": "ACC-55555",
    "PatientComments": "fictional comment text",
}
SEQUENCE_VALUE = "Nested^Fictitious"


def _phantom(tmp_path: Path, name: str = "study", **kwargs: object) -> Path:
    spec = PhantomSpec(shape=(4, 16, 16))
    return write_dicom_series(make_phantom(spec), tmp_path / name, spec.spacing_mm, **kwargs)  # type: ignore[arg-type]


def _inject(folder: Path) -> None:
    for path in sorted(folder.glob("*.dcm")):
        ds = pydicom.dcmread(path)
        for keyword, value in FAKE.items():
            setattr(ds, keyword, value)
        ds.BurnedInAnnotation = "YES"
        block = ds.private_block(0x0009, "FAKE VENDOR", create=True)
        block.add_new(0x01, "LO", "private fictional value")
        item = Dataset()
        item.PerformingPhysicianName = SEQUENCE_VALUE
        ds.RequestAttributesSequence = Sequence([item])
        ds.save_as(path, enforce_file_format=True)


def _values() -> list[str]:
    values = [v for v in FAKE.values() if isinstance(v, str)]
    return [*values, *FAKE["OtherPatientIDs"], SEQUENCE_VALUE, "Phantom^Synthetic", "PHANTOM-0001"]


def test_clean_phantom_flags_only_name_and_review_items(tmp_path: Path) -> None:
    folder = _phantom(tmp_path)
    audit = audit_study_dir(folder)
    assert audit.files_scanned == 5
    assert audit.files_skipped == 1  # README.txt
    keywords = {(f.keyword, f.severity) for f in audit.findings}
    assert keywords == {
        ("PatientName", "fail"),
        ("PatientID", "review"),
        ("BurnedInAnnotation", "review"),
        ("PatientIdentityRemoved", "review"),
    }
    assert not audit.passed
    assert audit.burned_in_annotation == {"absent": 5}
    assert audit.private_tags == 0
    assert all(f.files == 5 for f in audit.findings)


def test_injected_identifiers_are_reported_without_values(tmp_path: Path) -> None:
    folder = _phantom(tmp_path)
    _inject(folder)
    audit = audit_study_dir(folder, pseudonyms={"PHANTOM-0001"})
    found = {f.keyword: f for f in audit.findings}
    for keyword in ("PatientBirthDate", "OtherPatientIDs", "InstitutionName", "AccessionNumber"):
        assert found[keyword].severity == "fail"
    assert found["ReferringPhysicianName"].category == "personnel"
    assert found["PerformingPhysicianName"].severity == "fail"  # nested in a sequence
    assert found["RequestAttributesSequence"].severity == "review"
    assert found["PatientComments"].category == "free_text"
    assert found["PrivateTags"].category == "private_tag"
    assert found["BurnedInAnnotation"].severity == "fail"
    assert found["PatientBirthDate"].tag == "(0010,0030)"
    assert "PatientID" not in found
    assert audit.private_tags == 2
    assert audit.burned_in_annotation == {"YES": 5}
    serialized = audit.model_dump_json() + audit.summary()
    for value in _values():
        assert value not in serialized
    assert "FAIL" in audit.summary()


def test_patient_id_and_name_rules() -> None:
    ds = Dataset()
    ds.PatientID = "LIDC-IDRI-0001"
    ds.PatientName = "LIDC-IDRI-0001"
    ds.PatientIdentityRemoved = "YES"
    ds.BurnedInAnnotation = "NO"
    ds.InstitutionName = ""
    ds.OtherPatientIDs = ["", ""]
    ds.OtherPatientIDsSequence = Sequence([])
    assert audit_dataset(ds, pseudonyms={"LIDC-IDRI-0001"}) == []
    hits = audit_dataset(ds, pseudonyms={"other"})
    assert hits == [
        (
            "PatientID",
            "(0010,0020)",
            "patient_identity",
            "fail",
            "not one of the expected dataset pseudonyms",
        )
    ]
    assert audit_dataset(ds)[0][3] == "review"


def test_audit_series_and_unreadable_files(tmp_path: Path) -> None:
    folder = _phantom(tmp_path)
    series = next(s for s in discover_series(folder) if s.n_files == 4)
    assert audit_series(series).files_scanned == 4
    broken = tmp_path / "broken.dcm"
    broken.write_bytes(b"\x00" * 10)
    missing = tmp_path / "missing.dcm"
    assert audit_files([broken, missing]).files_skipped == 2
    assert audit_files([]).passed


def test_identifier_values_feed_the_redactor(tmp_path: Path) -> None:
    folder = _phantom(tmp_path)
    _inject(folder)
    files = sorted(folder.glob("*.dcm"))
    values = identifier_values(files, keep={"Fictional General Hospital"})
    assert {"19010203", "MRN-998877", "MRN-112233", "ACC-55555"} <= values
    assert "Fictional General Hospital" not in values
    assert "PHANTOM-0001" not in values
    assert "fictional comment text" not in values  # review-level by default
    assert "fictional comment text" in identifier_values(files, severities=("fail", "review"))
    assert identifier_values([tmp_path / "missing.dcm"]) == frozenset()
    same = _phantom(tmp_path, "same", patient_id="Phantom^Synthetic")
    assert "Phantom^Synthetic" not in identifier_values(sorted(same.glob("*.dcm")))
    redactor = Redactor(identifiers=values)
    text = "MRN-998877 accession ACC-55555 born 19010203"
    assert (
        redactor.redact(text)
        == f"{ID_PLACEHOLDER} accession {ID_PLACEHOLDER} born {ID_PLACEHOLDER}"
    )


def test_redactor_paths(tmp_path: Path) -> None:
    data = tmp_path / "data"
    home = tmp_path / "home" / "user"
    redactor = Redactor.for_roots(
        [Root(str(data), "[data]"), Root(str(home), "[home]", keep_relative=False), Root("/", "x")]
    )
    assert redactor.redact(f"{data}/raw/lidc/P1/a.dcm") == "[data]/raw/lidc/P1/a.dcm"
    assert redactor.redact(f"{home}/Patients/Doe/scan") == "[home]/scan"
    assert redactor.redact(f"at {home}") == "at [home]"
    assert redactor.redact(f"{data}2/x") == "[path]/x"
    assert redactor.redact("see /srv/cases/Doe/s1, ok") == "see [path]/s1, ok"
    assert redactor.redact(r"C:\Users\jdoe\scan\a.dcm") == "[path]/a.dcm"
    unchanged = "http://127.0.0.1:11434/api/generate and/or 1/2/3 mm/year"
    assert redactor.redact(unchanged) == unchanged
    once = redactor.redact(f"{data}/raw and /srv/x/y")
    assert redactor.redact(once) == once
    link = tmp_path / "link"
    link.symlink_to(data, target_is_directory=True)
    data.mkdir()
    linked = Redactor.for_roots([Root(str(link), "[data]")])
    assert linked.redact(f"{data}/raw") == "[data]/raw"


def test_redactor_identifiers_and_objects() -> None:
    redactor = Redactor(identifiers=frozenset({"Doe^John", "p"}))
    assert redactor.redact("Doe^John / Doe John / John") == "[redacted] / [redacted] / [redacted]"
    assert redactor.redact("pp p") == "pp p"
    obj = {"/srv/a/b": ["Doe", ("x", 1)], "n": None}
    assert redactor.redact_obj(obj) == {"[path]/b": ["[redacted]", ["x", 1]], "n": None}


def test_settings_redactor_covers_data_repo_and_home(tmp_path: Path) -> None:
    settings = Settings(repo_root=tmp_path / "repo", data_dir=tmp_path / "repo" / "data")
    redactor = settings_redactor(settings)
    assert redactor.redact(f"{tmp_path}/repo/data/raw") == "[data]/raw"
    assert redactor.redact(f"{tmp_path}/repo/configs") == "[repo]/configs"
    assert redactor.redact(f"{Path.home()}/x/y") == "[home]/y"


def test_analysis_results_are_redacted(phantom_dir: Path) -> None:
    folder = phantom_dir
    study = load_study_dir(folder)
    result = analysis.analyze_study(study, "heuristic-hu", Settings())
    result.raw_error = f"failed reading {folder}/img_0001.dcm"
    result.raw_meta = {"note": "ACC-55555"}
    result.perf.error = f"{Path.home()}/secret/file"
    result.prepared_images = [b"png"]
    redacted = redact_result(result, Redactor(identifiers=frozenset({"ACC-55555"})))
    assert redacted.raw_error == "failed reading [path]/img_0001.dcm"
    assert redacted.raw_meta == {"note": ID_PLACEHOLDER}
    assert redacted.perf.error == "[path]/file"
    assert redacted.prepared_images == [b"png"]
    assert redacted.patient_id == result.patient_id == "PHANTOM-0001"
    assert redacted.provenance == result.provenance
    assert redacted.report == result.report


def test_cli_audit_text_json_and_strict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    monkeypatch.setattr(privacy_cli, "get_settings", lambda: settings)
    folder = _phantom(tmp_path)
    _inject(folder)
    text = runner.invoke(cli.app, ["privacy", "audit", str(folder)])
    assert text.exit_code == 0, text.output
    assert "InstitutionName" in text.output
    assert "does not prove" in text.output
    as_json = runner.invoke(cli.app, ["privacy", "audit", str(folder), "--json"])
    payload = json.loads(as_json.stdout)
    assert payload["files_scanned"] == 5
    strict = runner.invoke(cli.app, ["privacy", "audit", str(folder), "--strict"])
    assert strict.exit_code == 1
    for output in (text.output, as_json.output):
        for value in _values():
            assert value not in output


def test_cli_audit_uses_split_guard_and_pseudonyms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(repo_root=tmp_path, data_dir=tmp_path / "data")
    monkeypatch.setattr(privacy_cli, "get_settings", lambda: settings)
    split = make_split(
        [CaseRecord(dataset="demo", patient_id=f"P-{i}", case_id=f"P-{i}") for i in range(5)],
        "demo",
    )
    save_split(split, settings.data_dir, settings.manifests_dir)
    development = split.cases(Phase.DEVELOPMENT)[0]
    folder = _phantom(settings.data_dir / "raw" / "demo", development, patient_id=development)
    result = runner.invoke(cli.app, ["privacy", "audit", str(folder), "--json"])
    assert result.exit_code == 0, result.output
    keywords = {f["keyword"] for f in json.loads(result.stdout)["findings"]}
    assert "PatientID" not in keywords
    sealed = settings.data_dir / "sealed" / "x"
    sealed.mkdir(parents=True)
    denied = runner.invoke(cli.app, ["privacy", "audit", str(sealed)])
    assert denied.exit_code == 1
    assert "sealed input is forbidden" in denied.output
    missing = runner.invoke(cli.app, ["privacy", "audit", str(tmp_path / "nowhere" / "x")])
    assert missing.exit_code == 1
    assert str(tmp_path) not in missing.output
    assert "[repo]/nowhere/x" in missing.output


def test_cli_analyze_errors_hide_absolute_paths(tmp_path: Path) -> None:
    missing = tmp_path / "Doe_John" / "study"
    result = runner.invoke(cli.app, ["analyze", str(missing)])
    assert result.exit_code == 1
    assert "Analysis failed" in result.output
    assert str(tmp_path) not in result.output
    assert "[path]/study" in result.output


def test_analyze_study_redacts_model_errors(
    phantom_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import Mock

    from thoraxbench.schemas import FindingsReport, PreparedInput, RawOutput

    model = Mock()
    model.prepare.return_value = PreparedInput(view_id="v", view_version="1")
    model.infer.return_value = RawOutput(error=f"cannot open {Path.home()}/cases/Doe/x.npy")
    model.parse.return_value = FindingsReport(abstain=True)
    monkeypatch.setattr(analysis, "load_model", lambda *_args, **_kwargs: model)
    result = analysis.analyze_study(load_study_dir(phantom_dir), "heuristic-hu", Settings())
    assert result.raw_error == "cannot open [home]/x.npy"
    assert result.perf.error == "cannot open [home]/x.npy"
