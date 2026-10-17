# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from thoraxbench.adapters.heuristic import heuristic_findings
from thoraxbench.config import get_settings
from thoraxbench.sampling import STRATEGIES, get_strategy
from thoraxbench.schemas import AnalysisRequest
from thoraxbench.study import Study, StudyLoadError, load_study_dir
from thoraxbench.views import get_view, render_slice_png


@pytest.fixture(scope="module")
def study(phantom_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Study:
    cache = tmp_path_factory.mktemp("cache")
    first = load_study_dir(phantom_dir, dataset="phantom", cache_dir=cache)
    # second load hits the npz cache
    second = load_study_dir(
        phantom_dir, dataset="phantom", cache_dir=cache, series_uid=first.volume.series_uid
    )
    assert np.array_equal(first.volume.hu, second.volume.hu)
    assert second.qc.to_dict() == first.qc.to_dict()
    assert second.selection == first.selection
    return second


def test_study_basics(study: Study) -> None:
    assert study.case_id == study.patient_id == "PHANTOM-0001"
    assert study.cues is study.cues  # computed once
    assert study.qc.adequate


def test_load_error(tmp_path: Path) -> None:
    with pytest.raises(StudyLoadError):
        load_study_dir(tmp_path)


@pytest.mark.parametrize("sid", sorted(STRATEGIES))
def test_strategies_deterministic(study: Study, sid: str) -> None:
    strat = get_strategy(sid, n=8)
    a = strat.select(study.volume, study.cues)
    b = get_strategy(sid, n=8).select(study.volume, study.cues)
    assert a == b
    assert a.indices == sorted(set(a.indices))
    assert len(a.indices) == len(a.tags)
    assert all(0 <= i < study.volume.shape[0] for i in a.indices)
    assert len(strat.sha256) == 64
    assert strat.params["n"] == 8


def test_anatomy_covers_landmarks(study: Study) -> None:
    sel = get_strategy("anatomy", n=12).select(study.volume, study.cues)
    joined = " | ".join(sel.tags)
    for tag in ("apex", "carina", "lung bases", "upper abdomen"):
        assert tag in joined


def test_anatomy_without_landmarks(study: Study) -> None:
    cues = study.cues.model_copy(update={"landmarks": None, "lung_z_extent": None})
    sel = get_strategy("anatomy", n=12).select(study.volume, cues)
    assert "carina" in sel.tags


def test_two_stage_and_mip(study: Study) -> None:
    sel = get_strategy("two_stage", n=6).select(study.volume, study.cues)
    assert any(t.startswith("candidate") for t in sel.tags) or study.cues.nodule_candidates == []
    mip = get_strategy("mip_slabs", n=3, slab_mm=10.0).select(study.volume, study.cues)
    assert len(mip.indices) <= 3
    assert mip.slab_mm >= 10.0
    assert get_strategy("contact_sheet", n=4).select(study.volume, study.cues).montage


@pytest.mark.parametrize(
    "view_id",
    ["medgemma_ct_v1", "generic_multislice_v1", "multiwindow_separate_v1", "contact_sheet_v1"],
)
def test_image_views(study: Study, view_id: str) -> None:
    view = get_view(view_id, n=6, size=128)
    prep = view.build(study, AnalysisRequest())
    assert prep.images
    assert len(prep.images) == len(prep.image_captions)
    img = Image.open(io.BytesIO(prep.images[-1]))
    assert img.format == "PNG"
    assert "Deterministic measurements" in prep.context
    assert prep.meta["view_sha256"] == view.sha256  # type: ignore[union-attr]
    if view_id != "contact_sheet_v1":
        assert prep.image_captions[0].startswith("Image 1: coronal")


def test_mip_view_and_inadequate_context(study: Study) -> None:
    view = get_view("generic_multislice_v1", n=4, size=64, slab_mm=10.0, coronal=False)
    bad = Study("p", "c", "p", study.volume, _cues=study.cues)
    bad.volume.qc.warnings.append("synthetic warning")
    prep = view.build(bad, AnalysisRequest())
    assert "10 mm MIP" in prep.image_captions[0]
    bad.volume.qc.warnings.pop()


def test_render_slice_png(study: Study) -> None:
    for window in ("lung", "medgemma", "bone"):
        data = render_slice_png(study.volume.hu[10], window, size=64)
        assert Image.open(io.BytesIO(data)).size == (64, 64)


@pytest.mark.parametrize(
    ("view_id", "shape"), [("ct_clip_v1", (1, 240, 480, 480)), ("m3d_lamed_v1", (1, 32, 256, 256))]
)
def test_tensor_views(study: Study, tmp_path: Path, view_id: str, shape: tuple[int, ...]) -> None:
    prep = get_view(view_id, cache_dir=tmp_path).build(study, AnalysisRequest())
    assert prep.tensor_path is not None
    arr = np.load(prep.tensor_path)
    assert arr.shape == shape
    assert prep.meta["shape"] == list(shape)


def test_unknown_view() -> None:
    with pytest.raises(KeyError):
        get_view("nope")


def test_heuristic_on_real_cues(study: Study) -> None:
    from thoraxbench.adapters.factory import load_model

    model = load_model("heuristic-hu", get_settings())
    req = AnalysisRequest()
    report = model.parse(model.infer(model.prepare(study, req), req))
    labels = {f.label for f in report.findings}
    assert {"emphysema", "pleural_effusion", "consolidation", "ground_glass_opacity"} <= labels
    # phantom has an effusion and an 8 mm radius nodule
    assert report.label_probability("pleural_effusion") is not None
    raw = heuristic_findings({"metal_voxels": 50})
    assert any(f["label"] == "medical_device" for f in raw["findings"])


def test_cue_ablation_hash_and_actual_context(study: Study) -> None:
    from thoraxbench.views.builders import MultiSliceView

    with_cues = MultiSliceView("medgemma_ct_v1", "medgemma", n=2, size=64, coronal=False)
    without_cues = MultiSliceView(
        "medgemma_ct_v1", "medgemma", n=2, size=64, coronal=False, include_cues=False
    )
    assert with_cues.sha256 != without_cues.sha256
    prepared = without_cues.build(study, AnalysisRequest())
    assert prepared.context == ""
    assert prepared.meta["include_cues"] is False
    assert prepared.images == with_cues.build(study, AnalysisRequest()).images


@pytest.mark.parametrize("invalid", [None, 0, 1, "false", "true"])
def test_cue_ablation_rejects_non_boolean_configuration(invalid: object) -> None:
    from thoraxbench.views.builders import get_view

    with pytest.raises(ValueError, match="include_cues must be a boolean"):
        get_view("medgemma_ct_v1", include_cues=invalid)


def test_default_caption_style_keeps_historical_view_hash() -> None:
    # view_sha256 recorded by the E001-cue-ablation run (with_cues, v0.3.16).
    view = get_view(
        "medgemma_ct_v1", strategy="anatomy", n=9, size=256, coronal=False, include_cues=True
    )
    assert view.sha256 == "14c227e7abb070208acc0344f6118781d75c33f2457da139805b49f8dbea09b5"
    strict = get_view(
        "medgemma_ct_v1",
        strategy="anatomy",
        n=9,
        size=256,
        coronal=False,
        include_cues=True,
        caption_style="image_only",
    )
    assert strict.sha256 != view.sha256


def test_image_only_captions_name_no_source_slice(study: Study) -> None:
    view = get_view(
        "medgemma_ct_v1",
        strategy="lung_extent",
        n=6,
        slab_mm=5.0,
        size=64,
        coronal=False,
        include_cues=False,
        caption_style="image_only",
    )
    prepared = view.build(study, AnalysisRequest())
    n = len(prepared.images)
    assert n == len(prepared.image_captions) >= 3
    assert prepared.context == ""
    assert prepared.meta["caption_style"] == "image_only"
    for k, caption in enumerate(prepared.image_captions, start=1):
        assert caption.startswith(f"IMAGE {k}: axial, MedGemma RGB")
        assert "slice " not in caption.replace("single", "")
        assert "z=" not in caption
        assert "/" not in caption.split("level:")[0].replace("wide/soft-tissue/narrow", "")
        assert "mm MIP slab" in caption
    assert "upper third" in prepared.image_captions[0]
    assert "lower third" in prepared.image_captions[-1]
    single = get_view(
        "medgemma_ct_v1",
        strategy="uniform",
        n=2,
        size=64,
        coronal=False,
        caption_style="image_only",
    ).build(study, AnalysisRequest())
    assert all("single" in c and "third" not in c for c in single.image_captions)


def test_caption_style_is_validated() -> None:
    with pytest.raises(ValueError, match="caption_style"):
        get_view("medgemma_ct_v1", caption_style="slices")
