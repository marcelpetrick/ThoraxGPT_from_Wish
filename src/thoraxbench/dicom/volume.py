# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Geometry normalisation, Hounsfield-unit volume and quality control (Vision §9.2-9.5).

Conventions of the canonical :class:`Volume`:

* ``hu`` is ``int16`` with shape ``(z, y, x)`` and keeps real Hounsfield units
  (no normalisation, Vision §9.3), clipped to [-1024, 3071].
* Slice index 0 is the most **cranial** (superior) slice, matching radiologist reading order.
* ``spacing_mm`` is ``(z, y, x)`` in millimetres.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pydicom

from thoraxbench.dicom.discovery import SeriesInfo, discover_series, select_series
from thoraxbench.dicom.headers import HEADER_ERRORS
from thoraxbench.dicom.progress import Progress, emit_progress

HU_MIN = -1024
HU_MAX = 3071
DUPLICATE_TOLERANCE_MM = 0.01
GAP_FACTOR = 1.5
MIN_ADEQUATE_SLICES = 20
MIN_ADEQUATE_COVERAGE_MM = 150.0
MAX_ADEQUATE_GAP_MM = 20.0
MIN_LUNG_FRACTION = 0.02

HUArray = npt.NDArray[np.int16]


class DicomPixelError(ValueError):
    """Selected CT pixel loading failed; never silently discard selected slices."""

    code = "dicom_read_error"

    def __init__(self, discovery: dict[str, int], header_error_types: dict[str, int]) -> None:
        super().__init__("Selected CT pixel data could not be decoded")
        self.discovery = dict(discovery)
        self.header_error_types = dict(header_error_types)


@dataclass
class QCReport:
    """Quality-control metadata recorded for every loaded volume (Vision §9.5)."""

    n_slices: int
    spacing_mm: tuple[float, float, float]
    axial_coverage_mm: float
    hu_min: int
    hu_max: int
    hu_percentiles: dict[str, float]
    gaps_mm: list[float]
    duplicates_removed: int
    non_uniform_spacing: bool
    gantry_tilt_suspected: bool
    lung_voxel_fraction: float
    body_region_confidence: float
    contrast: bool | None
    kernel: str | None
    selected_series_reason: str
    warnings: list[str] = field(default_factory=list)

    @property
    def adequate(self) -> bool:
        """Whether the study is adequate for automated reading; otherwise abstain."""
        return (
            self.n_slices >= MIN_ADEQUATE_SLICES
            and self.axial_coverage_mm >= MIN_ADEQUATE_COVERAGE_MM
            and (max(self.gaps_mm) if self.gaps_mm else 0.0) <= MAX_ADEQUATE_GAP_MM
            and self.lung_voxel_fraction >= MIN_LUNG_FRACTION
        )

    @property
    def limitations(self) -> list[str]:
        """Human-readable reasons why the study may be inadequate."""
        out: list[str] = []
        if self.n_slices < MIN_ADEQUATE_SLICES:
            out.append(f"only {self.n_slices} slices")
        if self.axial_coverage_mm < MIN_ADEQUATE_COVERAGE_MM:
            out.append(f"axial coverage {self.axial_coverage_mm:.0f} mm is below full-thorax")
        if self.gaps_mm and max(self.gaps_mm) > MAX_ADEQUATE_GAP_MM:
            out.append(f"slice gap of {max(self.gaps_mm):.1f} mm")
        if self.lung_voxel_fraction < MIN_LUNG_FRACTION:
            out.append("little or no aerated lung found (is this a chest CT?)")
        return out + self.warnings

    def to_dict(self) -> dict[str, Any]:
        """Serialise including derived properties."""
        data = asdict(self)
        data["adequate"] = self.adequate
        data["limitations"] = self.limitations
        return data


@dataclass
class Volume:
    """Canonical HU volume of one CT series."""

    hu: HUArray
    spacing_mm: tuple[float, float, float]
    patient_id: str
    study_uid: str
    series_uid: str
    z_positions_mm: list[float]
    qc: QCReport

    @property
    def shape(self) -> tuple[int, int, int]:
        """Volume shape ``(z, y, x)``."""
        z, y, x = self.hu.shape
        return int(z), int(y), int(x)


def _slice_normal(orientation: tuple[float, ...]) -> npt.NDArray[np.float64]:
    row = np.asarray(orientation[:3], dtype=np.float64)
    col = np.asarray(orientation[3:6], dtype=np.float64)
    return np.cross(row, col)


def _to_hu(ds: pydicom.Dataset) -> npt.NDArray[np.float64]:
    pixels = ds.pixel_array.astype(np.float64)
    padding = ds.get("PixelPaddingValue")
    pad_mask = pixels == float(padding) if padding is not None else None
    slope = float(ds.get("RescaleSlope", 1.0) or 1.0)
    intercept = float(ds.get("RescaleIntercept", 0.0) or 0.0)
    hu = pixels * slope + intercept
    if pad_mask is not None:
        hu[pad_mask] = HU_MIN
    return hu


def lung_voxel_fraction(hu: HUArray) -> float:
    """Fraction of voxels in the aerated-lung range [-950, -500] HU."""
    if hu.size == 0:
        return 0.0
    return float(np.count_nonzero((hu >= -950) & (hu <= -500)) / hu.size)


def _read_pixel_datasets(series: SeriesInfo, progress: Progress | None) -> list[pydicom.Dataset]:
    emit_progress(progress, "pixel_decode", 0, None)
    datasets: list[pydicom.Dataset] = []
    for index, path in enumerate(series.files):
        if progress is not None and index and index % 25 == 0:
            progress("pixel_decode", 0, None)
        datasets.append(pydicom.dcmread(path))
    return datasets


def _decode_slices(
    slices: list[tuple[float, pydicom.Dataset]], progress: Progress | None
) -> list[npt.NDArray[np.float64]]:
    emit_progress(progress, "pixel_decode", 0, len(slices))
    decoded = []
    for completed, (_, dataset) in enumerate(slices, 1):
        decoded.append(_to_hu(dataset))
        emit_progress(progress, "pixel_decode", completed, len(slices))
    return decoded


def load_volume(
    series: SeriesInfo, selection_reason: str = "", *, progress: Progress | None = None
) -> Volume:
    """Load pixel data of *series*, normalise geometry and convert to HU.

    Slices are ordered along the slice normal, duplicates (same position) are removed,
    gaps and non-uniform spacing are recorded as QC warnings instead of being hidden.
    """
    datasets = _read_pixel_datasets(series, progress)
    warnings: list[str] = []
    orientation = series.orientation or (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    normal = _slice_normal(orientation)
    positioned: list[tuple[float, pydicom.Dataset]] = []
    for ds in datasets:
        ipp = ds.get("ImagePositionPatient")
        if ipp is None:
            pos = float(ds.get("InstanceNumber", len(positioned)))
            warnings.append("ImagePositionPatient missing; ordered by InstanceNumber")
        else:
            pos = float(np.dot(np.asarray([float(v) for v in ipp]), normal))
        positioned.append((pos, ds))
    # cranial first: patient "S" is +z in LPS; normal of axial slices points to +z
    positioned.sort(key=lambda item: (-item[0], int(item[1].get("InstanceNumber", 0))))

    unique: list[tuple[float, pydicom.Dataset]] = []
    for pos, item in positioned:
        if unique and abs(unique[-1][0] - pos) < DUPLICATE_TOLERANCE_MM:
            continue
        unique.append((pos, item))
    duplicates = len(positioned) - len(unique)
    if duplicates:
        warnings.append(f"{duplicates} duplicate slice(s) removed")

    positions = [p for p, _ in unique]
    diffs = np.abs(np.diff(positions)) if len(positions) > 1 else np.asarray([], dtype=float)
    first = unique[0][1]
    fallback_dz = float(first.get("SliceThickness", 1.0) or 1.0)
    dz = float(np.median(diffs)) if diffs.size else fallback_dz
    gaps = [float(d) for d in diffs if d > GAP_FACTOR * dz]
    non_uniform = bool(diffs.size and (diffs.max() - diffs.min()) > 0.1 * dz)
    if gaps:
        warnings.append(f"{len(gaps)} gap(s) larger than {GAP_FACTOR}x the median spacing")

    tilt = False
    ipps = [ds.get("ImagePositionPatient") for _, ds in unique]
    if all(v is not None for v in ipps) and len(ipps) > 1:
        pts = np.asarray([[float(c) for c in v] for v in ipps])
        in_plane = pts - np.outer(pts @ normal, normal)
        tilt = bool(np.ptp(in_plane, axis=0).max() > 1.0)
        if tilt:
            warnings.append("in-plane drift of slice origins: gantry tilt suspected")

    decoded = _decode_slices(unique, progress)
    emit_progress(progress, "input_qc", 0, 1)
    stacked = np.stack(decoded)
    hu = np.clip(np.rint(stacked), HU_MIN, HU_MAX).astype(np.int16)
    row_mm, col_mm = (float(v) for v in first.get("PixelSpacing", (1.0, 1.0)))
    spacing = (dz, row_mm, col_mm)
    coverage = float(abs(positions[0] - positions[-1]) + dz) if positions else 0.0
    lung_fraction = lung_voxel_fraction(hu)
    qc = QCReport(
        n_slices=int(hu.shape[0]),
        spacing_mm=spacing,
        axial_coverage_mm=coverage,
        hu_min=int(hu.min()),
        hu_max=int(hu.max()),
        hu_percentiles={
            f"p{q}": float(v)
            for q, v in zip((1, 5, 50, 95, 99), np.percentile(hu, [1, 5, 50, 95, 99]), strict=True)
        },
        gaps_mm=gaps,
        duplicates_removed=duplicates,
        non_uniform_spacing=non_uniform,
        gantry_tilt_suspected=tilt,
        lung_voxel_fraction=lung_fraction,
        body_region_confidence=min(1.0, lung_fraction / 0.15),
        contrast=bool(series.contrast) if series.contrast is not None else None,
        kernel=series.kernel,
        selected_series_reason=selection_reason,
        warnings=sorted(set(warnings)),
    )
    emit_progress(progress, "input_qc", 1, 1)
    return Volume(
        hu=hu,
        spacing_mm=spacing,
        patient_id=series.patient_id,
        study_uid=series.study_uid,
        series_uid=series.series_uid,
        z_positions_mm=positions,
        qc=qc,
    )


def load_study(
    root: Path, *, progress: Progress | None = None
) -> tuple[Volume | None, dict[str, Any]]:
    """Discover, select and load the chest CT series below *root*.

    Returns the volume (or ``None``) and a metadata dict with all selection decisions.
    """
    discovery: dict[str, int] = {}
    header_error_types: dict[str, int] = {}
    series = discover_series(root, discovery, header_error_types, progress=progress)
    selection = select_series(series)
    meta: dict[str, Any] = {
        "n_series": len(series),
        "discovery": discovery,
        "header_error_types": header_error_types,
        "warnings": (
            [f"{discovery['headers_unreadable']} unreadable DICOM header file(s) skipped"]
            if discovery["headers_unreadable"]
            else []
        ),
        "selected_series": selection.series.series_uid if selection.series else None,
        "reason": selection.reason,
        "rejected": selection.rejected,
    }
    if selection.series is None:
        return None, meta
    try:
        volume = load_volume(selection.series, selection.reason, progress=progress)
    except (*HEADER_ERRORS, RuntimeError) as error:
        raise DicomPixelError(discovery, header_error_types) from error
    volume.qc.warnings.extend(meta["warnings"])
    return volume, meta
