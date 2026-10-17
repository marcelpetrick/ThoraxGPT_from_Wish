# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Sanity diagnostics: config validation, inputs, request layouts, parsing and metrics."""

import base64
import hashlib
import io
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from PIL import Image
from pydantic import ValidationError

from thoraxbench.adapters.base import load_model_config
from thoraxbench.benchmark import sanity as sn
from thoraxbench.benchmark import sanity_inputs as si
from thoraxbench.config import REPO_ROOT
from thoraxbench.index import IndexEntry
from thoraxbench.preprocess import HUCues
from thoraxbench.schemas import LesionAnnotation, ReferenceLabels

SANITY_DIR = REPO_ROOT / "configs" / "experiments" / "sanity"
MODELS = REPO_ROOT / "configs" / "models"
YES_NO = {"kind": "yes_no", "text": "Nodule in $n_images images?"}


def _cfg(**changes: Any) -> sn.SanityConfig:
    base: dict[str, Any] = {
        "id": "T-1",
        "test": "obvious_target",
        "models": ["medgemma1.5-q4"],
        "question": YES_NO,
        "synthetic": {"phantoms": [{"diameter_mm": 20}]},
    }
    return sn.SanityConfig.model_validate(base | changes)


def _item(n: int = 2, *, truth: int | None = 1) -> si.SanityItem:
    images = [si.png_bytes(np.full((8, 8), 10 * k, dtype=np.uint8)) for k in range(n)]
    return si.SanityItem("k", "g", "real", images, [f"cap {k}" for k in range(n)], truth, "p")


@pytest.mark.parametrize("path", sorted(SANITY_DIR.glob("*.yaml")), ids=lambda p: p.name)
def test_repository_sanity_configs_validate(path: Path) -> None:
    loaded = sn.load_sanity(path)
    assert path.read_text(encoding="utf-8").startswith("# SPDX-License-Identifier:")
    assert loaded.config.id == path.stem
    assert loaded.config.phases == ["calibration"]
    for model in loaded.config.models:
        assert load_model_config(model, MODELS).adapter == "ollama"


def test_config_rejections(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="unique"):
        _cfg(models=["a", "a"])
    with pytest.raises(ValidationError, match="synthetic or lidc"):
        _cfg(synthetic=None)
    with pytest.raises(ValidationError, match="paired_slab"):
        _cfg(test="paired_slab")
    with pytest.raises(ValidationError, match="position_binding"):
        _cfg(test="position_binding", question={"kind": "choice", "text": "x"}, n_images=1)
    with pytest.raises(ValidationError, match="free_text"):
        _cfg(test="description")
    with pytest.raises(ValidationError, match="yes_no"):
        _cfg(question={"kind": "free_text", "text": "x"})
    with pytest.raises(ValidationError):
        _cfg(phases=["internal_test"])
    with pytest.raises(ValidationError):
        _cfg(phases=["sealed"])
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(["not", "a", "mapping"]), encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        sn.load_sanity(bad)


def test_image_perturbations_keep_size_and_mode() -> None:
    rgb = si.png_bytes(np.zeros((6, 9, 3), dtype=np.uint8))
    grey = si.png_bytes(np.zeros((6, 9), dtype=np.uint8))
    rng = np.random.default_rng(0)
    for src, mode in ((rgb, "RGB"), (grey, "L")):
        for out in (si.gray_like(src), si.noise_like(src, rng)):
            with Image.open(io.BytesIO(out)) as img:
                assert (img.size, img.mode) == ((9, 6), mode)
    with Image.open(io.BytesIO(si.gray_like(grey, 77))) as img:
        assert set(np.asarray(img).ravel()) == {77}
    assert si.derangement(1, rng) == [0]
    for seed in range(20):
        order = si.derangement(3, np.random.default_rng(seed))
        assert sorted(order) == [0, 1, 2]
        assert order != [0, 1, 2]
    with Image.open(io.BytesIO(si.disk_image(40))) as img:
        arr = np.asarray(img)
    assert arr[20, 20] == 255
    assert arr[0, 0] == 0


def test_derangement_rotates_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fixed:
        def permutation(self, n: int) -> list[int]:
            return list(range(n))

    assert si.derangement(3, Fixed()) == [1, 2, 0]  # type: ignore[arg-type]  # test double


def test_caption_helpers() -> None:
    assert si.strip_caption_prefix("IMAGE 3: axial, lung") == "axial, lung"
    assert si.strip_caption_prefix("Image 1: x") == "x"
    assert si.strip_caption_prefix("no prefix: here") == "no prefix: here"
    assert si.axial_caption("lung", 9.0) == "axial chest CT, lung window W1500/L-600, 9 mm slab"
    assert si.rendered_thickness_mm(100, 50, 0.0, 2.5) == 2.5
    assert si.rendered_thickness_mm(100, 50, 5.0, 2.5) == 7.5
    assert si.size_bin(4.0) == "3-6 mm"
    assert si.size_bin(8.0) == "6-10 mm"
    assert si.size_bin(12.0) == ">=10 mm"


def test_phantom_inputs_render_and_sample() -> None:
    phantom = si.load_phantom(si.phantom_spec(0, "left", 20.0), "SANITY-T")
    assert phantom.study.dataset == "synthetic"
    assert phantom.nodule_index == round(0.35 * 64)
    png, caption = si.phantom_single(phantom, "medgemma", 96, 5.0)
    with Image.open(io.BytesIO(png)) as img:
        assert (img.size, img.mode) == ((96, 96), "RGB")
    assert "MedGemma RGB" in caption
    images, captions, indices = si.view_images(phantom.study, "lung", 4, 64, 5.0)
    assert len(images) == len(captions) == len(indices) == 4
    assert not captions[0].startswith("IMAGE")


def _entry(case_id: str, lesions: list[tuple[float, float, str]], nz: int = 64) -> IndexEntry:
    les = [
        LesionAnnotation(label=label, center_zyx=(z, 1.0, 1.0), diameter_mm=d)
        for z, d, label in lesions
    ]
    return IndexEntry(
        dataset="lidc_idri",
        case_id=case_id,
        patient_id=case_id,
        series_uid=f"1.2.{case_id}",
        path=f"raw/lidc_idri/{case_id}",
        stratum="nodule" if les else "negative",
        n_slices=nz,
        spacing_mm=(5.0, 0.7, 0.7),
        qc_adequate=True,
        qc_limitations=[],
        reference=ReferenceLabels(
            dataset="lidc_idri",
            patient_id=case_id,
            study_uid=case_id,
            labels={"pulmonary_nodule": bool(les)},
            lesions=les,
        ),
        cues=HUCues(lung_z_extent=(5, 56)),
    )


def test_control_index_keeps_distance_from_every_lesion() -> None:
    entry = _entry("A", [(100.0, 10.0, "pulmonary_nodule"), (200.0, 40.0, "pulmonary_mass")])
    idx, gap = si.control_index(entry, 20, min_distance_mm=30.0, slab_mm=5.0) or (None, None)
    assert idx is not None
    assert gap is not None
    assert gap >= 30.0
    for z, d in ((100.0, 10.0), (200.0, 40.0)):
        assert abs(idx * 5.0 - z) - d / 2 - 2.5 >= 30.0
    second = si.control_index(entry, 20, min_distance_mm=30.0, slab_mm=5.0, used=[idx])
    assert second is not None
    assert second[0] != idx
    assert si.control_index(entry, 20, min_distance_mm=500.0, slab_mm=5.0) is None
    no_extent = entry.model_copy(update={"cues": HUCues()})
    assert si.control_index(no_extent, 0, min_distance_mm=0.0, slab_mm=0.0) is not None


def test_select_pairs_round_robin_cap_and_missing_controls() -> None:
    entries = [
        _entry("A", [(100.0, 10.0, "pulmonary_nodule"), (150.0, 4.0, "pulmonary_nodule")]),
        _entry("B", [(120.0, 2.0, "pulmonary_nodule"), (130.0, 8.0, "pulmonary_nodule")]),
        _entry("C", []),
        _entry("D", [(140.0, 6.0, "pulmonary_nodule")], nz=30),
    ]
    pairs, counts = si.select_pairs(
        entries, min_diameter_mm=3.0, max_lesions=3, min_distance_mm=30.0, slab_mm=5.0
    )
    assert counts["eligible_lesions"] == 4
    assert counts["selected"] == len(pairs) == 3
    assert len({p.entry.case_id for p in pairs[:2]}) == 2  # round-robin across patients
    assert all(p.lesion.diameter_mm >= 3.0 for p in pairs)
    assert all(p.control_distance_mm >= 30.0 for p in pairs)
    _, strict = si.select_pairs(
        entries, min_diameter_mm=3.0, max_lesions=10, min_distance_mm=400.0, slab_mm=5.0
    )
    assert strict["without_control"] == 4
    assert strict["selected"] == 0


def test_build_messages_layouts() -> None:
    question = sn.Question(kind="yes_no", text="Any of $n_images?", system="sys")
    item = _item(2)
    single = sn.build_messages(item, "single", question)
    assert single[0] == {"role": "system", "content": "sys"}
    assert len(single) == 2
    assert len(single[1]["images"]) == 2
    assert "IMAGE 1: cap 0\nIMAGE 2: cap 1" in single[1]["content"]
    assert single[1]["content"].endswith("Any of 2?")
    inter = sn.build_messages(item, "interleaved", question)
    assert [m.get("content") for m in inter[1:3]] == ["IMAGE 1: cap 0", "IMAGE 2: cap 1"]
    assert all(len(m["images"]) == 1 for m in inter[1:3])
    assert inter[-1] == {"role": "user", "content": "Any of 2?"}
    one = sn.build_messages(_item(1), "interleaved", sn.Question(kind="yes_no", text="q"))
    assert len(one) == 1
    assert one[0]["content"].startswith("The attached image is IMAGE 1.")
    none = replace_images(item, [])
    assert "images" not in sn.build_messages(none, "single", question)[1]


def replace_images(item: si.SanityItem, images: list[bytes]) -> si.SanityItem:
    from dataclasses import replace

    return replace(item, images=images)


def test_payload_schema_prefill_and_redaction() -> None:
    cfg = _cfg(top_logprobs=5, num_ctx=2048)
    qwen = load_model_config("qwen3-vl-4b-nothink", MODELS)
    payload = sn.build_payload(_item(2), "single", cfg, qwen)
    assert payload["think"] is False
    assert payload["messages"][-1] == {"role": "assistant", "content": "<think>\n\n</think>\n\n"}
    assert payload["logprobs"] is True
    assert payload["top_logprobs"] == 5
    assert payload["options"]["num_ctx"] == 2048
    assert payload["format"]["properties"]["confidence"]["enum"][-1] == 1.0
    redacted = sn.redact_payload(payload)
    user = redacted["messages"][0]
    assert "images" not in user
    assert user["image_bytes_omitted"] is True
    assert user["image_sha256"] == _item(2).image_sha256
    medgemma = load_model_config("medgemma1.5-q4", MODELS)
    free = _cfg(test="description", question={"kind": "free_text", "text": "d"})
    plain = sn.build_payload(_item(1), "single", free, medgemma)
    assert "format" not in plain
    assert "logprobs" not in plain
    assert "think" not in plain
    choice = sn.answer_schema(sn.Question(kind="choice", text="c"), 4)
    assert choice is not None
    assert choice["properties"]["image"]["enum"] == [1, 2, 3, 4]
    no_lp = sn.build_payload(_item(1), "single", _cfg(top_logprobs=0), medgemma)
    assert "logprobs" not in no_lp


def _lp(token: str, alts: dict[str, float]) -> dict[str, Any]:
    return {
        "token": token,
        "logprob": alts.get(token, -1.0),
        "top_logprobs": [{"token": t, "logprob": v} for t, v in alts.items()],
    }


def test_yes_and_choice_probabilities_from_logprobs() -> None:
    lps = [
        _lp('{"', {'{"': 0.0}),
        _lp("yes", {"yes": math.log(0.6), "Yes": math.log(0.1), "no": math.log(0.3), "x": -1}),
    ]
    assert sn.yes_probability(lps) == pytest.approx(0.7)
    assert sn.yes_probability("bad") is None
    assert sn.yes_probability([_lp("no", {"maybe": -0.1})]) is None
    assert sn.yes_probability([{"token": "no", "top_logprobs": [{"token": "no"}]}]) is None
    probs = sn.choice_probabilities([_lp("3", {"3": math.log(0.5), "1": math.log(0.5)})], 4)
    assert probs == {1: 0.5, 2: 0.0, 3: 0.5, 4: 0.0}
    assert sn.choice_probabilities(None, 4) is None
    assert sn.choice_probabilities([_lp("3", {"9": -0.1})], 4) is None


def test_parse_answer_variants() -> None:
    yes_no = sn.Question(kind="yes_no", text="q")
    body = {
        "message": {"content": '{"nodule": "no", "confidence": 0.8}', "thinking": "abc"},
        "done_reason": "stop",
        "prompt_eval_count": 300,
        "eval_count": 9,
        "logprobs": [_lp("no", {"no": math.log(0.75), "yes": math.log(0.25)})],
    }
    parsed = sn.parse_answer(yes_no, body, 1)
    assert parsed["answer"] == "no"
    assert parsed["stated_p_yes"] == pytest.approx(0.2)
    assert parsed["p_yes"] == pytest.approx(0.25)
    assert parsed["thinking_chars"] == 3
    assert parsed["prompt_tokens"] == 300
    weird = {"message": {"content": '{"nodule": "maybe", "confidence": 3}'}}
    got = sn.parse_answer(yes_no, weird, 1)
    assert got["answer"] is None
    assert got["confidence"] is None
    assert got["stated_p_yes"] is None
    assert sn.parse_answer(yes_no, {"message": {"content": "[1]"}}, 1)["answer"] is None
    assert sn.parse_answer(yes_no, None, 1) == {"answer": None, "parse": "no response"}
    assert sn.parse_answer(yes_no, {"message": "x"}, 1)["parse"] == "empty output"
    choice = sn.Question(kind="choice", text="c")
    assert sn.parse_answer(choice, {"message": {"content": '{"image": 2}'}}, 4)["answer"] == 2
    assert sn.parse_answer(choice, {"message": {"content": '{"image": 7}'}}, 4)["answer"] is None
    free = sn.Question(kind="free_text", text="d")
    text = sn.parse_answer(free, {"message": {"content": "A chest CT."}}, 1)
    assert text["answer"] == "A chest CT."
    assert text["parse"] == "free text"
    assert sn.parse_answer(free, {"message": {"content": " "}}, 1)["parse"] == "empty output"


def _rec(**fields: Any) -> dict[str, Any]:
    base = {
        "model": "m",
        "window": "lung",
        "layout": "single",
        "group": "g",
        "condition": "real",
        "truth": 1,
        "patient": "p",
        "answer": "yes",
        "p_yes": 0.5,
        "stated_p_yes": 0.5,
        "captions": ["a", "b", "c", "d"],
    }
    return base | fields


def test_binary_metrics_and_paired_win_rate() -> None:
    records = [
        _rec(truth=1, patient=f"p{k}", group=f"g{k}", condition="lesion", p_yes=0.6 + k / 100)
        for k in range(10)
    ] + [
        _rec(truth=0, patient=f"p{k}", group=f"g{k}", condition="control", p_yes=0.5, answer="no")
        for k in range(10)
    ]
    records[0]["answer"] = None
    out = sn.binary_metrics(records, n_boot=50, seed=0)
    assert out["n"] == 20
    assert out["patients"] == 10
    assert out["unparsed"] == 1
    assert out["auroc_p_yes"] == 1.0
    assert out["auroc_p_yes_ci95"] == [1.0, 1.0]
    assert out["sensitivity"] == 1.0
    assert out["specificity"] == 1.0
    assert out["yes_rate_negatives"] == 0.0
    assert out["distinct_stated_p_yes"] == 1
    assert sn.binary_metrics(records, n_boot=0, seed=0)["auroc_p_yes_ci95"] is None
    win = sn.paired_win_rate(records, "lesion", "control")
    assert win == {"pairs": 10, "win_rate": 1.0}
    tie = [_rec(condition="a", p_yes=0.3), _rec(condition="b", p_yes=0.3), _rec(p_yes=None)]
    assert sn.paired_win_rate(tie, "a", "b") == {"pairs": 1, "win_rate": 0.5}
    lose = [_rec(condition="a", p_yes=0.1), _rec(condition="b", p_yes=0.3)]
    assert sn.paired_win_rate(lose, "a", "b")["win_rate"] == 0.0
    assert sn.paired_win_rate([], "a", "b") == {"pairs": 0, "win_rate": None}


def test_test_specific_aggregates() -> None:
    dep = [
        _rec(condition="real", p_yes=0.9, confidence=0.9, prompt_tokens=300),
        _rec(condition="gray", p_yes=0.9),
        _rec(condition="noise", p_yes=0.8),
        _rec(condition="none", p_yes=None),
    ]
    rows = sn.image_dependence_metrics(dep)
    assert rows[0]["same_answer_real_gray_noise"] is True
    assert rows[0]["delta_p_yes_noise"] == pytest.approx(0.1)
    assert "delta_p_yes_none" not in rows[0]
    target = [
        _rec(condition="nodule30mm", truth=1, p_yes=0.9),
        _rec(condition="none", truth=0, p_yes=0.2, answer="no"),
        _rec(condition="none", truth=0, p_yes=0.3, answer=None, group="h"),
    ]
    trows = sn.obvious_target_metrics(target)
    by = {r["condition"]: r for r in trows}
    assert by["nodule30mm"]["win_rate"] == 1.0
    assert by["nodule30mm"]["auroc_vs_none"] == 1.0
    assert by["none"]["unparsed"] == 1
    binding = [
        _rec(truth=k % 4 + 1, answer=1, choice_probabilities={1: 0.7, 2: 0.1, 3: 0.1, 4: 0.1})
        for k in range(20)
    ]
    brow = sn.binding_metrics(binding)[0]
    assert brow["correct"] == 5
    assert brow["chance"] == 5.0
    assert brow["passes_90pct"] is False
    assert brow["answers"] == {"1": 20}
    assert brow["mean_p_correct"] == pytest.approx(0.25)
    pairs = [
        _rec(condition="lesion", truth=1, size_bin="3-6 mm", group="a"),
        _rec(condition="control", truth=0, answer="no", group="a"),
    ]
    prow = sn.paired_slab_metrics(pairs, n_boot=0, seed=0)[0]
    assert prow["by_size"] == {"3-6 mm": {"n": 1, "yes": 1, "mean_p_yes": 0.5}}
    assert prow["paired_pairs"] == 1


def test_limit_groups_keeps_whole_groups() -> None:
    items = [si.SanityItem(f"k{n}", f"g{n // 2}", "c", [], [], None, "p") for n in range(6)]
    assert [i.key for i in sn.limit_groups(items, 2)] == ["k0", "k1", "k2", "k3"]
    assert sn.limit_groups(items, None) == items


def test_item_describe_has_digests_not_pixels() -> None:
    item = _item(2)
    described = item.describe()
    assert described["image_sha256"] == [hashlib.sha256(i).hexdigest() for i in item.images]
    assert base64.b64encode(item.images[0]).decode() not in str(described)
