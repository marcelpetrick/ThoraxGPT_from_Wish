# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""The common model interface (Vision §17) and model configuration."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

import yaml
from pydantic import BaseModel, ConfigDict, Field

from thoraxbench.schemas import (
    AnalysisRequest,
    Capabilities,
    FindingsReport,
    PreparedInput,
    RawOutput,
)


class ModelUnavailableError(RuntimeError):
    """Raised when a model cannot be prepared/run (no view, service down, unknown id)."""


@runtime_checkable
class ThoraxModel(Protocol):
    """Interface every local model adapter implements (Vision §17)."""

    id: str

    def capabilities(self) -> Capabilities:
        """Return what the model can do."""
        ...

    def available(self) -> bool:
        """Return whether the backing runtime and weights are reachable."""
        ...

    def prepare(self, study: Any, request: AnalysisRequest) -> PreparedInput:
        """Turn a study (volume + cues) into model-specific input."""
        ...

    def infer(self, prepared: PreparedInput, request: AnalysisRequest) -> RawOutput:
        """Run the model locally."""
        ...

    def parse(self, raw: RawOutput) -> FindingsReport:
        """Convert raw output into the common schema."""
        ...


@runtime_checkable
class ViewBuilderLike(Protocol):
    """What adapters need from a view builder (implemented in ``thoraxbench.views``)."""

    def build(self, study: Any, request: AnalysisRequest) -> PreparedInput:
        """Render model input for *study*."""
        ...


ViewResolver = Callable[[str, dict[str, Any]], ViewBuilderLike | None]


def default_view_resolver(view_id: str, params: dict[str, Any]) -> ViewBuilderLike | None:
    """Resolve *view_id* via ``thoraxbench.views.get_view(view_id, **params)`` if available.

    Returns ``None`` when the views package (or the view) does not exist, so a model can be
    loaded for availability checks even without a view.
    """
    try:
        views = importlib.import_module("thoraxbench.views")
    except ImportError:
        return None
    get_view = getattr(views, "get_view", None)
    if get_view is None:
        return None
    try:
        view = get_view(view_id, **params)
    except KeyError, ValueError:
        return None
    return view if isinstance(view, ViewBuilderLike) else None


class ModelConfig(BaseModel):
    """One ``configs/models/<id>.yaml`` entry."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    id: str
    adapter: Literal["ollama", "http_service", "heuristic", "monai_detector"]
    family: str
    tag: str | None = None
    service: str | None = None
    base_url: str | None = None
    view: str
    view_params: dict[str, Any] = Field(default_factory=dict)
    prompt: str | None = None
    quantization: str | None = None
    capabilities: Capabilities = Field(default_factory=Capabilities)
    options: dict[str, Any] = Field(default_factory=dict)
    timeout_s: float = 600.0
    license: str = "unknown"
    tier: str = ""
    notes: str = ""


def load_model_config(model_id: str, models_dir: Path) -> ModelConfig:
    """Load ``<models_dir>/<model_id>.yaml``.

    Raises:
        ModelUnavailableError: if the file does not exist or its id mismatches.
    """
    path = models_dir / f"{model_id}.yaml"
    if not path.is_file():
        msg = f"unknown model '{model_id}' (no {path})"
        raise ModelUnavailableError(msg)
    config = ModelConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if config.id != model_id:
        msg = f"{path.name}: id '{config.id}' does not match '{model_id}'"
        raise ModelUnavailableError(msg)
    return config


def list_model_configs(models_dir: Path) -> list[ModelConfig]:
    """All model configs, sorted by id."""
    return [load_model_config(p.stem, models_dir) for p in sorted(models_dir.glob("*.yaml"))]


class ViewBackedModel:
    """Shared ``prepare`` implementation for adapters that render through a view."""

    def __init__(self, config: ModelConfig, view: ViewBuilderLike | None) -> None:
        self.config = config
        self.id = config.id
        self.view = view

    def capabilities(self) -> Capabilities:
        """Capabilities declared in the model config."""
        return self.config.capabilities

    def prepare(self, study: Any, request: AnalysisRequest) -> PreparedInput:
        """Render *study* with the configured view.

        Raises:
            ModelUnavailableError: if no view builder is configured.
        """
        if self.view is None:
            msg = f"model '{self.id}' has no usable view '{self.config.view}'"
            raise ModelUnavailableError(msg)
        return self.view.build(study, request)
