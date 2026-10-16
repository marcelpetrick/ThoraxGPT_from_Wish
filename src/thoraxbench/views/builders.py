# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""View builders turning a :class:`~thoraxbench.study.Study` into model input.

Image views follow radiologist practice (docs/reading_practice.md): named windows, optional
MIP slabs, an optional coronal overview, and a caption per image naming plane, window, slab,
slice position and anatomical level. Captions are authoritative for the model.

* ``medgemma_ct_v1`` — RGB encoding of the official MedGemma CT notebook
  (R = -1024..1024, G = -135..215, B = 0..80 HU), one image per sampled slice.
* ``generic_multislice_v1`` — lung-window greyscale images (control for general VLMs).
* ``multiwindow_separate_v1`` — lung + mediastinal window image per slice (S3 variant).
* ``contact_sheet_v1`` — one montage of lung-window slices (S6).
* ``ct_clip_v1`` / ``m3d_lamed_v1`` — normalised 3D tensors saved as ``.npy`` for the
  optional PyTorch services (CT-CLIP: HU clip [-1000, 1000]/1000, spacing 1.5x0.75x0.75 mm,
  crop/pad 240x480x480 with -1; M3D-LaMed: min-max to [0, 1], 32x256x256).
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from PIL import Image
from scipy import ndimage

from thoraxbench.preprocess import (
    MEDGEMMA_RGB_WINDOWS,
    WINDOWS,
    coronal_reformat,
    mip_slab,
    rgb_encode,
)
from thoraxbench.preprocess.windows import apply_range
from thoraxbench.sampling import Selection, get_strategy
from thoraxbench.schemas import AnalysisRequest, PreparedInput
from thoraxbench.study import Study


def _png(arr: npt.NDArray[np.uint8], size: int) -> bytes:
    img = Image.fromarray(arr)
    if size and max(img.size) != size:
        img = img.resize((size, size), Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def render_slice_png(hu2d: npt.NDArray[np.int16], window: str, size: int = 512) -> bytes:
    """Render one HU image with a named window (``medgemma`` = RGB encoding) as PNG."""
    if window == "medgemma":
        return _png(rgb_encode(hu2d, MEDGEMMA_RGB_WINDOWS), size)
    win = WINDOWS[window]
    return _png(apply_range(hu2d, win.low, win.high), size)


def _montage(tiles: list[npt.NDArray[np.uint8]], tile: int) -> npt.NDArray[np.uint8]:
    cols = math.ceil(math.sqrt(len(tiles)))
    rows = math.ceil(len(tiles) / cols)
    sheet = np.zeros((rows * tile, cols * tile), dtype=np.uint8)
    for k, t in enumerate(tiles):
        img = np.asarray(Image.fromarray(t).resize((tile, tile), Image.Resampling.BILINEAR))
        r, c = divmod(k, cols)
        sheet[r * tile : (r + 1) * tile, c * tile : (c + 1) * tile] = img
    return sheet


@dataclass(frozen=True)
class MultiSliceView:
    """Rendered 2D images of sampled slices."""

    view_id: str
    mode: str  # medgemma | lung | multiwindow | montage
    strategy: str = "anatomy"
    n: int = 16
    size: int = 512
    slab_mm: float = 0.0
    coronal: bool = True
    include_cues: bool = True
    strategy_params: dict[str, Any] = field(default_factory=dict)
    version: str = "2"

    def __post_init__(self) -> None:
        if type(self.include_cues) is not bool:
            raise ValueError("include_cues must be a boolean")

    @property
    def sha256(self) -> str:
        """Hash of every parameter that changes the rendered input."""
        blob = json.dumps(
            {
                k: getattr(self, k)
                for k in (
                    "view_id",
                    "mode",
                    "strategy",
                    "n",
                    "size",
                    "slab_mm",
                    "coronal",
                    "include_cues",
                    "strategy_params",
                    "version",
                )
            },
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()

    def _image(self, hu2d: npt.NDArray[np.int16], window: str) -> npt.NDArray[np.uint8]:
        if window == "medgemma":
            return rgb_encode(hu2d, MEDGEMMA_RGB_WINDOWS)
        win = WINDOWS[window]
        return apply_range(hu2d, win.low, win.high)

    def _windows(self) -> list[str]:
        return {
            "medgemma": ["medgemma"],
            "lung": ["lung"],
            "montage": ["lung"],
            "multiwindow": ["lung", "mediastinum"],
        }[self.mode]

    def build(self, study: Study, request: AnalysisRequest) -> PreparedInput:
        """Sample slices, render them and caption every image."""
        vol = study.volume
        strategy = get_strategy(self.strategy, n=self.n, **self.strategy_params)
        sel: Selection = strategy.select(vol, study.cues)
        slab = self.slab_mm or sel.slab_mm
        images: list[bytes] = []
        captions: list[str] = []
        nz = vol.shape[0]
        window_names = {
            "medgemma": "MedGemma RGB (wide/soft-tissue/narrow)",
            "lung": "lung window W1500/L-600",
            "mediastinum": "mediastinal window W350/L50",
        }
        if self.coronal:
            cor = coronal_reformat(vol.hu, vol.spacing_mm, slab_mm=20.0)
            images.append(
                _png(self._image(cor, "lung" if self.mode != "medgemma" else "medgemma"), self.size)
            )
            captions.append(
                "coronal overview, 20 mm slab, top = cranial (apex), image left = patient right"
            )
        tiles: list[npt.NDArray[np.uint8]] = []
        for idx, tag in zip(sel.indices, sel.tags, strict=True):
            hu2d = mip_slab(vol.hu, idx, slab, vol.spacing_mm[0]) if slab > 0 else vol.hu[idx]
            z = vol.z_positions_mm[idx] if idx < len(vol.z_positions_mm) else float(idx)
            slab_txt = f"{slab:.0f} mm MIP" if slab > 0 else f"{vol.spacing_mm[0]:.1f} mm slice"
            for window in self._windows():
                arr = self._image(hu2d, window)
                if self.mode == "montage":
                    tiles.append(arr)
                    continue
                images.append(_png(arr, self.size))
                captions.append(
                    f"axial, {window_names[window]}, {slab_txt}, slice {idx + 1}/{nz}, "
                    f"z={z:.0f} mm, level: {tag}"
                )
        if self.mode == "montage" and tiles:
            images.append(_png(_montage(tiles, max(64, self.size // 4)), 0))
            captions.append(
                "contact sheet of axial lung-window slices, row-major, cranial first: "
                + ", ".join(f"{i + 1}" for i in sel.indices)
            )
        context = study.cues.summary() if self.include_cues else ""
        if not study.qc.adequate:
            context += " Study-quality limitations: " + "; ".join(study.qc.limitations) + "."
        return PreparedInput(
            view_id=self.view_id,
            view_version=self.version,
            images=images,
            image_captions=[f"Image {k + 1}: {c}" for k, c in enumerate(captions)],
            slice_indices=list(sel.indices),
            context=context,
            meta={
                "strategy": strategy.id,
                "strategy_sha256": strategy.sha256,
                "view_sha256": self.sha256,
                "slab_mm": slab,
                "n_images": len(images),
                "include_cues": self.include_cues,
                "tags": sel.tags,
            },
        )


def _resample(
    hu: npt.NDArray[np.float32],
    spacing: tuple[float, float, float],
    target: tuple[float, float, float],
) -> npt.NDArray[np.float32]:
    zoom = tuple(s / t for s, t in zip(spacing, target, strict=True))
    out: npt.NDArray[np.float32] = ndimage.zoom(hu, zoom, order=1)
    return out


def _crop_pad(
    arr: npt.NDArray[np.float32], shape: tuple[int, int, int], fill: float
) -> npt.NDArray[np.float32]:
    out = np.full(shape, fill, dtype=np.float32)
    src, dst = [], []
    for have, want in zip(arr.shape, shape, strict=True):
        if have >= want:
            start = (have - want) // 2
            src.append(slice(start, start + want))
            dst.append(slice(0, want))
        else:
            start = (want - have) // 2
            src.append(slice(0, have))
            dst.append(slice(start, start + have))
    out[tuple(dst)] = arr[tuple(src)]
    return out


@dataclass(frozen=True)
class TensorView:
    """3D tensor for a PyTorch service, written to ``cache_dir`` as ``.npy``."""

    view_id: str
    cache_dir: Path = Path("data/cache/tensors")
    version: str = "1"

    def tensor(self, study: Study) -> npt.NDArray[np.float32]:
        """Normalised tensor ``(1, D, H, W)`` as the official preprocessing expects."""
        hu = study.volume.hu.astype(np.float32)
        if self.view_id == "ct_clip_v1":
            arr = _resample(
                np.clip(hu, -1000, 1000) / 1000.0, study.volume.spacing_mm, (1.5, 0.75, 0.75)
            )
            arr = _crop_pad(arr, (240, 480, 480), -1.0)
        else:  # m3d_lamed_v1
            lo, hi = float(hu.min()), float(hu.max())
            norm = (hu - lo) / max(hi - lo, 1.0)
            zoom = (32 / hu.shape[0], 256 / hu.shape[1], 256 / hu.shape[2])
            arr = ndimage.zoom(norm, zoom, order=1).astype(np.float32)
            arr = _crop_pad(arr, (32, 256, 256), 0.0)
        return arr[np.newaxis]

    def build(self, study: Study, request: AnalysisRequest) -> PreparedInput:
        """Write the tensor and reference it by path."""
        arr = self.tensor(study)
        path = self.cache_dir / f"{study.volume.series_uid}.{self.view_id}.npy"
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, arr)
        return PreparedInput(
            view_id=self.view_id,
            view_version=self.version,
            tensor_path=str(path),
            context=study.cues.summary(),
            meta={"shape": list(arr.shape)},
        )


VIEWS: dict[str, dict[str, Any]] = {
    "medgemma_ct_v1": {"mode": "medgemma", "strategy": "anatomy", "n": 24},
    "generic_multislice_v1": {"mode": "lung", "strategy": "anatomy", "n": 16},
    "multiwindow_separate_v1": {"mode": "multiwindow", "strategy": "anatomy", "n": 12},
    "contact_sheet_v1": {"mode": "montage", "strategy": "contact_sheet", "n": 25, "coronal": False},
    "ct_clip_v1": {},
    "m3d_lamed_v1": {},
}


def get_view(view_id: str, **params: Any) -> MultiSliceView | TensorView:
    """Build a view by id; *params* override the defaults (KeyError if unknown)."""
    defaults = VIEWS[view_id]
    if view_id in {"ct_clip_v1", "m3d_lamed_v1"}:
        return TensorView(view_id=view_id, **params)
    return MultiSliceView(view_id=view_id, **{**defaults, **params})
