# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
import json
from dataclasses import dataclass, field
from typing import Any, ClassVar

import httpx
import pytest
import respx

from thoraxbench.adapters import (
    HeuristicModel,
    HttpServiceModel,
    ModelUnavailableError,
    OllamaModel,
    ThoraxModel,
    default_view_resolver,
    list_model_configs,
    load_model,
    load_model_config,
)
from thoraxbench.config import Settings
from thoraxbench.schemas import AnalysisRequest, PreparedInput

OLLAMA = "http://localhost:11434"
REQ = AnalysisRequest(labels=["emphysema", "pulmonary_nodule"])
GOOD = {
    "findings": [{"label": "emphysema", "present": True, "confidence": 0.9}],
    "abstain": False,
}


class FakeView:
    def build(self, study: Any, request: AnalysisRequest) -> PreparedInput:
        return PreparedInput(
            view_id="fake",
            view_version="1",
            images=[b"png"],
            image_captions=["lung"],
            tensor_path="/tmp/t.npy",
        )


def _settings() -> Settings:
    return Settings(ollama_url=OLLAMA)


def _resolver(view_id: str, params: dict[str, Any]) -> FakeView:
    return FakeView()


def _chat(content: str) -> dict[str, Any]:
    return {
        "message": {"content": content},
        "eval_count": 10,
        "prompt_eval_count": 300,
        "total_duration": 2e9,
        "load_duration": 1e8,
        "eval_duration": 1e9,
        "done_reason": "stop",
    }


def test_all_model_configs_load() -> None:
    configs = list_model_configs(Settings().configs_dir / "models")
    assert len(configs) == 15
    assert {c.adapter for c in configs} == {"ollama", "http_service", "heuristic"}
    with pytest.raises(ModelUnavailableError):
        load_model_config("nope", Settings().configs_dir / "models")


def test_config_id_mismatch(tmp_path: Any) -> None:
    (tmp_path / "a.yaml").write_text("id: b\nadapter: heuristic\nfamily: x\nview: v\n")
    with pytest.raises(ModelUnavailableError, match="does not match"):
        load_model_config("a", tmp_path)


@respx.mock
def test_ollama_infer_and_runtime() -> None:
    respx.get(f"{OLLAMA}/api/tags").mock(
        return_value=httpx.Response(
            200, json={"models": [{"name": "medgemma1.5:4b-it-q4_K_M", "digest": "abc", "size": 3}]}
        )
    )
    respx.post(f"{OLLAMA}/api/show").mock(
        return_value=httpx.Response(
            200, json={"details": {"family": "gemma3"}, "capabilities": ["vision"]}
        )
    )
    respx.get(f"{OLLAMA}/api/ps").mock(
        return_value=httpx.Response(
            200, json={"models": [{"name": "medgemma1.5:4b-it-q4_K_M", "size": 5, "size_vram": 4}]}
        )
    )
    chat = respx.post(f"{OLLAMA}/api/chat").mock(
        return_value=httpx.Response(200, json=_chat(json.dumps(GOOD)))
    )
    model = load_model("medgemma1.5-q4", _settings(), view_resolver=_resolver)
    assert isinstance(model, OllamaModel)
    assert isinstance(model, ThoraxModel)
    assert model.available()
    assert model.capabilities().multi_image
    assert model.describe()["digest"] == "abc"
    assert model.vram() == {"size": 5, "size_vram": 4}
    raw = model.infer(model.prepare(object(), REQ), REQ)
    assert raw.tokens_generated == 10
    assert raw.meta["prompt_id"] == "P3"
    payload = json.loads(chat.calls.last.request.content)
    assert payload["options"]["temperature"] == 0
    assert payload["options"]["num_predict"] == 4096
    assert payload["messages"][1]["images"]
    assert model.parse(raw).positive_labels() == {"emphysema"}


@respx.mock
def test_ollama_two_pass_and_think() -> None:
    chat = respx.post(f"{OLLAMA}/api/chat").mock(
        side_effect=[
            httpx.Response(200, json=_chat('{"observations": []}')),
            httpx.Response(200, json=_chat(json.dumps(GOOD))),
        ]
    )
    model = load_model("qwen3.5-4b", _settings(), prompt_id="P4", view_resolver=_resolver)
    raw = model.infer(PreparedInput(view_id="v", view_version="1"), AnalysisRequest())
    assert raw.meta["calls"] == 2
    assert raw.tokens_generated == 20
    assert json.loads(chat.calls[0].request.content)["think"] is False
    assert "images" not in json.loads(chat.calls[0].request.content)["messages"][1]


@respx.mock
@pytest.mark.parametrize(("prompt", "truncated_pass"), [("P3", 1), ("P4", 1), ("P4", 2)])
def test_ollama_token_limit_abstains_and_preserves_output(prompt: str, truncated_pass: int) -> None:
    text = json.dumps(GOOD)
    truncated = _chat(text) | {"done_reason": "length", "eval_count": 4096}
    responses = [httpx.Response(200, json=truncated)]
    if truncated_pass == 2:
        responses.insert(0, httpx.Response(200, json=_chat('{"observations": []}')))
    chat = respx.post(f"{OLLAMA}/api/chat").mock(side_effect=responses)
    model = load_model("medgemma1.5-q4", _settings(), prompt_id=prompt)
    raw = model.infer(PreparedInput(view_id="v", view_version="1"), REQ)
    assert raw.text == text
    assert raw.error == "generation token limit reached"
    assert raw.meta["done_reason"] == "length"
    assert raw.tokens_generated == 4096 + (10 if truncated_pass == 2 else 0)
    assert chat.call_count == truncated_pass
    assert model.parse(raw).abstain
    assert not model.parse(raw).findings


@respx.mock
def test_ollama_config_can_override_generation_limit() -> None:
    chat = respx.post(f"{OLLAMA}/api/chat").mock(
        return_value=httpx.Response(200, json=_chat(json.dumps(GOOD)))
    )
    original = load_model("medgemma1.5-q4", _settings())
    assert isinstance(original, OllamaModel)
    config = original.config.model_copy(update={"options": {"ollama": {"num_predict": 128}}})
    model = OllamaModel(config, original.prompt, OLLAMA, client=original.client)
    model.infer(PreparedInput(view_id="v", view_version="1"), REQ)
    assert json.loads(chat.calls.last.request.content)["options"]["num_predict"] == 128


@respx.mock
def test_ollama_errors() -> None:
    respx.get(f"{OLLAMA}/api/tags").mock(side_effect=httpx.ConnectError("down"))
    respx.get(f"{OLLAMA}/api/ps").mock(side_effect=httpx.ConnectError("down"))
    route = respx.post(f"{OLLAMA}/api/chat")
    model = load_model("moondream", _settings(), view_resolver=lambda v, p: None)
    assert not model.available()
    assert model.describe() == {}
    assert model.vram() is None
    with pytest.raises(ModelUnavailableError):
        model.prepare(object(), REQ)
    prep = PreparedInput(view_id="v", view_version="1")
    for response, needle in [
        (httpx.TimeoutException("slow"), "timeout"),
        (httpx.ConnectError("x"), "http error"),
        (httpx.Response(500, text="oops"), "HTTP 500"),
        (httpx.Response(200, text="not json"), "non-JSON"),
    ]:
        route.mock(side_effect=[response])
        raw = model.infer(prep, REQ)
        assert raw.error is not None
        assert needle in raw.error
        assert model.parse(raw).abstain


@respx.mock
def test_ollama_vram_not_loaded_and_tag_rules() -> None:
    respx.get(f"{OLLAMA}/api/ps").mock(return_value=httpx.Response(200, json={"models": []}))
    model = load_model("moondream", _settings())
    assert isinstance(model, OllamaModel)
    assert model._matches("moondream:latest")
    assert model.vram() is None
    cfg = model.config.model_copy(update={"tag": None})
    with pytest.raises(ValueError, match="needs a 'tag'"):
        OllamaModel(cfg, model.prompt, OLLAMA)


@respx.mock
def test_http_service() -> None:
    base = Settings().service_urls["ct_clip"]
    respx.get(f"{base}/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    infer = respx.post(f"{base}/v1/infer").mock(
        return_value=httpx.Response(200, json={"probabilities": {"Emphysema": 0.7}, "text": ""})
    )
    model = load_model("ct-clip", view_resolver=_resolver)
    assert isinstance(model, HttpServiceModel)
    assert model.available()
    assert model.capabilities().three_d_native
    raw = model.infer(model.prepare(object(), REQ), REQ)
    assert json.loads(infer.calls.last.request.content)["tensor_path"] == "/tmp/t.npy"
    assert model.parse(raw).label_probability("emphysema") == pytest.approx(0.7)
    infer.mock(side_effect=httpx.TimeoutException("slow"))
    assert model.infer(PreparedInput(view_id="v", view_version="1"), REQ).error == "timeout"
    infer.mock(return_value=httpx.Response(500))
    assert "service error" in (
        model.infer(PreparedInput(view_id="v", view_version="1"), REQ).error or ""
    )


@respx.mock
def test_http_service_down() -> None:
    base = Settings().service_urls["m3d_lamed"]
    respx.get(f"{base}/health").mock(side_effect=httpx.ConnectError("down"))
    model = load_model("m3d-lamed-4b", view_resolver=_resolver)
    assert not model.available()


def test_unknown_service(tmp_path: Any) -> None:
    models = tmp_path / "configs" / "models"
    models.mkdir(parents=True)
    (models / "x.yaml").write_text("id: x\nadapter: http_service\nfamily: f\nview: v\n")
    s = Settings(repo_root=tmp_path)
    with pytest.raises(ModelUnavailableError, match="unknown service"):
        load_model("x", s, view_resolver=_resolver)


@dataclass
class Cand:
    diameter_mm: float
    side: str
    z_index: int


@dataclass
class Cues:
    emphysema_laa950_pct: float = 12.0
    effusion_ml_left: float = 0.0
    effusion_ml_right: float = 80.0
    nodule_candidates: list[Any] = field(default_factory=lambda: [Cand(8.0, "right", 5)])
    calcium_voxels: int = 0
    pneumothorax_air_ml: float = 0.0
    metal_voxels: int = 0


class PlainCues:
    emphysema_laa950_pct = 1.0
    effusion_ml_left = 30.0
    effusion_ml_right = 30.0
    nodule_candidates: ClassVar[list[Any]] = [Cand(40.0, "left", 2), Cand(35.0, "right", 9)]
    calcium_voxels = 50


def test_heuristic_model() -> None:
    model = load_model("heuristic-hu")
    assert isinstance(model, HeuristicModel)
    assert model.available()
    assert model.capabilities().probabilities
    rep = model.parse(model.infer(model.prepare(Cues(), AnalysisRequest()), AnalysisRequest()))
    pos = rep.positive_labels()
    assert {"emphysema", "pleural_effusion", "pulmonary_nodule"} <= pos
    assert "pulmonary_mass" not in pos
    nod = next(f for f in rep.findings if f.label == "pulmonary_nodule")
    assert nod.size_mm == 8.0
    assert nod.evidence_images == [5]

    class Study:
        cues = PlainCues()

    rep2 = model.parse(model.infer(model.prepare(Study(), REQ), REQ))
    assert {f.label for f in rep2.findings} == {"emphysema", "pulmonary_nodule"}
    rep3 = model.parse(
        model.infer(model.prepare(PlainCues(), AnalysisRequest()), AnalysisRequest())
    )
    mass = next(f for f in rep3.findings if f.label == "pulmonary_mass")
    assert mass.laterality.value == "bilateral"
    eff = next(f for f in rep3.findings if f.label == "pleural_effusion")
    assert eff.laterality.value == "bilateral"
    with pytest.raises(TypeError):
        model.prepare(object(), REQ)


def test_default_view_resolver() -> None:
    # thoraxbench.views may or may not exist yet; either way the resolver never raises
    result = default_view_resolver("does-not-exist", {})
    assert result is None or hasattr(result, "build")


def test_default_view_resolver_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    mod = types.ModuleType("thoraxbench.views")
    monkeypatch.setitem(sys.modules, "thoraxbench.views", mod)
    assert default_view_resolver("x", {}) is None  # no get_view

    def get_view(view_id: str, **params: Any) -> Any:
        if view_id == "missing":
            raise KeyError(view_id)
        return FakeView() if view_id == "ok" else object()

    mod.get_view = get_view  # type: ignore[attr-defined]
    assert isinstance(default_view_resolver("ok", {}), FakeView)
    assert default_view_resolver("missing", {}) is None
    assert default_view_resolver("bad", {}) is None
    monkeypatch.setitem(sys.modules, "thoraxbench.views", None)
    assert default_view_resolver("ok", {}) is None
