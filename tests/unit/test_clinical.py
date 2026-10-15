# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
import pytest

from thoraxbench.ontology import load_ontology
from thoraxbench.ontology.clinical import Severity, Urgency, load_clinical_kb
from thoraxbench.ontology.guidelines import (
    NoduleType,
    fleischner,
    lung_rads_baseline_solid,
    size_bin,
)


def test_kb_covers_ontology_exactly() -> None:
    kb = load_clinical_kb()
    assert set(kb.entries) == set(load_ontology().ids())
    assert "not medical advice" in kb.disclaimer.lower()
    nodule = kb.get("pulmonary_nodule")
    assert nodule is not None
    assert nodule.severity is Severity.LOW
    assert nodule.urgency is Urgency.ROUTINE
    assert nodule.sources
    assert kb.get("unknown") is None
    for entry in kb.entries.values():
        assert entry.plain_language
        assert entry.prevalence
        _ = entry.severity  # every severity parses


def test_ct_rate_names_agree_with_ontology() -> None:
    onto = load_ontology()
    kb = load_clinical_kb()
    for lb in onto.labels:
        entry = kb.get(lb.id)
        assert entry is not None
        if entry.ct_rate_label and "ct_rate" in lb.native:
            assert entry.ct_rate_label == lb.native["ct_rate"]


@pytest.mark.parametrize(
    ("size", "kwargs", "expected"),
    [
        (4.0, {}, "No routine follow-up."),
        (4.0, {"high_risk": True}, "Optional CT at 12 months."),
        (7.0, {}, "CT at 6-12 months, then consider CT at 18-24 months."),
        (7.0, {"high_risk": True, "multiple": True}, "CT at 3-6 months, then CT at 18-24 months."),
        (12.0, {}, "Consider CT at 3 months, PET/CT, or tissue sampling."),
        (12.0, {"multiple": True}, "CT at 3-6 months, then consider CT at 18-24 months."),
        (4.0, {"nodule_type": NoduleType.GROUND_GLASS}, "No routine follow-up."),
        (9.0, {"nodule_type": NoduleType.GROUND_GLASS}, "CT at 6-12 months to confirm"),
        (9.0, {"nodule_type": NoduleType.PART_SOLID}, "CT at 3-6 months to confirm"),
        (4.0, {"nodule_type": NoduleType.PART_SOLID, "multiple": True}, "consider CT at 2 and 4"),
        (9.0, {"nodule_type": NoduleType.GROUND_GLASS, "multiple": True}, "most suspicious"),
    ],
)
def test_fleischner(size: float, kwargs: dict[str, object], expected: str) -> None:
    advice = fleischner(size, **kwargs)  # type: ignore[arg-type]
    assert advice.applicable
    assert expected in advice.advice
    assert "35" in advice.caveat


def test_fleischner_edge_cases() -> None:
    assert not fleischner(None).applicable
    mass = fleischner(35.0)
    assert mass.category == "mass"
    assert not mass.applicable


@pytest.mark.parametrize(
    ("size", "cat"), [(None, "0"), (4.0, "2"), (7.0, "3"), (10.0, "4A"), (20.0, "4B")]
)
def test_lung_rads(size: float | None, cat: str) -> None:
    assert lung_rads_baseline_solid(size).category == cat


def test_size_bins() -> None:
    assert [size_bin(s) for s in (3, 6, 8, 9, 31)] == [
        "<6 mm",
        "6-8 mm",
        "6-8 mm",
        ">8 mm",
        ">=30 mm (mass)",
    ]
