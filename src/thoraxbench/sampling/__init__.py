# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Versioned, deterministic slice-selection strategies S1-S6 (Vision §10)."""

from thoraxbench.sampling.strategies import (
    STRATEGIES,
    AnatomyBalanced,
    ContactSheet,
    LungExtent,
    MipSlabs,
    Selection,
    ThoraxSweep,
    TwoStage,
    Uniform,
    coarse_to_fine,
    get_strategy,
)

__all__ = [
    "STRATEGIES",
    "AnatomyBalanced",
    "ContactSheet",
    "LungExtent",
    "MipSlabs",
    "Selection",
    "ThoraxSweep",
    "TwoStage",
    "Uniform",
    "coarse_to_fine",
    "get_strategy",
]
