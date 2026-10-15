# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Ollama adapter (Vision §17): sends only local rendered images and prompts to localhost."""

from __future__ import annotations

import base64
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
        models: list[dict[str, Any]] = resp.json().get("models", [])
        return models

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
        except httpx.HTTPError, ValueError:
            return {}
        return {
            "tag": self.tag,
            "digest": entry.get("digest") if entry else None,
            "size_bytes": entry.get("size") if entry else None,
            "details": details.get("details", {}),
            "capabilities": details.get("capabilities", []),
        }

    def vram(self) -> dict[str, int] | None:
        """``size`` and ``size_vram`` of the loaded model from ``/api/ps`` (None if absent)."""
        try:
            resp = self.client.get(f"{self.base_url}/api/ps", timeout=10.0)
            resp.raise_for_status()
            running = resp.json().get("models", [])
        except httpx.HTTPError, ValueError:
            return None
        for m in running:
            if self._matches(str(m.get("name", m.get("model", "")))):
                return {"size": int(m.get("size", 0)), "size_vram": int(m.get("size_vram", 0))}
        return None

    # -- inference -----------------------------------------------------------------------
    def _labels(self, request: AnalysisRequest) -> list[str]:
        return request.labels or self.ontology.ids(core_only=True)

    def _chat(
        self, system: str, user: str, images: list[bytes], schema: dict[str, Any] | str
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
        start = time.perf_counter()
        try:
            resp = self.client.post(
                f"{self.base_url}/api/chat", json=payload, timeout=self.config.timeout_s
            )
        except httpx.TimeoutException:
            return None, f"timeout after {self.config.timeout_s:.0f} s", time.perf_counter() - start
        except httpx.HTTPError as exc:
            return None, f"http error: {exc}", time.perf_counter() - start
        elapsed = time.perf_counter() - start
        if resp.status_code != httpx.codes.OK:
            return None, f"ollama HTTP {resp.status_code}: {resp.text[:300]}", elapsed
        try:
            return resp.json(), None, elapsed
        except ValueError:
            return None, "ollama returned non-JSON response", elapsed

    def infer(self, prepared: PreparedInput, request: AnalysisRequest) -> RawOutput:
        """Run one (or, for two-pass prompts, two) chat calls against Ollama."""
        labels = self._labels(request)
        n = len(prepared.images)
        rendered = self.prompt.render(labels, n, prepared.image_captions, prepared.context)
        schema: dict[str, Any] | str = (
            "json" if self.prompt.two_pass else self.prompt.schema(labels)
        )
        data, error, latency = self._chat(rendered.system, rendered.user, prepared.images, schema)
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
                second.system, second.user, [], self.prompt.schema(labels)
            )
            latency += latency2
            if data:
                calls.append(data)
        meta: dict[str, Any] = {
            "model": self.tag,
            "prompt_id": self.prompt.id,
            "prompt_sha256": self.prompt.sha256,
            "calls": len(calls),
        }
        if error is not None or data is None:
            return RawOutput(error=error or "no response", latency_s=latency, meta=meta)
        meta.update(
            {
                "load_duration_s": sum(c.get("load_duration", 0) for c in calls) / NS_PER_S,
                "eval_duration_s": sum(c.get("eval_duration", 0) for c in calls) / NS_PER_S,
                "total_duration_s": sum(c.get("total_duration", 0) for c in calls) / NS_PER_S,
                "done_reason": data.get("done_reason"),
            }
        )
        return RawOutput(
            text=str(data.get("message", {}).get("content", "")),
            error="generation token limit reached"
            if any(c.get("done_reason") == "length" for c in calls)
            else None,
            tokens_generated=sum(int(c.get("eval_count", 0)) for c in calls),
            prompt_tokens=sum(int(c.get("prompt_eval_count", 0)) for c in calls),
            latency_s=latency,
            meta=meta,
        )

    def parse(self, raw: RawOutput) -> FindingsReport:
        """Parse the model's JSON into the common schema."""
        return parse_findings(raw, self.ontology)
