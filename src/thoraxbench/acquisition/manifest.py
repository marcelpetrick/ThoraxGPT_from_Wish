# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Acquisition manifest (Vision §8): IDs, counts and hashes only, never pixel data.

The same JSON is written to ``data/raw/<id>/_acquisition.json`` and to the committed
``manifests/datasets/<id>.json``. The format is the one produced by the pilot prototype.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class AcquisitionManifest(BaseModel):
    """Provenance record of one dataset's local raw copy."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    dataset: str
    collection: str
    provider: str
    source_url: str
    doi: str | None = None
    source_version: str | None = None
    downloaded_at: str
    verified_at: str
    files: int = Field(ge=0)
    total_bytes: int = Field(alias="bytes", ge=0)
    patients: int = Field(ge=0)
    series: int = Field(ge=0)
    series_by_modality: dict[str, int]
    sha256_manifest: str
    sha256_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license: str
    license_snapshot: dict[str, str | None]
    tool_version: str
    selection: dict[str, object]
    api: dict[str, object]
    previous_run_results: dict[str, int] | None = None
    run_results: dict[str, int] | None = None
    run_history: str | None = None


def load_manifest(path: Path) -> AcquisitionManifest | None:
    """Read a manifest if it exists."""
    if not path.is_file():
        return None
    return AcquisitionManifest.model_validate_json(path.read_text(encoding="utf-8"))


def dump_manifest(manifest: AcquisitionManifest) -> str:
    """Serialize with the on-disk key names and the prototype's one-space indent."""
    return manifest.model_dump_json(by_alias=True, indent=1)


def write_manifest(manifest: AcquisitionManifest, *paths: Path) -> None:
    """Write the identical manifest JSON to every path."""
    text = dump_manifest(manifest)
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
