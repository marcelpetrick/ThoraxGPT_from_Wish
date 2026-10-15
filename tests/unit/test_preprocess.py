# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
import numpy as np
import pytest

from thoraxbench.dicom.volume import QCReport, Volume
from thoraxbench.preprocess import (
    MEDGEMMA_RGB_WINDOWS,
    WINDOWS,
    Window,
    apply_range,
    apply_window,
    body_mask,
    coronal_reformat,
    hu_cues,
    lung_mask,
    lung_z_extent,
    mip_slab,
    rgb_encode,
)
from thoraxbench.preprocess.cues import _agatston_weight
from thoraxbench.synthetic import PhantomSpec, make_phantom


def _volume(hu: np.ndarray, spacing: tuple[float, float, float]) -> Volume:
    qc = QCReport(
        n_slices=hu.shape[0],
        spacing_mm=spacing,
        axial_coverage_mm=0.0,
        hu_min=0,
        hu_max=0,
        hu_percentiles={},
        gaps_mm=[],
        duplicates_removed=0,
        non_uniform_spacing=False,
        gantry_tilt_suspected=False,
        lung_voxel_fraction=0.0,
        body_region_confidence=0.0,
        contrast=None,
        kernel=None,
        selected_series_reason="",
    )
    return Volume(
        hu=hu,
        spacing_mm=spacing,
        patient_id="p",
        study_uid="s",
        series_uid="se",
        z_positions_mm=[float(i) for i in range(hu.shape[0])],
        qc=qc,
    )


def _phantom(**kw: object) -> Volume:
    spec = PhantomSpec(**kw)  # type: ignore[arg-type]
    return _volume(make_phantom(spec), spec.spacing_mm)


def test_windows() -> None:
    assert WINDOWS["lung"].low == -1350
    assert WINDOWS["lung"].high == 150
    out = apply_window(np.array([-2000, -600, 2000]), -600, 1500)
    assert out.tolist() == [0, 128, 255]
    assert apply_range([0, 80], 0, 80).tolist() == [0, 255]
    with pytest.raises(ValueError, match="must exceed"):
        apply_range([0], 5, 5)
    assert Window.from_range(-1024, 1024) == MEDGEMMA_RGB_WINDOWS[0]
    assert rgb_encode(np.zeros((2, 2), dtype=np.int16)).shape == (2, 2, 3)


def test_masks_and_reformat() -> None:
    vol = _phantom(shape=(32, 64, 64))
    original = vol.hu.copy()
    body = body_mask(vol.hu)
    lungs = lung_mask(vol.hu, body)
    assert body.sum() > lungs.sum() > 0
    ext = lung_z_extent(lungs)
    assert ext is not None
    assert 0 < ext[0] < ext[1] < 31
    assert lung_z_extent(np.zeros((3, 2, 2), dtype=bool)) is None
    assert lung_mask(np.full((4, 8, 8), -1000, dtype=np.int16)).sum() == 0
    mip = mip_slab(vol.hu, 10, 10.0, 5.0)
    assert mip.shape == (64, 64)
    assert (mip >= vol.hu[10]).all()
    with pytest.raises(IndexError):
        mip_slab(vol.hu, 99, 10.0, 5.0)
    cor = coronal_reformat(vol.hu, vol.spacing_mm, slab_mm=5.0)
    assert cor.shape == (64, 64)  # 32 * 5 mm / 2.5 mm
    same = coronal_reformat(vol.hu, (2.5, 2.5, 2.5), y_index=10)
    assert same.shape == (32, 64)
    assert np.array_equal(vol.hu, original)


def test_cues_normal_phantom() -> None:
    cues = hu_cues(_phantom())
    assert cues.lung_z_extent is not None
    assert cues.landmarks is not None
    lm = cues.landmarks
    assert lm.apex <= lm.carina <= lm.base
    assert lm.carina_method == "fraction"
    assert cues.emphysema_laa950_pct < 1.0
    assert cues.nodule_candidates == []
    assert cues.metal_components == 0
    assert cues.pleural_air_ml == 0.0
    assert "thick_slices" in cues.coverage_flags
    assert "Deterministic measurements" in cues.summary()


def test_cues_findings_phantom() -> None:
    vol = _phantom(nodule_radius_mm=8.0, effusion=True, emphysema=True, coronary_calcification=True)
    vol.hu[30:33, 60:63, 60:63] = 3000  # metal device
    cues = hu_cues(vol)
    assert cues.emphysema_laa950_pct > 10
    assert cues.pleural_fluid_ml["right"] > 10
    assert cues.pleural_fluid_ml["right"] > cues.pleural_fluid_ml["left"]
    assert cues.pleural_fluid_depth_mm["right"] > 0
    assert cues.cardiac_calcium_ml > 0
    assert cues.agatston_like > 0
    assert cues.metal_components == 1
    assert any(c.side == "right" and 10 <= c.diameter_mm <= 20 for c in cues.nodule_candidates)
    text = cues.summary()
    assert "largest candidates" in text


def test_cues_pleural_air_and_coverage() -> None:
    vol = _phantom(shape=(40, 128, 128), spacing_mm=(2.0, 2.5, 2.5))
    vol.hu[10:25, 50:80, 15:30] = -1000  # lateral air pocket (right side)
    cues = hu_cues(vol)
    assert cues.pleural_air_ml > 2.0
    assert "thick_slices" not in cues.coverage_flags
    cut = _phantom(shape=(40, 128, 128))
    cut_cues = hu_cues(_volume(cut.hu[5:30], cut.spacing_mm))
    assert "incomplete_coverage_apex" in cut_cues.coverage_flags
    assert "incomplete_coverage_base" in cut_cues.coverage_flags


def test_cues_no_lung_and_downsample() -> None:
    cues = hu_cues(_volume(np.full((4, 8, 8), 40, dtype=np.int16), (1.0, 1.0, 1.0)))
    assert "no_lung_found" in cues.coverage_flags
    assert "no aerated lung" in cues.summary()
    big = _phantom(shape=(16, 400, 400), spacing_mm=(5.0, 0.8, 0.8))
    assert hu_cues(big).downsample == 2


def test_cues_airway_carina() -> None:
    vol = _phantom(shape=(64, 128, 128))
    # trachea: midline air column in the upper slices
    vol.hu[2:20, 60:66, 61:67] = -1000
    lm = hu_cues(vol).landmarks
    assert lm is not None
    assert lm.carina_method == "airway"


@pytest.mark.parametrize(("hu", "w"), [(150, 1), (250, 2), (350, 3), (500, 4)])
def test_agatston_weight(hu: float, w: int) -> None:
    assert _agatston_weight(hu) == w
