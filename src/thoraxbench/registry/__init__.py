# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Dataset registry and the license/terms policy gate (Vision §2.5, §6)."""

from thoraxbench.registry.datasets import (
    ACQUIRABLE_STATUSES,
    DatasetEntry,
    DatasetStatus,
    PolicyError,
    load_registry,
    require_acquirable,
)

__all__ = [
    "ACQUIRABLE_STATUSES",
    "DatasetEntry",
    "DatasetStatus",
    "PolicyError",
    "load_registry",
    "require_acquirable",
]
