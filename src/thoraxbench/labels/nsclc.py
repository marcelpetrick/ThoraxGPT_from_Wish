# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""NSCLC-Radiogenomics DICOM-SEG tumour masks → lesion + study labels.

Every patient in the collection has a primary non-small-cell lung cancer; the 3D Slicer
segmentation gives its extent. Diameter = longest in-plane bounding-box side over all frames.
Study labels: ``pulmonary_mass = True`` if the tumour is >= 30 mm, otherwise
``pulmonary_nodule = True``. All other labels (including the other size class) stay unknown,
because the collection does not annotate further lesions.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pydicom

from thoraxbench.dicom import Volume
from thoraxbench.schemas import LesionAnnotation, ReferenceLabels

MASS_MM = 30.0


def find_seg(patient_dir: Path) -> Path | None:
    """First DICOM-SEG file below *patient_dir*, or ``None``."""
    for path in sorted(patient_dir.rglob("*.dcm")):
        ds = pydicom.dcmread(path, stop_before_pixels=True)
        if str(ds.get("Modality", "")) == "SEG":
            return path
    return None


def seg_lesion(
    seg_path: Path, volume: Volume, ct_origin_xy: tuple[float, float]
) -> LesionAnnotation:
    """Tumour lesion from a binary DICOM-SEG, in canonical volume millimetres."""
    ds = pydicom.dcmread(seg_path)
    frames = np.asarray(ds.pixel_array)
    if frames.ndim == 2:
        frames = frames[np.newaxis]
    sy, sx = (
        float(v) for v in ds.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0].PixelSpacing
    )
    zs: list[float] = []
    ys: list[float] = []
    xs: list[float] = []
    diameter = 0.0
    dz = volume.spacing_mm[0]
    positions = np.asarray(volume.z_positions_mm)
    for k, frame in enumerate(frames):
        rows, cols = np.nonzero(frame)
        if rows.size == 0:
            continue
        ipp = [
            float(v)
            for v in ds.PerFrameFunctionalGroupsSequence[k]
            .PlanePositionSequence[0]
            .ImagePositionPatient
        ]
        z_index = int(np.argmin(np.abs(positions - ipp[2])))
        zs.extend([z_index * dz] * rows.size)
        ys.extend((ipp[1] + rows * sy - ct_origin_xy[1]).tolist())
        xs.extend((ipp[0] + cols * sx - ct_origin_xy[0]).tolist())
        extent = max((rows.max() - rows.min() + 1) * sy, (cols.max() - cols.min() + 1) * sx)
        diameter = max(diameter, float(extent))
    center = (float(np.mean(zs)), float(np.mean(ys)), float(np.mean(xs))) if zs else (0.0, 0.0, 0.0)
    return LesionAnnotation(
        label="pulmonary_mass" if diameter >= MASS_MM else "pulmonary_nodule",
        center_zyx=center,
        diameter_mm=round(diameter, 1),
        readers=1,
        native_term="NSCLC primary tumour (DICOM-SEG)",
    )


def nsclc_reference(
    patient_dir: Path, volume: Volume, ct_origin_xy: tuple[float, float], case_id: str
) -> ReferenceLabels:
    """Build the reference labels of one NSCLC-Radiogenomics patient."""
    seg = find_seg(patient_dir)
    labels: dict[str, bool | None] = {}
    lesions: list[LesionAnnotation] = []
    if seg is not None:
        lesion = seg_lesion(seg, volume, ct_origin_xy)
        lesions.append(lesion)
        labels[lesion.label] = True
    return ReferenceLabels(
        dataset="nsclc_radiogenomics",
        patient_id=volume.patient_id,
        study_uid=case_id,
        labels=labels,
        lesions=lesions,
        native_labels={"source": seg.name if seg else "no SEG", "histology": "NSCLC"},
    )
