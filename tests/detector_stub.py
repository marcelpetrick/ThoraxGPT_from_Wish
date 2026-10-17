# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Explicit scripted detector output for synthetic UI/export checks, never accuracy tests."""

from typing import Any
from unittest.mock import Mock

import pytest

from thoraxbench.analysis import AnalysisResult, analyze_study
from thoraxbench.api import app as api
from thoraxbench.config import Settings
from thoraxbench.schemas import Finding, FindingsReport, LesionCandidate
from thoraxbench.study import Study


def scripted_result(
    study: Study, model_id: str, settings: Settings, **kwargs: Any
) -> AnalysisResult:
    """Use the real guarded engine with HU rules; replace only the labelled test output."""
    result = analyze_study(study, "heuristic-hu", settings, **kwargs)
    return result.model_copy(
        update={
            "model_id": model_id,
            "raw_text": "Scripted synthetic detector output; no detector network ran.",
            "report": FindingsReport(
                findings=[
                    Finding(
                        label="pulmonary_nodule", present=True, confidence=0.9, source="detector"
                    )
                ],
                lesions=[
                    LesionCandidate(center_zyx_mm=(110.0, 100.0, 100.0), diameter_mm=6, score=0.9)
                ],
            ),
            "view_meta": {"possible_training_overlap": "unknown"},
        }
    )


def install_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mark the scripted detector available without installing or downloading weights."""
    monkeypatch.setattr(api, "analyze_study", scripted_result)
    available = Mock()
    available.available.return_value = True
    monkeypatch.setattr(api, "load_model", lambda *_args, **_kwargs: available)
