# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
from pathlib import Path

import pytest

from thoraxbench.config import Settings
from thoraxbench.parsing import extract_json, parse_findings
from thoraxbench.prompts import PROMPT_IDS, findings_json_schema, load_prompt
from thoraxbench.schemas import RawOutput

PROMPTS = Settings().configs_dir / "prompts"


@pytest.mark.parametrize("pid", PROMPT_IDS)
def test_all_prompts_render(pid: str) -> None:
    p = load_prompt(pid, PROMPTS)
    assert len(p.sha256) == 64
    r = p.render(["pulmonary_nodule", "emphysema"], 2, ["lung window axial", "mediastinal"], "")
    assert "$" not in r.user
    assert "No deterministic measurements" in r.user
    if p.two_pass:
        r2 = p.render_second_pass('{"observations": []}', ["emphysema"], 2)
        assert "observations" in r2.user
    else:
        with pytest.raises(ValueError, match="single-pass"):
            p.render_second_pass("{}", [], 0)


def test_prompt_id_mismatch(tmp_path: Path) -> None:
    (tmp_path / "PX.yaml").write_text("id: P9\nversion: '1'\ntitle: t\nsystem: s\nuser: u\n")
    with pytest.raises(ValueError, match="does not match"):
        load_prompt("PX", tmp_path)


def test_schema_constrained() -> None:
    s = findings_json_schema(["emphysema"])
    assert s["properties"]["findings"]["items"]["properties"]["label"]["enum"] == ["emphysema"]
    assert findings_json_schema()["properties"]["findings"]["items"]["properties"]["label"] == {
        "type": "string"
    }


@pytest.mark.parametrize(
    ("text", "repair"),
    [
        ('{"a": 1}', None),
        ('```json\n{"a": 1}\n```', "removed code fence"),
        ('Here you go: {"a": 1} hope it helps', "dropped trailing prose"),
        ('{"a": 1,}', "removed trailing commas"),
        ("{'a': 1}", "converted single quotes"),
        ('```json\n{"a": 1, "b": [1, 2', "closed truncated JSON"),
        ('{"a": 1, "b": "tru', "closed truncated JSON"),
        ('{"a": 1, "b":', "closed truncated JSON"),
    ],
)
def test_extract_json(text: str, repair: str | None) -> None:
    value, repairs = extract_json(text)
    assert value is not None
    assert value["a"] == 1
    if repair:
        assert repair in repairs
    else:
        assert repairs == []


@pytest.mark.parametrize("text", ["", "no json here", "{ :: ]"])
def test_extract_json_failure(text: str) -> None:
    value, repairs = extract_json(text)
    assert value is None
    assert repairs


def test_extract_escaped_string() -> None:
    value, _ = extract_json('{"a": 1, "b": "x\\"y')
    assert value == {"a": 1, "b": 'x"y'}


def test_parse_findings_full() -> None:
    text = """{"study_quality": {"adequate": "yes", "limitations": "thick slices"},
      "findings": [
        {"label": "Lung nodule", "present": "yes", "confidence": "85%",
         "laterality": "right", "size_bin": "6-8mm", "evidence_images": [3, "4", "x"],
         "description": "round opacity"},
        {"label": "GGO", "present": "absent", "confidence": "high"},
        {"label": "emphysema", "present": "uncertain", "confidence": 7},
        {"label": "pleural effusion", "present": true, "confidence": 170, "size_mm": "12 mm"},
        {"label": "pneumothorax", "present": false, "confidence": "??", "size_bin": "huge"},
        {"label": "lung nodule", "present": false},
        {"label": "spaceship", "description": "odd"},
        {"label": "", "present": true}
      ],
      "negative_findings": ["fracture", "unicorn", "emphysema"],
      "impression": "nodule", "urgent_flags": null, "abstain": "no"}"""
    rep = parse_findings(RawOutput(text=text))
    f = {x.label: x for x in rep.findings}
    assert f["pulmonary_nodule"].confidence == 0.85
    assert f["pulmonary_nodule"].size_mm == 7.0
    assert "size bin 6-8mm" in f["pulmonary_nodule"].description
    assert f["pulmonary_nodule"].evidence_images == [3, 4]
    assert f["ground_glass_opacity"].present is False
    assert f["emphysema"].present is None
    assert f["emphysema"].confidence == 0.07
    assert f["pleural_effusion"].confidence == 1.0
    assert f["pleural_effusion"].size_mm == 12.0
    assert f["pneumothorax"].confidence is None
    assert rep.negative_findings == ["fracture"]
    assert any("spaceship" in s for s in rep.incidental_findings)
    assert rep.impression == ["nodule"]
    assert rep.study_quality.limitations == ["thick slices"]
    assert not rep.abstain
    joined = " ".join(rep.parse_warnings)
    for needle in (
        "duplicate",
        "unknown label",
        "clamped",
        "unsupported measurement",
        "unknown size bin",
        "unreadable confidence",
        "unknown negative",
    ):
        assert needle in joined


def test_parse_alternative_shapes() -> None:
    rep = parse_findings('[{"label": "emphysema"}, "atelectasis"]')
    assert rep.positive_labels() == {"emphysema", "atelectasis"}
    rep2 = parse_findings(
        '{"findings": {"emphysema": true, "atelectasis": 0.3, "pneumothorax": "no",'
        ' "consolidation": {"present": true}, "fibrosis": null}, "study_quality": 5}'
    )
    assert rep2.label_probability("atelectasis") == 0.3
    assert rep2.label_probability("pneumothorax") == 0.0
    assert rep2.label_probability("fibrosis_interstitial") == 0.5
    assert parse_findings('{"findings": "weird"}').findings == []
    assert (
        parse_findings('{"findings": [{"label": "emphysema", "confidence": true}]}')
        .findings[0]
        .confidence
        == 1.0
    )


def test_parse_abstentions() -> None:
    assert parse_findings(RawOutput(error="boom")).abstain
    assert parse_findings("").abstain
    assert parse_findings("I cannot read this").abstain
    assert parse_findings('"just a string"').abstain


def test_parse_probabilities() -> None:
    raw = RawOutput(text='"x"', probabilities={"Emphysema": 0.8, "Lung nodule": 0.2, "zz": 0.9})
    rep = parse_findings(raw)
    assert rep.label_probability("emphysema") == pytest.approx(0.8)
    assert rep.label_probability("pulmonary_nodule") == pytest.approx(0.2)
    assert rep.findings[0].source == "probability"
    assert any("zz" in w for w in rep.parse_warnings)
    assert not parse_findings(RawOutput(probabilities={"emphysema": 0.4})).abstain
