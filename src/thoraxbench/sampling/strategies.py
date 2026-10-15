# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Slice-selection strategies.

Every strategy is deterministic (no randomness), versioned, and hashed into the run
provenance. A strategy returns a :class:`Selection`: slice indices (cranial-first, matching
:class:`~thoraxbench.dicom.Volume`) with a short anatomical tag per slice, plus an optional slab
thickness for MIP rendering.

| id | Vision | idea |
|---|---|---|
| ``uniform`` (S1) | §10 S1 | N slices evenly spaced over the whole volume |
| ``lung_extent`` (S2) | §10 S2 | N slices evenly spaced inside the lung z-range |
| ``anatomy`` (S4) | §10 S4 | landmark slices (apex … upper abdomen) + even fill |
| ``two_stage`` (S5) | §10 S5 | lung-extent context + slices of deterministic nodule candidates |
| ``mip_slabs`` | reading practice | contiguous thin MIP slabs covering the lungs (nodule search) |
| ``contact_sheet`` (S6) | §10 S6 | lung-extent slices meant to be tiled into one montage image |

S3 (multi-window) is a rendering choice and lives in :mod:`thoraxbench.views`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np

from thoraxbench.dicom import Volume
from thoraxbench.preprocess import HUCues


@dataclass(frozen=True)
class Selection:
    """Chosen slices with tags (e.g. ``"carina"``) and an optional MIP slab thickness."""

    indices: list[int]
    tags: list[str]
    slab_mm: float = 0.0
    montage: bool = False


def _evenly(lo: int, hi: int, n: int) -> list[int]:
    """``n`` distinct indices evenly spaced in ``[lo, hi]`` (fewer if the range is short)."""
    if hi < lo:
        return []
    n = max(1, min(n, hi - lo + 1))
    return sorted({round(v) for v in np.linspace(lo, hi, n)})


def _lung_range(volume: Volume, cues: HUCues) -> tuple[int, int]:
    if cues.lung_z_extent is not None:
        return cues.lung_z_extent
    return 0, volume.shape[0] - 1


@dataclass(frozen=True)
class Strategy:
    """Base class: id/version/params and the provenance hash."""

    id: ClassVar[str] = "base"
    version: ClassVar[str] = "1"
    n: int = 16

    @property
    def params(self) -> dict[str, Any]:
        """Parameters that influence the selection."""
        return {"n": self.n}

    @property
    def sha256(self) -> str:
        """Hash of id, version and parameters (goes into run provenance)."""
        blob = json.dumps({"id": self.id, "version": self.version, **self.params}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def select(self, volume: Volume, cues: HUCues) -> Selection:  # pragma: no cover - abstract
        """Choose slices of *volume*."""
        raise NotImplementedError


@dataclass(frozen=True)
class Uniform(Strategy):
    """S1: evenly spaced over the whole volume."""

    id: ClassVar[str] = "uniform"

    def select(self, volume: Volume, cues: HUCues) -> Selection:
        """Choose ``n`` evenly spaced slices of the whole volume."""
        idx = _evenly(0, volume.shape[0] - 1, self.n)
        return Selection(idx, ["uniform"] * len(idx))


@dataclass(frozen=True)
class LungExtent(Strategy):
    """S2: evenly spaced inside the lung z-range."""

    id: ClassVar[str] = "lung_extent"

    def select(self, volume: Volume, cues: HUCues) -> Selection:
        """Choose ``n`` evenly spaced slices between lung apex and base."""
        lo, hi = _lung_range(volume, cues)
        idx = _evenly(lo, hi, self.n)
        return Selection(idx, ["lung"] * len(idx))


@dataclass(frozen=True)
class AnatomyBalanced(Strategy):
    """S4: guaranteed landmark coverage, then evenly filled inside the lungs."""

    id: ClassVar[str] = "anatomy"
    upper_abdomen_mm: float = 30.0

    @property
    def params(self) -> dict[str, Any]:
        """Parameters that influence the selection."""
        return {"n": self.n, "upper_abdomen_mm": self.upper_abdomen_mm}

    def select(self, volume: Volume, cues: HUCues) -> Selection:
        """Landmarks first (apex, upper lobes, carina, hila, heart, lower lobes, dome, base)."""
        lo, hi = _lung_range(volume, cues)
        nz = volume.shape[0]
        tagged: dict[int, str] = {}
        lm = cues.landmarks
        if lm is not None:
            upper = (lm.apex + lm.carina) // 2
            hila = min(lm.carina + max(1, round(15.0 / volume.spacing_mm[0])), lm.heart)
            lower = (lm.heart + lm.dome) // 2
            points = [
                (lm.apex, "apex"),
                (upper, "upper lobes"),
                (lm.carina, "carina"),
                (hila, "hila"),
                (lm.heart, "heart/mediastinum"),
                (lower, "lower lobes"),
                (lm.dome, "diaphragm dome / costophrenic angles"),
                (lm.base, "lung bases"),
            ]
        else:
            fractions = (0.0, 0.2, 0.3, 0.4, 0.55, 0.75, 0.9, 1.0)
            names = (
                "apex",
                "upper lobes",
                "carina",
                "hila",
                "heart/mediastinum",
                "lower lobes",
                "diaphragm dome / costophrenic angles",
                "lung bases",
            )
            points = [
                (round(lo + f * (hi - lo)), name) for f, name in zip(fractions, names, strict=True)
            ]
        abdomen = min(nz - 1, hi + max(1, round(self.upper_abdomen_mm / volume.spacing_mm[0])))
        points.append((abdomen, "upper abdomen"))
        for idx, name in points:
            key = int(np.clip(idx, 0, nz - 1))
            tagged[key] = f"{tagged[key]} + {name}" if key in tagged else name
        for idx in _evenly(lo, hi, self.n):
            if len(tagged) >= self.n:
                break
            tagged.setdefault(idx, "lung")
        ordered = sorted(tagged)
        return Selection(ordered, [tagged[i] for i in ordered])


@dataclass(frozen=True)
class TwoStage(Strategy):
    """S5: context slices plus every deterministic nodule-candidate slice (up to a cap)."""

    id: ClassVar[str] = "two_stage"
    candidate_share: float = 0.5

    @property
    def params(self) -> dict[str, Any]:
        """Parameters that influence the selection."""
        return {"n": self.n, "candidate_share": self.candidate_share}

    def select(self, volume: Volume, cues: HUCues) -> Selection:
        """Half the budget on candidates (largest first), the rest evenly in the lungs."""
        n_cand = round(self.n * self.candidate_share)
        tagged: dict[int, str] = {}
        ranked = sorted(cues.nodule_candidates, key=lambda c: -c.diameter_mm)
        for cand in ranked:
            if len(tagged) >= n_cand:
                break
            tagged.setdefault(cand.z_index, f"candidate {cand.diameter_mm:.0f} mm {cand.side}")
        lo, hi = _lung_range(volume, cues)
        for idx in _evenly(lo, hi, self.n):
            if len(tagged) >= self.n:
                break
            tagged.setdefault(idx, "lung")
        ordered = sorted(tagged)
        return Selection(ordered, [tagged[i] for i in ordered])


@dataclass(frozen=True)
class MipSlabs(Strategy):
    """Contiguous MIP slabs of ``slab_mm`` covering the lungs, capped at ``n`` slabs."""

    id: ClassVar[str] = "mip_slabs"
    slab_mm: float = 10.0
    n: int = 30

    @property
    def params(self) -> dict[str, Any]:
        """Parameters that influence the selection."""
        return {"n": self.n, "slab_mm": self.slab_mm}

    def select(self, volume: Volume, cues: HUCues) -> Selection:
        """Slab centres every ``slab_mm`` (or wider when ``n`` would be exceeded)."""
        lo, hi = _lung_range(volume, cues)
        step = max(1, round(self.slab_mm / volume.spacing_mm[0]))
        centers = list(range(lo + step // 2, hi + 1, step)) or [lo]
        if len(centers) > self.n:
            centers = _evenly(lo, hi, self.n)
        slab = max(self.slab_mm, (hi - lo + 1) * volume.spacing_mm[0] / max(len(centers), 1))
        return Selection(centers, ["mip"] * len(centers), slab_mm=round(slab, 1))


@dataclass(frozen=True)
class ContactSheet(Strategy):
    """S6: lung-extent slices tiled into one montage by the view."""

    id: ClassVar[str] = "contact_sheet"

    def select(self, volume: Volume, cues: HUCues) -> Selection:
        """Select the S2 slices and flag them for montage rendering."""
        base = LungExtent(n=self.n).select(volume, cues)
        return Selection(base.indices, base.tags, montage=True)


STRATEGIES: dict[str, type[Strategy]] = {
    cls.id: cls for cls in (Uniform, LungExtent, AnatomyBalanced, TwoStage, MipSlabs, ContactSheet)
}


def get_strategy(strategy_id: str, **params: Any) -> Strategy:
    """Instantiate a strategy by id (KeyError if unknown)."""
    return STRATEGIES[strategy_id](**params)
