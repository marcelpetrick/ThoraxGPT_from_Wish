# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Index build over a synthetic data directory laid out like the real acquisition."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

import thoraxbench.index as idx
from thoraxbench.config import REPO_ROOT, Settings
from thoraxbench.dicom import discover_series
from thoraxbench.index import build_index, case_records, load_index, open_study
from thoraxbench.registry import PolicyError
from thoraxbench.splits import CaseRecord, Phase, SealedAccessError, make_split, save_split
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series, write_seg

pytestmark = pytest.mark.integration

NODULE = """<unblindedReadNodule><noduleID>1</noduleID><roi><imageZposition>0.0</imageZposition>
<inclusion>TRUE</inclusion><edgeMap><xCoord>40</xCoord><yCoord>40</yCoord></edgeMap>
<edgeMap><xCoord>44</xCoord><yCoord>40</yCoord></edgeMap></roi></unblindedReadNodule>"""
XML = '<?xml version="1.0"?><LidcReadMessage xmlns="http://www.nih.gov"><readingSession>{}</readingSession></LidcReadMessage>'


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("THORAXBENCH_DATA_DIR", str(tmp_path))
    spec = PhantomSpec(shape=(40, 64, 64), spacing_mm=(5.0, 5.0, 5.0), nodule_radius_mm=8.0)
    hu = make_phantom(spec)
    xml_dir = tmp_path / "raw" / "lidc_idri" / "_labels" / "xml_selected"
    xml_dir.mkdir(parents=True)
    for pid in ("P1", "P2"):
        staging = write_dicom_series(
            hu, tmp_path / "staging" / pid, spec.spacing_mm, patient_id=pid, include_scout=False
        )
        series = discover_series(staging)[0]
        (tmp_path / "raw" / "lidc_idri" / pid).mkdir(parents=True)
        staging.rename(tmp_path / "raw" / "lidc_idri" / pid / series.series_uid)
        (xml_dir / f"{series.series_uid}.xml").write_text(XML.format(NODULE if pid == "P1" else ""))
        nd = tmp_path / "raw" / "nsclc_radiogenomics" / pid
        ct = write_dicom_series(
            hu,
            tmp_path / "staging_ct" / pid,
            spec.spacing_mm,
            patient_id=pid,
            include_scout=False,
            shuffle=False,
        )
        nd.mkdir(parents=True)
        ct.rename(nd / discover_series(ct)[0].series_uid)
        mask = np.zeros(spec.shape, dtype=bool)
        mask[10:14, 20:30, 20:28] = True
        positions = [
            float((spec.shape[0] - 1 - k) * spec.spacing_mm[0]) for k in range(spec.shape[0])
        ]
        write_seg(mask, nd / "seg" / "seg.dcm", spec.spacing_mm, z_positions_mm=positions)
    (tmp_path / "raw" / "lidc_idri" / "EMPTY").mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "configs").symlink_to(REPO_ROOT / "configs", target_is_directory=True)
    for dataset in idx.SUPPORTED:
        (tmp_path / "raw" / dataset / "SEALED").mkdir()
        records = [
            CaseRecord(dataset=dataset, patient_id=pid, case_id=pid)
            for pid in ("P1", "P2", "SEALED")
        ]
        if dataset == "lidc_idri":
            records.append(CaseRecord(dataset=dataset, patient_id="P1", case_id="EMPTY"))
        for seed in range(100):
            split = make_split(records, dataset, salt=f"synthetic-{seed}")
            if split.cases(Phase.SEALED) == ["SEALED"]:
                break
        assert split.cases(Phase.SEALED) == ["SEALED"]
        save_split(split, tmp_path, repo / "manifests")
    return tmp_path


def _settings(data_dir: Path) -> Settings:
    return Settings(repo_root=data_dir / "repo", data_dir=data_dir)


def test_build_and_load_lidc(data_dir: Path) -> None:
    settings = _settings(data_dir)
    messages: list[str] = []
    entries = build_index("lidc_idri", settings, progress=messages.append)
    assert [e.case_id for e in entries] == ["P1", "P2"]
    assert any("skip EMPTY" in m for m in messages)
    by_id = load_index("lidc_idri", settings)
    assert by_id["P1"].stratum == "nodule"
    assert by_id["P2"].stratum == "negative"
    assert {r.stratum for r in case_records(by_id)} == {"nodule", "negative"}
    study = open_study(by_id["P1"], settings)
    assert study.cues == by_id["P1"].cues
    assert [e.case_id for e in build_index("lidc_idri", settings, limit=2)] == ["P1"]


def test_build_nsclc(data_dir: Path) -> None:
    entries = build_index("nsclc_radiogenomics", _settings(data_dir))
    assert len(entries) == 2
    ref = entries[0].reference
    assert ref.labels == {"pulmonary_mass": True}  # 10 px * 5 mm = 50 mm
    lesion = ref.lesions[0]
    assert lesion.diameter_mm == pytest.approx(50.0)
    assert lesion.center_zyx[0] == pytest.approx(11.5 * 5.0)
    assert entries[0].stratum == "tumour"


def test_unsupported_and_gated(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="no label loader"):
        build_index("ct_rate", _settings(data_dir))
    monkeypatch.setattr(idx, "SUPPORTED", (*idx.SUPPORTED, "ct_rate"))
    with pytest.raises(PolicyError):
        build_index("ct_rate", _settings(data_dir))


def test_sealed_folders_and_split_file_never_read(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_load = idx.load_study_dir
    original_reference = idx._reference
    original_read = Path.read_text
    loaded: list[str] = []
    labelled: list[str] = []

    def load(path: Path, **kwargs: Any) -> Any:
        assert path.name != "SEALED"
        loaded.append(path.name)
        return original_load(path, **kwargs)

    def reference(dataset: str, path: Path, study: Any, settings: Settings) -> Any:
        assert path.name != "SEALED"
        labelled.append(path.name)
        return original_reference(dataset, path, study, settings)

    def read(path: Path, *args: Any, **kwargs: Any) -> str:
        assert "sealed" not in path.parts
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(idx, "load_study_dir", load)
    monkeypatch.setattr(idx, "_reference", reference)
    monkeypatch.setattr(Path, "read_text", read)
    entries = build_index("lidc_idri", _settings(data_dir))
    assert loaded == ["EMPTY", "P1", "P2"]
    assert labelled == ["P1", "P2"]
    sealed = entries[0].model_copy(update={"case_id": "SEALED", "path": "raw/lidc_idri/SEALED"})
    with pytest.raises(SealedAccessError):
        open_study(sealed, _settings(data_dir))
    assert "SEALED" not in loaded


def test_missing_split_fails_before_study_or_label_reads(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (data_dir / "splits" / "lidc_idri.json").unlink()

    def reject(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("missing split allowed a study or label read")

    monkeypatch.setattr(idx, "load_study_dir", reject)
    monkeypatch.setattr(idx, "_reference", reject)
    with pytest.raises(FileNotFoundError):
        build_index("lidc_idri", _settings(data_dir))


def test_stale_index_path_cannot_redirect_to_sealed_case(data_dir: Path) -> None:
    entry = build_index("lidc_idri", _settings(data_dir))[0]
    redirected = entry.model_copy(update={"path": "raw/lidc_idri/SEALED"})
    with pytest.raises(SealedAccessError, match="path"):
        open_study(redirected, _settings(data_dir))
    original = data_dir / entry.path
    original.rename(original.with_name("original"))
    original.symlink_to(original.parent / "SEALED", target_is_directory=True)
    with pytest.raises(SealedAccessError, match="path"):
        open_study(entry, _settings(data_dir))
