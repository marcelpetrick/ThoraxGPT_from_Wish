# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
from pathlib import Path

import pytest

from thoraxbench.labels import cluster_nodules, lidc_reference, parse_lidc_xml
from thoraxbench.study import Study, load_study_dir


def _roi(z: float, pts: list[tuple[int, int]], inclusion: str = "TRUE") -> str:
    edges = "".join(f"<edgeMap><xCoord>{x}</xCoord><yCoord>{y}</yCoord></edgeMap>" for x, y in pts)
    return (
        f"<roi><imageZposition>{z}</imageZposition><imageSOP_UID>1</imageSOP_UID>"
        f"<inclusion>{inclusion}</inclusion>{edges}</roi>"
    )


def _nodule(nid: str, rois: str, malignancy: int | None = 3) -> str:
    chars = (
        f"<characteristics><malignancy>{malignancy}</malignancy></characteristics>"
        if malignancy
        else ""
    )
    return f"<unblindedReadNodule><noduleID>{nid}</noduleID>{chars}{rois}</unblindedReadNodule>"


def _xml(sessions: list[str]) -> str:
    body = "".join(
        f"<readingSession>{s}<nonNodule><nonNoduleID>9</nonNoduleID></nonNodule></readingSession>"
        for s in sessions
    )
    return (
        f'<?xml version="1.0"?><LidcReadMessage xmlns="http://www.nih.gov">{body}</LidcReadMessage>'
    )


@pytest.fixture(scope="module")
def study(phantom_dir: Path) -> Study:
    return load_study_dir(phantom_dir)


def test_parse_cluster_and_reference(tmp_path: Path, study: Study) -> None:
    z = study.volume.z_positions_mm[20]
    big = [(40, 40), (52, 40), (46, 34), (46, 46)]  # 12 px * 2.5 mm = 30 mm wide
    nodule = [(60, 60), (64, 60)]  # 4 px * 2.5 = 10 mm
    xml = _xml(
        [
            _nodule("A", _roi(z, nodule) + _roi(z, [(1, 1)], "FALSE")),
            _nodule("B", _roi(z, nodule), malignancy=None) + _nodule("BIG", _roi(z, big)),
            _nodule("small", _roi(z, [(10, 10)])),
        ]
    )
    path = tmp_path / "x.xml"
    path.write_text(xml)
    marks = parse_lidc_xml(path)
    assert len(marks) == 4
    assert any(m.small for m in marks)
    lesions = cluster_nodules(marks, study.volume)
    assert len(lesions) == 2
    nod = next(les for les in lesions if les.label == "pulmonary_nodule")
    assert nod.readers == 2
    assert nod.diameter_mm == pytest.approx(10.0)
    assert nod.malignancy == 3.0
    ref = lidc_reference(path, study.volume, "case")
    assert ref.labels == {"pulmonary_nodule": True, "pulmonary_mass": True}


def test_negative_study(tmp_path: Path, study: Study) -> None:
    path = tmp_path / "neg.xml"
    path.write_text(_xml([_nodule("s", _roi(0.0, [(5, 5)]))]))
    ref = lidc_reference(path, study.volume, "c")
    assert ref.labels == {"pulmonary_nodule": False, "pulmonary_mass": False}
    assert ref.lesions == []
