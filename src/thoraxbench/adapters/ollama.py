# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Ollama adapter (Vision §17): sends only local rendered images and prompts to localhost."""

from __future__ import annotations

import base64
import hashlib
import math
import time
from typing import Any

import httpx

from thoraxbench.adapters.base import ModelConfig, ViewBackedModel, ViewBuilderLike
from thoraxbench.ontology import Ontology, load_ontology
from thoraxbench.parsing import parse_findings
from thoraxbench.prompts import PromptTemplate
from thoraxbench.schemas import AnalysisRequest, FindingsReport, PreparedInput, RawOutput

NS_PER_S = 1e9
DEFAULT_NUM_CTX = 16384
DEFAULT_NUM_PREDICT = 4096


def _provider_error(data: dict[str, Any]) -> str | None:
    """Validate provider fields before runtime accounting or content extraction."""
    if "error" in data:
        return f"ollama provider error: {str(data['error'])[:300]}"
    message = data.get("message", {})
    if not isinstance(message, dict):
        return "ollama returned a non-object message"
    if "content" in message and not isinstance(message["content"], str):
        return "ollama returned non-string message content"
    for key in ("eval_count", "prompt_eval_count"):
        if key in data and (type(data[key]) is not int or data[key] < 0):
            return f"ollama returned invalid {key}: {str(data[key])[:100]}"
    for key in ("total_duration", "load_duration", "eval_duration", "prompt_eval_duration"):
        if key not in data:
            continue
        value = data[key]
        try:
            valid = (
                not isinstance(value, bool)
                and isinstance(value, int | float)
                and math.isfinite(value)
                and value >= 0
            )
        except OverflowError:
            valid = False
        if not valid:
            return f"ollama returned invalid {key}: {str(value)[:100]}"
    return None


def _total(calls: list[dict[str, Any]], field: str) -> int | float | None:
    """Sum only validated, completely reported values; missing is not zero."""
    if not calls or any(field not in call for call in calls):
        return None
    total: int | float = 0
    for call in calls:
        value = call[field]
        if not isinstance(value, int | float):
            return None
        total += value
    return total


class OllamaModel(ViewBackedModel):
    """A vision-language model served by a local Ollama server.

    Decoding is deterministic: ``temperature=0`` and ``seed=0`` unless the model config
    overrides them. The output is constrained with the findings JSON schema
    (Ollama structured outputs), with a 4096-token generation limit by default.
    """

    def __init__(
        self,
        config: ModelConfig,
        prompt: PromptTemplate,
        base_url: str,
        *,
        view: ViewBuilderLike | None = None,
        client: httpx.Client | None = None,
        ontology: Ontology | None = None,
    ) -> None:
        super().__init__(config, view)
        if not config.tag:
            msg = f"ollama model '{config.id}' needs a 'tag'"
            raise ValueError(msg)
        self.tag: str = config.tag
        self.prompt = prompt
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=config.timeout_s)
        self.ontology = ontology or load_ontology()

    # -- runtime information -------------------------------------------------------------
    def _tags(self) -> list[dict[str, Any]]:
        resp = self.client.get(f"{self.base_url}/api/tags", timeout=10.0)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            raise ValueError("ollama returned malformed model inventory")
        return [
            item
            for item in payload["models"]
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]

    def _matches(self, name: str) -> bool:
        wanted = self.tag if ":" in self.tag else f"{self.tag}:latest"
        return name == wanted

    def available(self) -> bool:
        """Return True if the Ollama server is reachable and has the model pulled."""
        try:
            return any(self._matches(str(m.get("name", ""))) for m in self._tags())
        except httpx.HTTPError, ValueError:
            return False

    def describe(self) -> dict[str, Any]:
        """Model digest, size and details for provenance (empty dict if unreachable)."""
        try:
            entry = next((m for m in self._tags() if self._matches(str(m.get("name", "")))), None)
            show = self.client.post(f"{self.base_url}/api/show", json={"model": self.tag})
            show.raise_for_status()
            details = show.json()
            if not isinstance(details, dict):
                return {}
        except httpx.HTTPError, ValueError:
            return {}
        return {
            "tag": self.tag,
            "digest": entry["digest"] if entry and isinstance(entry.get("digest"), str) else None,
            "size_bytes": entry["size"]
            if entry and type(entry.get("size")) is int and entry["size"] >= 0
            else None,
            "details": details["details"] if isinstance(details.get("details"), dict) else {},
            "capabilities": [
                item for item in details.get("capabilities", []) if isinstance(item, str)
            ]
            if isinstance(details.get("capabilities"), list)
            else [],
        }

    def vram(self) -> dict[str, int] | None:
        """``size`` and ``size_vram`` of the loaded model from ``/api/ps`` (None if absent)."""
        try:
            resp = self.client.get(f"{self.base_url}/api/ps", timeout=10.0)
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
                return None
            running = payload["models"]
        except httpx.HTTPError, ValueError:
            return None
        for m in running:
            if not isinstance(m, dict):
                continue
            name = m.get("name") or m.get("model")
            if isinstance(name, str) and self._matches(name):
                if any(type(m.get(key)) is not int or m[key] < 0 for key in ("size", "size_vram")):
                    return None
                return {"size": m["size"], "size_vram": m["size_vram"]}
        return None

    # -- inference -----------------------------------------------------------------------
    def _labels(self, request: AnalysisRequest) -> list[str]:
        return request.labels or self.ontology.ids(core_only=True)

    def _chat(
        self,
        system: str,
        user: str,
        images: list[bytes],
        schema: dict[str, Any] | str,
        *,
        request_log: list[dict[str, Any]] | None = None,
        response_log: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any] | None, str | None, float]:
        message: dict[str, Any] = {"role": "user", "content": user}
        if images:
            message["images"] = [base64.b64encode(img).decode("ascii") for img in images]
        options: dict[str, Any] = {
            "temperature": 0,
            "seed": 0,
            "num_ctx": DEFAULT_NUM_CTX,
            "num_predict": DEFAULT_NUM_PREDICT,
        }
        options.update(self.config.options.get("ollama", {}))
        payload: dict[str, Any] = {
            "model": self.tag,
            "messages": [{"role": "system", "content": system}, message],
            "stream": False,
            "format": schema,
            "options": options,
            "keep_alive": self.config.options.get("keep_alive", "10m"),
        }
        if "think" in self.config.options:
            payload["think"] = self.config.options["think"]
        # Reviewed per model config: an empty think block makes thinking models answer.
        prefill = self.config.options.get("assistant_prefill")
        extra = (
            [{"role": "assistant", "content": prefill}]
            if isinstance(prefill, str) and prefill
            else []
        )
        payload["messages"].extend(extra)
        if request_log is not None:
            recorded_messages: list[dict[str, Any]] = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
                *extra,
            ]
            if images:
                recorded_messages[1].update(
                    {
                        "image_sha256": [hashlib.sha256(image).hexdigest() for image in images],
                        "image_bytes_omitted": True,
                    }
                )
            request_log.append(payload | {"messages": recorded_messages})
        start = time.perf_counter()
        try:
            resp = self.client.post(
                f"{self.base_url}/api/chat", json=payload, timeout=self.config.timeout_s
            )
        except httpx.HTTPError as exc:
            elapsed = time.perf_counter() - start
            error = (
                f"timeout after {self.config.timeout_s:.0f} s"
                if isinstance(exc, httpx.TimeoutException)
                else f"http error: {exc}"
            )
            if response_log is not None:
                response_log.append(
                    {"error": error, "error_type": type(exc).__name__, "latency_s": elapsed}
                )
            return None, error, elapsed
        elapsed = time.perf_counter() - start
        diagnostic: dict[str, Any] = {"http_status": resp.status_code, "latency_s": elapsed}
        if response_log is not None:
            response_log.append(diagnostic)
        if resp.status_code != httpx.codes.OK:
            error = f"ollama HTTP {resp.status_code}: {resp.text[:300]}"
            diagnostic.update({"body_text": resp.text[:300], "error": error})
            return None, error, elapsed
        try:
            data = resp.json()
        except ValueError:
            error = "ollama returned non-JSON response"
            diagnostic.update({"body_text": resp.text[:300], "error": error})
            return None, error, elapsed
        diagnostic["body"] = data
        if not isinstance(data, dict):
            diagnostic["error"] = "ollama returned a non-object JSON response"
            return None, diagnostic["error"], elapsed
        provider_error = _provider_error(data)
        if provider_error:
            diagnostic.update({"error": provider_error, "body_text": resp.text[:300]})
            return None, provider_error, elapsed
        return data, None, elapsed

    def infer(self, prepared: PreparedInput, request: AnalysisRequest) -> RawOutput:
        """Run one (or, for two-pass prompts, two) chat calls against Ollama."""
        labels = self._labels(request)
        n = len(prepared.images)
        rendered = self.prompt.render(labels, n, prepared.image_captions, prepared.context)
        schema: dict[str, Any] | str = (
            "json" if self.prompt.two_pass else self.prompt.schema(labels, n_images=n)
        )
        requests: list[dict[str, Any]] = []
        responses: list[dict[str, Any]] = []
        data, error, latency = self._chat(
            rendered.system,
            rendered.user,
            prepared.images,
            schema,
            request_log=requests,
            response_log=responses,
        )
        calls = [data] if data else []
        if (
            data is not None
            and error is None
            and data.get("done_reason") != "length"
            and self.prompt.two_pass
        ):
            first = str(data.get("message", {}).get("content", ""))
            second = self.prompt.render_second_pass(
                first, labels, n, captions=prepared.image_captions, context=prepared.context
            )
            data, error, latency2 = self._chat(
                second.system,
                second.user,
                [],
                self.prompt.schema(labels, n_images=n),
                request_log=requests,
                response_log=responses,
            )
            latency += latency2
            if data:
                calls.append(data)
        meta: dict[str, Any] = {
            "model": self.tag,
            "prompt_id": self.prompt.id,
            "prompt_sha256": self.prompt.sha256,
            "calls": len(calls),
            "requests": requests,
            "responses": responses,
        }
        for field in ("load_duration", "eval_duration", "total_duration"):
            value = _total(calls, field)
            meta[f"{field}_s"] = value / NS_PER_S if value is not None else None
        meta["done_reason"] = data.get("done_reason") if data is not None else None
        generated = _total(calls, "eval_count")
        prompt_tokens = _total(calls, "prompt_eval_count")
        if error is not None or data is None:
            return RawOutput(
                error=error or "no response",
                latency_s=latency,
                meta=meta,
                tokens_generated=int(generated) if generated is not None else None,
                prompt_tokens=int(prompt_tokens) if prompt_tokens is not None else None,
            )
        return RawOutput(
            text=str(data.get("message", {}).get("content", "")),
            error="generation token limit reached"
            if any(c.get("done_reason") == "length" for c in calls)
            else None,
            tokens_generated=int(generated) if generated is not None else None,
            prompt_tokens=int(prompt_tokens) if prompt_tokens is not None else None,
            latency_s=latency,
            meta=meta,
        )

    def parse(self, raw: RawOutput) -> FindingsReport:
        """Parse the model's JSON into the common schema."""
        return parse_findings(raw, self.ontology)
