# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Atomic checkpoint recovery and runtime identity checks use synthetic metadata only."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import httpx
import pytest
import respx

from thoraxbench.adapters.base import load_model_config
from thoraxbench.benchmark.checkpoint import BenchmarkStore, runtime_identity
from thoraxbench.config import REPO_ROOT, Settings

IDENTITY: dict[str, Any] = {"runtime_models": {}, "selected": []}


@pytest.fixture
def store(tmp_path: Path) -> BenchmarkStore:
    settings = Settings(data_dir=tmp_path / "data")
    folder = settings.data_path("results", "benchmark", "test", "invocation")
    folder.mkdir(parents=True)
    result = BenchmarkStore(folder, settings)
    result.initialize(IDENTITY, resume=False)
    return result


def test_store_refuses_concurrent_writer_and_artifact_escapes(
    store: BenchmarkStore, tmp_path: Path
) -> None:
    with store.locked(), pytest.raises(RuntimeError, match="already in use"), store.locked():
        pass
    for path in ("../../../../outside.json", str(tmp_path / "outside.json")):
        with pytest.raises(ValueError, match=r"results|escapes"):
            store.path(path)
    (store.folder / "cases").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="results"):
        store.write("cases/test.json", "{}")


def test_orphan_case_does_not_replace_checkpointed_unit(
    store: BenchmarkStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = store.save
    monkeypatch.setattr(store, "save", Mock(side_effect=OSError("interrupted checkpoint")))
    with pytest.raises(OSError, match="interrupted checkpoint"):
        store.save_unit("abc", {"unit": "abc"}, 1.0)
    orphan = next((store.folder / "cases").glob("*.json"))
    orphan_bytes = orphan.read_bytes()
    monkeypatch.setattr(store, "save", original)
    resumed = BenchmarkStore(store.folder, store.settings)
    resumed.initialize(IDENTITY, resume=True)
    assert resumed.load_unit("abc") is None
    resumed.save_unit("abc", {"unit": "abc"}, 2.0)
    assert resumed.load_unit("abc") == {"unit": "abc"}
    assert orphan.read_bytes() == orphan_bytes
    with pytest.raises(ValueError, match="Cannot replace"):
        resumed.save_unit("abc", {"unit": "abc"}, 3.0)


def test_provisional_outputs_recover_without_clobbering_completed(
    store: BenchmarkStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    write = store.write

    def fail_markdown(name: str, text: str, *, replace: bool = False) -> Any:
        if name == "report.md":
            raise OSError("report interrupted")
        return write(name, text, replace=replace)

    monkeypatch.setattr(store, "write", fail_markdown)
    with pytest.raises(OSError, match="report interrupted"):
        store.finish('{"provisional":true}', "report")
    resumed = BenchmarkStore(store.folder, store.settings)
    resumed.initialize(IDENTITY, resume=True)
    first = resumed.finish('{"final":true}', "complete report")
    assert first[0].read_text() == '{"final":true}'
    assert resumed.finish("different", "different") == first
    assert first[0].read_text() == '{"final":true}'
    with pytest.raises(ValueError, match="Cannot replace"):
        resumed.save_unit("new", {"unit": "new"}, 1.0)
    first[1].write_text("corrupt")
    with pytest.raises(ValueError, match="checksum"):
        resumed.finish("different", "different")


@pytest.mark.parametrize(
    "identity",
    [
        {"runtime_models": {"m": {"adapter": "ollama", "digest": None}}, "selected": []},
        {
            "runtime_models": {},
            "selected": [{"entry": "hash", "input": {"sha256": None, "error": "OSError"}}],
        },
    ],
)
def test_unknown_weights_or_unverified_input_refuse_resume(
    tmp_path: Path, identity: dict[str, Any]
) -> None:
    settings = Settings(data_dir=tmp_path)
    folder = tmp_path / "results" / "run"
    folder.mkdir(parents=True)
    store = BenchmarkStore(folder, settings)
    store.initialize(identity, resume=False)
    with pytest.raises(ValueError, match="Resume requires"):
        store.initialize(identity, resume=True)


def test_case_payload_and_envelope_validation(store: BenchmarkStore) -> None:
    store.save_unit("abc", {"unit": "wrong"}, 0)
    with pytest.raises(ValueError, match="Invalid benchmark case"):
        store.load_unit("abc")
    with pytest.raises(FileExistsError):
        store.write("manifest.json", "cannot replace")
    (store.folder / "manifest.json").write_text(json.dumps({"payload": []}))
    with pytest.raises(ValueError, match="integrity envelope"):
        store.initialize(IDENTITY, resume=True)


@respx.mock
def test_runtime_digest_is_matched_to_configured_local_model() -> None:
    settings = Settings()
    model = load_model_config("medgemma1.5-q4", REPO_ROOT / "configs" / "models")
    respx.get(f"{settings.ollama_url}/api/tags").mock(
        return_value=httpx.Response(
            200,
            json={
                "models": [
                    {"name": "other", "digest": "wrong"},
                    None,
                    {"name": model.tag, "digest": "known"},
                ],
            },
        )
    )
    assert runtime_identity(model, settings)["digest"] == "known"
    service = load_model_config("ct-clip", REPO_ROOT / "configs" / "models")
    respx.get(f"{settings.service_urls['ct_clip']}/health").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "ok",
                "model_hash": "servicehash",
                "timestamp": "ignored",
            },
        )
    )
    assert runtime_identity(service, settings) == {
        "adapter": "http_service",
        "endpoint": settings.service_urls["ct_clip"],
        "digest": "servicehash",
    }
    assert (
        runtime_identity(
            service.model_copy(update={"base_url": "https://remote.example"}), settings
        )["digest"]
        is None
    )
    assert (
        runtime_identity(
            service.model_copy(update={"base_url": "http://localhost:8011"}), settings
        )["digest"]
        == "servicehash"
    )


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {"models": None},
        {"models": [{"name": "medgemma1.5:4b-it-q4_K_M", "digest": None}]},
    ],
)
@respx.mock
def test_unknown_runtime_identity_is_explicit(body: object) -> None:
    settings = Settings()
    model = load_model_config("medgemma1.5-q4", settings.configs_dir / "models")
    respx.get(f"{settings.ollama_url}/api/tags").mock(return_value=httpx.Response(200, json=body))
    assert runtime_identity(model, settings)["digest"] is None
