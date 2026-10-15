# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Study index: one entry per case with reference labels and cached HU cues.

``thoraxbench index <dataset>`` walks ``data/raw/<dataset>/<patient>/<series>/``, loads each
development study once, derives reference labels and deterministic cues, and writes
``data/index/<dataset>.json``. A frozen split must exist before indexing; sealed studies are
never opened. Benchmarks then reuse development cues and labels (Vision §8).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pydicom
from pydantic import BaseModel

from thoraxbench.config import Settings
from thoraxbench.labels import lidc_reference, nsclc_reference
from thoraxbench.preprocess import HUCues
from thoraxbench.registry import load_registry, require_acquirable
from thoraxbench.schemas import ReferenceLabels
from thoraxbench.splits import CaseGuard, CaseRecord, Phase, SealedAccessError
from thoraxbench.study import Study, StudyLoadError, load_study_dir

SUPPORTED = ("lidc_idri", "nsclc_radiogenomics")


class IndexEntry(BaseModel):
    """One indexed case."""

    dataset: str
    case_id: str
    patient_id: str
    series_uid: str
    path: str
    stratum: str
    n_slices: int
    spacing_mm: tuple[float, float, float]
    qc_adequate: bool
    qc_limitations: list[str]
    reference: ReferenceLabels
    cues: HUCues


def index_path(settings: Settings, dataset: str) -> Path:
    """Location of the index file of *dataset*."""
    return settings.data_path("index", f"{dataset}.json")


def _ct_origin(series_dir: Path) -> tuple[float, float]:
    first = next(iter(sorted(series_dir.glob("*.dcm"))))
    ipp = pydicom.dcmread(first, stop_before_pixels=True).ImagePositionPatient
    return float(ipp[0]), float(ipp[1])


def _reference(
    dataset: str, patient_dir: Path, study: Study, settings: Settings
) -> ReferenceLabels:
    if dataset == "lidc_idri":
        xml = settings.data_path(
            "raw", dataset, "_labels", "xml_selected", f"{study.volume.series_uid}.xml"
        )
        return lidc_reference(xml, study.volume, study.case_id)
    series_dir = patient_dir / study.volume.series_uid
    return nsclc_reference(patient_dir, study.volume, _ct_origin(series_dir), study.case_id)


def _stratum(dataset: str, ref: ReferenceLabels) -> str:
    if dataset == "lidc_idri":
        return "nodule" if ref.labels.get("pulmonary_nodule") else "negative"
    return "tumour"


def build_index(
    dataset: str,
    settings: Settings,
    *,
    progress: Callable[[str], None] = lambda _msg: None,
    limit: int | None = None,
) -> list[IndexEntry]:
    """Index only development folders of an approved dataset with an existing frozen split.

    Raises:
        ValueError: if the dataset has no label loader yet.
        thoraxbench.registry.PolicyError: if the dataset is not approved.
        FileNotFoundError: if the frozen split does not exist.
    """
    if dataset not in SUPPORTED:
        msg = f"no label loader for {dataset}; supported: {', '.join(SUPPORTED)}"
        raise ValueError(msg)
    require_acquirable(load_registry(settings.configs_dir / "datasets")[dataset])
    root = settings.data_path("raw", dataset)
    guard = CaseGuard.load(settings.data_dir, settings.manifests_dir, dataset)
    patients = [root / case_id for case_id in guard.cases(Phase.DEVELOPMENT)]
    entries: list[IndexEntry] = []
    for patient_dir in patients[:limit]:
        guard.check(patient_dir.name, Phase.DEVELOPMENT)
        _check_case_path(patient_dir, dataset, patient_dir.name, settings)
        try:
            study = load_study_dir(patient_dir, dataset=dataset, case_id=patient_dir.name)
        except StudyLoadError as exc:
            progress(f"skip {patient_dir.name}: {exc}")
            continue
        ref = _reference(dataset, patient_dir, study, settings)
        entry = IndexEntry(
            dataset=dataset,
            case_id=study.case_id,
            patient_id=study.patient_id,
            series_uid=study.volume.series_uid,
            path=str(patient_dir.relative_to(settings.data_dir)),
            stratum=_stratum(dataset, ref),
            n_slices=study.volume.shape[0],
            spacing_mm=study.volume.spacing_mm,
            qc_adequate=study.qc.adequate,
            qc_limitations=study.qc.limitations,
            reference=ref,
            cues=study.cues,
        )
        entries.append(entry)
        progress(f"indexed {entry.case_id}: {entry.stratum}, {len(ref.lesions)} lesion(s)")
    out = index_path(settings, dataset)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps([e.model_dump(mode="json") for e in entries], indent=1) + "\n", encoding="utf-8"
    )
    return entries


def load_index(dataset: str, settings: Settings) -> dict[str, IndexEntry]:
    """Read the index of *dataset* keyed by case id (FileNotFoundError if not built)."""
    data = json.loads(index_path(settings, dataset).read_text(encoding="utf-8"))
    return {e["case_id"]: IndexEntry.model_validate(e) for e in data}


def case_records(entries: dict[str, IndexEntry]) -> list[CaseRecord]:
    """Split input records (patient + stratum) from an index."""
    return [
        CaseRecord(dataset=e.dataset, patient_id=e.patient_id, case_id=e.case_id, stratum=e.stratum)
        for e in entries.values()
    ]


def _check_case_path(path: Path, dataset: str, case_id: str, settings: Settings) -> None:
    root = settings.data_path("raw", dataset).resolve()
    expected = root / case_id
    if expected.parent != root or path.resolve() != expected or expected.resolve() != expected:
        msg = f"case {case_id} path is not its development dataset folder"
        raise SealedAccessError(msg)


def open_study(entry: IndexEntry, settings: Settings) -> Study:
    """Load a guarded development study and attach its cached cues."""
    guard = CaseGuard.load(settings.data_dir, settings.manifests_dir, entry.dataset)
    guard.check(entry.case_id, Phase.DEVELOPMENT)
    _check_case_path(settings.data_dir / entry.path, entry.dataset, entry.case_id, settings)
    study = load_study_dir(
        settings.data_dir / entry.path, dataset=entry.dataset, case_id=entry.case_id
    )
    study.attach_cues(entry.cues)
    return study
