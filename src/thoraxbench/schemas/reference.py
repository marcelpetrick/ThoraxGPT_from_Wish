# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Reference (ground-truth) labels and lesion annotations."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LesionAnnotation(BaseModel):
    """One annotated lesion (e.g. an LIDC nodule consensus)."""

    label: str = "pulmonary_nodule"
    center_zyx: tuple[float, float, float]
    diameter_mm: float
    readers: int = 1
    malignancy: float | None = None
    native_term: str = ""


class ReferenceLabels(BaseModel):
    """Study-level labels (``True``/``False``/``None`` = unknown) and lesions."""

    dataset: str
    patient_id: str
    study_uid: str
    labels: dict[str, bool | None] = Field(default_factory=dict)
    lesions: list[LesionAnnotation] = Field(default_factory=list)
    report_text: str | None = None
    native_labels: dict[str, str] = Field(default_factory=dict)
