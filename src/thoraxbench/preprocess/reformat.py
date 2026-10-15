# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Thin-slab maximum-intensity projections and coronal reformats."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from scipy import ndimage


def slab_bounds(nz: int, center_idx: int, slab_mm: float, spacing_z_mm: float) -> tuple[int, int]:
    """Half-open slice range ``[lo, hi)`` of a slab centred on *center_idx*."""
    if not 0 <= center_idx < nz:
        msg = f"slice index {center_idx} outside 0..{nz - 1}"
        raise IndexError(msg)
    half = max(0, round(slab_mm / spacing_z_mm / 2))
    return max(0, center_idx - half), min(nz, center_idx + half + 1)


def mip_slab(
    hu: npt.NDArray[np.int16], center_idx: int, slab_mm: float, spacing_z_mm: float
) -> npt.NDArray[np.int16]:
    """Axial maximum-intensity projection over a slab centred on *center_idx*.

    Radiologists use 5-10 mm MIP slabs to tell nodules (spherical) from vessels (tubular).
    The slab is clamped to the volume.
    """
    lo, hi = slab_bounds(hu.shape[0], center_idx, slab_mm, spacing_z_mm)
    return hu[lo:hi].max(axis=0)


def coronal_reformat(
    hu: npt.NDArray[np.int16],
    spacing_mm: tuple[float, float, float],
    y_index: int | None = None,
    slab_mm: float = 0.0,
) -> npt.NDArray[np.int16]:
    """Coronal image (rows = z cranial to caudal, cols = x) resampled to square pixels.

    Args:
        hu: Volume ``(z, y, x)``.
        spacing_mm: Voxel spacing ``(z, y, x)``.
        y_index: Coronal plane; default is the middle of the volume.
        slab_mm: If > 0, a MIP over that anterior-posterior thickness.
    """
    _, ny, _ = hu.shape
    y = ny // 2 if y_index is None else int(np.clip(y_index, 0, ny - 1))
    half = max(0, round(slab_mm / spacing_mm[1] / 2))
    plane = hu[:, max(0, y - half) : min(ny, y + half + 1), :].max(axis=1)
    factor = spacing_mm[0] / spacing_mm[2]
    if abs(factor - 1.0) < 1e-6:
        return plane.astype(np.int16)
    zoomed: npt.NDArray[np.float32] = ndimage.zoom(plane.astype(np.float32), (factor, 1.0), order=1)
    return np.rint(zoomed).astype(np.int16)
