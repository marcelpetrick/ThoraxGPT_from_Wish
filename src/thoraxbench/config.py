# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Runtime settings, resolved from environment variables with ``THORAXBENCH_`` prefix."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUDGET_GB = 10.0


def _env(name: str, default: str) -> str:
    return os.environ.get(f"THORAXBENCH_{name}", default)


@dataclass(frozen=True)
class Settings:
    """Paths and endpoints used by every component.

    Attributes:
        repo_root: Root of the source checkout (configs, manifests).
        data_dir: Git-ignored data directory (raw, cache, splits, sealed, results).
        ollama_url: Base URL of the local Ollama server.
        data_budget_bytes: Hard disk budget for ``data_dir``.
        service_urls: Base URLs of optional local 3D-model services keyed by service id.
    """

    repo_root: Path = REPO_ROOT
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(REPO_ROOT / "data"))))
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434"))
    data_budget_bytes: int = field(
        default_factory=lambda: int(float(_env("DATA_BUDGET_GB", str(DEFAULT_BUDGET_GB))) * 1e9)
    )
    service_urls: dict[str, str] = field(
        default_factory=lambda: {
            "ct_clip": _env("CT_CLIP_URL", "http://localhost:8011"),
            "m3d_lamed": _env("M3D_URL", "http://localhost:8012"),
            "ct_chat": _env("CT_CHAT_URL", "http://localhost:8013"),
            "radfm": _env("RADFM_URL", "http://localhost:8014"),
            "huatuo_vision": _env("HUATUO_URL", "http://localhost:8015"),
        }
    )

    @property
    def configs_dir(self) -> Path:
        """Directory holding versioned YAML configuration."""
        return self.repo_root / "configs"

    @property
    def manifests_dir(self) -> Path:
        """Directory holding committed manifests (IDs/hashes only)."""
        return self.repo_root / "manifests"

    def data_path(self, *parts: str) -> Path:
        """Return a path inside the data directory."""
        return self.data_dir.joinpath(*parts)


def get_settings() -> Settings:
    """Build settings from the current environment."""
    return Settings()
