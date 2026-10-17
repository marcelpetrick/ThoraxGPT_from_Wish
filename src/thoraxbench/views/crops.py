# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Candidate-centred CT crops for lesion-level VLM verification (``candidate_crops_v1``).

A 896 px image of the whole chest gives one vision token per ~20 mm; a 64 mm crop gives
~4 mm per token (docs/approach-review-2026-10-17.md §3). This view renders, for every
candidate centre in the reference-lesion millimetre frame (``z = slice * dz``, slice 0
cranial; ``y = row * dy``; ``x = col * dx``), a square lung-window crop:

* ``axial``: rows = anterior to posterior, columns = patient right to left (image left =
  patient right), at the candidate's z;
* ``coronal`` (optional): rows = cranial to caudal, columns = patient right to left, at
  the candidate's y.

Pixels are sampled from the HU volume with trilinear interpolation on a millimetre grid
(``crop_mm / size`` per pixel, pixel centres), so in-plane and through-plane spacing are
honoured. Outside the volume the crop is filled with air (-1024 HU). An optional MIP slab
takes the maximum over planes spaced at the source spacing within ``±slab_mm / 2``.

Everything stays in memory: PNG bytes in a :class:`PreparedInput`, nothing is written.
Captions never contain detector scores, so a verifier is not told the expected answer.
Every parameter that changes the pixels enters :attr:`CandidateCropView.sha256`.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
from PIL import Image
from scipy import ndimage

from thoraxbench.dicom import Volume
from thoraxbench.preprocess import WINDOWS
from thoraxbench.preprocess.windows import apply_range
from thoraxbench.schemas import LesionCandidate, PreparedInput

CROP_VIEW_ID = "candidate_crops_v1"
PLANES = ("axial", "coronal")
AIR_HU = -1024.0

Centre = tuple[float, float, float]


@dataclass(frozen=True)
class CandidateCropView:
    """Square lung-window crops around candidate centres (millimetre geometry)."""

    view_id: str = CROP_VIEW_ID
    crop_mm: float = 64.0
    size: int = 896
    window: str = "lung"
    planes: tuple[str, ...] = ("axial",)
    slab_mm: float = 0.0
    version: str = "1"

    def __post_init__(self) -> None:
        if not math.isfinite(self.crop_mm) or self.crop_mm <= 0:
            raise ValueError("crop_mm must be a positive finite number")
        if self.size < 16:
            raise ValueError("size must be at least 16 pixels")
        if self.window not in WINDOWS:
            raise ValueError(f"unknown window {self.window!r}")
        if not self.planes or any(p not in PLANES for p in self.planes):
            raise ValueError(f"planes must be a non-empty subset of {PLANES}")
        if len(set(self.planes)) != len(self.planes):
            raise ValueError("planes must be unique")
        if not math.isfinite(self.slab_mm) or self.slab_mm < 0:
            raise ValueError("slab_mm must be a finite non-negative number")

    @property
    def sha256(self) -> str:
        """Hash of every parameter that changes the rendered crops."""
        params = {
            "view_id": self.view_id,
            "crop_mm": self.crop_mm,
            "size": self.size,
            "window": self.window,
            "planes": list(self.planes),
            "slab_mm": self.slab_mm,
            "version": self.version,
            "interpolation": "scipy.ndimage.map_coordinates order=1 cval=-1024",
        }
        return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()

    def _offsets(self) -> npt.NDArray[np.float64]:
        """Pixel-centre offsets from the crop centre in millimetres."""
        step = self.crop_mm / self.size
        return (np.arange(self.size, dtype=np.float64) + 0.5) * step - self.crop_mm / 2

    def _normal_offsets(self, spacing: float) -> npt.NDArray[np.float64]:
        if self.slab_mm <= 0:
            return np.zeros(1)
        half = math.floor(self.slab_mm / 2 / spacing)
        return np.arange(-half, half + 1, dtype=np.float64) * spacing

    def crop_hu(self, volume: Volume, centre_zyx_mm: Centre, plane: str) -> npt.NDArray[np.float32]:
        """Interpolated HU crop ``(size, size)`` around *centre_zyx_mm* in *plane*."""
        if plane not in PLANES:
            raise ValueError(f"unknown plane {plane!r}")
        dz, dy, dx = (float(s) for s in volume.spacing_mm)
        cz, cy, cx = (float(c) for c in centre_zyx_mm)
        offsets = self._offsets()
        rows, cols = np.meshgrid(offsets, offsets, indexing="ij")
        x_idx = (cx + cols) / dx
        hu = volume.hu.astype(np.float32, copy=False)
        best: npt.NDArray[np.float32] | None = None
        normal_spacing = dz if plane == "axial" else dy
        for shift in self._normal_offsets(normal_spacing):
            if plane == "axial":
                z_idx = np.full_like(rows, (cz + shift) / dz)
                y_idx = (cy + rows) / dy
            else:
                z_idx = (cz + rows) / dz
                y_idx = np.full_like(rows, (cy + shift) / dy)
            sample = ndimage.map_coordinates(
                hu, [z_idx, y_idx, x_idx], order=1, mode="constant", cval=AIR_HU
            ).astype(np.float32)
            best = sample if best is None else np.maximum(best, sample)
        assert best is not None  # noqa: S101 - at least one normal offset exists
        return best

    def _png(self, crop: npt.NDArray[np.float32]) -> bytes:
        win = WINDOWS[self.window]
        buf = io.BytesIO()
        Image.fromarray(apply_range(crop, win.low, win.high)).save(
            buf, format="PNG", optimize=False
        )
        return buf.getvalue()

    def build(self, study: Any, candidates: Sequence[LesionCandidate | Centre]) -> PreparedInput:
        """Render every candidate in every configured plane (images in memory)."""
        volume: Volume = study.volume
        shape_mm = [
            (n - 1) * float(s) for n, s in zip(volume.shape, volume.spacing_mm, strict=True)
        ]
        images: list[bytes] = []
        captions: list[str] = []
        crops: list[dict[str, Any]] = []
        win = WINDOWS[self.window]
        slab = f"{self.slab_mm:g} mm MIP slab" if self.slab_mm > 0 else "single plane"
        for number, item in enumerate(candidates, start=1):
            centre = item.center_zyx_mm if isinstance(item, LesionCandidate) else item
            centre = (float(centre[0]), float(centre[1]), float(centre[2]))
            inside = all(0.0 <= c <= extent for c, extent in zip(centre, shape_mm, strict=True))
            for plane in self.planes:
                images.append(self._png(self.crop_hu(volume, centre, plane)))
                orientation = (
                    "top = anterior, image left = patient right"
                    if plane == "axial"
                    else "top = cranial, image left = patient right"
                )
                captions.append(
                    f"IMAGE {len(images)}: candidate {number}, {plane}, {self.window} window "
                    f"W{win.width:g}/L{win.center:g}, {self.crop_mm:g} mm field of view "
                    f"centred on the candidate, {slab}, {orientation}"
                )
                crops.append(
                    {
                        "image": len(images),
                        "candidate": number,
                        "plane": plane,
                        "center_zyx_mm": list(centre),
                        "inside_volume": inside,
                    }
                )
        return PreparedInput(
            view_id=self.view_id,
            view_version=self.version,
            images=images,
            image_captions=captions,
            meta={
                "view_sha256": self.sha256,
                "crop_mm": self.crop_mm,
                "size": self.size,
                "mm_per_pixel": self.crop_mm / self.size,
                "planes": list(self.planes),
                "slab_mm": self.slab_mm,
                "n_images": len(images),
                "crops": crops,
                "include_cues": False,
            },
        )
