# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Task D: segmentation / localization overlap metrics."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
from scipy.ndimage import center_of_mass
from scipy.spatial.distance import directed_hausdorff

from thoraxbench.scoring.classification import safe_div

BoolArray = npt.NDArray[np.bool_]
Box = tuple[float, float, float, float, float, float]  # z0, y0, x0, z1, y1, x1


def dice(pred: BoolArray, ref: BoolArray) -> float | None:
    """Dice coefficient ``2|A∩B| / (|A|+|B|)``; ``None`` when both masks are empty."""
    inter = int(np.logical_and(pred, ref).sum())
    return safe_div(2 * inter, int(pred.sum()) + int(ref.sum()))


def iou(pred: BoolArray, ref: BoolArray) -> float | None:
    """Intersection over union; ``None`` when both masks are empty."""
    inter = int(np.logical_and(pred, ref).sum())
    union = int(np.logical_or(pred, ref).sum())
    return safe_div(inter, union)


def hausdorff(
    pred: BoolArray, ref: BoolArray, spacing: Sequence[float] = (1.0, 1.0, 1.0)
) -> float | None:
    """Symmetric Hausdorff distance in mm between mask voxels; ``None`` if a mask is empty."""
    a = np.argwhere(pred) * np.asarray(spacing, dtype=np.float64)
    b = np.argwhere(ref) * np.asarray(spacing, dtype=np.float64)
    if len(a) == 0 or len(b) == 0:
        return None
    return float(max(directed_hausdorff(a, b)[0], directed_hausdorff(b, a)[0]))


def center_distance(
    pred: BoolArray, ref: BoolArray, spacing: Sequence[float] = (1.0, 1.0, 1.0)
) -> float | None:
    """Distance in mm between mask centres of mass; ``None`` if a mask is empty."""
    if not pred.any() or not ref.any():
        return None
    ca = np.asarray(center_of_mass(pred)) * np.asarray(spacing)
    cb = np.asarray(center_of_mass(ref)) * np.asarray(spacing)
    return float(np.linalg.norm(ca - cb))


def box_iou(a: Box, b: Box) -> float:
    """3D IoU of two axis-aligned boxes ``(z0, y0, x0, z1, y1, x1)``."""
    inter = 1.0
    for i in range(3):
        lo, hi = max(a[i], b[i]), min(a[i + 3], b[i + 3])
        if hi <= lo:
            return 0.0
        inter *= hi - lo
    vol_a = math.prod(a[i + 3] - a[i] for i in range(3))
    vol_b = math.prod(b[i + 3] - b[i] for i in range(3))
    return inter / (vol_a + vol_b - inter)


def hit_rate(distances: Sequence[float | None], radius_mm: float) -> float | None:
    """Fraction of lesions whose predicted centre lies within *radius_mm* (None = miss)."""
    if not distances:
        return None
    return sum(1 for d in distances if d is not None and d <= radius_mm) / len(distances)
