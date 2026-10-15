# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Deterministic body and lung masks from HU thresholds (threshold + morphology).

Thresholds are design choices recorded in the cue version (docs/reading_practice.md §3.2):
body > -500 HU, aerated lung < -400 HU inside the body.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from scipy import ndimage

BODY_THRESHOLD_HU = -500
LUNG_THRESHOLD_HU = -400
MIN_LUNG_COMPONENT_FRACTION = 0.05

BoolArray = npt.NDArray[np.bool_]


def largest_components(mask: BoolArray, keep: int, min_fraction: float = 0.0) -> BoolArray:
    """Keep the *keep* largest connected components (≥ *min_fraction* of the largest)."""
    labels, n = ndimage.label(mask)
    if n == 0:
        return np.zeros_like(mask, dtype=bool)
    sizes = np.bincount(labels.ravel())[1:]
    order = np.argsort(-sizes, kind="stable")[:keep]
    biggest = sizes[order[0]]
    chosen = [int(i) + 1 for i in order if sizes[i] >= min_fraction * biggest]
    return np.isin(labels, chosen)


def fill_slices(mask: BoolArray) -> BoolArray:
    """Fill holes slice by slice (axial)."""
    if mask.size == 0:
        return mask.astype(bool)
    return np.stack([ndimage.binary_fill_holes(s) for s in mask]).astype(bool)


def body_mask(hu: npt.NDArray[np.int16]) -> BoolArray:
    """Body (patient) mask: tissue above -500 HU, holes filled per slice, largest component."""
    return largest_components(fill_slices(hu > BODY_THRESHOLD_HU), keep=1)


def lung_mask(hu: npt.NDArray[np.int16], body: BoolArray | None = None) -> BoolArray:
    """Aerated-lung mask: air below -400 HU *inside* the body, the two largest components.

    Components smaller than 5 % of the largest one (bowel gas, small airway pieces) are dropped.
    """
    body = body_mask(hu) if body is None else body
    candidate = (hu < LUNG_THRESHOLD_HU) & body
    return largest_components(candidate, keep=2, min_fraction=MIN_LUNG_COMPONENT_FRACTION)


def lung_envelope(lungs: BoolArray) -> BoolArray:
    """Lung mask with intrapulmonary holes (nodules, vessels, consolidation) filled per slice."""
    return fill_slices(lungs)


def lung_z_extent(mask: BoolArray) -> tuple[int, int] | None:
    """First and last slice index (cranial-first) that contains lung, or ``None``."""
    rows = np.flatnonzero(mask.reshape(mask.shape[0], -1).any(axis=1))
    if rows.size == 0:
        return None
    return int(rows[0]), int(rows[-1])
