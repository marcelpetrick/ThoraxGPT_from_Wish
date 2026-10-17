# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Bounded, illustrative detector crops for live review and offline exports."""

import base64
from typing import Any

from thoraxbench.analysis import AnalysisResult
from thoraxbench.study import Study
from thoraxbench.views import CandidateCropView

MAX_CANDIDATE_PREVIEWS = 12


def candidate_review(result: AnalysisResult, study: Study) -> dict[str, Any] | None:
    """Return sourced candidates and bounded post-inference crops, never model evidence.

    Existing benchmark case detail must not call this helper: saved benchmark artifacts do
    not retain prepared pixels. This helper requires the live, already guarded study.
    """
    if result.model_id != "monai-lung-nodule":
        return None
    if (result.dataset, result.case_id, result.series_uid) != (
        study.dataset,
        study.case_id,
        study.volume.series_uid,
    ):
        raise ValueError("candidate review study does not match the analysis result")
    lesions = result.report.lesions
    if lesions is None or result.report.abstain or result.raw_error:
        return None
    prepared = CandidateCropView(size=256, planes=("axial", "coronal")).build(
        study, lesions[:MAX_CANDIDATE_PREVIEWS]
    )
    candidates: list[dict[str, Any]] = []
    for number, lesion in enumerate(lesions, start=1):
        index = round(lesion.center_zyx_mm[0] / study.volume.spacing_mm[0])
        item = lesion.model_dump(mode="json") | {
            "number": number,
            "slice_index": index if 0 <= index < study.volume.shape[0] else None,
            "previews": [],
        }
        if number <= MAX_CANDIDATE_PREVIEWS:
            for offset, plane in enumerate(("axial", "coronal")):
                png = prepared.images[(number - 1) * 2 + offset]
                item["previews"].append(
                    {
                        "plane": plane,
                        "data_url": "data:image/png;base64,"
                        + base64.b64encode(png).decode("ascii"),
                    }
                )
        candidates.append(item)
    return {
        "candidates": candidates,
        "previewed": min(len(lesions), MAX_CANDIDATE_PREVIEWS),
        "total": len(lesions),
        "crop_view_sha256": prepared.meta["view_sha256"],
        "possible_training_overlap": result.view_meta.get("possible_training_overlap", "unknown"),
        "illustrative": True,
    }
