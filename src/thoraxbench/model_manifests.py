# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Offline model-configuration snapshots; no runtime, licensing or training certification."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from thoraxbench.adapters.base import list_model_configs
from thoraxbench.provenance import sha256_of_file

SHA256 = r"^[0-9a-f]{64}$"
MODEL_ID = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"


class DigestEvidence(BaseModel):
    """A historical digest quoted from the committed aggregate results, never a live probe."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_file: Literal["docs/results.md"] = "docs/results.md"
    source_section: str = Field(min_length=1)
    source_label: str = Field(min_length=1)
    recorded_at: date


class ModelManifest(BaseModel):
    """Version-one source-config snapshot with explicitly unverified runtime state."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    snapshot_version: int = Field(ge=1)
    snapshot_date: date
    model_id: str = Field(pattern=MODEL_ID)
    source_config: str
    source_config_sha256: str = Field(pattern=SHA256)
    adapter: Literal["ollama", "http_service", "heuristic"]
    family: str
    tag: str | None
    service: str | None
    quantization: str | None
    declared_license: str
    references: list[str] = Field(min_length=1)
    recorded_digest: str | None = Field(default=None, pattern=SHA256)
    digest_evidence: DigestEvidence | None = None
    current_availability: Literal["unknown"] = "unknown"
    terms_acceptance: Literal["unknown"] = "unknown"
    possible_training_overlap: Literal["unknown"] = "unknown"
    overlap_rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_evidence(self) -> ModelManifest:
        if (self.recorded_digest is None) != (self.digest_evidence is None):
            raise ValueError("A recorded digest and its evidence must be supplied together")
        return self


def load_model_manifests(repo_root: Path) -> dict[str, ModelManifest]:
    """Validate complete snapshots against current config bytes and cited historical rows.

    Reads configuration, manifests and (only for cited digests) ``docs/results.md``.
    It never contacts a provider, reads weights/studies or confirms current installation.
    Evidence checks confirm that the cited digest occurs in the named source row; they
    cannot authenticate the publisher, establish complete training history or accept terms.
    """
    configs = list_model_configs(repo_root / "configs" / "models")
    if not configs:
        raise ValueError("No model configurations found")
    expected = {config.id: config for config in configs}
    folder = repo_root / "manifests" / "models"
    found: dict[str, ModelManifest] = {}
    for path in sorted(folder.glob("*.json")):
        if path.name == "schema.json":
            continue
        snapshot = ModelManifest.model_validate_json(path.read_text(encoding="utf-8"))
        if path.stem != snapshot.model_id or snapshot.model_id in found:
            raise ValueError(f"Model manifest filename/identity mismatch: {path.name}")
        if snapshot.model_id not in expected:
            raise ValueError(f"Unconfigured model manifest: {snapshot.model_id}")
        config = expected[snapshot.model_id]
        relative = f"configs/models/{config.id}.yaml"
        if snapshot.source_config != relative or snapshot.source_config_sha256 != sha256_of_file(
            repo_root / relative
        ):
            raise ValueError(f"Stale model configuration snapshot: {config.id}")
        fields = ("adapter", "family", "tag", "service", "quantization")
        if any(getattr(snapshot, key) != getattr(config, key) for key in fields) or (
            snapshot.declared_license != config.license
        ):
            raise ValueError(f"Model configuration fields differ: {config.id}")
        _check_digest_evidence(repo_root, snapshot)
        found[snapshot.model_id] = snapshot
    missing = sorted(set(expected) - set(found))
    if missing:
        raise ValueError(f"Missing model manifests: {', '.join(missing)}")
    return found


def _check_digest_evidence(repo_root: Path, snapshot: ModelManifest) -> None:
    evidence = snapshot.digest_evidence
    if evidence is None:
        return
    text = (repo_root / evidence.source_file).read_text(encoding="utf-8")
    heading = f"## {evidence.source_section}"
    if heading not in text.splitlines():
        raise ValueError(f"Model digest evidence section missing: {snapshot.model_id}")
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    row = f"| {evidence.source_label} | `{snapshot.recorded_digest}` |"
    if row not in section.splitlines():
        raise ValueError(f"Model digest evidence row missing: {snapshot.model_id}")
