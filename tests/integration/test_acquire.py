# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""End-to-end acquisition against a mocked NBIA API (no network, no real data)."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from thoraxbench.acquisition import AcquireOptions, AcquisitionManifest, BudgetError, acquire
from thoraxbench.acquisition import service as service_module
from thoraxbench.cli import acquire as cli_acquire
from thoraxbench.cli.main import app
from thoraxbench.config import Settings
from thoraxbench.registry import PolicyError
from thoraxbench.splits.split import CaseRecord, Phase, make_split, save_split, split_paths

pytestmark = pytest.mark.integration

LICENSE_URI = "http://creativecommons.org/licenses/by/3.0/"
ENTRY = """
id: pilot
name: Pilot Collection
provider: TCIA
license: CC-BY-3.0
license_url: {license_url}
access: public
redistribution: allowed_with_attribution
source_url: https://example.org/pilot
doi: 10.0000/pilot
raw_format: DICOM
status: {status}
acquisition:
{acquisition}
"""
DEFAULT_ACQ = """  nbia_collection: PILOT COLL
  source_version: v1
  label_files:
  - labels.csv
  - xml.zip
  lidc_xml_archive: xml.zip"""


def _uid(n: int) -> str:
    return f"1.2.826.0.1.{n}"


def _series_zip(n_dicom: int, *, extra: dict[str, bytes] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for i in range(n_dicom):
            bundle.writestr(f"{i + 1:08d}.dcm", b"synthetic-not-dicom-%d" % i)
        bundle.writestr("LICENSE", "License Information. CC BY 3.0 synthetic test text.")
        for name, data in (extra or {}).items():
            bundle.writestr(name, data)
    return buffer.getvalue()


def _xml_zip(uids: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for i, uid in enumerate(uids):
            bundle.writestr(
                f"{i:03d}/{i}.xml", f"<x><SeriesInstanceUid>{uid}</SeriesInstanceUid></x>"
            )
            bundle.writestr(f"dup/{i}.xml", f"<SeriesInstanceUid>{uid}</SeriesInstanceUid>")
        bundle.writestr("readme.txt", "not xml")
    return buffer.getvalue()


@dataclass
class FakeNbia:
    """Routes NBIA/TCIA URLs to synthetic payloads and records every request."""

    patients: int = 4
    images: int = 3
    license_uri: str = LICENSE_URI
    collection: str = "PILOT COLL"
    declared_size: int | None = None
    zips: dict[str, bytes] = field(default_factory=dict)
    fail_status: dict[str, int] = field(default_factory=dict)
    requests: list[str] = field(default_factory=list)

    def rows(self) -> list[dict[str, object]]:
        rows = []
        for n in range(self.patients):
            uid = _uid(n)
            payload = self.zips.setdefault(uid, _series_zip(self.images))
            rows.append(
                {
                    "SeriesInstanceUID": uid,
                    "PatientID": f"PILOT-{n:03d}",
                    "Modality": "CT",
                    "Collection": self.collection,
                    "ImageCount": self.images,
                    "FileSize": self.declared_size or len(payload) * 2,
                    "LicenseURI": self.license_uri,
                    "LicenseName": "CC BY 3.0",
                    "StudyInstanceUID": f"1.2.826.0.2.{n}",
                }
            )
        return rows

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        for marker, status in self.fail_status.items():
            if marker in url:
                return httpx.Response(status)
        path = request.url.path
        if path.endswith("/getSeries"):
            assert "%20" in url  # NBIA collection names keep their space
            return httpx.Response(200, json=self.rows())
        if path.endswith("/getImage"):
            return httpx.Response(200, content=self.zips[request.url.params["SeriesInstanceUID"]])
        if path.endswith("/labels.csv"):
            return httpx.Response(200, content=b"patient,label\n")
        if path.endswith("/xml.zip"):
            return httpx.Response(200, content=_xml_zip([_uid(n) for n in range(self.patients)]))
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))

    def image_requests(self) -> list[str]:
        return [u for u in self.requests if "/getImage" in u]


def _settings(
    tmp_path: Path,
    *,
    status: str = "approved",
    acquisition: str = DEFAULT_ACQ,
    license_url: str = "https://creativecommons.org/licenses/by/3.0/",
    budget: int = 10_000_000,
) -> Settings:
    configs = tmp_path / "configs" / "datasets"
    configs.mkdir(parents=True, exist_ok=True)
    (configs / "pilot.yaml").write_text(
        ENTRY.format(status=status, acquisition=acquisition, license_url=license_url)
    )
    return Settings(repo_root=tmp_path, data_dir=tmp_path / "data", data_budget_bytes=budget)


def _run(
    settings: Settings, fake: FakeNbia, lines: list[str] | None = None, **kwargs: object
) -> service_module.AcquisitionReport:
    options = AcquireOptions(**{"patients": 2, **kwargs})  # type: ignore[arg-type]
    sink = lines if lines is not None else []
    return acquire(
        "pilot", settings, options, client=fake.client(), sleep=lambda _s: None, echo=sink.append
    )


def test_full_acquisition_then_idempotent_resume(tmp_path: Path) -> None:
    settings, fake = _settings(tmp_path), FakeNbia()
    lines: list[str] = []
    report = _run(settings, fake, lines)
    assert report.ok, report.errors
    assert sorted(report.results.values()) == ["downloaded", "downloaded"]
    ds = settings.data_path("raw", "pilot")
    selection = json.loads((ds / "_selection.json").read_text())
    assert len(selection["series"]) == 2
    for row in selection["series"]:
        series_dir = ds / row["PatientID"] / row["SeriesInstanceUID"]
        assert len(list(series_dir.glob("*.dcm"))) == 3
    assert not (ds / ".partial").exists()
    sha = (ds / "_sha256.txt").read_text().splitlines()
    for line in sha:
        digest, rel = line.split("  ", 1)
        assert hashlib.sha256((ds / rel).read_bytes()).hexdigest() == digest
    assert any(rel.endswith("_labels/labels.csv") for rel in (s.split("  ")[1] for s in sha))
    committed = settings.manifests_dir / "datasets" / "pilot.json"
    assert committed.read_text() == (ds / "_acquisition.json").read_text()
    manifest = AcquisitionManifest.model_validate_json(committed.read_text())
    assert manifest.series == 2
    assert manifest.patients == 2
    assert manifest.files == len(sha)
    assert manifest.run_results == {"downloaded": 2}
    assert manifest.doi == "https://doi.org/10.0000/pilot"
    assert "LICENSE file shipped" in (manifest.license_snapshot["text_excerpt"] or "")
    assert ".dcm" not in committed.read_text().replace("<uid>", "")  # IDs/hashes only
    xml = list((ds / "_labels" / "xml_selected").glob("*.xml"))
    assert len(xml) == 4  # two series, each with a duplicate reader file
    assert any("reader XML matched for 2/2" in line for line in lines)
    assert (ds / "_api_log.jsonl").read_text().count("\n") == len(fake.requests)

    fake.requests.clear()
    notes: list[str] = []
    again = _run(settings, fake, notes)
    assert any("--patients is ignored" in line for line in notes)
    assert again.ok
    assert set(again.results.values()) == {"skipped_complete"}
    assert fake.image_requests() == []
    assert not any("/getSeries" in u for u in fake.requests)  # frozen selection reused
    assert again.manifest is not None
    assert again.manifest.downloaded_at == manifest.downloaded_at
    assert again.manifest.previous_run_results == {"downloaded": 2}
    assert again.manifest.run_results == {"skipped_complete": 2}
    assert "skipped_complete=2" in (again.manifest.run_history or "")


def test_verify_detects_changed_and_missing_files(tmp_path: Path) -> None:
    settings, fake = _settings(tmp_path), FakeNbia()
    assert _run(settings, fake).ok
    ds = settings.data_path("raw", "pilot")
    before = (ds / "_acquisition.json").read_text()
    victim = sorted(ds.glob("PILOT-*/*/*.dcm"))[0]
    victim.write_bytes(b"tampered")
    report = _run(settings, fake, verify=True)
    assert not report.ok
    assert any("SHA-256 mismatch" in f for f in report.checksum_failures)
    assert (ds / "_acquisition.json").read_text() == before
    victim.unlink()
    report = _run(settings, fake)
    assert any("missing listed file" in f for f in report.checksum_failures)


def test_dry_run_downloads_and_writes_nothing(tmp_path: Path) -> None:
    settings, fake = _settings(tmp_path), FakeNbia()
    lines: list[str] = []
    report = _run(settings, fake, lines, dry_run=True)
    assert report.plan.fits
    assert len(report.plan.by_state("pending")) == 2
    assert report.results == {}
    assert fake.image_requests() == []
    assert not settings.data_path("raw").exists()
    assert not settings.manifests_dir.exists()
    assert any("pending" in line and _uid(0)[:8] in line for line in lines)
    assert not any("PILOT-" in line for line in lines)  # no patient IDs in the plan output


def test_policy_gate_runs_before_any_request(tmp_path: Path) -> None:
    fake = FakeNbia()
    for status in ("pending_terms_review", "pending_access", "rejected"):
        settings = _settings(tmp_path / status, status=status)
        with pytest.raises(PolicyError, match="acquisition is only allowed"):
            _run(settings, fake)
    assert fake.requests == []


def test_registry_must_name_collection_and_license(tmp_path: Path) -> None:
    fake = FakeNbia()
    with pytest.raises(PolicyError, match="nbia_collection"):
        _run(_settings(tmp_path / "a", acquisition="  source_version: v1"), fake)
    with pytest.raises(PolicyError, match="license_url"):
        _run(_settings(tmp_path / "b", license_url="null"), fake)
    with pytest.raises(KeyError):
        acquire("nope", _settings(tmp_path / "c"), AcquireOptions(), client=fake.client())
    assert fake.requests == []


@pytest.mark.parametrize(
    ("fake", "match"),
    [
        (FakeNbia(license_uri="https://creativecommons.org/licenses/by-nc/3.0/"), "license URI"),
        (FakeNbia(collection="OTHER COLL"), "belongs to 'OTHER COLL'"),
    ],
)
def test_license_is_never_inherited(tmp_path: Path, fake: FakeNbia, match: str) -> None:
    with pytest.raises(PolicyError, match=match):
        _run(_settings(tmp_path), fake)
    assert fake.image_requests() == []


def test_frozen_selection_license_is_rechecked(tmp_path: Path) -> None:
    settings, fake = _settings(tmp_path), FakeNbia()
    assert _run(settings, fake, dry_run=False).ok
    path = settings.data_path("raw", "pilot", "_selection.json")
    payload = json.loads(path.read_text())
    payload["series"][0]["LicenseURI"] = None
    path.write_text(json.dumps(payload))
    with pytest.raises(PolicyError, match="license URI None"):
        _run(settings, fake)


def test_new_selection_needs_patient_count(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="--patients"):
        _run(_settings(tmp_path), FakeNbia(), patients=None)


def test_whole_plan_budget_refusal(tmp_path: Path) -> None:
    fake = FakeNbia(declared_size=4_000_000)
    settings = _settings(tmp_path, budget=7_000_000)
    report = _run(settings, fake, dry_run=True, patients=3)
    assert len(report.plan.items) == 1  # selection stops at the budget
    assert report.plan.fits
    # A frozen selection whose pending bytes exceed the budget is refused before download.
    ds = settings.data_path("raw", "pilot")
    ds.mkdir(parents=True)
    rows = fake.rows()[:2]
    (ds / "_selection.json").write_text(json.dumps({"seed": 1, "rule": "r", "series": rows}))
    lines: list[str] = []
    dry = _run(settings, fake, lines, dry_run=True)
    assert not dry.plan.fits
    assert not dry.ok
    assert any("REFUSED" in line for line in lines)
    with pytest.raises(BudgetError, match="data budget"):
        _run(settings, fake)
    assert fake.image_requests() == []


def test_stream_budget_guard_stops_remaining_series(tmp_path: Path) -> None:
    fake = FakeNbia(declared_size=10)
    for n in range(3):
        fake.zips[_uid(n)] = _series_zip(3, extra={"pad.bin": b"x" * 40_000})
    settings = _settings(tmp_path, budget=20_000)
    report = _run(settings, fake, patients=3)
    assert list(report.results.values()) == ["skipped_budget"] * 3
    assert len(fake.image_requests()) == 1
    assert not report.ok


def test_incomplete_series_directory_is_not_modified(tmp_path: Path) -> None:
    settings, fake = _settings(tmp_path), FakeNbia()
    _run(settings, fake, dry_run=True)
    first = fake.rows()[0]
    stale = settings.data_path(
        "raw", "pilot", str(first["PatientID"]), str(first["SeriesInstanceUID"])
    )
    stale.mkdir(parents=True)
    (stale / "00000001.dcm").write_bytes(b"partial")
    selection = [r for r in fake.rows() if r["PatientID"] == first["PatientID"]]
    (stale.parent.parent / "_selection.json").write_text(json.dumps({"series": selection}))
    report = _run(settings, fake)
    assert report.plan.by_state("incomplete")
    assert report.results == {first["SeriesInstanceUID"]: "error"}
    assert "immutable" in report.errors[0]
    assert (stale / "00000001.dcm").read_bytes() == b"partial"


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        (_series_zip(2), "got 2 DICOM file"),
        (b"not a zip", "not a valid ZIP"),
        (_series_zip(3, extra={"../escape.dcm": b"x"}), "unsafe path"),
        (_series_zip(3, extra={"md5hashes.csv": b"filename,md5\n00000001.dcm,00\n"}), "MD5"),
        (_series_zip(3, extra={"md5hashes.csv": b"gone.dcm,00\n"}), "missing file"),
    ],
)
def test_bad_archives_are_rejected(tmp_path: Path, payload: bytes, match: str) -> None:
    fake = FakeNbia(patients=1)
    fake.zips[_uid(0)] = payload
    settings = _settings(tmp_path)
    report = _run(settings, fake, patients=1)
    assert report.results == {_uid(0): "error"}
    assert match in report.errors[0]
    assert not settings.data_path("raw", "pilot", "PILOT-000").exists()
    assert not settings.data_path("raw", "pilot", "escape.dcm").exists()


def test_valid_md5_list_is_accepted(tmp_path: Path) -> None:
    fake = FakeNbia(patients=1)
    first = b"synthetic-not-dicom-0"
    md5 = hashlib.md5(first, usedforsecurity=False).hexdigest()
    listing = f"filename,md5\n00000001.dcm,{md5}\n\n".encode()
    fake.zips[_uid(0)] = _series_zip(3, extra={"md5hashes.csv": listing})
    report = _run(_settings(tmp_path), fake, patients=1)
    assert report.ok, report.errors


def test_http_errors_are_retried_then_reported(tmp_path: Path) -> None:
    fake = FakeNbia(patients=1, fail_status={"getImage": 503, "labels.csv": 500})
    report = _run(_settings(tmp_path), fake, patients=1)
    assert len(fake.image_requests()) == 3
    assert report.results == {_uid(0): "error"}
    assert any("labels.csv" in e for e in report.errors)
    fake = FakeNbia(fail_status={"getSeries": 500})
    with pytest.raises(service_module.AcquisitionError, match="GET failed"):
        _run(_settings(tmp_path / "x"), fake)


def test_label_configuration_is_validated(tmp_path: Path) -> None:
    acq = "  nbia_collection: PILOT COLL\n  label_files:\n  - ../evil.csv"
    report = _run(_settings(tmp_path / "a", acquisition=acq), FakeNbia(), patients=1)
    assert any("unsafe label file name" in e for e in report.errors)
    acq = "  nbia_collection: PILOT COLL\n  label_files: one.csv"
    report = _run(_settings(tmp_path / "b", acquisition=acq), FakeNbia(), patients=1)
    assert any("must be a list" in e for e in report.errors)
    assert report.manifest is not None
    assert report.manifest.source_version == ""


def test_frozen_split_blocks_new_patients(tmp_path: Path) -> None:
    settings, fake = _settings(tmp_path), FakeNbia()
    cases = [
        CaseRecord(dataset="pilot", patient_id=f"PILOT-{n:03d}", case_id=f"PILOT-{n:03d}")
        for n in range(5)
    ]
    split = make_split(cases, "pilot")
    save_split(split, settings.data_dir, settings.manifests_dir)
    assert "PILOT-000" in {split.patient_of[c] for c in split.cases(Phase.DEVELOPMENT)}
    sealed_file = split_paths(settings.data_dir, settings.manifests_dir, "pilot")["sealed"]
    sealed_before = sealed_file.stat().st_mtime_ns
    with pytest.raises(PolicyError, match="bypass the sealed split"):
        _run(settings, fake)
    ds = settings.data_path("raw", "pilot")
    ds.mkdir(parents=True)
    (ds / "_selection.json").write_text(json.dumps({"series": fake.rows()[:1]}))
    with pytest.raises(PolicyError, match="not part of the frozen split"):
        _run(settings, fake)
    (ds / "PILOT-000").mkdir()  # an existing split patient may be completed
    assert _run(settings, fake).results == {_uid(0): "downloaded"}
    assert sealed_file.stat().st_mtime_ns == sealed_before


def test_target_outside_raw_is_refused(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    settings.data_path("raw").mkdir(parents=True)
    settings.data_path("raw", "pilot").symlink_to(elsewhere)
    with pytest.raises(PolicyError, match="outside"):
        _run(settings, FakeNbia())


def test_empty_series_inventory(tmp_path: Path) -> None:
    fake = FakeNbia(patients=0)
    report = _run(_settings(tmp_path), fake, dry_run=True)
    assert report.plan.items == ()
    assert report.plan.estimate_bytes == 0


# --------------------------------------------------------------------------- CLI
runner = CliRunner()


@pytest.fixture
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeNbia:
    fake = FakeNbia()
    settings = _settings(tmp_path)
    monkeypatch.setattr(cli_acquire, "get_settings", lambda: settings)
    monkeypatch.setattr(service_module, "default_client", fake.client)
    return fake


def test_cli_dry_run_and_download(cli_env: FakeNbia) -> None:
    result = runner.invoke(app, ["acquire", "pilot", "--patients", "1", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Dry run: nothing was downloaded" in result.output
    assert cli_env.image_requests() == []
    result = runner.invoke(app, ["acquire", "pilot", "--patients", "1", "--modality", "ct"])
    assert result.exit_code == 0, result.output
    assert "manifest:" in result.output
    result = runner.invoke(app, ["acquire", "pilot", "--verify"])
    assert result.exit_code == 0, result.output


def test_cli_exit_codes(cli_env: FakeNbia, tmp_path: Path) -> None:
    result = runner.invoke(app, ["acquire", "pilot"])
    assert result.exit_code == 1
    assert "--patients" in result.output
    result = runner.invoke(app, ["acquire", "unknown"])
    assert result.exit_code == 1
    cli_env.fail_status["getImage"] = 500
    result = runner.invoke(app, ["acquire", "pilot", "--patients", "1"])
    assert result.exit_code == 1
    assert "problem:" in result.output
    (tmp_path / "configs" / "datasets" / "pilot.yaml").write_text(
        ENTRY.format(status="rejected", acquisition=DEFAULT_ACQ, license_url=LICENSE_URI)
    )
    result = runner.invoke(app, ["acquire", "pilot", "--patients", "1"])
    assert result.exit_code == 2
    assert "Acquisition refused" in result.output


def test_cli_default_client_is_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    fake = FakeNbia()
    clients: list[httpx.Client] = []

    def make() -> httpx.Client:
        clients.append(fake.client())
        return clients[-1]

    monkeypatch.setattr(service_module, "default_client", make)
    acquire("pilot", settings, AcquireOptions(patients=1, dry_run=True), echo=lambda _s: None)
    assert clients[0].is_closed


def test_series_budget_is_rechecked_against_actual_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, fake = _settings(tmp_path), FakeNbia()
    calls: list[int] = []

    def usage(_settings: Settings) -> int:
        calls.append(1)
        return 0 if len(calls) == 1 else settings.data_budget_bytes

    monkeypatch.setattr(service_module, "_usage", usage)
    report = _run(settings, fake)
    assert set(report.results.values()) == {"skipped_budget"}
    assert "does not fit the remaining data budget" in report.errors[0]
    assert fake.image_requests() == []


def test_existing_reader_xml_is_never_rewritten(tmp_path: Path) -> None:
    settings, fake = _settings(tmp_path), FakeNbia()
    _run(settings, fake, dry_run=True)
    chosen = _run(settings, fake, dry_run=True).plan.by_state("pending")
    xml_dir = settings.data_path("raw", "pilot", "_labels", "xml_selected")
    xml_dir.mkdir(parents=True)
    keep = xml_dir / f"{chosen[0].series_uid}.xml"
    keep.write_bytes(b"pilot reader choice")
    lines: list[str] = []
    assert _run(settings, fake, lines).ok
    assert keep.read_bytes() == b"pilot reader choice"
    assert any("reader XML matched for 2/2" in line for line in lines)
    index = json.loads((xml_dir.parent / "xml_selected_index.json").read_text())
    assert list(index["matched"]) == [chosen[1].series_uid]
    assert index["missing"] == []
    before = (xml_dir.parent / "xml_selected_index.json").read_bytes()
    report = _run(settings, fake, verify=True)
    assert report.ok, report.checksum_failures
    assert report.checksum_failures == []
    assert (xml_dir.parent / "xml_selected_index.json").read_bytes() == before
    assert keep.read_bytes() == b"pilot reader choice"
