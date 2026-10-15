# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Adapter for 3D/PyTorch models running as separate local HTTP services (Vision §17).

Service contract (implemented by each local service process, e.g. CT-CLIP on :8011):

* ``GET  /health`` → ``{"status": "ok", "model": "...", "weights_sha256": "..."}``
* ``POST /v1/infer`` with JSON
  ``{"tensor_path": str | null, "labels": [...], "request": str, "question": str | null,
  "meta": {...}}`` → ``{"probabilities": {label: p}, "text": str}``. ``probabilities`` is
  set by classifiers (CT-CLIP), ``text`` by generative models (M3D-LaMed, CT-CHAT, RadFM)
  and should contain the findings JSON of Vision §11.

The tensor is written by the view (e.g. ``ct_clip_v1``) to a local file; only its path is
sent, the CT data never leaves the machine.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from thoraxbench.adapters.base import ModelConfig, ViewBackedModel, ViewBuilderLike
from thoraxbench.ontology import Ontology, load_ontology
from thoraxbench.parsing import parse_findings
from thoraxbench.schemas import AnalysisRequest, FindingsReport, PreparedInput, RawOutput


class HttpServiceModel(ViewBackedModel):
    """A model behind the local HTTP service contract described in the module docstring."""

    def __init__(
        self,
        config: ModelConfig,
        base_url: str,
        view: ViewBuilderLike | None = None,
        client: httpx.Client | None = None,
        ontology: Ontology | None = None,
    ) -> None:
        super().__init__(config, view)
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=config.timeout_s)
        self.ontology = ontology or load_ontology()

    def health(self) -> dict[str, Any] | None:
        """Return the ``/health`` document, or ``None`` if the service is unreachable."""
        try:
            resp = self.client.get(f"{self.base_url}/health", timeout=5.0)
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()
        except httpx.HTTPError, ValueError:
            return None
        return body

    def available(self) -> bool:
        """Return True when ``/health`` answers with ``status == "ok"``."""
        health = self.health()
        return bool(health and health.get("status") == "ok")

    def infer(self, prepared: PreparedInput, request: AnalysisRequest) -> RawOutput:
        """POST the prepared tensor path and labels to ``/v1/infer``."""
        payload = {
            "tensor_path": prepared.tensor_path,
            "labels": request.labels or self.ontology.ids(core_only=True),
            "request": request.request,
            "question": request.question,
            "meta": {"view_id": prepared.view_id, "view_version": prepared.view_version},
        }
        start = time.perf_counter()
        try:
            resp = self.client.post(
                f"{self.base_url}/v1/infer", json=payload, timeout=self.config.timeout_s
            )
            resp.raise_for_status()
            body = resp.json()
        except httpx.TimeoutException:
            return RawOutput(error="timeout", latency_s=time.perf_counter() - start)
        except (httpx.HTTPError, ValueError) as exc:
            return RawOutput(error=f"service error: {exc}", latency_s=time.perf_counter() - start)
        probs = body.get("probabilities") or {}
        return RawOutput(
            text=str(body.get("text") or ""),
            probabilities={str(k): float(v) for k, v in probs.items()},
            tokens_generated=body.get("tokens_generated"),
            latency_s=time.perf_counter() - start,
            meta={"service": self.config.service, "base_url": self.base_url},
        )

    def parse(self, raw: RawOutput) -> FindingsReport:
        """Probabilities and/or findings JSON → common schema."""
        return parse_findings(raw, self.ontology)
