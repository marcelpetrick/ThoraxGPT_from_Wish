# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Frozen experiment configurations (``configs/experiments/*.yaml``, Vision §24, §26).

An experiment names one model setup (or a small sweep of variants), the datasets, the
reference labels to score and the scoring parameters. The byte hash of the YAML file is the
experiment's config hash; it is the same hash a future sealed-evaluation freeze records.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from thoraxbench.provenance import sha256_of_obj
from thoraxbench.splits.guard import config_sha256

DevelopmentPhase = Literal["calibration", "internal_test"]
SAFE_ID = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"


class Variant(BaseModel):
    """One arm of a sweep; unset fields inherit the experiment's base setup."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=SAFE_ID)
    model: str | None = None
    prompt: str | None = None
    view_overrides: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class RunSpec:
    """A fully resolved model setup that the runner executes on every case."""

    variant: str
    model: str
    prompt: str | None
    view_overrides: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "variant": self.variant,
            "model": self.model,
            "prompt": self.prompt,
            "view_overrides": dict(self.view_overrides),
        }


class ExperimentConfig(BaseModel):
    """Schema of an experiment YAML file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=SAFE_ID)
    title: str = ""
    description: str = ""
    vision_ref: str = ""
    split: Literal["development"] = "development"
    phases: list[DevelopmentPhase] = Field(
        default_factory=lambda: list[DevelopmentPhase](["calibration", "internal_test"]),
        min_length=1,
    )
    model: str
    prompt: str | None = None
    view_overrides: dict[str, Any] = Field(default_factory=dict)
    datasets: list[str] = Field(min_length=1)
    labels: list[str] = Field(min_length=1)
    thresholds: dict[str, float] = Field(default_factory=dict)
    n_boot: int = Field(default=1000, ge=0)
    seed: int = 0
    variants: list[Variant] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> ExperimentConfig:
        ids = [v.id for v in self.variants]
        if len(ids) != len(set(ids)):
            msg = "variant ids must be unique"
            raise ValueError(msg)
        unknown = set(self.thresholds) - set(self.labels)
        if unknown:
            msg = f"thresholds for unscored labels: {', '.join(sorted(unknown))}"
            raise ValueError(msg)
        if len(self.datasets) != len(set(self.datasets)):
            msg = "datasets must be unique"
            raise ValueError(msg)
        return self

    def runs(self) -> list[RunSpec]:
        """Return the resolved setups: the base setup, or one per variant."""
        if not self.variants:
            return [RunSpec("base", self.model, self.prompt, dict(self.view_overrides))]
        return [
            RunSpec(
                variant=v.id,
                model=v.model or self.model,
                prompt=v.prompt if v.prompt is not None else self.prompt,
                view_overrides={**self.view_overrides, **v.view_overrides},
            )
            for v in self.variants
        ]


@dataclass(frozen=True)
class LoadedExperiment:
    """A parsed experiment together with the hashes that identify it."""

    config: ExperimentConfig
    path: Path
    file_sha256: str

    @property
    def canonical_sha256(self) -> str:
        """Hash of the parsed configuration (independent of YAML formatting)."""
        return sha256_of_obj(self.config.model_dump(mode="json"))


def load_experiment(path: Path) -> LoadedExperiment:
    """Read and validate an experiment YAML file.

    Raises:
        OSError: if the file cannot be read.
        ValueError: if the YAML is not a mapping or fails validation.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"experiment config {path} must be a YAML mapping"
        raise ValueError(msg)
    return LoadedExperiment(ExperimentConfig.model_validate(data), path, config_sha256(path))
