# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Inference endpoints cannot send medical inputs beyond the local machine."""

import httpx
import pytest

from thoraxbench.adapters import ModelUnavailableError, OllamaModel, load_model
from thoraxbench.adapters.factory import require_local_endpoint
from thoraxbench.config import Settings


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434",
        "https://LOCALHOST:443",
        "http://127.0.0.1:8011",
        "http://127.23.45.67:8011/prefix",
        "http://[::1]:11434",
    ],
)
def test_local_endpoints_are_allowed(url: str) -> None:
    require_local_endpoint(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://192.168.1.2:11434",
        "http://0.0.0.0:11434",
        "http://[::]:11434",
        "http://localhost.example.com",
        "http://localhost@remote.example",
        "http://user:secret@localhost",
        "http://@localhost",
        "ftp://localhost",
        "localhost:11434",
        "http://localhost:invalid",
        "http://localhost:65536",
        "http://localhost:0",
        "http://[::1",
        "http://localhost\n.remote.example",
        "http://localhost/?target=remote",
        "http://localhost/#remote",
        "",
    ],
)
def test_remote_and_invalid_endpoints_are_rejected(url: str) -> None:
    with pytest.raises(ModelUnavailableError, match="loopback"):
        require_local_endpoint(url)


def test_factory_checks_ollama_endpoint() -> None:
    with pytest.raises(ModelUnavailableError, match="loopback"):
        load_model("medgemma1.5-q4", Settings(ollama_url="https://example.com"))


def test_factory_checks_http_service_endpoint() -> None:
    settings = Settings(service_urls={"ct_clip": "http://192.168.1.2:8011"})
    with pytest.raises(ModelUnavailableError, match="loopback"):
        load_model("ct-clip", settings)


def test_injected_client_must_not_follow_redirects() -> None:
    with (
        httpx.Client(follow_redirects=True) as client,
        pytest.raises(ModelUnavailableError, match="redirects"),
    ):
        load_model("medgemma1.5-q4", client=client)


def test_factory_keeps_injected_nonredirecting_client() -> None:
    with httpx.Client() as client:
        model = load_model("medgemma1.5-q4", client=client)
        assert isinstance(model, OllamaModel)
        assert model.client is client


def test_default_client_ignores_proxy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://remote.example:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://remote.example:3128")
    model = load_model("medgemma1.5-q4")
    assert isinstance(model, OllamaModel)
    client = model.client
    try:
        assert not client.trust_env
        assert not client.follow_redirects
    finally:
        client.close()
