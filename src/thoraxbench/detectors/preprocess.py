# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Bundle-adapted input preparation and box-to-millimetre conversion (NumPy/SciPy only).

Adapts ``configs/inference.json`` of MONAI ``lung_nodule_ct_detection`` v0.6.10 for a
canonical :class:`~thoraxbench.dicom.Volume` (``hu`` is ``(z, y, x)``, slice 0 cranial,
rows anterior to posterior, columns patient right to left):

1. linear resampling toward 0.703125 x 0.703125 x 1.25 mm (SciPy corner-aligned grid);
2. HU clip to [-1024, 300] and linear scaling to [0, 1] (``ScaleIntensityRanged``);
3. axis order and flips to RAS ``(x, y, z)`` (``Orientationd(axcodes="RAS")``).

Detector boxes come back as ``xyzxyz`` corners in that RAS voxel grid. They are mapped back
to the reference-lesion frame of :mod:`thoraxbench.labels` (``z = slice * dz``,
``y = row * dy``, ``x = col * dx``) with the exact effective spacing of the resampled grid.
This is not numerically identical to upstream ``Spacingd``; record this adapted view and
do not present scores as a reproduction of the upstream benchmark.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
from scipy import ndimage

from thoraxbench.schemas import LesionCandidate

PREPROCESS_VERSION = "1"
TARGET_SPACING_ZYX = (1.25, 0.703125, 0.703125)
HU_RANGE = (-1024.0, 300.0)

FloatArray = npt.NDArray[np.float32]


def preprocess_sha256() -> str:
    """Hash of every preprocessing parameter that changes the network input."""
    blob = json.dumps(
        {
            "version": PREPROCESS_VERSION,
            "target_spacing_zyx": TARGET_SPACING_ZYX,
            "hu_range": HU_RANGE,
            "interpolation": "scipy.ndimage.zoom order=1 grid_mode=False",
            "orientation": "RAS (x, y, z)",
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


@dataclass(frozen=True)
class BundleGeometry:
    """Source and resampled grid geometry needed to map boxes back to millimetres."""

    source_shape_zyx: tuple[int, int, int]
    source_spacing_zyx: tuple[float, float, float]
    resampled_shape_zyx: tuple[int, int, int]

    @property
    def effective_spacing_zyx(self) -> tuple[float, float, float]:
        """Millimetres per resampled voxel (corner-aligned ``ndimage.zoom`` grid)."""
        out = []
        for n_in, n_out, spacing in zip(
            self.source_shape_zyx, self.resampled_shape_zyx, self.source_spacing_zyx, strict=True
        ):
            out.append(spacing * (n_in - 1) / (n_out - 1) if n_out > 1 else spacing)
        return out[0], out[1], out[2]

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable form (no pixel data)."""
        return asdict(self) | {"effective_spacing_zyx": self.effective_spacing_zyx}


def bundle_input(
    hu: npt.NDArray[np.integer[Any]] | FloatArray, spacing_zyx: tuple[float, float, float]
) -> tuple[FloatArray, BundleGeometry]:
    """Return the RAS ``(x, y, z)`` network input in [0, 1] and its geometry."""
    if hu.ndim != 3 or min(hu.shape) < 1:
        raise ValueError("expected a non-empty (z, y, x) volume")
    if len(spacing_zyx) != 3 or any(not math.isfinite(s) or s <= 0 for s in spacing_zyx):
        raise ValueError("spacing must contain three positive finite numbers")
    zoom = [s / t for s, t in zip(spacing_zyx, TARGET_SPACING_ZYX, strict=True)]
    shape_out = [max(1, round(n * z)) for n, z in zip(hu.shape, zoom, strict=True)]
    zoom = [n_out / n_in for n_out, n_in in zip(shape_out, hu.shape, strict=True)]
    resampled = ndimage.zoom(hu.astype(np.float32), zoom, order=1, grid_mode=False)
    lo, hi = HU_RANGE
    scaled = (np.clip(resampled, lo, hi) - lo) / (hi - lo)
    ras = np.ascontiguousarray(scaled.transpose(2, 1, 0)[::-1, ::-1, ::-1], dtype=np.float32)
    shape = resampled.shape
    geometry = BundleGeometry(
        source_shape_zyx=(int(hu.shape[0]), int(hu.shape[1]), int(hu.shape[2])),
        source_spacing_zyx=(float(spacing_zyx[0]), float(spacing_zyx[1]), float(spacing_zyx[2])),
        resampled_shape_zyx=(int(shape[0]), int(shape[1]), int(shape[2])),
    )
    return ras, geometry


def box_to_mm(
    box_xyzxyz: npt.ArrayLike, geometry: BundleGeometry
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Map one RAS voxel box to ``(centre_zyx_mm, extent_zyx_mm)`` in the reference frame."""
    x1, y1, z1, x2, y2, z2 = (float(v) for v in np.asarray(box_xyzxyz, dtype=np.float64))
    nz, ny, nx = geometry.resampled_shape_zyx
    sz, sy, sx = geometry.effective_spacing_zyx
    centre = (
        ((nz - 1) - (z1 + z2) / 2) * sz,
        ((ny - 1) - (y1 + y2) / 2) * sy,
        ((nx - 1) - (x1 + x2) / 2) * sx,
    )
    extent = (abs(z2 - z1) * sz, abs(y2 - y1) * sy, abs(x2 - x1) * sx)
    return centre, extent


def candidates_from_boxes(
    boxes: npt.ArrayLike,
    scores: npt.ArrayLike,
    geometry: BundleGeometry,
    *,
    label: str = "pulmonary_nodule",
) -> list[LesionCandidate]:
    """Convert detector output to millimetre candidates, highest score first.

    The diameter is the longer in-plane box side, the closest analogue of the LIDC
    long-axis contour diameter. It is a box size, not a measured nodule diameter.
    """
    box_arr = np.asarray(boxes, dtype=np.float64).reshape(-1, 6)
    score_arr = np.asarray(scores, dtype=np.float64).reshape(-1)
    if len(box_arr) != len(score_arr):
        raise ValueError("boxes and scores differ in length")
    out: list[LesionCandidate] = []
    for box, score in zip(box_arr, score_arr, strict=True):
        if not np.all(np.isfinite(box)) or not np.isfinite(score):
            raise ValueError("detector returned non-finite boxes or scores")
        if not 0.0 <= score <= 1.0:
            raise ValueError("detector score is outside [0, 1]")
        lower, upper = box[:3], box[3:]
        shape_xyz = np.asarray(geometry.resampled_shape_zyx[::-1])
        if np.any(lower < 0) or np.any(upper > shape_xyz) or np.any(upper <= lower):
            raise ValueError("detector box is reversed, empty or outside the prepared volume")
        centre, extent = box_to_mm(box, geometry)
        source_extent = [
            (n - 1) * spacing
            for n, spacing in zip(
                geometry.source_shape_zyx, geometry.source_spacing_zyx, strict=True
            )
        ]
        if any(c < 0 or c > limit for c, limit in zip(centre, source_extent, strict=True)):
            raise ValueError("detector candidate centre is outside the source volume")
        out.append(
            LesionCandidate(
                label=label,
                center_zyx_mm=(round(centre[0], 2), round(centre[1], 2), round(centre[2], 2)),
                diameter_mm=round(max(extent[1], extent[2]), 2),
                score=round(float(score), 6),
            )
        )
    return sorted(out, key=lambda c: -c.score)


def mm_to_box(
    centre_zyx_mm: tuple[float, float, float],
    extent_zyx_mm: tuple[float, float, float],
    geometry: BundleGeometry,
) -> list[float]:
    """Inverse of :func:`box_to_mm` (used by tests and stub networks)."""
    nz, ny, nx = geometry.resampled_shape_zyx
    sz, sy, sx = geometry.effective_spacing_zyx
    cz = (nz - 1) - centre_zyx_mm[0] / sz
    cy = (ny - 1) - centre_zyx_mm[1] / sy
    cx = (nx - 1) - centre_zyx_mm[2] / sx
    hz, hy, hx = extent_zyx_mm[0] / sz / 2, extent_zyx_mm[1] / sy / 2, extent_zyx_mm[2] / sx / 2
    return [cx - hx, cy - hy, cz - hz, cx + hx, cy + hy, cz + hz]
