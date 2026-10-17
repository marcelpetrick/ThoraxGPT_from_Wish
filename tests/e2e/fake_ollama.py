# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""A scripted loopback stand-in for Ollama whose chat replies wait for the test.

It returns synthetic, clearly labelled responses only; no model runs. Tests release each
held ``/api/chat`` request explicitly, which makes long inference reproducible.
"""

from __future__ import annotations

import contextlib
import json
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

SCRIPTED_CONTENT = json.dumps(
    {
        "study_quality": {"adequate": True, "limitations": []},
        "findings": [],
        "negative_findings": [],
        "abstain": True,
        "uncertainty": "Scripted synthetic test response; no model ran.",
    }
)


class FakeOllama:
    """Hold chat requests until :meth:`release` is called; record disconnects."""

    def __init__(self, tags: list[str]) -> None:
        self.tags = tags
        self.chats = 0
        self.pulls = 0
        self.disconnects = 0
        self._release = threading.Semaphore(0)
        self._lock = threading.Lock()
        self.url = ""

    def release(self, count: int = 1) -> None:
        """Let *count* held chat requests answer."""
        for _ in range(count):
            self._release.release()

    def handler(self) -> type[BaseHTTPRequestHandler]:
        """Build the request handler bound to this fake."""
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _json(self, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                if self.path == "/api/tags":
                    self._json({"models": [{"name": tag} for tag in fake.tags]})
                else:
                    self._json({"models": []})

            def do_POST(self) -> None:
                self.rfile.read(int(self.headers.get("content-length", "0")))
                if self.path not in {"/api/chat", "/api/pull"}:
                    self._json({"digest": "synthetic-test-digest"})
                    return
                with fake._lock:
                    if self.path == "/api/chat":
                        fake.chats += 1
                    else:
                        fake.pulls += 1
                self.connection.settimeout(0.1)
                while not fake._release.acquire(timeout=0.1):
                    try:
                        if self.connection.recv(1, socket.MSG_PEEK) == b"":  # client closed
                            with fake._lock:
                                fake.disconnects += 1
                            return
                    except TimeoutError:
                        continue
                    except OSError:
                        return
                self.connection.settimeout(None)
                if self.path == "/api/pull":
                    self._json({"status": "success"})
                    return
                self._json(
                    {
                        "message": {"content": SCRIPTED_CONTENT},
                        "done_reason": "stop",
                        "eval_count": 1,
                        "prompt_eval_count": 1,
                        "total_duration": 1_000_000,
                    }
                )

            def log_message(self, *_: Any) -> None:
                return

        return Handler


@contextlib.contextmanager
def fake_ollama(tags: list[str]) -> Iterator[FakeOllama]:
    """Serve a :class:`FakeOllama` on a free loopback port."""
    fake = FakeOllama(tags)
    server = ThreadingHTTPServer(("127.0.0.1", 0), fake.handler())
    server.daemon_threads = True
    fake.url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield fake
    finally:
        fake.release(64)
        server.shutdown()
        server.server_close()
