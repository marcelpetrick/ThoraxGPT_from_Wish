# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
import pytest

from thoraxbench.ontology import CATEGORIES, load_ontology
from thoraxbench.schemas import (
    Capabilities,
    Finding,
    FindingsReport,
    Laterality,
    PreparedInput,
    ReferenceLabels,
)


def test_ontology_loads_and_maps() -> None:
    onto = load_ontology()
    assert onto.version == "1"
    assert len(onto.sha256) == 64
    ids = onto.ids()
    assert "pulmonary_nodule" in ids
    assert set(onto.ids(core_only=True)) < set(ids)
    assert all(lb.category in CATEGORIES for lb in onto.labels)
    assert onto.get("emphysema").name == "Emphysema"
    with pytest.raises(KeyError):
        onto.get("nope")
    ct_rate = onto.native_to_canonical("ct_rate")
    assert ct_rate["Lung opacity"] == ["ground_glass_opacity", "lung_opacity"]
    assert len(ct_rate) == 18  # CT-RATE's 18 abnormality labels are all mapped


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Pulmonary nodule", "pulmonary_nodule"),
        ("GGO", "ground_glass_opacity"),
        ("pleural-effusion", "pleural_effusion"),
        ("Coronary artery wall calcification", "coronary_calcification"),
        ("unicorn", None),
    ],
)
def test_normalise(text: str, expected: str | None) -> None:
    assert load_ontology().normalise(text) == expected


def test_findings_probabilities() -> None:
    rep = FindingsReport(
        findings=[
            Finding(label="pulmonary_nodule", present=True, confidence=0.8, laterality="RIGHT"),
            Finding(label="emphysema", present=False, confidence=0.9, laterality=None),
            Finding(label="atelectasis", present=None),
            Finding(label="consolidation"),
        ],
        negative_findings=["pneumothorax"],
    )
    assert rep.label_probability("pulmonary_nodule") == 0.8
    assert rep.label_probability("emphysema") == pytest.approx(0.1)
    assert rep.label_probability("atelectasis") is None
    assert rep.label_probability("consolidation") is None
    assert rep.label_probability("pneumothorax") == 0.0
    assert rep.label_probability("fracture") is None
    assert rep.positive_labels() == {"pulmonary_nodule"}
    assert rep.findings[0].laterality is Laterality.RIGHT
    assert rep.findings[1].laterality is Laterality.UNKNOWN
    assert Finding(label="x", laterality="sideways").laterality is Laterality.UNKNOWN


def test_model_io_types() -> None:
    caps = Capabilities.model_validate({"3d_native": True, "probabilities": True})
    assert caps.three_d_native
    assert caps.model_dump(by_alias=True)["3d_native"] is True
    prep = PreparedInput(view_id="v", view_version="1", images=[b"abc", b"de"])
    assert prep.input_bytes == 5
    ref = ReferenceLabels(dataset="d", patient_id="p", study_uid="s", labels={"a": True})
    assert ref.labels["a"]


@pytest.mark.parametrize(
    ("present", "confidence", "expected"),
    [
        (True, None, None),
        (False, None, None),
        (None, 0.9, None),
        # The explicit answer sets the direction; confidence only sets strength.
        (True, 0.2, 0.8),
        (False, 0.2, 0.2),
        (False, 0.0, 0.0),
        (True, 0.5, None),
    ],
)
def test_shared_probability_and_positive_labels(
    present: bool | None, confidence: float | None, expected: float | None
) -> None:
    finding = Finding(label="pulmonary_nodule", present=present, confidence=confidence)
    report = FindingsReport(findings=[finding])
    assert finding.presence_probability() == expected
    assert report.label_probability(finding.label) == expected
    assert report.positive_labels() == (
        {finding.label} if expected is not None and expected >= 0.5 else set()
    )
    report.abstain = True
    assert report.label_probability(finding.label) is None
    assert report.positive_labels() == set()
