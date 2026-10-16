# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Shared browser fixtures: loopback workbench servers over synthetic data only."""

from __future__ import annotations

import contextlib
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from playwright.sync_api import Page, sync_playwright

from thoraxbench.config import Settings


@contextlib.contextmanager
def serve(settings: Settings) -> Iterator[str]:
    """Serve the workbench for *settings* on a free loopback port and yield its URL."""
    from thoraxbench.api.app import create_app

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    address = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(base_url=address, timeout=1.0) as client:
            for _ in range(100):
                if server.started:
                    assert client.get("/").status_code == 200
                    break
                if not thread.is_alive():
                    pytest.fail("local workbench server stopped during startup")
                time.sleep(0.05)
            else:
                pytest.fail("local workbench server did not start")
        yield address
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()


@contextlib.contextmanager
def browser_page(address: str) -> Iterator[Page]:
    """Open Chromium with German/dark browser hints; the UI must still default to EN/light."""
    with sync_playwright() as playwright:
        default = Path(playwright.chromium.executable_path)
        candidates = sorted(
            (Path.home() / ".cache" / "ms-playwright").glob("chromium-*/chrome-linux*/chrome")
        )
        executable = default if default.exists() else candidates[-1] if candidates else default
        browser = playwright.chromium.launch(executable_path=str(executable))
        context = browser.new_context(locale="de-DE", color_scheme="dark", accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(15_000)
        page.clock.install()
        page.goto(address)
        try:
            yield page
        finally:
            context.close()
            browser.close()


@pytest.fixture(scope="module")
def ui_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    settings = Settings(
        data_dir=tmp_path_factory.mktemp("ui-synthetic"), ollama_url="http://127.0.0.1:1"
    )
    with serve(settings) as address:
        yield address


@pytest.fixture
def ui_page(ui_server: str) -> Iterator[Page]:
    with browser_page(ui_server) as page:
        yield page
