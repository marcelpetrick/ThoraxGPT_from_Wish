# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
from pathlib import Path

import pytest

from thoraxbench.config import get_settings


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("THORAXBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("THORAXBENCH_DATA_BUDGET_GB", "2")
    monkeypatch.setenv("THORAXBENCH_OLLAMA_URL", "http://ollama:11434")
    s = get_settings()
    assert s.data_dir == tmp_path
    assert s.data_budget_bytes == 2_000_000_000
    assert s.ollama_url == "http://ollama:11434"
    assert s.data_path("raw", "x") == tmp_path / "raw" / "x"
    assert s.configs_dir.name == "configs"
    assert s.manifests_dir.name == "manifests"
    assert "ct_clip" in s.service_urls
