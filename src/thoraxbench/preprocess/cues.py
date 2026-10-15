# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Deterministic HU measurements ("evidence cues") computed from the canonical volume.

The cues imitate quantitative reads a radiologist does (docs/reading_practice.md §3.7).
They are evidence, not findings: thresholds are heuristics and every value is reported
with the cue version, so results stay comparable and auditable. Items marked *heuristic*
have no validated cut-off.

All indices refer to the canonical volume (cranial-first, full resolution); cues may be
computed on an in-plane down-sampled copy for speed (``downsample`` field).
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, Field
from scipy import ndimage

from thoraxbench.dicom.volume import Volume
from thoraxbench.preprocess.masks import (
    BoolArray,
    body_mask,
    lung_envelope,
    lung_mask,
    lung_z_extent,
)

HU_CUES_VERSION = "hu_cues_v1"

LAA_THRESHOLD_HU = -950
GGO_RANGE_HU = (-700, -300)
CONSOLIDATION_HU = -100
SIMPLE_FLUID_HU = (0.0, 20.0)
DENSE_FLUID_HU = (20.0, 70.0)
NODULE_HU = -300
NODULE_DIAMETER_MM = (3.0, 30.0)
MAX_NODULE_ELONGATION = 3.0
MAX_NODULE_CANDIDATES = 20
CALCIUM_HU = 130
METAL_HU = 2000
PLEURAL_AIR_HU = -950
THICK_SLICE_MM = 3.0
SHELL_MM = 100.0
DENSE_NEAR_FLUID_MM = 10.0
MIN_COLLECTION_ML = 2.0
DOWNSAMPLE_ABOVE_PX = 384


class NoduleCandidate(BaseModel):
    """Compact high-attenuation cluster inside the lung outline (nodule candidate)."""

    z_index: int
    centroid_zyx: tuple[float, float, float]
    diameter_mm: float
    side: Literal["left", "right"]
    mean_hu: float


class Landmarks(BaseModel):
    """Anatomical z-landmarks (slice indices, cranial-first) and how they were found."""

    apex: int
    carina: int
    max_lung: int
    heart: int
    dome: int
    base: int
    carina_method: Literal["airway", "fraction"]
    heart_method: Literal["soft_tissue", "fraction"]
    dome_method: Literal["area_drop", "base"]


class HUCues(BaseModel):
    """Deterministic quantitative cues of one volume."""

    version: str = HU_CUES_VERSION
    downsample: int = 1
    lung_volume_ml: float = 0.0
    lung_z_extent: tuple[int, int] | None = None
    landmarks: Landmarks | None = None
    coverage_flags: list[str] = Field(default_factory=list)
    emphysema_laa950_pct: float = 0.0
    ggo_burden_pct: float = 0.0
    consolidation_pct: float = 0.0
    pleural_fluid_ml: dict[str, float] = Field(default_factory=lambda: {"left": 0.0, "right": 0.0})
    pleural_dense_fluid_ml: dict[str, float] = Field(
        default_factory=lambda: {"left": 0.0, "right": 0.0}
    )
    pleural_fluid_depth_mm: dict[str, float] = Field(
        default_factory=lambda: {"left": 0.0, "right": 0.0}
    )
    pleural_air_ml: float = 0.0
    cardiac_calcium_ml: float = 0.0
    agatston_like: float = 0.0
    metal_components: int = 0
    nodule_candidates: list[NoduleCandidate] = Field(default_factory=list)

    def summary(self) -> str:
        """One-paragraph English summary used as model context and report evidence."""
        if self.lung_z_extent is None:
            return "Deterministic measurements: no aerated lung found."
        parts = [
            f"lung volume {self.lung_volume_ml:.0f} ml",
            f"%LAA-950 {self.emphysema_laa950_pct:.1f}%",
            f"GGO-range voxels {self.ggo_burden_pct:.1f}%",
            f"consolidation-range voxels {self.consolidation_pct:.1f}%",
            "dependent fluid 0-20 HU right {:.0f} ml / left {:.0f} ml".format(
                self.pleural_fluid_ml["right"], self.pleural_fluid_ml["left"]
            ),
            f"pleural air candidates {self.pleural_air_ml:.0f} ml",
            f"cardiac-region calcium {self.cardiac_calcium_ml:.2f} ml "
            f"(Agatston-like {self.agatston_like:.0f})",
            f"metal components {self.metal_components}",
            f"{len(self.nodule_candidates)} nodule candidate(s)",
        ]
        if self.nodule_candidates:
            top = ", ".join(
                f"{c.diameter_mm:.0f} mm {c.side} (slice {c.z_index})"
                for c in self.nodule_candidates[:5]
            )
            parts.append(f"largest candidates: {top}")
        if self.coverage_flags:
            parts.append("flags: " + ", ".join(self.coverage_flags))
        return f"Deterministic measurements ({self.version}, heuristic): " + "; ".join(parts) + "."


def _pct(part: int, whole: int) -> float:
    return 100.0 * part / whole if whole else 0.0


def _central_band(shape: tuple[int, int], mid_x: float, half_width: float) -> BoolArray:
    xs = np.arange(shape[1])
    band = np.abs(xs - mid_x) < half_width
    return np.broadcast_to(band, shape)


def _carina(
    work: npt.NDArray[np.int16],
    *,
    body: BoolArray,
    extent: tuple[int, int],
    max_lung: int,
    mid_x: float,
    body_width: float,
    pixel_mm2: float,
) -> int | None:
    """Last slice of the first run (≥3 slices) with exactly one central airway lumen."""
    run_start: int | None = None
    last: int | None = None
    stop = max(max_lung, (extent[0] + extent[1]) // 2)
    for z in range(extent[0], stop + 1):
        band = _central_band(work.shape[1:], mid_x, 0.08 * body_width)
        air = (work[z] < -400) & body[z] & band
        labels, n = ndimage.label(air)
        lumens = 0
        for comp in range(1, n + 1):
            pix = np.argwhere(labels == comp)
            area = len(pix) * pixel_mm2
            central = abs(float(pix[:, 1].mean()) - mid_x) < 0.04 * body_width
            lumens += int(20 <= area <= 700 and central)
        if lumens == 1:
            run_start = z if run_start is None else run_start
            last = z
        elif run_start is not None:
            break
    if run_start is None or last is None or last - run_start + 1 < 3:
        return None
    return last


def _landmarks(
    work: npt.NDArray[np.int16],
    *,
    body: BoolArray,
    lungs: BoolArray,
    extent: tuple[int, int],
    mid_x: float,
    body_width: float,
    pixel_mm2: float,
) -> Landmarks:
    apex, base = extent
    areas = lungs.reshape(lungs.shape[0], -1).sum(axis=1)
    max_lung = int(np.argmax(areas))
    span = base - apex
    carina = _carina(
        work,
        body=body,
        extent=extent,
        max_lung=max_lung,
        mid_x=mid_x,
        body_width=body_width,
        pixel_mm2=pixel_mm2,
    )
    carina_method: Literal["airway", "fraction"] = "airway"
    if carina is None:
        carina, carina_method = apex + round(0.3 * span), "fraction"
    band = _central_band(work.shape[1:], mid_x, 0.2 * body_width)
    soft = (work >= 0) & (work <= 100) & body & band
    soft_area = soft.reshape(soft.shape[0], -1).sum(axis=1)
    lo = max(max_lung, apex)
    heart_method: Literal["soft_tissue", "fraction"] = "soft_tissue"
    if soft_area[lo : base + 1].max(initial=0) > 0:
        heart = lo + int(np.argmax(soft_area[lo : base + 1]))
    else:
        heart, heart_method = apex + round(0.6 * span), "fraction"
    dome_method: Literal["area_drop", "base"] = "area_drop"
    below = [z for z in range(max_lung + 1, base + 1) if areas[z] < 0.6 * areas[max_lung]]
    if below:
        dome = below[0]
    else:
        dome, dome_method = base, "base"
    return Landmarks(
        apex=apex,
        carina=carina,
        max_lung=max_lung,
        heart=heart,
        dome=dome,
        base=base,
        carina_method=carina_method,
        heart_method=heart_method,
        dome_method=dome_method,
    )


def _side_masks(shape: tuple[int, ...], mid_x: float) -> tuple[BoolArray, BoolArray]:
    xs = np.arange(shape[-1])
    right = np.broadcast_to(xs < mid_x, shape)  # patient right = image left (LPS)
    return right, ~right


def _nodule_candidates(
    work: npt.NDArray[np.int16],
    env: BoolArray,
    spacing: tuple[float, float, float],
    stride: int,
    mid_x: float,
) -> list[NoduleCandidate]:
    dz, dy, dx = spacing
    voxel_mm3 = dz * dy * dx
    labels, n = ndimage.label((work > NODULE_HU) & env)
    out: list[NoduleCandidate] = []
    for idx, sl in enumerate(ndimage.find_objects(labels), start=1):
        if sl is None:  # pragma: no cover - find_objects only returns None for gaps
            continue
        comp = labels[sl] == idx
        volume_mm3 = float(comp.sum()) * voxel_mm3
        diameter = (6.0 * volume_mm3 / np.pi) ** (1.0 / 3.0)
        if not NODULE_DIAMETER_MM[0] <= diameter <= NODULE_DIAMETER_MM[1]:
            continue
        extents = [(s.stop - s.start) * sp for s, sp in zip(sl, spacing, strict=True)]
        if max(extents) / max(min(extents), 1e-6) > MAX_NODULE_ELONGATION:
            continue
        cz, cy, cx = (
            float(c + s.start) for c, s in zip(ndimage.center_of_mass(comp), sl, strict=True)
        )
        out.append(
            NoduleCandidate(
                z_index=round(cz),
                centroid_zyx=(cz, cy * stride, cx * stride),
                diameter_mm=round(diameter, 1),
                side="right" if cx < mid_x else "left",
                mean_hu=round(float(work[sl][comp].mean()), 1),
            )
        )
    del n
    out.sort(key=lambda c: (-c.diameter_mm, c.z_index, c.centroid_zyx))
    return out[:MAX_NODULE_CANDIDATES]


def _agatston_weight(max_hu: float) -> int:
    if max_hu >= 400:
        return 4
    if max_hu >= 300:
        return 3
    if max_hu >= 200:
        return 2
    return 1


def _cardiac_calcium(
    work: npt.NDArray[np.int16],
    *,
    body: BoolArray,
    lm: Landmarks,
    mid_x: float,
    body_width: float,
    spacing: tuple[float, float, float],
) -> tuple[float, float]:
    """Calcium ≥130 HU in an approximate cardiac box; returns (ml, Agatston-like score)."""
    dz, dy, dx = spacing
    ys = np.flatnonzero(body.any(axis=(0, 2)))
    y_front, y_back = float(ys[0]), float(ys[-1])
    y_lo = y_front + 0.15 * (y_back - y_front)
    y_hi = (y_front + y_back) / 2
    box = np.zeros(work.shape, dtype=bool)
    x_lo = max(0, int(mid_x - 0.15 * body_width))
    x_hi = int(mid_x + 0.15 * body_width) + 1
    box[lm.carina : lm.dome + 1, int(y_lo) : int(y_hi) + 1, x_lo:x_hi] = True
    calc = (work >= CALCIUM_HU) & body & box
    score = 0.0
    for z in np.flatnonzero(calc.any(axis=(1, 2))):
        labels, n = ndimage.label(calc[z])
        for comp in range(1, n + 1):
            pix = labels == comp
            area = float(pix.sum()) * dy * dx
            if area >= 1.0:
                score += area * _agatston_weight(float(work[z][pix].max()))
    return float(calc.sum()) * dz * dy * dx / 1000.0, score * dz / 3.0


def _pleural(
    work: npt.NDArray[np.int16],
    *,
    body: BoolArray,
    lungs: BoolArray,
    env: BoolArray,
    extent: tuple[int, int],
    mid_x: float,
    body_width: float,
    spacing: tuple[float, float, float],
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """Dependent pleural fluid volumes (simple 0-20 HU, dense 20-70 HU) and AP depth."""
    dz, dy, dx = spacing
    voxel_ml = dz * dy * dx / 1000.0
    dist = ndimage.distance_transform_edt(~env, sampling=spacing)
    zmask = np.zeros(work.shape, dtype=bool)
    zmask[extent[0] : extent[1] + 1] = True
    lateral = ~_central_band(work.shape[1:], mid_x, 0.1 * body_width)
    shell = body & ~env & (dist <= SHELL_MM) & zmask & lateral
    smooth = ndimage.uniform_filter(work.astype(np.float32), size=3)
    right, left = _side_masks(work.shape, mid_x)
    fluid: dict[str, float] = {}
    dense: dict[str, float] = {}
    depth: dict[str, float] = {}
    for name, side in (("right", right), ("left", left)):
        side_lung = lungs & side
        cy = float(np.argwhere(side_lung)[:, 1].mean()) if side_lung.any() else work.shape[1] / 2
        dependent = np.zeros(work.shape, dtype=bool)
        dependent[:, int(np.ceil(cy)) :, :] = True
        region = shell & side & dependent
        simple = region & (smooth >= SIMPLE_FLUID_HU[0]) & (smooth <= SIMPLE_FLUID_HU[1])
        labels, n = ndimage.label(simple)
        if n:
            sizes = np.bincount(labels.ravel())[1:] * voxel_ml
            keep = [i + 1 for i, s in enumerate(sizes) if s >= MIN_COLLECTION_ML]
            simple = np.isin(labels, keep)
        fluid[name] = round(float(simple.sum()) * voxel_ml, 1)
        if simple.any():
            near = ndimage.distance_transform_edt(~simple, sampling=spacing) <= DENSE_NEAR_FLUID_MM
            dense_mask = (
                region & near & (smooth > DENSE_FLUID_HU[0]) & (smooth <= DENSE_FLUID_HU[1])
            )
            dense[name] = round(float(dense_mask.sum()) * voxel_ml, 1)
            rows = simple.any(axis=2)  # (z, y)
            depth[name] = round(float(rows.sum(axis=1).max()) * dy, 1)
        else:
            dense[name] = 0.0
            depth[name] = 0.0
    return fluid, dense, depth


def _pleural_air(
    work: npt.NDArray[np.int16],
    body: BoolArray,
    mid_x: float,
    body_width: float,
    spacing: tuple[float, float, float],
) -> float:
    """Large confluent very-low-attenuation air (< -950 HU) off the midline (heuristic).

    Captures pneumothorax and also large bullae; the central airway is excluded.
    """
    voxel_ml = spacing[0] * spacing[1] * spacing[2] / 1000.0
    air = ndimage.binary_opening(body & (work < PLEURAL_AIR_HU), structure=np.ones((3, 3, 3)))
    labels, n = ndimage.label(air)
    total = 0.0
    for idx in range(1, n + 1):
        comp = labels == idx
        volume = float(comp.sum()) * voxel_ml
        cx = float(np.argwhere(comp)[:, 2].mean())
        if volume >= MIN_COLLECTION_ML and abs(cx - mid_x) > 0.1 * body_width:
            total += volume
    return round(total, 1)


def hu_cues(volume: Volume) -> HUCues:
    """Compute all deterministic cues of *volume* (canonical HU is not modified)."""
    hu = volume.hu
    stride = 2 if hu.shape[2] > DOWNSAMPLE_ABOVE_PX else 1
    work = hu[:, ::stride, ::stride]
    dz, dy, dx = volume.spacing_mm
    spacing = (dz, dy * stride, dx * stride)
    voxel_ml = spacing[0] * spacing[1] * spacing[2] / 1000.0
    flags: list[str] = []
    if dz > THICK_SLICE_MM:
        flags.append("thick_slices")
    body = body_mask(work)
    lungs = lung_mask(work, body)
    extent = lung_z_extent(lungs)
    if extent is None or not body.any():
        return HUCues(downsample=stride, coverage_flags=[*flags, "no_lung_found"])
    if extent[0] == 0:
        flags.append("incomplete_coverage_apex")
    if extent[1] == work.shape[0] - 1:
        flags.append("incomplete_coverage_base")
    env = lung_envelope(lungs)
    xs = np.argwhere(body)[:, 2]
    mid_x = float(xs.mean())
    body_width = float(xs.max() - xs.min() + 1)
    lm = _landmarks(
        work,
        body=body,
        lungs=lungs,
        extent=extent,
        mid_x=mid_x,
        body_width=body_width,
        pixel_mm2=spacing[1] * spacing[2],
    )
    env_count = int(env.sum())
    consolidation = ndimage.binary_opening(
        env & (work > CONSOLIDATION_HU), structure=np.ones((1, 3, 3))
    )
    fluid, dense, depth = _pleural(
        work,
        body=body,
        lungs=lungs,
        env=env,
        extent=extent,
        mid_x=mid_x,
        body_width=body_width,
        spacing=spacing,
    )
    calcium_ml, agatston = _cardiac_calcium(
        work, body=body, lm=lm, mid_x=mid_x, body_width=body_width, spacing=spacing
    )
    _, metal_n = ndimage.label(work > METAL_HU)
    return HUCues(
        downsample=stride,
        lung_volume_ml=round(float(lungs.sum()) * voxel_ml, 1),
        lung_z_extent=extent,
        landmarks=lm,
        coverage_flags=flags,
        emphysema_laa950_pct=round(
            _pct(int((env & (work < LAA_THRESHOLD_HU)).sum()), env_count), 2
        ),
        ggo_burden_pct=round(
            _pct(
                int((env & (work >= GGO_RANGE_HU[0]) & (work <= GGO_RANGE_HU[1])).sum()),
                env_count,
            ),
            2,
        ),
        consolidation_pct=round(_pct(int(consolidation.sum()), env_count), 2),
        pleural_fluid_ml=fluid,
        pleural_dense_fluid_ml=dense,
        pleural_fluid_depth_mm=depth,
        pleural_air_ml=_pleural_air(work, body, mid_x, body_width, spacing),
        cardiac_calcium_ml=round(calcium_ml, 3),
        agatston_like=round(agatston, 1),
        metal_components=int(metal_n),
        nodule_candidates=_nodule_candidates(work, env, spacing, stride, mid_x / 1.0),
    )
