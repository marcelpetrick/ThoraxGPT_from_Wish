# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Patient-level splits and the sealed-validation guard (Vision §2.4, §14-§16)."""

from thoraxbench.splits.guard import CaseGuard, FreezeRecord, SealedAccessError, freeze_experiment
from thoraxbench.splits.split import (
    CaseRecord,
    Phase,
    SplitManifest,
    SplitResult,
    load_split,
    make_split,
    save_split,
)

__all__ = [
    "CaseGuard",
    "CaseRecord",
    "FreezeRecord",
    "Phase",
    "SealedAccessError",
    "SplitManifest",
    "SplitResult",
    "freeze_experiment",
    "load_split",
    "make_split",
    "save_split",
]
