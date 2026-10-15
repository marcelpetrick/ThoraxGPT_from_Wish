# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""CT display windows (level/width) mapping HU to 8-bit grey values.

Reading-practice windows follow docs/reading_practice.md §3.1. The MedGemma RGB encoding is
copied from Google's official notebook ``high_dimensional_ct_hugging_face.ipynb``
(``window_clips = [(-1024, 1024), (-135, 215), (0, 80)]``).
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class Window:
    """A display window given as centre (level) and width in HU."""

    center: float
    width: float

    @property
    def low(self) -> float:
        """Lowest HU value displayed (black)."""
        return self.center - self.width / 2

    @property
    def high(self) -> float:
        """Highest HU value displayed (white)."""
        return self.center + self.width / 2

    @classmethod
    def from_range(cls, low: float, high: float) -> Window:
        """Build a window from its HU range."""
        return cls((low + high) / 2, high - low)


#: Standard chest-CT reading windows (level/width in HU).
WINDOWS: MappingProxyType[str, Window] = MappingProxyType(
    {
        "lung": Window(-600.0, 1500.0),
        "mediastinum": Window(50.0, 350.0),
        "bone": Window(400.0, 1800.0),
        "abdomen": Window(50.0, 400.0),
    }
)

#: MedGemma 1.5 CT RGB encoding: R = wide, G = mediastinum, B = narrow ("brain") window.
MEDGEMMA_RGB_WINDOWS: tuple[Window, Window, Window] = (
    Window.from_range(-1024.0, 1024.0),
    Window.from_range(-135.0, 215.0),
    Window.from_range(0.0, 80.0),
)


def apply_range(hu: npt.ArrayLike, low: float, high: float) -> npt.NDArray[np.uint8]:
    """Clip *hu* to ``[low, high]`` and scale linearly to 0-255 (rounded)."""
    if high <= low:
        msg = f"window high ({high}) must exceed low ({low})"
        raise ValueError(msg)
    arr = np.clip(np.asarray(hu, dtype=np.float32), low, high)
    scaled = (arr - low) / (high - low) * 255.0
    return np.rint(scaled).astype(np.uint8)


def apply_window(hu: npt.ArrayLike, center: float, width: float) -> npt.NDArray[np.uint8]:
    """Apply a level/width window and return 8-bit grey values."""
    win = Window(center, width)
    return apply_range(hu, win.low, win.high)


def rgb_encode(
    hu: npt.ArrayLike, windows: tuple[Window, Window, Window] = MEDGEMMA_RGB_WINDOWS
) -> npt.NDArray[np.uint8]:
    """Stack three windows as RGB channels, shape ``(..., 3)``."""
    return np.stack([apply_range(hu, w.low, w.high) for w in windows], axis=-1)
