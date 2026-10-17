# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Build a :class:`ThoraxModel` from ``configs/models/<id>.yaml``."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

import httpx

from thoraxbench.adapters.base import (
    ModelUnavailableError,
    ThoraxModel,
    ViewResolver,
    default_view_resolver,
    load_model_config,
)
from thoraxbench.adapters.heuristic import HeuristicModel
from thoraxbench.adapters.http_service import HttpServiceModel
from thoraxbench.adapters.monai_detector import MonaiDetectorModel
from thoraxbench.adapters.ollama import OllamaModel
from thoraxbench.config import Settings, get_settings
from thoraxbench.prompts import load_prompt


def require_local_endpoint(base_url: str) -> None:
    """Reject inference URLs outside HTTP(S) loopback before constructing a client."""
    message = "inference requires an HTTP(S) loopback endpoint without credentials"
    try:
        parsed = urlsplit(base_url)
        host = parsed.hostname
        port = parsed.port
        if (
            any(char.isspace() for char in base_url)
            or parsed.scheme not in {"http", "https"}
            or host is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or port == 0
        ):
            raise ValueError(message)
        if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
            raise ValueError(message)
    except ValueError as exc:
        raise ModelUnavailableError(message) from exc


def _local_client(base_url: str, client: httpx.Client | None, timeout_s: float) -> httpx.Client:
    require_local_endpoint(base_url)
    if client is not None:
        if client.follow_redirects:
            raise ModelUnavailableError("inference clients must not follow redirects")
        return client
    # Environment proxies must never forward local medical input to another host.
    return httpx.Client(timeout=timeout_s, follow_redirects=False, trust_env=False)


def load_model(
    model_id: str,
    settings: Settings | None = None,
    *,
    prompt_id: str | None = None,
    client: httpx.Client | None = None,
    view_resolver: ViewResolver | None = None,
) -> ThoraxModel:
    """Instantiate the adapter configured for *model_id*.

    Args:
        model_id: file stem in ``configs/models``.
        settings: paths and endpoints (defaults to the environment).
        prompt_id: override the config's prompt (e.g. for experiment E004).
        client: shared ``httpx.Client`` (tests inject a mocked one).
        view_resolver: maps (view id, params) to a view builder; defaults to
            ``thoraxbench.views.get_view`` when that package exists.

    Raises:
        ModelUnavailableError: for unknown ids or incomplete configs.
    """
    s = settings or get_settings()
    config = load_model_config(model_id, s.configs_dir / "models")
    if config.adapter == "heuristic":
        return HeuristicModel(config)
    if config.adapter == "monai_detector":
        return MonaiDetectorModel(config, s)
    view = (view_resolver or default_view_resolver)(config.view, dict(config.view_params))
    if config.adapter == "ollama":
        chosen = prompt_id or config.prompt or "P3"
        prompt = load_prompt(chosen, s.configs_dir / "prompts")
        return OllamaModel(
            config,
            prompt,
            s.ollama_url,
            view=view,
            client=_local_client(s.ollama_url, client, config.timeout_s),
        )
    service = config.service or ""
    base_url = config.base_url or s.service_urls.get(service)
    if not base_url:
        msg = f"model '{model_id}': unknown service '{service}' and no base_url"
        raise ModelUnavailableError(msg)
    return HttpServiceModel(
        config, base_url, view=view, client=_local_client(base_url, client, config.timeout_s)
    )
