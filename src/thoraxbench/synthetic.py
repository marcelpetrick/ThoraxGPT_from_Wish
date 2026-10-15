# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Synthetic chest-CT phantoms written as real DICOM series.

Used by the test-suite, the demo command and the UI smoke tests, so no patient data is
ever needed to exercise the full pipeline. The phantom is *not* anatomically realistic; it
contains the HU structures the pipeline cares about: air, body soft tissue, two aerated
lungs, a spine, and optional findings (solid nodule, pleural effusion, emphysema, coronary
calcification).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

AIR = -1000
SOFT_TISSUE = 40
LUNG = -850
EMPHYSEMA = -980
FLUID = 10
BONE = 700
CALCIUM = 400
NODULE = 30


@dataclass(frozen=True)
class PhantomSpec:
    """Which synthetic findings to include in the phantom."""

    shape: tuple[int, int, int] = (64, 128, 128)
    spacing_mm: tuple[float, float, float] = (5.0, 2.5, 2.5)
    nodule_radius_mm: float = 0.0
    nodule_side: str = "right"
    effusion: bool = False
    emphysema: bool = False
    coronary_calcification: bool = False
    seed: int = 0


def make_phantom(spec: PhantomSpec) -> npt.NDArray[np.int16]:
    """Build a synthetic thorax HU volume ``(z, y, x)`` with index 0 cranial."""
    nz, ny, nx = spec.shape
    dz, dy, dx = spec.spacing_mm
    z, y, x = np.meshgrid(np.arange(nz) * dz, np.arange(ny) * dy, np.arange(nx) * dx, indexing="ij")
    cy, cx = ny * dy / 2, nx * dx / 2
    vol = np.full(spec.shape, AIR, dtype=np.float64)
    body = ((y - cy) / (0.42 * ny * dy)) ** 2 + ((x - cx) / (0.46 * nx * dx)) ** 2 <= 1
    vol[body] = SOFT_TISSUE
    # lungs occupy the middle 80 % of the z range
    z_frac = z / max(nz * dz, 1.0)
    lung_z = (z_frac > 0.08) & (z_frac < 0.88)
    lung_ry, lung_rx = 0.30 * ny * dy, 0.17 * nx * dx
    right_c = cx - 0.22 * nx * dx  # patient right is image left
    left_c = cx + 0.22 * nx * dx
    right_lung = (((y - cy) / lung_ry) ** 2 + ((x - right_c) / lung_rx) ** 2 <= 1) & lung_z
    left_lung = (((y - cy) / lung_ry) ** 2 + ((x - left_c) / lung_rx) ** 2 <= 1) & lung_z
    vol[right_lung | left_lung] = LUNG
    spine = ((y - (cy + 0.30 * ny * dy)) ** 2 + (x - cx) ** 2) <= (0.06 * nx * dx) ** 2
    vol[spine & body] = BONE
    rng = np.random.default_rng(spec.seed)
    if spec.emphysema:
        holes = rng.random(spec.shape) < 0.35
        vol[(right_lung | left_lung) & holes] = EMPHYSEMA
    if spec.effusion:
        dependent = y > cy + 0.12 * ny * dy
        vol[right_lung & dependent] = FLUID
    if spec.coronary_calcification:
        heart_z = (z_frac > 0.55) & (z_frac < 0.65)
        spot = ((y - (cy - 0.05 * ny * dy)) ** 2 + (x - (cx + 0.05 * nx * dx)) ** 2) <= 9.0
        vol[heart_z & spot & body] = CALCIUM
    if spec.nodule_radius_mm > 0:
        nc_x = right_c if spec.nodule_side == "right" else left_c
        nc_z = 0.35 * nz * dz
        nodule = ((z - nc_z) ** 2 + (y - cy) ** 2 + (x - nc_x) ** 2) <= spec.nodule_radius_mm**2
        vol[nodule] = NODULE
    noise = rng.normal(0.0, 8.0, spec.shape)
    return np.clip(np.rint(vol + noise), -1024, 3071).astype(np.int16)


def write_dicom_series(
    hu: npt.NDArray[np.int16],
    out_dir: Path,
    spacing_mm: tuple[float, float, float],
    *,
    patient_id: str = "PHANTOM-0001",
    study_uid: str | None = None,
    series_description: str = "CHEST 5mm",
    include_scout: bool = True,
    shuffle: bool = True,
    duplicate_slice: bool = False,
) -> Path:
    """Write *hu* as an axial CT DICOM series (stored with slope 1, intercept -1024).

    Files are written in shuffled order by default so that loaders must sort by geometry.
    Returns *out_dir*.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    study_uid = study_uid or generate_uid()
    series_uid = generate_uid()
    nz = hu.shape[0]
    dz, dy, dx = spacing_mm
    order = list(range(nz))
    if shuffle:
        order = [int(i) for i in np.random.default_rng(1).permutation(nz)]
    if duplicate_slice:
        order.append(order[0])
    for file_no, k in enumerate(order):
        ds = _base_dataset(patient_id, study_uid, series_uid, series_description)
        ds.InstanceNumber = k + 1
        # index 0 is cranial: highest z position
        ds.ImagePositionPatient = [0.0, 0.0, float((nz - 1 - k) * dz)]
        ds.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        ds.PixelSpacing = [dy, dx]
        ds.SliceThickness = dz
        _set_pixels(ds, hu[k])
        ds.save_as(out_dir / f"img_{file_no:04d}.dcm", enforce_file_format=True)
    if include_scout:
        scout = _base_dataset(patient_id, study_uid, generate_uid(), "SCOUT")
        scout.ImageType = ["ORIGINAL", "PRIMARY", "LOCALIZER"]
        scout.InstanceNumber = 1
        scout.ImagePositionPatient = [0.0, 0.0, 0.0]
        scout.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 0.0, -1.0]
        scout.PixelSpacing = [1.0, 1.0]
        _set_pixels(scout, hu[:, hu.shape[1] // 2, :].astype(np.int16))
        scout.save_as(out_dir / "scout.dcm", enforce_file_format=True)
    (out_dir / "README.txt").write_text("synthetic phantom, not patient data\n", encoding="utf-8")
    return out_dir


def _base_dataset(patient_id: str, study_uid: str, series_uid: str, description: str) -> Dataset:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = CTImageStorage
    sop_uid = generate_uid()
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = Dataset()
    ds.file_meta = meta
    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = sop_uid
    ds.Modality = "CT"
    ds.PatientID = patient_id
    ds.PatientName = "Phantom^Synthetic"
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.SeriesDescription = description
    ds.ImageType = ["ORIGINAL", "PRIMARY", "AXIAL"]
    ds.ConvolutionKernel = "B30f"
    ds.Manufacturer = "ThoraxBench Synthetic"
    ds.RescaleSlope = 1
    ds.RescaleIntercept = -1024
    return ds


def _set_pixels(ds: Dataset, hu_slice: npt.NDArray[np.int16]) -> None:
    stored = (hu_slice.astype(np.int32) + 1024).clip(0, 4095).astype(np.uint16)
    ds.Rows, ds.Columns = stored.shape
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 16
    ds.BitsStored = 12
    ds.HighBit = 11
    ds.PixelRepresentation = 0
    ds.PixelData = stored.tobytes()
