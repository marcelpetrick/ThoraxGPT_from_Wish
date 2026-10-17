# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Post-inference previews are bounded, source-labelled and never substituted evidence."""

from pathlib import Path

import pytest

from tests.detector_stub import scripted_result
from thoraxbench.config import Settings
from thoraxbench.reports.candidates import candidate_review
from thoraxbench.reports.html_report import render_html_report
from thoraxbench.schemas import LesionCandidate
from thoraxbench.study import load_study_dir
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series


def test_candidate_previews_are_bounded_and_identity_checked(tmp_path: Path) -> None:
    spec = PhantomSpec(nodule_radius_mm=6)
    folder = write_dicom_series(make_phantom(spec), tmp_path / "demo", spec.spacing_mm)
    study = load_study_dir(folder, dataset="demo", case_id="phantom")
    result = scripted_result(study, "monai-lung-nodule", Settings(data_dir=tmp_path))
    lesion = LesionCandidate(center_zyx_mm=(110, 100, 100), score=0.8)
    result.report.lesions = [lesion] * 13
    review = candidate_review(result, study)
    assert review is not None
    assert (review["total"], review["previewed"]) == (13, 12)
    assert len(review["candidates"][-1]["previews"]) == 0
    assert len(review["candidates"][0]["previews"]) == 2
    result.report.lesions = [lesion.model_copy(update={"source": "<script>bad()</script>"})]
    html = render_html_report(result, study)
    assert "<script>bad()</script>" not in html
    assert "&lt;script&gt;bad()&lt;/script&gt;" in html
    result.report.lesions = []
    empty = candidate_review(result, study)
    assert empty is not None
    assert empty["total"] == 0
    assert "No detector candidates" in render_html_report(result, study)
    result.report.abstain = True
    assert candidate_review(result, study) is None
    result.report.abstain = False
    result.report.lesions = None
    assert candidate_review(result, study) is None
    result.case_id = "other"
    with pytest.raises(ValueError, match="does not match"):
        candidate_review(result, study)
    result.model_id = "some-vlm"
    assert candidate_review(result, study) is None
