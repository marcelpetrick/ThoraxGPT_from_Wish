# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Run provenance: everything needed to reconstruct a benchmark result (Vision §24)."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from thoraxbench import __version__

CMD_TIMEOUT_S = 5


def canonical_json(obj: Any) -> str:
    """Deterministic JSON (sorted keys, no whitespace) used for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha256_of_obj(obj: Any) -> str:
    """SHA-256 of the canonical JSON form of *obj*."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def sha256_of_file(path: Path, chunk: int = 1 << 20) -> str:
    """SHA-256 of a file's bytes (streamed)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def scoring_source_hash() -> str:
    """Identify scoring rules and the shared prediction schema by their actual bytes."""
    package = Path(__file__).parent
    return sha256_of_obj(
        {
            str(path.relative_to(package)): sha256_of_file(path)
            for folder in ("scoring", "schemas")
            for path in sorted((package / folder).glob("*.py"))
        }
    )


def _run(args: list[str], cwd: Path | None = None) -> str | None:
    exe = shutil.which(args[0])
    if exe is None:
        return None
    try:
        return subprocess.run(  # noqa: S603 - trusted executable, static arguments
            [exe, *args[1:]],
            capture_output=True,
            text=True,
            check=True,
            timeout=CMD_TIMEOUT_S,
            cwd=cwd,
        ).stdout.strip()
    except OSError, subprocess.SubprocessError:
        return None


def git_state(repo: Path) -> tuple[str | None, bool | None]:
    """Return ``(commit, dirty)`` for *repo*, or ``(None, None)`` outside git."""
    commit = _run(["git", "rev-parse", "HEAD"], cwd=repo)
    if commit is None:
        return None, None
    status = _run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo)
    return commit, bool(status)


def gpu_info() -> dict[str, str | None]:
    """GPU name, driver and CUDA version from ``nvidia-smi`` (all ``None`` if absent)."""
    info: dict[str, str | None] = {"gpu": None, "driver": None, "cuda": None}
    query = _run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])
    if query:
        first = query.splitlines()[0].split(",")
        info["gpu"] = first[0].strip()
        if len(first) > 1:
            info["driver"] = first[1].strip()
    banner = _run(["nvidia-smi"])
    if banner and "CUDA Version:" in banner:
        info["cuda"] = banner.split("CUDA Version:")[1].split()[0].strip("|")
    return info


class RunProvenance(BaseModel):
    """Provenance embedded in every result and durable benchmark case artifact."""

    git_commit: str | None = None
    git_dirty: bool | None = None
    thoraxbench_version: str = __version__
    dataset_manifest_hash: str | None = None
    split_manifest_hash: str | None = None
    ground_truth_hash: str | None = None
    scoring_hash: str | None = None
    input_hash: str | None = None
    model_id: str | None = None
    model_hash: str | None = None
    container_digest: str | None = None
    prompt_hash: str | None = None
    preprocess_hash: str | None = None
    config_hash: str | None = None
    seed: int = 0
    hardware: str = Field(default_factory=lambda: platform.processor() or platform.machine())
    gpu: str | None = None
    driver: str | None = None
    cuda: str | None = None
    python: str = Field(default_factory=lambda: sys.version.split()[0])
    platform: str = Field(default_factory=platform.platform)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @classmethod
    def collect(cls, repo: Path, **fields: Any) -> RunProvenance:
        """Gather git and hardware state, then apply *fields* (hashes, model id, seed)."""
        commit, dirty = git_state(repo)
        return cls(git_commit=commit, git_dirty=dirty, **gpu_info(), **fields)

    def fingerprint(self) -> str:
        """Hash of everything that determines the result (excludes time and hardware)."""
        keys = (
            "git_commit",
            "thoraxbench_version",
            "model_id",
            "dataset_manifest_hash",
            "split_manifest_hash",
            "ground_truth_hash",
            "scoring_hash",
            "input_hash",
            "model_hash",
            "prompt_hash",
            "preprocess_hash",
            "config_hash",
            "seed",
        )
        return sha256_of_obj({k: getattr(self, k) for k in keys})
