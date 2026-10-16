# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""The canonical :class:`Study`: one selected CT series, its HU volume and its cues.

A study is what every model adapter receives in ``prepare``. Loading DICOM is expensive, so
HU volumes are cached as compressed ``.npz`` files in ``data/cache/volumes/`` keyed by the
series UID (the cache is derived data and can be deleted at any time, Vision §23).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from thoraxbench.dicom import QCReport, Volume, load_study
from thoraxbench.preprocess import HUCues, hu_cues
from thoraxbench.privacy import identifier_values

CACHE_VERSION = "1"


@dataclass
class Study:
    """A loaded study ready for preprocessing and inference."""

    dataset: str
    case_id: str
    patient_id: str
    volume: Volume
    selection: dict[str, Any] = field(default_factory=dict)
    _cues: HUCues | None = field(default=None, repr=False)
    identifiers: frozenset[str] = field(default_factory=frozenset, repr=False)

    @property
    def cues(self) -> HUCues:
        """Deterministic HU cues (computed once, lazily)."""
        if self._cues is None:
            self._cues = hu_cues(self.volume)
        return self._cues

    def attach_cues(self, cues: HUCues) -> None:
        """Use previously computed cues (e.g. from the study index) instead of recomputing."""
        self._cues = cues

    @property
    def qc(self) -> QCReport:
        """Quality-control report of the volume."""
        return self.volume.qc


class StudyLoadError(RuntimeError):
    """Raised when a folder contains no usable chest CT series."""


def _cache_file(cache_dir: Path, series_uid: str) -> Path:
    return cache_dir / f"{series_uid}.v{CACHE_VERSION}.npz"


def _save_cache(path: Path, volume: Volume, selection: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "spacing_mm": volume.spacing_mm,
        "patient_id": volume.patient_id,
        "study_uid": volume.study_uid,
        "series_uid": volume.series_uid,
        "z_positions_mm": volume.z_positions_mm,
        "qc": {
            k: v for k, v in volume.qc.to_dict().items() if k not in {"adequate", "limitations"}
        },
        "selection": selection,
    }
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, hu=volume.hu, meta=np.array(json.dumps(meta)))
    tmp.replace(path)


def _load_cache(path: Path) -> tuple[Volume, dict[str, Any]]:
    with np.load(path) as data:
        hu = data["hu"].astype(np.int16)
        meta = json.loads(str(data["meta"]))
    qc_data = meta["qc"]
    qc_data["spacing_mm"] = tuple(qc_data["spacing_mm"])
    volume = Volume(
        hu=hu,
        spacing_mm=tuple(meta["spacing_mm"]),
        patient_id=meta["patient_id"],
        study_uid=meta["study_uid"],
        series_uid=meta["series_uid"],
        z_positions_mm=list(meta["z_positions_mm"]),
        qc=QCReport(**qc_data),
    )
    return volume, dict(meta["selection"])


def load_study_dir(
    path: Path,
    *,
    dataset: str = "adhoc",
    case_id: str | None = None,
    cache_dir: Path | None = None,
    series_uid: str | None = None,
) -> Study:
    """Load the chest CT study below *path* (DICOM folder).

    With *cache_dir* and a known *series_uid*, a cached volume is used when present.

    Raises:
        StudyLoadError: if no eligible CT series exists.
    """
    if cache_dir is not None and series_uid is not None:
        cached = _cache_file(cache_dir, series_uid)
        if cached.exists():
            volume, selection = _load_cache(cached)
            return Study(
                dataset,
                case_id or volume.patient_id,
                volume.patient_id,
                volume,
                selection,
                identifiers=identifier_values(
                    (p for p in path.rglob("*") if p.is_file()), keep=(volume.patient_id,)
                ),
            )
    loaded, selection = load_study(path)
    if loaded is None:
        msg = f"no eligible axial chest CT series below {path}: {selection['reason']}"
        raise StudyLoadError(msg)
    volume = loaded
    if cache_dir is not None:
        _save_cache(_cache_file(cache_dir, volume.series_uid), volume, selection)
    return Study(
        dataset,
        case_id or volume.patient_id,
        volume.patient_id,
        volume,
        selection,
        identifiers=identifier_values(
            (p for p in path.rglob("*") if p.is_file()), keep=(volume.patient_id,)
        ),
    )
