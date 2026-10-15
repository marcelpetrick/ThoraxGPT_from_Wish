# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Gated acquisition of approved datasets from the TCIA NBIA public API (Vision §8)."""

from thoraxbench.acquisition.manifest import AcquisitionManifest
from thoraxbench.acquisition.nbia import AcquisitionError, BudgetError, NbiaClient, SeriesRecord
from thoraxbench.acquisition.service import (
    AcquireOptions,
    AcquisitionPlan,
    AcquisitionReport,
    acquire,
)

__all__ = [
    "AcquireOptions",
    "AcquisitionError",
    "AcquisitionManifest",
    "AcquisitionPlan",
    "AcquisitionReport",
    "BudgetError",
    "NbiaClient",
    "SeriesRecord",
    "acquire",
]
