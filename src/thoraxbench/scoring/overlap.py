# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Training-overlap tracking for benchmark tables (Vision §16)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Literal

Overlap = Literal["yes", "no", "unknown"]

# Documented pretraining exposure of known models (lower-case dataset ids).
KNOWN_TRAINING_DATA: dict[str, frozenset[str]] = {
    "rules": frozenset(),
    "ct_clip": frozenset({"ct_rate"}),
    "ct_chat": frozenset({"ct_rate", "radgenome_chestct"}),
    "m3d_lamed": frozenset({"m3d_data", "m3d_cap", "m3d_vqa"}),
    "radfm": frozenset({"medmd", "radmd"}),
    # MONAI lung_nodule_ct_detection bundle: trained on LUNA16, i.e. 888 LIDC-IDRI scans
    # (bundle docs/data_license.txt). Patients of every LIDC split may be in LUNA16.
    "monai_retinanet_luna16": frozenset({"luna16", "lidc_idri"}),
}


def normalize_family(family: str) -> str:
    """Normalize model YAML family identifiers without changing recorded results."""
    return family.strip().lower().replace("-", "_")


def combine_overlaps(values: Iterable[Overlap]) -> Overlap:
    """Combine documented flags: yes wins, followed by unknown, then no."""
    flags = set(values)
    if "yes" in flags:
        return "yes"
    return "unknown" if not flags or "unknown" in flags else "no"


def possible_training_overlap(
    model_family: str,
    dataset_id: str,
    *,
    parents: Mapping[str, Iterable[str]] | None = None,
    model_training_data: Mapping[str, Iterable[str]] | None = None,
) -> Overlap:
    """Return ``yes`` / ``no`` / ``unknown`` for the benchmark-table column.

    A dataset overlaps when it, or any of its parent datasets (e.g. RadGenome-ChestCT is
    derived from CT-RATE), is in the model's documented training data. Models without
    documented training data yield ``unknown`` — never ``no``.
    """
    table = {
        normalize_family(k): frozenset(v)
        for k, v in (model_training_data or KNOWN_TRAINING_DATA).items()
    }
    trained = table.get(normalize_family(model_family))
    if trained is None:
        return "unknown"
    lineage = {dataset_id, *((parents or {}).get(dataset_id, ()))}
    return "yes" if lineage & trained else "no"
