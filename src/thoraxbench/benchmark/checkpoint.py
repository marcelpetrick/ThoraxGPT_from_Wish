# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Integrity-checked, atomic development benchmark checkpoints and immutable case artifacts."""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field

from thoraxbench.adapters.base import ModelConfig
from thoraxbench.adapters.factory import require_local_endpoint
from thoraxbench.config import Settings
from thoraxbench.provenance import sha256_of_file, sha256_of_obj
from thoraxbench.reports.html_report import require_results_path


class Record(BaseModel):
    """One terminal case artifact linked by digest, not caller-controlled filename."""

    model_config = ConfigDict(extra="forbid")
    file: str
    sha256: str
    elapsed_s: float = Field(ge=0)


class Checkpoint(BaseModel):
    """The sole authoritative progress record; interrupted units remain pending."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    identity_sha256: str
    started_at: str
    status: Literal["running", "complete"] = "running"
    active_runtime_s: float = Field(default=0, ge=0)
    units: dict[str, Record] = Field(default_factory=dict)
    outputs: dict[str, Record] = Field(default_factory=dict)


def runtime_identity(model: ModelConfig, settings: Settings) -> dict[str, Any]:
    """Snapshot local runtime weights without downloading or invoking inference."""
    if model.adapter == "heuristic":
        return {"adapter": model.adapter, "identity": "source-hashed"}
    endpoint = (
        settings.ollama_url
        if model.adapter == "ollama"
        else (model.base_url or settings.service_urls.get(model.service or "", ""))
    )
    try:
        require_local_endpoint(endpoint)
        with httpx.Client(timeout=2.0, trust_env=False, follow_redirects=False) as client:
            response = client.get(
                f"{endpoint.rstrip('/')}/{'api/tags' if model.adapter == 'ollama' else 'health'}"
            )
            response.raise_for_status()
            body = response.json()
        if model.adapter == "ollama":
            tag = model.tag if ":" in (model.tag or "") else f"{model.tag}:latest"
            candidates = body.get("models", []) if isinstance(body, dict) else []
            for candidate in candidates if isinstance(candidates, list) else []:
                if isinstance(candidate, dict) and candidate.get("name") == tag:
                    digest = candidate.get("digest")
                    if isinstance(digest, str) and digest.strip():
                        return {"adapter": model.adapter, "endpoint": endpoint, "digest": digest}
        elif isinstance(body, dict):
            digest = body.get("model_hash") or body.get("model_digest")
            if body.get("status") == "ok" and isinstance(digest, str) and digest.strip():
                return {"adapter": model.adapter, "endpoint": endpoint, "digest": digest}
    except OSError, ValueError, RuntimeError, httpx.HTTPError:
        pass
    return {"adapter": model.adapter, "endpoint": endpoint, "digest": None}


class BenchmarkStore:
    """Own a unique invocation folder; only its checkpoint and provisional outputs replace."""

    def __init__(self, folder: Path, settings: Settings) -> None:
        self.folder = folder
        self.settings = settings
        self.state: Checkpoint
        self.identity: dict[str, Any] = {}

    def path(self, relative: str) -> Path:
        """Reject escapes from both ignored results and this invocation (including symlinks)."""
        path = self.folder / relative
        require_results_path(path, self.settings)
        if not path.resolve().is_relative_to(self.folder.resolve()):
            raise ValueError("Benchmark artifact escapes its invocation directory")
        return path

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Refuse concurrent writers, automatically releasing locks after interruption."""
        with self.path(".lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("Benchmark invocation is already in use") from exc
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def initialize(self, identity: dict[str, Any], *, resume: bool) -> None:
        """Validate identity and checkpoint before any artifact reuse or new inference."""
        digest = sha256_of_obj(identity)
        self.identity = identity
        if resume:
            saved = self._read_envelope("manifest.json")
            if saved != identity:
                raise ValueError("Resume identity mismatch; start a new invocation")
            if any(
                item["entry"] is not None and (not item["input"] or not item["input"].get("sha256"))
                for item in identity["selected"]
            ):
                raise ValueError("Resume requires verified selected input content hashes")
            if any(
                value.get("digest") is None
                for value in identity["runtime_models"].values()
                if value.get("adapter") != "heuristic"
            ):
                raise ValueError("Resume requires a known current runtime model digest")
            self.state = Checkpoint.model_validate(self._read_envelope("checkpoint.json"))
            if self.state.identity_sha256 != digest:
                raise ValueError("Checkpoint identity mismatch")
            for record in [*self.state.units.values(), *self.state.outputs.values()]:
                self.verify(record)
        else:
            self.state = Checkpoint(
                identity_sha256=digest, started_at=datetime.now(UTC).isoformat()
            )
            self._write_envelope("manifest.json", identity, replace=False)
            self.save()

    def _read_envelope(self, name: str) -> dict[str, Any]:
        envelope = json.loads(self.path(name).read_text(encoding="utf-8"))
        if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
            raise ValueError("Invalid benchmark integrity envelope")
        payload: dict[str, Any] = envelope["payload"]
        if envelope.get("sha256") != sha256_of_obj(payload):
            raise ValueError("Benchmark integrity checksum mismatch")
        return payload

    def read_checkpoint(self) -> Checkpoint:
        """Validate the authoritative checkpoint without replacing any output."""
        return Checkpoint.model_validate(self._read_envelope("checkpoint.json"))

    def _write_envelope(self, name: str, value: dict[str, Any], *, replace: bool) -> None:
        self.write(
            name,
            json.dumps(
                {"payload": value, "sha256": sha256_of_obj(value)}, sort_keys=True, indent=2
            ),
            replace=replace,
        )

    def write(self, name: str, text: str, *, replace: bool = False) -> Record:
        """Write through a flushed sibling temp file, with no replacement of immutable artifacts."""
        path = self.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path(f"{name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as output:
                output.write(text)
                output.flush()
                os.fsync(output.fileno())
            self.path(name)
            if replace:
                os.replace(temporary, path)
            else:
                os.link(temporary, path)
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)
        return Record(file=name, sha256=sha256_of_file(path), elapsed_s=0)

    def save(self) -> None:
        """Commit all completed units atomically; failures in persistence stop the benchmark."""
        self._write_envelope("checkpoint.json", self.state.model_dump(mode="json"), replace=True)

    def verify(self, record: Record) -> Path:
        """Check an artifact's digest before parsing/reusing it."""
        path = self.path(record.file)
        if sha256_of_file(path) != record.sha256:
            raise ValueError("Benchmark artifact checksum mismatch")
        return path

    def load_unit(self, key: str) -> dict[str, Any] | None:
        """Return only a durably checkpointed terminal artifact."""
        record = self.state.units.get(key)
        if record is None:
            return None
        payload = json.loads(self.verify(record).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("unit") != key:
            raise ValueError("Invalid benchmark case artifact")
        return payload

    def save_unit(self, key: str, payload: dict[str, Any], elapsed_s: float) -> None:
        """Append an immutable terminal unit, then atomically checkpoint its checksum."""
        if self.state.status != "running" or key in self.state.units:
            raise ValueError("Cannot replace a completed benchmark unit")
        record = self.write(f"cases/{key}-{uuid4().hex}.json", json.dumps(payload, indent=2))
        record.elapsed_s = elapsed_s
        self.state.units[key] = record
        self.save()

    def finish(self, result_json: str, markdown: str) -> tuple[Path, Path]:
        """Publish final aggregates; never replace completed invocation outputs."""
        if self.state.status == "complete":
            return self.verify(self.state.outputs["json"]), self.verify(
                self.state.outputs["markdown"]
            )
        self.state.outputs = {
            "json": self.write("result.json", result_json, replace=True),
            "markdown": self.write("report.md", markdown, replace=True),
        }
        self.state.status = "complete"
        self.save()
        return self.path("result.json"), self.path("report.md")
