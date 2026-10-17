# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Detector reference baseline: bundle pinning, geometry, adapter (stub network), crops."""

from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import numpy.typing as npt
import pytest
from PIL import Image

import thoraxbench.adapters.monai_detector as adapter_module
import thoraxbench.benchmark.checkpoint as checkpoint_module
import thoraxbench.detectors.bundle as bundle_module
import thoraxbench.detectors.retinanet as retinanet_module
from thoraxbench.adapters import MonaiDetectorModel, load_model, load_model_config
from thoraxbench.benchmark.checkpoint import runtime_identity
from thoraxbench.config import REPO_ROOT, Settings
from thoraxbench.detectors.bundle import (
    BundleFile,
    BundleIntegrityError,
    bundle_dir,
    fetch_bundle,
    file_url,
    verify_bundle,
    verify_file,
)
from thoraxbench.detectors.preprocess import (
    HU_RANGE,
    BundleGeometry,
    box_to_mm,
    bundle_input,
    candidates_from_boxes,
    mm_to_box,
    preprocess_sha256,
)
from thoraxbench.detectors.retinanet import (
    DEVICE_ENV,
    Detections,
    DetectorParams,
    cached_backend,
    detector_packages_available,
)
from thoraxbench.dicom import QCReport, Volume
from thoraxbench.schemas import AnalysisRequest, LesionCandidate, RawOutput
from thoraxbench.scoring import possible_training_overlap
from thoraxbench.views import CROP_VIEW_ID, CandidateCropView

REQ = AnalysisRequest(labels=["pulmonary_nodule"])


def _volume(hu: npt.NDArray[np.int16], spacing: tuple[float, float, float]) -> Volume:
    qc = QCReport(
        n_slices=hu.shape[0],
        spacing_mm=spacing,
        axial_coverage_mm=hu.shape[0] * spacing[0],
        hu_min=int(hu.min()),
        hu_max=int(hu.max()),
        hu_percentiles={},
        gaps_mm=[],
        duplicates_removed=0,
        non_uniform_spacing=False,
        gantry_tilt_suspected=False,
        lung_voxel_fraction=0.5,
        body_region_confidence=1.0,
        contrast=None,
        kernel=None,
        selected_series_reason="synthetic",
    )
    return Volume(
        hu=hu,
        spacing_mm=spacing,
        patient_id="p",
        study_uid="s",
        series_uid="se",
        z_positions_mm=[float(i) * spacing[0] for i in range(hu.shape[0])],
        qc=qc,
    )


def _sphere_volume(
    centre_mm: tuple[float, float, float],
    radius_mm: float,
    shape: tuple[int, int, int] = (40, 64, 64),
    spacing: tuple[float, float, float] = (2.5, 1.5, 1.5),
) -> Volume:
    z, y, x = np.meshgrid(
        *(np.arange(n) * s for n, s in zip(shape, spacing, strict=True)), indexing="ij"
    )
    dist = np.sqrt((z - centre_mm[0]) ** 2 + (y - centre_mm[1]) ** 2 + (x - centre_mm[2]) ** 2)
    hu = np.full(shape, -850, dtype=np.int16)
    hu[dist <= radius_mm] = 40
    return _volume(hu, spacing)


@dataclass
class _Study:
    volume: Volume
    dataset: str = "lidc_idri"


@dataclass
class StubBackend:
    """Stand-in network: one box per configured millimetre centre, fixed scores."""

    geometry: BundleGeometry
    centres: list[tuple[tuple[float, float, float], float]]
    seen: list[tuple[int, ...]] = field(default_factory=list)

    def detect(self, volume_xyz: npt.NDArray[np.float32]) -> Detections:
        self.seen.append(volume_xyz.shape)
        assert 0.0 <= float(volume_xyz.min()) <= float(volume_xyz.max()) <= 1.0
        boxes = [mm_to_box(c, (6.0, 6.0, 6.0), self.geometry) for c, _ in self.centres]
        return Detections(
            boxes=np.asarray(boxes, dtype=np.float64).reshape(-1, 6),
            scores=np.asarray([s for _, s in self.centres], dtype=np.float64),
            meta={"device": "stub", "peak_rss_bytes": 1},
        )


@pytest.fixture
def fake_weights(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """A tiny fake state dict pinned in place of the real weights (no real weights in CI)."""
    settings = Settings(repo_root=REPO_ROOT, data_dir=tmp_path / "data")
    payload = b"not-a-real-state-dict"
    item = BundleFile("models/model.pt", len(payload), hashlib.sha256(payload).hexdigest())
    target = bundle_dir(settings) / item.path
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    for module in (adapter_module, checkpoint_module):
        monkeypatch.setattr(module, "WEIGHTS_ITEM", item)
    monkeypatch.setattr(adapter_module, "detector_packages_available", lambda: True)
    return settings


# --- bundle pinning ---------------------------------------------------------------------


def _pin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: bytes) -> BundleFile:
    item = BundleFile("docs/x.txt", len(payload), hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(bundle_module, "BUNDLE_FILES", (item,))
    return item


def test_bundle_files_are_pinned_to_one_revision() -> None:
    assert bundle_module.WEIGHTS_ITEM.path == "models/model.pt"
    assert all(len(f.sha256) == 64 for f in bundle_module.BUNDLE_FILES)
    assert not any(f.path.endswith(".ts") for f in bundle_module.BUNDLE_FILES)
    url = file_url(bundle_module.WEIGHTS_ITEM)
    assert bundle_module.BUNDLE_REVISION in url
    assert url.startswith("https://huggingface.co/MONAI/lung_nodule_ct_detection/resolve/")


def test_verify_file_rejects_missing_wrong_size_hash_and_symlink(tmp_path: Path) -> None:
    payload = b"abc"
    item = BundleFile("f.bin", 3, hashlib.sha256(payload).hexdigest())
    with pytest.raises(BundleIntegrityError, match="missing"):
        verify_file(tmp_path, item)
    (tmp_path / "f.bin").write_bytes(b"abcd")
    with pytest.raises(BundleIntegrityError, match="size"):
        verify_file(tmp_path, item)
    (tmp_path / "f.bin").write_bytes(b"abd")
    with pytest.raises(BundleIntegrityError, match="checksum"):
        verify_file(tmp_path, item)
    (tmp_path / "f.bin").write_bytes(payload)
    assert verify_file(tmp_path, item) == item.sha256
    (tmp_path / "real.bin").write_bytes(payload)
    (tmp_path / "f.bin").unlink()
    (tmp_path / "f.bin").symlink_to(tmp_path / "real.bin")
    with pytest.raises(BundleIntegrityError, match="symlink"):
        verify_file(tmp_path, item)


def test_fetch_requires_acknowledgement(tmp_path: Path) -> None:
    settings = Settings(repo_root=REPO_ROOT, data_dir=tmp_path)
    with pytest.raises(PermissionError, match="terms"):
        fetch_bundle(settings, acknowledge_license=False)
    assert not (tmp_path / "models").exists()


def test_fetch_downloads_verifies_and_skips_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"bundle terms"
    item = _pin(tmp_path, monkeypatch, payload)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=payload)

    settings = Settings(repo_root=REPO_ROOT, data_dir=tmp_path)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    messages: list[str] = []
    assert fetch_bundle(
        settings, acknowledge_license=True, client=client, progress=messages.append
    ) == {item.path: item.sha256}
    assert calls == [file_url(item)]
    assert (bundle_dir(settings) / item.path).read_bytes() == payload
    fetch_bundle(settings, acknowledge_license=True, client=client)
    assert len(calls) == 1  # verified file kept, not downloaded again
    assert verify_bundle(settings) == {item.path: item.sha256}
    assert any("downloading" in m for m in messages)


@pytest.mark.parametrize("served", [b"tampered!!!!", b"too long payload bytes"])
def test_fetch_rejects_and_deletes_altered_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: bytes
) -> None:
    item = _pin(tmp_path, monkeypatch, b"bundle terms")
    settings = Settings(repo_root=REPO_ROOT, data_dir=tmp_path)
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, content=served))
    )
    with pytest.raises(BundleIntegrityError, match="failed verification"):
        fetch_bundle(settings, acknowledge_license=True, client=client)
    folder = bundle_dir(settings) / "docs"
    assert not (folder / "x.txt").exists()
    assert not list(folder.glob("*.partial"))
    assert item.path == "docs/x.txt"


def test_fetch_owns_and_closes_default_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"bundle terms"
    _pin(tmp_path, monkeypatch, payload)
    created: list[httpx.Client] = []
    real_client = httpx.Client

    def factory(**kwargs: Any) -> httpx.Client:
        assert kwargs["trust_env"] is False
        client = real_client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200, content=payload))
        )
        created.append(client)
        return client

    monkeypatch.setattr(bundle_module.httpx, "Client", factory)
    fetch_bundle(Settings(repo_root=REPO_ROOT, data_dir=tmp_path), acknowledge_license=True)
    assert created[0].is_closed


# --- preprocessing and geometry ---------------------------------------------------------


def test_bundle_input_scales_resamples_and_orients_ras() -> None:
    volume = _sphere_volume((50.0, 30.0, 20.0), 4.0)
    arr, geometry = bundle_input(volume.hu, volume.spacing_mm)
    nz, ny, nx = geometry.resampled_shape_zyx
    assert arr.shape == (nx, ny, nz)
    assert arr.dtype == np.float32
    assert float(arr.min()) >= 0.0
    assert float(arr.max()) <= 1.0
    # brightest voxel (the sphere) maps back to its millimetre centre
    i, j, k = np.unravel_index(int(np.argmax(arr)), arr.shape)
    centre, _ = box_to_mm([i, j, k, i, j, k], geometry)
    assert math.dist(centre, (50.0, 30.0, 20.0)) < 4.0
    # RAS: patient right (x = 0 mm) is the high-index end of axis 0
    assert geometry.source_shape_zyx == (40, 64, 64)
    eff = geometry.effective_spacing_zyx
    assert eff[0] == pytest.approx(1.25, rel=0.02)
    assert eff[2] == pytest.approx(0.703125, rel=0.02)
    assert geometry.to_dict()["effective_spacing_zyx"] == eff


def test_bundle_input_intensity_window() -> None:
    hu = np.array([[[-2000, -1024, 300, 3000]]], dtype=np.int16)
    arr, geometry = bundle_input(hu, (1.25, 0.703125, 0.703125))
    assert sorted(arr.ravel().tolist()) == [0.0, 0.0, 1.0, 1.0]
    assert HU_RANGE == (-1024.0, 300.0)
    assert geometry.effective_spacing_zyx[0] == 1.25  # single slice keeps its spacing
    with pytest.raises(ValueError, match="non-empty"):
        bundle_input(np.zeros((0, 2, 2), dtype=np.int16), (1.0, 1.0, 1.0))


def test_box_round_trip_and_candidate_conversion() -> None:
    geometry = BundleGeometry((40, 64, 64), (2.5, 1.5, 1.5), (80, 137, 137))
    box = mm_to_box((60.0, 40.0, 25.0), (5.0, 8.0, 6.0), geometry)
    centre, extent = box_to_mm(box, geometry)
    assert centre == pytest.approx((60.0, 40.0, 25.0))
    assert extent == pytest.approx((5.0, 8.0, 6.0))
    far = mm_to_box((10.0, 10.0, 10.0), (4.0, 4.0, 4.0), geometry)
    cands = candidates_from_boxes([far, box], [0.3, 0.9], geometry)
    assert [c.score for c in cands] == [0.9, 0.3]
    assert cands[0].diameter_mm == pytest.approx(8.0)
    assert cands[0].label == "pulmonary_nodule"
    assert candidates_from_boxes(np.zeros((0, 6)), [], geometry) == []
    with pytest.raises(ValueError, match="length"):
        candidates_from_boxes([box], [0.1, 0.2], geometry)
    assert len(preprocess_sha256()) == 64


def test_lesion_candidate_schema_bounds() -> None:
    with pytest.raises(ValueError, match="less than or equal to 1"):
        LesionCandidate(center_zyx_mm=(0, 0, 0), score=1.5)
    with pytest.raises(ValueError, match="Extra inputs"):
        LesionCandidate(center_zyx_mm=(0, 0, 0), score=0.5, unexpected=1)  # type: ignore[call-arg]


# --- backend helpers --------------------------------------------------------------------


def test_detector_params_and_device_override(monkeypatch: pytest.MonkeyPatch) -> None:
    params = DetectorParams()
    assert params.roi_size_xyz == (256, 256, 128)
    monkeypatch.setenv(DEVICE_ENV, "CPU")
    assert params.resolved_device_request() == "cpu"
    monkeypatch.setenv(DEVICE_ENV, "tpu")
    assert params.resolved_device_request() == "auto"
    with pytest.raises(ValueError, match="String should match"):
        DetectorParams(device="tpu")
    with pytest.raises(ValueError, match="Extra inputs"):
        DetectorParams.model_validate({"unknown": 1})
    assert isinstance(detector_packages_available(), bool)


def test_peak_memory_helpers() -> None:
    assert retinanet_module._peak_rss_bytes() > 0
    reset = retinanet_module._reset_peak_rss()
    hwm = retinanet_module._vm_hwm_bytes()
    assert isinstance(reset, bool)
    assert hwm is None or hwm > 0


def test_cached_backend_reuses_instances(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[Any] = []

    class Fake:
        def __init__(self, weights: Path, params: DetectorParams) -> None:
            built.append((weights, params))

        def detect(self, volume_xyz: Any) -> Detections:  # pragma: no cover - not called
            raise NotImplementedError

    monkeypatch.setattr(retinanet_module, "RetinaNetBackend", Fake)
    monkeypatch.setattr(retinanet_module, "_BACKENDS", {})
    a = cached_backend(Path("w"), "h1", DetectorParams())
    b = cached_backend(Path("w"), "h1", DetectorParams())
    c = cached_backend(Path("w"), "h2", DetectorParams())
    assert a is b
    assert a is not c
    assert len(built) == 2


# --- adapter ----------------------------------------------------------------------------


def _model(
    settings: Settings, centres: list[tuple[tuple[float, float, float], float]]
) -> tuple[MonaiDetectorModel, list[StubBackend]]:
    config = load_model_config("monai-lung-nodule", settings.configs_dir / "models")
    made: list[StubBackend] = []
    holder: dict[str, BundleGeometry] = {}

    def factory(weights: Path, digest: str, params: DetectorParams) -> StubBackend:
        assert weights.is_file()
        assert params.score_thresh == 0.02
        backend = StubBackend(holder["geometry"], centres)
        made.append(backend)
        return backend

    model = MonaiDetectorModel(config, settings, backend_factory=factory)
    original = model.prepare

    def prepare(study: Any, request: AnalysisRequest) -> Any:
        prepared = original(study, request)
        holder["geometry"] = BundleGeometry(
            **{
                k: tuple(v)
                for k, v in prepared.meta["geometry"].items()
                if k != "effective_spacing_zyx"
            }
        )
        return prepared

    model.prepare = prepare  # type: ignore[method-assign]
    return model, made


def test_config_and_factory_build_the_detector(fake_weights: Settings) -> None:
    model = load_model("monai-lung-nodule", fake_weights)
    assert isinstance(model, MonaiDetectorModel)
    assert model.capabilities().localization
    assert model.available()
    identity = model.describe()
    assert identity["digest"] == adapter_module.WEIGHTS_ITEM.sha256
    assert identity["revision"] == bundle_module.BUNDLE_REVISION
    assert possible_training_overlap(model.config.family, "lidc_idri") == "yes"
    assert possible_training_overlap(model.config.family, "nsclc_radiogenomics") == "no"


def test_unavailable_without_weights_or_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(repo_root=REPO_ROOT, data_dir=tmp_path)
    model = load_model("monai-lung-nodule", settings)
    assert isinstance(model, MonaiDetectorModel)
    monkeypatch.setattr(adapter_module, "detector_packages_available", lambda: False)
    assert not model.available()
    monkeypatch.setattr(adapter_module, "detector_packages_available", lambda: True)
    assert not model.available()
    assert model.describe()["digest"] is None
    volume = _sphere_volume((50.0, 30.0, 20.0), 4.0)
    prepared = model.prepare(_Study(volume), REQ)
    raw = model.infer(prepared, REQ)
    assert raw.error is not None
    assert "fetch_monai_bundle.py" in raw.error
    report = model.parse(raw)
    assert report.abstain
    assert report.lesions is None


def test_detector_report_candidates_and_study_probability(fake_weights: Settings) -> None:
    volume = _sphere_volume((50.0, 30.0, 20.0), 4.0)
    model, made = _model(fake_weights, [((50.0, 30.0, 20.0), 0.8), ((10.0, 80.0, 80.0), 0.1)])
    prepared = model.prepare(_Study(volume), REQ)
    assert prepared.images == []
    assert prepared.meta["possible_training_overlap"] == "yes"
    assert prepared.meta["include_cues"] is False
    assert prepared.view_id == "monai_lung_nodule_v1"
    raw = model.infer(prepared, REQ)
    assert raw.error is None
    assert raw.meta["n_candidates"] == 2
    assert raw.meta["detector"]["device"] == "stub"
    report = model.parse(raw)
    assert report.label_probability("pulmonary_nodule") == pytest.approx(0.8)
    assert report.lesions is not None
    assert report.lesions[0].center_zyx_mm == pytest.approx((50.0, 30.0, 20.0), abs=0.05)
    (finding,) = report.findings
    assert finding.source == "detector"
    assert finding.laterality.value == "right"
    assert made[0].seen
    # the staged array is consumed: a second infer without prepare is refused
    assert model.infer(prepared, REQ).error == "detector input was not prepared by this adapter"


def test_detector_without_candidates_and_label_filter(fake_weights: Settings) -> None:
    volume = _sphere_volume((50.0, 30.0, 20.0), 4.0)
    model, _ = _model(fake_weights, [])
    report = model.parse(
        model.infer(model.prepare(_Study(volume, "nsclc_radiogenomics"), REQ), REQ)
    )
    assert report.label_probability("pulmonary_nodule") == 0.0
    assert report.lesions == []
    other = AnalysisRequest(labels=["pulmonary_mass"])
    raw = model.infer(model.prepare(_Study(volume), other), other)
    assert json.loads(raw.text)["findings"] == []


def test_detector_runtime_error_and_invalid_output(fake_weights: Settings) -> None:
    config = load_model_config("monai-lung-nodule", fake_weights.configs_dir / "models")

    def broken(weights: Path, digest: str, params: DetectorParams) -> Any:
        raise RuntimeError("CUDA out of memory")

    model = MonaiDetectorModel(config, fake_weights, backend_factory=broken)
    volume = _sphere_volume((50.0, 30.0, 20.0), 4.0)
    raw = model.infer(model.prepare(_Study(volume), REQ), REQ)
    assert raw.error == "RuntimeError: CUDA out of memory"
    assert model.parse(RawOutput(text="{not json")).abstain
    assert model.parse(RawOutput(text='{"lesions": [{"score": 2}]}')).abstain


def test_runtime_identity_hashes_detector_weights(fake_weights: Settings, tmp_path: Path) -> None:
    config = load_model_config("monai-lung-nodule", fake_weights.configs_dir / "models")
    identity = runtime_identity(config, fake_weights)
    assert identity["digest"] == checkpoint_module.WEIGHTS_ITEM.sha256
    empty = Settings(repo_root=REPO_ROOT, data_dir=tmp_path / "empty")
    assert runtime_identity(config, empty)["digest"] is None


# --- candidate crops --------------------------------------------------------------------


def _decode(png: bytes) -> npt.NDArray[np.uint8]:
    return np.asarray(Image.open(io.BytesIO(png)))


def test_crop_view_centres_candidate_in_axial_and_coronal() -> None:
    volume = _sphere_volume((50.0, 30.0, 40.0), 5.0)
    view = CandidateCropView(size=64, crop_mm=32.0, planes=("axial", "coronal"))
    prepared = view.build(
        _Study(volume),
        [LesionCandidate(center_zyx_mm=(50.0, 30.0, 40.0), score=0.9), (50.0, 30.0, 50.0)],
    )
    assert prepared.view_id == CROP_VIEW_ID
    assert len(prepared.images) == 4
    assert prepared.meta["view_sha256"] == view.sha256
    assert prepared.meta["mm_per_pixel"] == 0.5
    for png in prepared.images[:2]:
        img = _decode(png)
        assert img.shape == (64, 64)
        assert img[32, 32] > 200  # sphere at the centre (lung window)
        assert img[2, 2] < 120  # lung parenchyma at the corner
    # shifted candidate: the sphere sits 10 mm towards patient right (image left)
    shifted = _decode(prepared.images[2])
    assert shifted[32, 32] < 120
    assert shifted[32, 12] > 200
    assert all("score" not in c and "0.9" not in c for c in prepared.image_captions)
    assert prepared.image_captions[1].startswith("IMAGE 2: candidate 1, coronal")
    assert [c["inside_volume"] for c in prepared.meta["crops"]] == [True, True, True, True]


def test_crop_view_pads_outside_and_mip_slab() -> None:
    volume = _sphere_volume((50.0, 30.0, 40.0), 3.0)
    single = CandidateCropView(size=32, crop_mm=16.0)
    slab = CandidateCropView(size=32, crop_mm=16.0, slab_mm=10.0)
    off_plane = (50.0 + 5.0, 30.0, 40.0)  # 5 mm away along z: outside a single plane
    assert single.crop_hu(volume, off_plane, "axial").max() < 0
    assert slab.crop_hu(volume, off_plane, "axial").max() > 0
    outside = single.build(_Study(volume), [(500.0, 30.0, 40.0)])
    assert outside.meta["crops"][0]["inside_volume"] is False
    assert len(np.unique(_decode(outside.images[0]))) == 1  # uniform air padding
    assert single.sha256 != slab.sha256
    assert single.sha256 != CandidateCropView(size=32, crop_mm=16.0, window="mediastinum").sha256
    with pytest.raises(ValueError, match="plane"):
        single.crop_hu(volume, off_plane, "sagittal")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"crop_mm": 0.0},
        {"size": 8},
        {"window": "nope"},
        {"planes": ()},
        {"planes": ("axial", "axial")},
        {"planes": ("sagittal",)},
        {"slab_mm": -1.0},
    ],
)
def test_crop_view_rejects_invalid_parameters(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"must|unknown"):
        CandidateCropView(**kwargs)


def test_crop_view_default_is_64mm_896px_axial() -> None:
    view = CandidateCropView()
    assert (view.crop_mm, view.size, view.planes, view.window) == (64.0, 896, ("axial",), "lung")


def test_bundle_refuses_parent_symlink_and_cleans_transport_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"bundle terms"
    item = _pin(tmp_path, monkeypatch, payload)
    settings = Settings(repo_root=REPO_ROOT, data_dir=tmp_path / "data")
    root = bundle_dir(settings)
    root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "docs").symlink_to(outside, target_is_directory=True)
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))
    )
    with pytest.raises(BundleIntegrityError, match=r"escapes|symlink"):
        fetch_bundle(settings, acknowledge_license=True, client=client)
    assert list(outside.iterdir()) == []
    (root / "docs").unlink()
    failed = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    with pytest.raises(httpx.HTTPStatusError, match="503"):
        fetch_bundle(settings, acknowledge_license=True, client=failed)
    assert not list(root.rglob("*.partial"))
    assert not (root / item.path).exists()


def test_bundle_directory_must_stay_inside_data(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (data / "models").symlink_to(outside, target_is_directory=True)
    with pytest.raises(BundleIntegrityError, match="escapes"):
        bundle_dir(Settings(data_dir=data))


def test_model_rechecks_weights_after_initial_availability(fake_weights: Settings) -> None:
    model = load_model("monai-lung-nodule", fake_weights)
    assert isinstance(model, MonaiDetectorModel)
    assert model.available()
    model.weights.write_bytes(b"altered")
    assert not model.available()


@pytest.mark.parametrize("spacing", [(0.0, 1.0, 1.0), (1.0, -1.0, 1.0), (math.nan, 1.0, 1.0)])
def test_bundle_input_refuses_invalid_spacing(spacing: tuple[float, float, float]) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        bundle_input(np.zeros((2, 2, 2), dtype=np.int16), spacing)


def test_single_voxel_resampling_stays_nonempty() -> None:
    arr, _ = bundle_input(np.zeros((1, 1, 1), dtype=np.int16), (0.1, 0.1, 0.1))
    assert arr.shape == (1, 1, 1)
    with pytest.raises(ValueError, match="positive multiples"):
        DetectorParams(roi_size_xyz=(0, 16, 8))
    with pytest.raises(ValueError, match="finite"):
        LesionCandidate(center_zyx_mm=(math.nan, 0, 0), score=0.5)


def test_detector_runtime_identity_tracks_device_and_packages(
    fake_weights: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_model_config("monai-lung-nodule", fake_weights.configs_dir / "models")
    monkeypatch.setenv(DEVICE_ENV, "cpu")
    cpu = runtime_identity(config, fake_weights)
    monkeypatch.setenv(DEVICE_ENV, "cuda")
    cuda = runtime_identity(config, fake_weights)
    assert cpu["device_request"] == "cpu"
    assert cuda["device_request"] == "cuda"
    assert set(cpu["packages"]) == {"torch", "torchvision", "monai"}
    assert cpu != cuda


@pytest.mark.parametrize(
    ("box", "score", "message"),
    [
        ([1, 1, 1, 3, 3, 3], 1.2, "outside"),
        ([math.nan, 1, 1, 3, 3, 3], 0.9, "non-finite"),
        ([1, 1, 1, 3, 3, 3], math.nan, "non-finite"),
        ([3, 1, 1, 1, 3, 3], 0.9, "reversed"),
        ([1, 1, 1, 1, 3, 3], 0.9, "empty"),
        ([-1, 1, 1, 3, 3, 3], 0.9, "outside"),
        ([1, 1, 1, 11, 3, 3], 0.9, "outside"),
        ([9.2, 1, 1, 10, 3, 3], 0.9, "centre"),
    ],
)
def test_invalid_detector_outputs_fail_explicitly(
    box: list[float], score: float, message: str
) -> None:
    geometry = BundleGeometry((10, 10, 10), (1.0, 1.0, 1.0), (10, 10, 10))
    with pytest.raises(ValueError, match=message):
        candidates_from_boxes([box], [score], geometry)


@pytest.mark.parametrize("centre", [(math.nan, 0, 0), (0, math.inf, 0)])
def test_crop_rejects_nonfinite_centre(centre: tuple[float, float, float]) -> None:
    volume = _sphere_volume((50, 30, 40), 3)
    with pytest.raises(ValueError, match="finite"):
        CandidateCropView(size=32).crop_hu(volume, centre, "axial")
