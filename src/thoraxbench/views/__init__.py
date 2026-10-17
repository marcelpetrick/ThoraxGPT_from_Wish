# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Model-specific input views (Vision §9.4): rendered slices, crops or saved tensors."""

from thoraxbench.views.builders import (
    VIEWS,
    MultiSliceView,
    TensorView,
    get_view,
    render_slice_png,
)
from thoraxbench.views.crops import CROP_VIEW_ID, CandidateCropView

__all__ = [
    "CROP_VIEW_ID",
    "VIEWS",
    "CandidateCropView",
    "MultiSliceView",
    "TensorView",
    "get_view",
    "render_slice_png",
]
