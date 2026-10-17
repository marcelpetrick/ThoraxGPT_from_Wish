# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Detector baseline through the real benchmark runner (stub network, fake pinned weights)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
import yaml

import thoraxbench.adapters.monai_detector as adapter_module
import thoraxbench.benchmark.checkpoint as checkpoint_module
from thoraxbench.benchmark import load_experiment, run_experiment, write_outputs
from thoraxbench.config import REPO_ROOT, Settings
from thoraxbench.detectors.bundle import BundleFile, bundle_dir
from thoraxbench.detectors.preprocess import BundleGeometry, mm_to_box
from thoraxbench.detectors.retinanet import Detections, DetectorParams
from thoraxbench.dicom import discover_series
from thoraxbench.index import build_index, load_index
from thoraxbench.splits import CaseRecord, Phase, make_split, save_split
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series

pytestmark = pytest.mark.integration

NODULE = """<unblindedReadNodule><noduleID>1</noduleID><roi><imageZposition>{z}</imageZposition>
<inclusion>TRUE</inclusion><edgeMap><xCoord>40</xCoord><yCoord>30</yCoord></edgeMap>
<edgeMap><xCoord>44</xCoord><yCoord>30</yCoord></edgeMap></roi></unblindedReadNodule>"""
XML = (
    '<?xml version="1.0"?><LidcReadMessage xmlns="http://www.nih.gov">'
    "<readingSession>{}</readingSession></LidcReadMessage>"
)
DEV = ("P1", "P2", "P3")


@pytest.fixture(scope="module")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """Three development LIDC-like patients, P1 with one reference nodule; indexed."""
    root = tmp_path_factory.mktemp("detector-bench")
    spec = PhantomSpec(shape=(40, 64, 64), spacing_mm=(5.0, 5.0, 5.0))
    hu = make_phantom(spec)
    xml_dir = root / "raw" / "lidc_idri" / "_labels" / "xml_selected"
    xml_dir.mkdir(parents=True)
    for pid in DEV:
        staging = write_dicom_series(
            hu, root / "staging" / pid, spec.spacing_mm, patient_id=pid, include_scout=False
        )
        series = discover_series(staging)[0]
        (root / "raw" / "lidc_idri" / pid).mkdir(parents=True)
        staging.rename(root / "raw" / "lidc_idri" / pid / series.series_uid)
        mark = NODULE.format(z=100.0) if pid == "P1" else ""
        (xml_dir / f"{series.series_uid}.xml").write_text(XML.format(mark))
    (root / "raw" / "lidc_idri" / "SEALED").mkdir()
    repo = root / "repo"
    repo.mkdir()
    (repo / "configs").symlink_to(REPO_ROOT / "configs", target_is_directory=True)
    records = [CaseRecord(dataset="lidc_idri", patient_id=p, case_id=p) for p in (*DEV, "SEALED")]
    for seed in range(200):
        split = make_split(records, "lidc_idri", salt=f"det-{seed}")
        if split.cases(Phase.SEALED) == ["SEALED"]:
            break
    assert split.cases(Phase.SEALED) == ["SEALED"]
    save_split(split, root, repo / "manifests")
    out = Settings(repo_root=repo, data_dir=root)
    assert [e.case_id for e in build_index("lidc_idri", out)] == list(DEV)
    return out


@pytest.fixture
def stub_detector(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Fake pinned weights and a stub network: one hit on P1's nodule plus one far FP."""
    payload = b"fake weights"
    item = BundleFile("models/model.pt", len(payload), hashlib.sha256(payload).hexdigest())
    target = bundle_dir(settings) / item.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    for module in (adapter_module, checkpoint_module):
        monkeypatch.setattr(module, "WEIGHTS_ITEM", item)
    monkeypatch.setattr(adapter_module, "detector_packages_available", lambda: True)
    reference = load_index("lidc_idri", settings)["P1"].reference.lesions[0].center_zyx
    devices: list[str] = []

    class Stub:
        def detect(self, volume_xyz: npt.NDArray[np.float32]) -> Detections:
            nx, ny, nz = volume_xyz.shape
            geometry = BundleGeometry((40, 64, 64), (5.0, 5.0, 5.0), (nz, ny, nx))
            boxes = [
                mm_to_box(reference, (6.0, 6.0, 6.0), geometry),
                mm_to_box((20.0, 20.0, 20.0), (6.0, 6.0, 6.0), geometry),
            ]
            devices.append("stub")
            return Detections(
                boxes=np.asarray(boxes, dtype=np.float64),
                scores=np.asarray([0.9, 0.3]),
                meta={"device": "stub"},
            )

    def factory(weights: Path, digest: str, params: DetectorParams) -> Stub:
        assert digest == item.sha256
        return Stub()

    monkeypatch.setattr(adapter_module, "cached_backend", factory)
    return devices


def _experiment(tmp_path: Path, **extra: Any) -> Path:
    data = {
        "id": "T013",
        "title": "detector synthetic",
        "model": "monai-lung-nodule",
        "phases": ["calibration", "internal_test"],
        "datasets": ["lidc_idri"],
        "labels": ["pulmonary_nodule"],
        "n_boot": 20,
    } | extra
    path = tmp_path / "T013.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_detector_run_scores_study_and_lesion_level(
    tmp_path: Path, settings: Settings, stub_detector: list[str]
) -> None:
    result = run_experiment(load_experiment(_experiment(tmp_path)), settings)
    (run,) = result.runs
    assert run.status_counts["scored"] == 3
    assert len(stub_detector) == 3
    metrics = run.metrics
    assert metrics["possible_training_overlap"] == {"lidc_idri": "yes"}
    per = metrics["per_dataset"]["lidc_idri"]
    assert per["possible_training_overlap"] == "yes"
    assert (per["n_cases"], per["n_scored"]) == (3, 3)
    task_c = metrics["task_c"]
    assert task_c["n_scans"] == 3
    strict = task_c["all_readers"]
    assert (strict["n_lesions"], strict["sensitivity"]) == (1, 1.0)
    assert strict["fp_per_scan"] == pytest.approx(5 / 3)  # far FP everywhere + hits on P2/P3
    assert strict["froc_at"]["1.0"] == 1.0
    # LUNA16 style: the single-reader nodule is ignored, not a target
    assert task_c["luna16_style"]["n_lesions"] == 0
    assert per["task_c"] == task_c
    assert run.provenance.model_hash == checkpoint_module.WEIGHTS_ITEM.sha256
    assert any("Task C (lesion localisation) is scored" in n for n in result.notes)
    _json_path, md_path = write_outputs(result, settings)
    markdown = md_path.read_text(encoding="utf-8")
    assert "possible_training_overlap: lidc_idri=yes" in markdown
    assert "### Task C — lesion level" in markdown
    assert "| lidc_idri | yes | all_readers | 3 | 1 |" in markdown
    assert "### Per dataset — study level" in markdown
    case = next(iter((result.output_dir or tmp_path).glob("units/*.json")), None)
    if case is not None:
        stored = json.loads(case.read_text(encoding="utf-8"))
        assert stored["report"]["lesions"]


def test_heuristic_run_keeps_task_c_unscored(tmp_path: Path, settings: Settings) -> None:
    result = run_experiment(
        load_experiment(_experiment(tmp_path, id="T000", model="heuristic-hu")), settings
    )
    (run,) = result.runs
    assert run.metrics["task_c"] is None
    assert run.metrics["possible_training_overlap"] == {"lidc_idri": "no"}
    assert any("not scored" in n for n in result.notes)
