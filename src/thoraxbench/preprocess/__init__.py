# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Deterministic preprocessing on canonical HU volumes (Vision §9.4, architecture §5.5).

Nothing in this package modifies ``Volume.hu``; every function returns new arrays.
"""

from thoraxbench.preprocess.cues import (
    HU_CUES_VERSION,
    HUCues,
    Landmarks,
    NoduleCandidate,
    hu_cues,
)
from thoraxbench.preprocess.masks import body_mask, lung_envelope, lung_mask, lung_z_extent
from thoraxbench.preprocess.reformat import coronal_reformat, mip_slab, slab_bounds
from thoraxbench.preprocess.windows import (
    MEDGEMMA_RGB_WINDOWS,
    WINDOWS,
    Window,
    apply_range,
    apply_window,
    rgb_encode,
)

__all__ = [
    "HU_CUES_VERSION",
    "MEDGEMMA_RGB_WINDOWS",
    "WINDOWS",
    "HUCues",
    "Landmarks",
    "NoduleCandidate",
    "Window",
    "apply_range",
    "apply_window",
    "body_mask",
    "coronal_reformat",
    "hu_cues",
    "lung_envelope",
    "lung_mask",
    "lung_z_extent",
    "mip_slab",
    "rgb_encode",
    "slab_bounds",
]
