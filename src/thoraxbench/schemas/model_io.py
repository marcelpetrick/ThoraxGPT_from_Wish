# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Model adapter I/O types (Vision §17)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Capabilities(BaseModel):
    """What a model can do; drives which benchmark tasks it is scored on."""

    model_config = ConfigDict(frozen=True)

    three_d_native: bool = Field(default=False, alias="3d_native")
    multi_image: bool = False
    classification: bool = False
    report_generation: bool = False
    localization: bool = False
    segmentation: bool = False
    probabilities: bool = False


class AnalysisRequest(BaseModel):
    """What the caller wants from a model for one study."""

    request: str = "full-thorax"
    labels: list[str] = Field(default_factory=list)
    question: str | None = None
    prompt_id: str = "P3"


class PreparedInput(BaseModel):
    """Model-specific rendered input (images as PNG bytes and/or a tensor path)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    view_id: str
    view_version: str
    images: list[bytes] = Field(default_factory=list, repr=False)
    image_captions: list[str] = Field(default_factory=list)
    slice_indices: list[int] = Field(default_factory=list)
    context: str = ""
    tensor_path: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    @property
    def input_bytes(self) -> int:
        """Total size of the rendered input."""
        return sum(len(b) for b in self.images)


class RawOutput(BaseModel):
    """Unparsed model output plus runtime measurements."""

    text: str = ""
    probabilities: dict[str, float] = Field(default_factory=dict)
    tokens_generated: int | None = None
    prompt_tokens: int | None = None
    latency_s: float = 0.0
    error: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
