# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Minimal client for the public TCIA NBIA REST API v1 (no login, public collections only).

Only three request types are used: ``getSeries`` (series inventory with license fields),
``getImage`` (one series as a ZIP archive) and plain label-file downloads from the TCIA
upload area. The ``httpx.Client`` is injected so tests run against ``httpx.MockTransport``.
"""

from __future__ import annotations

import json
import time
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from thoraxbench import __version__
from thoraxbench.registry import PolicyError

NBIA_BASE = "https://services.cancerimagingarchive.net/nbia-api/services/v1"
TCIA_UPLOADS = "https://www.cancerimagingarchive.net/wp-content/uploads"
USER_AGENT = f"thoraxbench/{__version__} (research benchmark; acquire)"

ApiLog = Callable[[dict[str, object]], None]


class AcquisitionError(RuntimeError):
    """Raised when a download or its verification fails."""


class BudgetError(PolicyError):
    """Raised when an acquisition would exceed the configured data budget."""


class SeriesRecord(BaseModel):
    """One ``getSeries`` row; unknown NBIA fields are preserved for the selection file."""

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)

    series_uid: str = Field(alias="SeriesInstanceUID", pattern=r"^[0-9]+(\.[0-9]+)+$")
    patient_id: str = Field(alias="PatientID", pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    modality: str = Field(alias="Modality")
    collection: str | None = Field(default=None, alias="Collection")
    image_count: int = Field(alias="ImageCount", ge=1)
    file_size: int = Field(alias="FileSize", ge=0)
    license_uri: str | None = Field(default=None, alias="LicenseURI")
    license_name: str | None = Field(default=None, alias="LicenseName")


SERIES_LIST = TypeAdapter(list[SeriesRecord])


def now_utc() -> str:
    """Return the current UTC time as ISO-8601 with seconds precision."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def nbia_url(endpoint: str, **params: str) -> str:
    """Build an NBIA URL with ``%20`` (not ``+``) for spaces, as the API expects."""
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"{NBIA_BASE}/{endpoint}?{query}"


def default_client() -> httpx.Client:
    """HTTP client used by the CLI for real acquisitions."""
    return httpx.Client(
        timeout=httpx.Timeout(60.0, read=600.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )


class NbiaClient:
    """Retrying NBIA/TCIA client that records every URL it calls."""

    def __init__(
        self,
        client: httpx.Client,
        *,
        retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        log: ApiLog | None = None,
    ) -> None:
        self._client = client
        self._retries = max(1, retries)
        self._sleep = sleep
        self._log = log

    def _record(self, url: str, status: object, nbytes: int | None = None) -> None:
        if self._log is not None:
            self._log({"t": now_utc(), "url": url, "status": status, "bytes": nbytes})

    def _backoff(self, attempt: int) -> None:
        if attempt + 1 < self._retries:
            self._sleep(float(2**attempt * 3))

    def get_bytes(self, url: str) -> bytes:
        """GET *url* with retries.

        Raises:
            AcquisitionError: after the last failed attempt.
        """
        last: Exception | None = None
        for attempt in range(self._retries):
            try:
                response = self._client.get(url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                self._record(url, f"error: {exc!r}")
                last = exc
                self._backoff(attempt)
                continue
            self._record(url, response.status_code, len(response.content))
            return response.content
        msg = f"GET failed after {self._retries} attempt(s): {url}: {last!r}"
        raise AcquisitionError(msg)

    def get_series(self, collection: str, modality: str) -> list[SeriesRecord]:
        """Series inventory of *collection* restricted to *modality*.

        NBIA answers an empty body when nothing matches; that yields an empty list.
        """
        body = self.get_bytes(nbia_url("getSeries", Collection=collection, Modality=modality))
        if not body.strip():
            return []
        try:
            rows = json.loads(body)
        except ValueError as exc:
            msg = f"getSeries for {collection}/{modality} returned invalid JSON"
            raise AcquisitionError(msg) from exc
        return SERIES_LIST.validate_python(rows)

    def download(self, url: str, dest: Path, *, max_bytes: int) -> int:
        """Stream *url* into *dest*; abort when more than *max_bytes* arrive.

        Raises:
            BudgetError: if the transfer exceeds *max_bytes* (not retried).
            AcquisitionError: after the last failed attempt.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        last: Exception | None = None
        for attempt in range(self._retries):
            written = 0
            try:
                with self._client.stream("GET", url) as response:
                    response.raise_for_status()
                    with dest.open("wb") as handle:
                        for chunk in response.iter_bytes(1 << 20):
                            written += len(chunk)
                            if written > max_bytes:
                                self._record(url, "aborted: data budget", written)
                                dest.unlink()
                                msg = f"download of {url} exceeds the remaining data budget"
                                raise BudgetError(msg)
                            handle.write(chunk)
            except httpx.HTTPError as exc:
                self._record(url, f"error: {exc!r}")
                last = exc
                self._backoff(attempt)
                continue
            self._record(url, 200, written)
            return written
        dest.unlink(missing_ok=True)
        msg = f"download failed after {self._retries} attempt(s): {url}: {last!r}"
        raise AcquisitionError(msg)
