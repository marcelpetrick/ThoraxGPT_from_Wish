# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Image inputs for the ``thoraxbench sanity`` diagnostics (synthetic and calibration-only).

Every builder returns :class:`SanityItem` objects: PNG images, one caption per image, the
known answer and a grouping key. Real-study items come only from calibration-phase index
entries (:func:`thoraxbench.benchmark.coverage.phase_entries`) and studies opened through the
guarded :func:`thoraxbench.index.open_study`. Rendered pixels stay in memory; only their
SHA-256 digests are persisted.

Lesion geometry reuses :func:`thoraxbench.benchmark.coverage.lesion_slices` (centre
``z = slice index x dz``, spherical extent) and the LIDC consensus lesions of
:mod:`thoraxbench.labels.lidc` stored in the index.
"""

from __future__ import annotations

import hashlib
import io
import math
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from PIL import Image

from thoraxbench.benchmark.coverage import lesion_slices
from thoraxbench.config import Settings
from thoraxbench.index import IndexEntry
from thoraxbench.preprocess import mip_slab
from thoraxbench.preprocess.reformat import slab_bounds
from thoraxbench.schemas import AnalysisRequest, LesionAnnotation
from thoraxbench.study import Study, load_study_dir
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series
from thoraxbench.views.builders import MultiSliceView, render_slice_png

#: Human-readable window names used in captions.
WINDOW_NAMES = {
    "lung": "lung window W1500/L-600",
    "medgemma": "MedGemma RGB (wide/soft-tissue/narrow)",
}
OpenStudy = Callable[[IndexEntry, Settings], Study]


@dataclass(frozen=True)
class SanityItem:
    """One model input: images with captions, a known answer and grouping keys."""

    key: str
    group: str
    condition: str
    images: list[bytes]
    captions: list[str]
    truth: int | None
    patient: str
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def image_sha256(self) -> list[str]:
        """Digests of the PNG bytes (the only persisted trace of the pixels)."""
        return [hashlib.sha256(image).hexdigest() for image in self.images]

    def describe(self) -> dict[str, Any]:
        """JSON-serialisable identity without pixels."""
        return {
            "key": self.key,
            "group": self.group,
            "condition": self.condition,
            "truth": self.truth,
            "patient": self.patient,
            "n_images": len(self.images),
            "image_sha256": self.image_sha256,
            "captions": list(self.captions),
            "meta": dict(self.meta),
        }


def png_bytes(arr: npt.NDArray[np.uint8]) -> bytes:
    """Encode an 8-bit grey or RGB array as PNG."""
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def _like(png: bytes) -> tuple[int, int, str]:
    with Image.open(io.BytesIO(png)) as img:
        return img.size[0], img.size[1], img.mode


def gray_like(png: bytes, value: int = 128) -> bytes:
    """Return a uniform grey image with the size and colour mode of *png*."""
    width, height, mode = _like(png)
    shape: tuple[int, ...] = (height, width, 3) if mode == "RGB" else (height, width)
    return png_bytes(np.full(shape, value, dtype=np.uint8))


def noise_like(png: bytes, rng: np.random.Generator) -> bytes:
    """Uniform 8-bit noise with the size and colour mode of *png*."""
    width, height, mode = _like(png)
    shape: tuple[int, ...] = (height, width, 3) if mode == "RGB" else (height, width)
    return png_bytes(rng.integers(0, 256, size=shape, dtype=np.uint8))


def derangement(n: int, rng: np.random.Generator) -> list[int]:
    """Return a seeded permutation of ``range(n)`` that moves at least one element (n >= 2)."""
    if n < 2:
        return list(range(n))
    order = [int(i) for i in rng.permutation(n)]
    if order == list(range(n)):
        order = order[1:] + order[:1]
    return order


def disk_image(size: int, *, radius_frac: float = 0.25, value: int = 255) -> bytes:
    """Black square with one large bright centred disk (position-binding probe)."""
    yy, xx = np.mgrid[0:size, 0:size]
    centre = (size - 1) / 2
    arr = np.zeros((size, size), dtype=np.uint8)
    arr[(yy - centre) ** 2 + (xx - centre) ** 2 <= (radius_frac * size) ** 2] = value
    return png_bytes(arr)


def render_axial(
    volume_hu: npt.NDArray[np.int16], idx: int, slab_mm: float, dz: float, *, window: str, size: int
) -> bytes:
    """Axial slice or MIP slab centred on *idx*, rendered with a named window."""
    hu2d = mip_slab(volume_hu, idx, slab_mm, dz) if slab_mm > 0 else volume_hu[idx]
    return render_slice_png(hu2d, window, size)


def rendered_thickness_mm(nz: int, idx: int, slab_mm: float, dz: float) -> float:
    """Actual rendered slab thickness after rounding to whole slices."""
    if slab_mm <= 0:
        return dz
    lo, hi = slab_bounds(nz, idx, slab_mm, dz)
    return (hi - lo) * dz


def axial_caption(window: str, thickness_mm: float) -> str:
    """Caption without any source-slice number."""
    return f"axial chest CT, {WINDOW_NAMES[window]}, {thickness_mm:.0f} mm slab"


def multi_view(window: str, n: int, size: int, slab_mm: float) -> MultiSliceView:
    """Return the E001-schema image path (lung_extent, image-only captions, no cues, no coronal)."""
    return MultiSliceView(
        view_id="sanity_multislice",
        mode="medgemma" if window == "medgemma" else "lung",
        strategy="lung_extent",
        n=n,
        size=size,
        slab_mm=slab_mm,
        coronal=False,
        include_cues=False,
        caption_style="image_only",
    )


def strip_caption_prefix(caption: str) -> str:
    """Drop the view's ``IMAGE k:`` prefix; the request layout adds its own numbering."""
    head, sep, tail = caption.partition(": ")
    return tail if sep and head.split(" ")[0] in {"IMAGE", "Image"} else caption


# -- synthetic phantoms ----------------------------------------------------------------


@dataclass(frozen=True)
class Phantom:
    """A synthetic study and the slice index of its nodule centre (no patient data)."""

    study: Study
    spec: PhantomSpec

    @property
    def nodule_index(self) -> int:
        """Centre slice of the phantom nodule (``make_phantom`` puts it at 35 % of z)."""
        nz = self.spec.shape[0]
        return min(max(round(0.35 * nz), 0), nz - 1)


def load_phantom(spec: PhantomSpec, patient_id: str) -> Phantom:
    """Write *spec* as DICOM to a temporary folder and load it like a real study."""
    with tempfile.TemporaryDirectory(prefix="thoraxbench-sanity-") as tmp:
        folder = write_dicom_series(
            make_phantom(spec), Path(tmp) / "study", spec.spacing_mm, patient_id=patient_id
        )
        study = load_study_dir(folder, dataset="synthetic", case_id=patient_id)
    return Phantom(study, spec)


def phantom_spec(seed: int, side: str, diameter_mm: float) -> PhantomSpec:
    """Default phantom geometry with an optional nodule of *diameter_mm* (0 = none)."""
    return PhantomSpec(nodule_radius_mm=diameter_mm / 2, nodule_side=side, seed=seed)


def phantom_single(phantom: Phantom, window: str, size: int, slab_mm: float) -> tuple[bytes, str]:
    """Render the slab through the phantom nodule level (same level with or without a nodule)."""
    vol = phantom.study.volume
    dz = vol.spacing_mm[0]
    idx = phantom.nodule_index
    png = render_axial(vol.hu, idx, slab_mm, dz, window=window, size=size)
    return png, axial_caption(window, rendered_thickness_mm(vol.shape[0], idx, slab_mm, dz))


def view_images(
    study: Study, window: str, n: int, size: int, slab_mm: float
) -> tuple[list[bytes], list[str], list[int]]:
    """Images, bare captions and source indices from the multi-slice view."""
    prepared = multi_view(window, n, size, slab_mm).build(study, AnalysisRequest())
    captions = [strip_caption_prefix(c) for c in prepared.image_captions]
    return list(prepared.images), captions, list(prepared.slice_indices)


# -- LIDC calibration geometry -----------------------------------------------------------


@dataclass(frozen=True)
class SlabPair:
    """A reference lesion slab and its matched same-patient control slab (indices only)."""

    entry: IndexEntry
    lesion: LesionAnnotation
    lesion_index: int
    control_index: int
    control_distance_mm: float


def _lung_range(entry: IndexEntry) -> tuple[int, int]:
    extent = entry.cues.lung_z_extent
    return extent if extent is not None else (0, entry.n_slices - 1)


def control_index(
    entry: IndexEntry,
    lesion_index: int,
    *,
    min_distance_mm: float,
    slab_mm: float,
    used: Sequence[int] = (),
) -> tuple[int, float] | None:
    """Lung-level slice closest to *lesion_index* that is far from every reference lesion.

    A candidate's slab edge must stay at least *min_distance_mm* from every lesion's
    spherical edge (any label, any size). Slices already *used* are skipped. Returns the
    index and its smallest edge distance, or ``None`` when no slice qualifies.
    """
    dz = entry.spacing_mm[0]
    lo, hi = _lung_range(entry)
    best: tuple[int, float] | None = None
    for idx in range(max(0, lo), min(entry.n_slices - 1, hi) + 1):
        if idx in used:
            continue
        slab_lo, slab_hi = slab_bounds(entry.n_slices, idx, slab_mm, dz)
        lower_edge = (slab_lo - 0.5) * dz
        upper_edge = (slab_hi - 0.5) * dz
        gap = min(
            (
                max(lower_edge - les.center_zyx[0], les.center_zyx[0] - upper_edge)
                - les.diameter_mm / 2
                for les in entry.reference.lesions
            ),
            default=math.inf,
        )
        if gap < min_distance_mm:
            continue
        if best is None or abs(idx - lesion_index) < abs(best[0] - lesion_index):
            best = (idx, gap)
    return best


def _patient_order(entries: Sequence[IndexEntry]) -> list[IndexEntry]:
    return sorted(entries, key=lambda e: hashlib.sha256(e.case_id.encode()).hexdigest())


def select_pairs(
    entries: Sequence[IndexEntry],
    *,
    min_diameter_mm: float,
    max_lesions: int,
    min_distance_mm: float,
    slab_mm: float,
    label: str = "pulmonary_nodule",
) -> tuple[list[SlabPair], dict[str, int]]:
    """Round-robin over patients (hash order), largest lesions first, capped at *max_lesions*.

    Returns the pairs and counts of eligible lesions and lesions without a control.
    """
    queues: list[tuple[IndexEntry, list[LesionAnnotation]]] = []
    eligible = 0
    for entry in _patient_order(entries):
        lesions = sorted(
            (
                les
                for les in entry.reference.lesions
                if les.label == label and les.diameter_mm >= min_diameter_mm
            ),
            key=lambda les: (-les.diameter_mm, les.center_zyx),
        )
        eligible += len(lesions)
        if lesions:
            queues.append((entry, lesions))
    pairs: list[SlabPair] = []
    used: dict[str, list[int]] = {}
    no_control = 0
    while len(pairs) < max_lesions and any(lesions for _, lesions in queues):
        for entry, lesions in queues:
            if not lesions or len(pairs) >= max_lesions:
                continue
            lesion = lesions.pop(0)
            centre = lesion_slices(lesion, entry)[1]
            taken = used.setdefault(entry.case_id, [])
            control = control_index(
                entry, centre, min_distance_mm=min_distance_mm, slab_mm=slab_mm, used=taken
            )
            if control is None:
                no_control += 1
                continue
            taken.append(control[0])
            pairs.append(SlabPair(entry, lesion, centre, control[0], round(control[1], 1)))
    return pairs, {
        "eligible_lesions": eligible,
        "without_control": no_control,
        "selected": len(pairs),
    }


def size_bin(diameter_mm: float) -> str:
    """Coarse lesion size bin for sensitivity breakdowns."""
    if diameter_mm < 6:
        return "3-6 mm"
    if diameter_mm < 10:
        return "6-10 mm"
    return ">=10 mm"


def pair_items(
    pairs: Sequence[SlabPair],
    settings: Settings,
    open_case: OpenStudy,
    *,
    window: str,
    size: int,
    slab_mm: float,
) -> list[SanityItem]:
    """Render one lesion slab and one control slab per pair (studies opened once each)."""
    items: list[SanityItem] = []
    studies: dict[str, Study] = {}
    for number, pair in enumerate(pairs):
        entry = pair.entry
        study = studies.get(entry.case_id)
        if study is None:
            study = studies[entry.case_id] = open_case(entry, settings)
        vol = study.volume
        dz = vol.spacing_mm[0]
        for truth, idx, role in (
            (1, pair.lesion_index, "lesion"),
            (0, pair.control_index, "control"),
        ):
            png = render_axial(vol.hu, idx, slab_mm, dz, window=window, size=size)
            items.append(
                SanityItem(
                    key=f"pair{number:03d}-{role}-{window}",
                    group=f"pair{number:03d}",
                    condition=role,
                    images=[png],
                    captions=[
                        axial_caption(window, rendered_thickness_mm(vol.shape[0], idx, slab_mm, dz))
                    ],
                    truth=truth,
                    patient=f"{entry.dataset}:{entry.patient_id}",
                    meta={
                        "case_id": entry.case_id,
                        "window": window,
                        "slice_index": idx,
                        "lesion_diameter_mm": pair.lesion.diameter_mm,
                        "size_bin": size_bin(pair.lesion.diameter_mm),
                        "lesion_readers": pair.lesion.readers,
                        "control_edge_distance_mm": pair.control_distance_mm,
                    },
                )
            )
    return items
