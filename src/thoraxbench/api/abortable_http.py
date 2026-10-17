# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""An httpx transport whose in-flight requests another thread can abort.

A stopped UI job must not keep waiting for a long local generation. This transport tracks
its TCP sockets and shuts them down on :meth:`AbortableTransport.abort`, so a blocked
read returns at once and the local provider sees a closed connection. Whether the provider
then stops generating is its own behaviour; Ollama may still finish in the background.
"""

from __future__ import annotations

import socket
from collections.abc import Iterable, Iterator
from threading import Event, Lock
from typing import Any

import httpcore
import httpx

CANCELLED = "request cancelled by operator"


class _TrackingBackend(httpcore.SyncBackend):
    def __init__(self, owner: AbortableTransport) -> None:
        self._owner = owner

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        self._owner.check()
        stream = super().connect_tcp(host, port, timeout, local_address, socket_options)
        sock = stream.get_extra_info("socket")
        if isinstance(sock, socket.socket):
            self._owner.track(sock)
        return stream


def _mapped(exc: Exception, request: httpx.Request, cancelled: bool) -> httpx.TransportError:
    if cancelled:
        return httpx.ReadError(CANCELLED, request=request)
    if isinstance(exc, httpcore.TimeoutException):
        return httpx.ReadTimeout(str(exc), request=request)
    if isinstance(exc, httpcore.ConnectError):
        return httpx.ConnectError(str(exc), request=request)
    if isinstance(exc, httpcore.ProtocolError):
        return httpx.RemoteProtocolError(str(exc), request=request)
    return httpx.ReadError(str(exc), request=request)


class _Body(httpx.SyncByteStream):
    def __init__(
        self, stream: Iterable[bytes], request: httpx.Request, owner: AbortableTransport
    ) -> None:
        self._stream, self._request, self._owner = stream, request, owner

    def __iter__(self) -> Iterator[bytes]:
        try:
            yield from self._stream
        except (httpcore.NetworkError, httpcore.ProtocolError, httpcore.TimeoutException) as exc:
            raise _mapped(exc, self._request, self._owner.aborted) from exc

    def close(self) -> None:
        close = getattr(self._stream, "close", None)
        if callable(close):
            close()


class AbortableTransport(httpx.BaseTransport):
    """HTTP/1.1 transport without proxies or environment trust; ``abort`` is thread-safe."""

    def __init__(self) -> None:
        self._aborted = Event()
        self._lock = Lock()
        self._sockets: list[socket.socket] = []
        self._pool = httpcore.ConnectionPool(network_backend=_TrackingBackend(self), retries=0)

    @property
    def aborted(self) -> bool:
        """Whether :meth:`abort` was called."""
        return self._aborted.is_set()

    def check(self) -> None:
        """Refuse new connections after an abort."""
        if self._aborted.is_set():
            raise httpcore.ConnectError(CANCELLED)

    def track(self, sock: socket.socket) -> None:
        """Remember a connection socket so :meth:`abort` can shut it down."""
        with self._lock:
            self._sockets.append(sock)
        if self._aborted.is_set():
            self.abort()

    def abort(self) -> None:
        """Interrupt every in-flight request and refuse further ones."""
        self._aborted.set()
        with self._lock:
            sockets = list(self._sockets)
        for sock in sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                continue

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Send *request*; an abort turns into ``httpx.ReadError`` (an ``HTTPError``)."""
        if self._aborted.is_set():
            raise httpx.ReadError(CANCELLED, request=request)
        if not isinstance(request.stream, Iterable):  # pragma: no cover - httpx contract
            raise httpx.ReadError("unsupported request body", request=request)
        core = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        try:
            response = self._pool.handle_request(core)
        except (httpcore.NetworkError, httpcore.ProtocolError, httpcore.TimeoutException) as exc:
            raise _mapped(exc, request, self._aborted.is_set()) from exc
        if not isinstance(response.stream, Iterable):  # pragma: no cover - httpcore contract
            raise httpx.ReadError("unsupported response body", request=request)
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=_Body(response.stream, request, self),
            extensions=response.extensions,
        )

    def close(self) -> None:
        """Close pooled connections."""
        self._pool.close()


def abortable_client(timeout_s: float) -> tuple[httpx.Client, AbortableTransport]:
    """Return a loopback-safe client (no redirects, no environment proxies) and its transport."""
    transport = AbortableTransport()
    client = httpx.Client(
        transport=transport, timeout=timeout_s, follow_redirects=False, trust_env=False
    )
    return client, transport
