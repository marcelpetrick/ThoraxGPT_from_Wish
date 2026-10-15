# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Dataset registry entries loaded from ``configs/datasets/*.yaml``."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class PolicyError(RuntimeError):
    """Raised when an action would violate the data/licensing policy."""


class DatasetStatus(StrEnum):
    """License review status of a data source (Vision §6, plus ``pending_access``)."""

    APPROVED = "approved"
    APPROVED_NONCOMMERCIAL = "approved_noncommercial"
    APPROVED_EVAL_ONLY = "approved_eval_only"
    PENDING_TERMS_REVIEW = "pending_terms_review"
    PENDING_ACCESS = "pending_access"
    REJECTED = "rejected"


ACQUIRABLE_STATUSES = frozenset(
    {
        DatasetStatus.APPROVED,
        DatasetStatus.APPROVED_NONCOMMERCIAL,
        DatasetStatus.APPROVED_EVAL_ONLY,
    }
)


class DatasetEntry(BaseModel):
    """One registered data source with its provenance and license decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    provider: str
    modality: str = "CT"
    anatomy: str = "thorax"
    license: str
    license_url: str | None = None
    access: str
    redistribution: str
    commercial_use: bool = False
    patient_level_split_required: bool = True
    source_url: str
    doi: str | None = None
    raw_format: str
    labels: list[str] = Field(default_factory=list)
    citation_required: bool = True
    citation: str | None = None
    status: DatasetStatus
    parent_datasets: list[str] = Field(default_factory=list)
    role: str = "development"
    acquisition: dict[str, object] = Field(default_factory=dict)
    notes: str | None = None

    @property
    def acquirable(self) -> bool:
        """Whether acquisition commands may run for this source."""
        return self.status in ACQUIRABLE_STATUSES


def load_registry(directory: Path) -> dict[str, DatasetEntry]:
    """Load every ``*.yaml`` registry entry in *directory*, keyed by id.

    Raises:
        ValueError: if two files declare the same id or a file id mismatches its name.
    """
    entries: dict[str, DatasetEntry] = {}
    for path in sorted(directory.glob("*.yaml")):
        entry = DatasetEntry.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if entry.id != path.stem:
            msg = f"{path.name}: id '{entry.id}' does not match the file name"
            raise ValueError(msg)
        if entry.id in entries:  # pragma: no cover - impossible: file names are unique
            msg = f"duplicate dataset id {entry.id}"
            raise ValueError(msg)
        entries[entry.id] = entry
    return entries


def require_acquirable(entry: DatasetEntry) -> None:
    """Refuse any acquisition for a source whose status is not approved (Vision §6).

    Raises:
        PolicyError: if the source is pending, gated without access, or rejected.
    """
    if not entry.acquirable:
        msg = (
            f"dataset '{entry.id}' has status '{entry.status}'; acquisition is only allowed "
            f"for {sorted(s.value for s in ACQUIRABLE_STATUSES)}"
        )
        raise PolicyError(msg)
