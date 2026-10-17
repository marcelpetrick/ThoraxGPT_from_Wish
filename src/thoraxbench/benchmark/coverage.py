# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Reference-lesion coverage of sampled model inputs (E001-coverage, no model, no pixels).

A vision-language model cannot report a nodule that is not on any attached image. This
module measures, for a sampling strategy, an image count ``n`` and a MIP slab thickness,
the fraction of reference lesions whose z-extent intersects at least one prepared axial
image or slab. It reuses the exact strategy code of :mod:`thoraxbench.sampling` and the
slab arithmetic of :func:`thoraxbench.preprocess.reformat.slab_bounds`.

Inputs come only from the development study index (reference lesions, slice count,
spacing and cached HU cues); no DICOM pixel data is read. Entries are restricted to one
development phase through :class:`~thoraxbench.splits.CaseGuard`. Sealed cases are never
requested, and entries of other phases are skipped before validation.

Lesion z-extent is approximated as ``centre ± diameter / 2`` (a sphere). LIDC centres are
consensus means, so this is an approximation of reader contours. "Covered" means the
lesion lies inside a rendered slab or on a rendered slice. It does not mean the lesion is
visible: wide MIP slabs can hide a nodule among vessels, and a 256-pixel render can lose it.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from thoraxbench.config import Settings
from thoraxbench.dicom import QCReport, Volume
from thoraxbench.index import IndexEntry, index_path
from thoraxbench.preprocess.reformat import slab_bounds
from thoraxbench.sampling import get_strategy
from thoraxbench.schemas import LesionAnnotation
from thoraxbench.splits import CaseGuard, Phase, SealedAccessError

COVERAGE_VERSION = "1"
#: Measured prompt cost per attached image with full source-slice captions (P2, Q4,
#: 2 vs 9 images: 1522 vs 3779 prompt tokens), rounded up. Gemma 3 itself uses 256.
TOKENS_PER_IMAGE = 325
#: Text tokens of a constrained prompt without images (same measurement, rounded up).
TEXT_TOKENS = 1000
#: Generation budget that must remain inside the context window.
GENERATION_RESERVE = 1024
DEFAULT_NUM_CTX = 16384
#: Thickest MIP slab accepted for a pick; reading practice uses 5-10 mm nodule slabs. The
#: rendered slab is rounded to whole slices, so allow one extra 2.5 mm slice.
MAX_READING_SLAB_MM = 12.5


@dataclass(frozen=True)
class CoverageSetting:
    """One sampling configuration: strategy, image budget and view MIP slab (0 = none)."""

    strategy: str
    n: int
    slab_mm: float = 0.0
    strategy_params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.n < 1:
            raise ValueError("image count must be at least 1")
        if not math.isfinite(self.slab_mm) or self.slab_mm < 0:
            raise ValueError("slab thickness must be a finite non-negative number")
        get_strategy(self.strategy, n=self.n, **self.strategy_params)

    @property
    def name(self) -> str:
        """Short human-readable identifier."""
        extra = "".join(f",{k}={v}" for k, v in sorted(self.strategy_params.items()))
        return f"{self.strategy}(n={self.n}{extra}) slab={self.slab_mm:g}mm"


@dataclass(frozen=True)
class CoverageRow:
    """Aggregate coverage of one setting over a set of studies (no case identifiers)."""

    setting: CoverageSetting
    n_studies: int
    n_lesions: int
    lesions_covered: int
    lesions_centre_covered: int
    n_lesions_ge6mm: int
    lesions_ge6mm_covered: int
    n_positive_studies: int
    positive_studies_covered: int
    mean_images: float
    max_images: int
    estimated_prompt_tokens: int
    max_rendered_slab_mm: float = 0.0

    @property
    def lesion_coverage(self) -> float | None:
        """Fraction of reference lesions on at least one prepared image or slab."""
        return self.lesions_covered / self.n_lesions if self.n_lesions else None

    def fits_context(self, num_ctx: int = DEFAULT_NUM_CTX) -> bool:
        """Whether the largest prepared input plus the generation reserve fits *num_ctx*."""
        return self.estimated_prompt_tokens + GENERATION_RESERVE <= num_ctx

    def to_dict(self, num_ctx: int = DEFAULT_NUM_CTX) -> dict[str, Any]:
        """JSON-serialisable aggregate (no identifiers)."""
        return {
            "setting": self.setting.name,
            "strategy": self.setting.strategy,
            "n": self.setting.n,
            "slab_mm": self.setting.slab_mm,
            "strategy_params": dict(self.setting.strategy_params),
            "n_studies": self.n_studies,
            "n_lesions": self.n_lesions,
            "lesions_covered": self.lesions_covered,
            "lesion_coverage": self.lesion_coverage,
            "lesions_centre_covered": self.lesions_centre_covered,
            "n_lesions_ge6mm": self.n_lesions_ge6mm,
            "lesions_ge6mm_covered": self.lesions_ge6mm_covered,
            "n_positive_studies": self.n_positive_studies,
            "positive_studies_covered": self.positive_studies_covered,
            "mean_images": self.mean_images,
            "max_images": self.max_images,
            "estimated_prompt_tokens": self.estimated_prompt_tokens,
            "max_rendered_slab_mm": self.max_rendered_slab_mm,
            "fits_context": self.fits_context(num_ctx),
        }


def phase_entries(
    dataset: str, settings: Settings, phase: Phase = Phase.CALIBRATION
) -> list[IndexEntry]:
    """Index entries of one development *phase*, checked by the case guard.

    Entries outside *phase* are skipped before validation. Sealed cases are never requested.

    Raises:
        SealedAccessError: if *phase* is sealed or a selected case fails the guard.
        FileNotFoundError: if the split or index does not exist.
    """
    if phase not in {Phase.CALIBRATION, Phase.INTERNAL_TEST}:
        raise SealedAccessError("coverage reads one development phase only")
    guard = CaseGuard.load(settings.data_dir, settings.manifests_dir, dataset)
    wanted = set(guard.cases(phase))
    raw = json.loads(index_path(settings, dataset).read_text(encoding="utf-8"))
    entries: list[IndexEntry] = []
    for item in raw:
        case_id = item.get("case_id") if isinstance(item, dict) else None
        if case_id not in wanted:
            continue
        guard.check(case_id, phase)
        entries.append(IndexEntry.model_validate(item))
    return sorted(entries, key=lambda e: e.case_id)


def _geometry_volume(entry: IndexEntry) -> Volume:
    """Build a pixel-free stand-in volume with the indexed slice count and spacing."""
    nz = entry.n_slices
    dz = entry.spacing_mm[0]
    qc = QCReport(
        n_slices=nz,
        spacing_mm=entry.spacing_mm,
        axial_coverage_mm=nz * dz,
        hu_min=0,
        hu_max=0,
        hu_percentiles={},
        gaps_mm=[],
        duplicates_removed=0,
        non_uniform_spacing=False,
        gantry_tilt_suspected=False,
        lung_voxel_fraction=0.0,
        body_region_confidence=0.0,
        contrast=None,
        kernel=None,
        selected_series_reason="coverage geometry only",
    )
    return Volume(
        hu=np.zeros((nz, 1, 1), dtype=np.int16),
        spacing_mm=entry.spacing_mm,
        patient_id="",
        study_uid="",
        series_uid="",
        z_positions_mm=[i * dz for i in range(nz)],
        qc=qc,
    )


def prepared_ranges(entry: IndexEntry, setting: CoverageSetting) -> list[tuple[int, int]]:
    """Half-open slice ranges ``[lo, hi)`` of every prepared axial image of *entry*.

    Mirrors :class:`thoraxbench.views.MultiSliceView`: the view slab overrides the strategy
    slab; without a slab each image is one source slice.
    """
    volume = _geometry_volume(entry)
    strategy = get_strategy(setting.strategy, n=setting.n, **setting.strategy_params)
    selection = strategy.select(volume, entry.cues)
    slab = setting.slab_mm or selection.slab_mm
    nz, dz = entry.n_slices, entry.spacing_mm[0]
    if slab > 0:
        return [slab_bounds(nz, idx, slab, dz) for idx in selection.indices]
    return [(idx, idx + 1) for idx in selection.indices]


def lesion_slices(lesion: LesionAnnotation, entry: IndexEntry) -> tuple[int, int, int]:
    """Approximate ``(first, centre, last)`` source slices of a lesion (spherical extent)."""
    dz = entry.spacing_mm[0]
    centre_mm = lesion.center_zyx[0]
    radius = lesion.diameter_mm / 2.0
    last_slice = entry.n_slices - 1
    centre = int(min(max(round(centre_mm / dz), 0), last_slice))
    first = int(min(max(math.ceil((centre_mm - radius) / dz - 1e-9), 0), centre))
    last = int(max(min(math.floor((centre_mm + radius) / dz + 1e-9), last_slice), centre))
    return first, centre, last


def _covered(span: tuple[int, int, int], ranges: Sequence[tuple[int, int]]) -> tuple[bool, bool]:
    first, centre, last = span
    any_overlap = any(lo <= last and first < hi for lo, hi in ranges)
    on_centre = any(lo <= centre < hi for lo, hi in ranges)
    return any_overlap, on_centre


def measure(
    entries: Sequence[IndexEntry],
    setting: CoverageSetting,
    *,
    labels: Iterable[str] = ("pulmonary_nodule", "pulmonary_mass"),
) -> CoverageRow:
    """Aggregate lesion coverage of *setting* over *entries*."""
    wanted = set(labels)
    n_lesions = covered = centre_covered = big = big_covered = 0
    positive = positive_covered = 0
    counts: list[int] = []
    thickest = 0.0
    for entry in entries:
        ranges = prepared_ranges(entry, setting)
        counts.append(len(ranges))
        thickest = max(
            thickest, max(((hi - lo) * entry.spacing_mm[0] for lo, hi in ranges), default=0.0)
        )
        lesions = [les for les in entry.reference.lesions if les.label in wanted]
        if lesions:
            positive += 1
        study_hit = False
        for lesion in lesions:
            hit, centre_hit = _covered(lesion_slices(lesion, entry), ranges)
            n_lesions += 1
            covered += hit
            centre_covered += centre_hit
            study_hit = study_hit or hit
            if lesion.diameter_mm >= 6.0:
                big += 1
                big_covered += hit
        positive_covered += study_hit
    max_images = max(counts, default=0)
    return CoverageRow(
        setting=setting,
        n_studies=len(entries),
        n_lesions=n_lesions,
        lesions_covered=covered,
        lesions_centre_covered=centre_covered,
        n_lesions_ge6mm=big,
        lesions_ge6mm_covered=big_covered,
        n_positive_studies=positive,
        positive_studies_covered=positive_covered,
        mean_images=round(sum(counts) / len(counts), 2) if counts else 0.0,
        max_images=max_images,
        estimated_prompt_tokens=TEXT_TOKENS + TOKENS_PER_IMAGE * max_images,
        max_rendered_slab_mm=round(thickest, 1),
    )


def default_grid() -> list[CoverageSetting]:
    """Return the E001-coverage sweep: strategy x n x slab (axial images only)."""
    grid: list[CoverageSetting] = []
    for n in (2, 4, 9, 16, 24, 32, 48):
        for strategy in ("uniform", "lung_extent", "anatomy"):
            for slab in (0.0, 5.0, 10.0):
                grid.append(CoverageSetting(strategy, n, slab))
        grid.append(CoverageSetting("mip_slabs", n, 0.0, {"slab_mm": 10.0}))
    return grid


def smallest_sufficient(
    rows: Sequence[CoverageRow],
    *,
    target: float = 0.9,
    num_ctx: int = DEFAULT_NUM_CTX,
    max_slab_mm: float = MAX_READING_SLAB_MM,
) -> CoverageRow | None:
    """Fewest-image setting meeting *target*, *num_ctx* and the reading-slab limit.

    Ties prefer the thinner rendered slab, then higher coverage. Slabs wider than
    *max_slab_mm* are excluded: they cover lesions geometrically but can hide them.
    """
    eligible = [
        r
        for r in rows
        if r.lesion_coverage is not None
        and r.lesion_coverage >= target
        and r.fits_context(num_ctx)
        and r.max_rendered_slab_mm <= max_slab_mm
    ]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda r: (r.max_images, r.max_rendered_slab_mm, -(r.lesion_coverage or 0.0)),
    )


def _pct(num: int, den: int) -> str:
    return f"{num}/{den} ({100.0 * num / den:.1f}%)" if den else "n/a"


def render_table(rows: Sequence[CoverageRow], *, num_ctx: int = DEFAULT_NUM_CTX) -> str:
    """Markdown table of aggregate coverage (no case identifiers)."""
    lines = [
        "| Setting | Images (mean/max) | Max rendered slab | Est. prompt tokens | Fits ctx "
        "| Lesions covered | Centre slice covered | Lesions >=6 mm covered "
        "| Positive studies covered |",
        "|---|---:|---:|---:|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| `{r.setting.name}` | {r.mean_images:g}/{r.max_images} | "
            f"{r.max_rendered_slab_mm:g} mm | {r.estimated_prompt_tokens} | "
            f"{'yes' if r.fits_context(num_ctx) else 'no'} | "
            f"{_pct(r.lesions_covered, r.n_lesions)} | "
            f"{_pct(r.lesions_centre_covered, r.n_lesions)} | "
            f"{_pct(r.lesions_ge6mm_covered, r.n_lesions_ge6mm)} | "
            f"{_pct(r.positive_studies_covered, r.n_positive_studies)} |"
        )
    return "\n".join(lines)
