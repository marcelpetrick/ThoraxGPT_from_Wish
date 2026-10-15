# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Index build over a synthetic data directory laid out like the real acquisition."""

from pathlib import Path

import numpy as np
import pytest

import thoraxbench.index as idx
from thoraxbench.config import get_settings
from thoraxbench.dicom import discover_series
from thoraxbench.index import build_index, case_records, load_index, open_study
from thoraxbench.registry import PolicyError
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
    return tmp_path


def test_build_and_load_lidc(data_dir: Path) -> None:
    settings = get_settings()
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
    entries = build_index("nsclc_radiogenomics", get_settings())
    assert len(entries) == 2
    ref = entries[0].reference
    assert ref.labels == {"pulmonary_mass": True}  # 10 px * 5 mm = 50 mm
    lesion = ref.lesions[0]
    assert lesion.diameter_mm == pytest.approx(50.0)
    assert lesion.center_zyx[0] == pytest.approx(11.5 * 5.0)
    assert entries[0].stratum == "tumour"


def test_unsupported_and_gated(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="no label loader"):
        build_index("ct_rate", get_settings())
    monkeypatch.setattr(idx, "SUPPORTED", (*idx.SUPPORTED, "ct_rate"))
    with pytest.raises(PolicyError):
        build_index("ct_rate", get_settings())
