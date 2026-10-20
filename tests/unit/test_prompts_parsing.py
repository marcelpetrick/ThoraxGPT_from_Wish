# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
import json
from pathlib import Path

import pytest

from thoraxbench.config import Settings
from thoraxbench.parsing import extract_json, parse_findings
from thoraxbench.prompts import PROMPT_IDS, findings_json_schema, load_prompt
from thoraxbench.prompts.schema import CONFIDENCE_LEVELS, strict_findings_json_schema
from thoraxbench.schemas import RawOutput

PROMPTS = Settings().configs_dir / "prompts"


LEGACY_PROMPTS = ("P0", "P1", "P2", "P3", "P4")
LEGACY_SHA256 = {
    "P2": "f5741b3999c96fc76f79ccd848cae80a202a3f97638a744310382f1f82d7cd9c",
}


def test_prompt_ids_keep_legacy_prompts() -> None:
    assert PROMPT_IDS[: len(LEGACY_PROMPTS)] == LEGACY_PROMPTS
    assert "P5" in PROMPT_IDS
    for pid, digest in LEGACY_SHA256.items():
        assert load_prompt(pid, PROMPTS).sha256 == digest
        assert load_prompt(pid, PROMPTS).schema_version == "1"


@pytest.mark.parametrize("pid", LEGACY_PROMPTS)
def test_all_prompts_render(pid: str) -> None:
    p = load_prompt(pid, PROMPTS)
    assert len(p.sha256) == 64
    r = p.render(["pulmonary_nodule", "emphysema"], 2, ["lung window axial", "mediastinal"], "")
    assert "image 1: lung window axial" in r.user
    assert "image 2: mediastinal" in r.user
    assert "image 0:" not in r.user
    assert p.version == ("1.0.3" if pid == "P4" else "1.0.2")
    assert "$" not in r.user
    assert "No deterministic measurements" in r.user
    if p.two_pass:
        r2 = p.render_second_pass('{"observations": []}', ["emphysema"], 2)
        assert "observations" in r2.user
    else:
        with pytest.raises(ValueError, match="single-pass"):
            p.render_second_pass("{}", [], 0)


def test_p5_renders_verbatim_captions_and_strict_schema() -> None:
    p = load_prompt("P5", PROMPTS)
    assert (p.version, p.schema_version, p.label_constrained, p.two_pass) == (
        "1.0.0",
        "2",
        True,
        False,
    )
    captions = ["IMAGE 1: axial, lung", "IMAGE 2: axial, lung"]
    r = p.render(["pulmonary_nodule", "pulmonary_mass"], 2, captions, "")
    assert "IMAGE 1: axial, lung\nIMAGE 2: axial, lung" in r.user
    assert "image 1:" not in r.user
    assert "$" not in r.user
    assert "No deterministic measurements" in r.user
    assert '"properties"' not in r.user  # the schema goes to Ollama format only
    schema = p.schema(["pulmonary_nodule", "pulmonary_mass"], n_images=2)
    assert schema == strict_findings_json_schema(["pulmonary_nodule", "pulmonary_mass"], n_images=2)
    assert (
        p.schema(["pulmonary_nodule"])["properties"]["findings"]["prefixItems"][0]["properties"][
            "evidence_images"
        ]["maxItems"]
        == 0
    )


def test_strict_schema_is_fixed_length_ordered_and_bounded() -> None:
    labels = ["pulmonary_nodule", "pulmonary_mass"]
    s = strict_findings_json_schema(labels, n_images=24)
    assert next(iter(s["properties"])) == "findings"
    assert s["required"][0] == "findings"
    assert s["additionalProperties"] is False
    findings = s["properties"]["findings"]
    assert (findings["minItems"], findings["maxItems"]) == (2, 2)
    assert "items" not in findings
    consts = [item["properties"]["label"] for item in findings["prefixItems"]]
    assert consts == [{"const": "pulmonary_nodule"}, {"const": "pulmonary_mass"}]
    item = findings["prefixItems"][0]
    assert item["additionalProperties"] is False
    assert item["properties"]["confidence"]["enum"] == list(CONFIDENCE_LEVELS)
    assert CONFIDENCE_LEVELS[0] == 0.0
    assert CONFIDENCE_LEVELS[-1] == 1.0
    assert len(CONFIDENCE_LEVELS) == 21
    evidence = item["properties"]["evidence_images"]
    assert evidence["items"] == {"type": "integer", "minimum": 1, "maximum": 24}
    assert evidence["maxItems"] == 4
    assert item["properties"]["description"]["maxLength"] == 160
    assert s["properties"]["uncertainty"]["maxLength"] == 240
    assert s["properties"]["impression"]["maxItems"] == 2
    assert s["properties"]["negative_findings"]["maxItems"] == 2
    assert s["properties"]["study_quality"]["additionalProperties"] is False
    with pytest.raises(ValueError, match="at least one"):
        strict_findings_json_schema([], n_images=1)
    with pytest.raises(ValueError, match="negative"):
        strict_findings_json_schema(labels, n_images=-1)


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ("schema_version: '3'\nlabel_constrained: true\n", "unknown schema_version"),
        ("schema_version: '2'\n", "label-constrained single-pass"),
        ("schema_version: '2'\nlabel_constrained: true\nsecond_pass: x\n", "single-pass"),
    ],
)
def test_schema_version_validation(tmp_path: Path, extra: str, message: str) -> None:
    (tmp_path / "PX.yaml").write_text(
        "id: PX\nversion: '1'\ntitle: t\nsystem: s\nuser: u\n" + extra, encoding="utf-8"
    )
    with pytest.raises(ValueError, match=message):
        load_prompt("PX", tmp_path)


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
    assert rep.positive_labels() == set()
    rep2 = parse_findings(
        '{"findings": {"emphysema": true, "atelectasis": 0.3, "pneumothorax": "no",'
        ' "consolidation": {"present": true}, "fibrosis": null}, "study_quality": 5}'
    )
    assert rep2.label_probability("atelectasis") == pytest.approx(0.3)
    assert rep2.label_probability("pneumothorax") is None
    assert rep2.label_probability("fibrosis_interstitial") is None
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


def test_schema_binds_attached_image_bounds_and_negative_label_ids() -> None:
    schema = findings_json_schema(["pulmonary_nodule"], n_images=2)
    fields = schema["properties"]["findings"]["items"]["properties"]
    assert fields["evidence_images"]["items"] == {"type": "integer", "minimum": 1, "maximum": 2}
    assert schema["properties"]["negative_findings"]["items"]["enum"] == ["pulmonary_nodule"]
    with pytest.raises(ValueError, match="negative"):
        findings_json_schema(n_images=-1)


def test_confident_negatives_with_zero_confidence_stay_negative() -> None:
    """Regression 2026-10-20: MedGemma's `present: false, confidence: 0.0` meant "absent".

    Reading confidence as "answer is correct" turned all 16 negatives into unsupported
    positives and the run abstained. The explicit answer now sets the direction.
    """
    from thoraxbench.analysis import _check_image_evidence

    labels = ["pulmonary_nodule", "pleural_effusion", "emphysema", "cardiomegaly"]
    text = json.dumps(
        {
            "findings": [
                {"label": label, "present": False, "confidence": 0.0, "evidence_images": []}
                for label in labels
            ],
            "negative_findings": labels,
            "abstain": False,
        }
    )
    report = parse_findings(text)
    _check_image_evidence(report, 4, required=True)
    assert not report.abstain
    assert report.positive_labels() == set()
    assert all(report.label_probability(label) == 0.0 for label in labels)
    assert not any("marked unavailable" in w for w in report.parse_warnings)
    summary = [w for w in report.parse_warnings if "read as strength" in w]
    assert summary == [
        "confidence read as strength of the explicit yes/no answer for 4 label(s): "
        "pulmonary_nodule, pleural_effusion, emphysema, cardiomegaly"
    ]
