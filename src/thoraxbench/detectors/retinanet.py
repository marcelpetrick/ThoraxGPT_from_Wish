# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""MONAI RetinaNet backend for the ``lung_nodule_ct_detection`` bundle (inference only).

PyTorch, torchvision and MONAI come from the optional ``detector`` extra and are imported
lazily, so the core package, CI tests and the wheel do not need them. The network topology,
anchors and box-selector settings copy the bundle's ``configs/inference.json``. Only the
sliding-window ROI is smaller (default ``256 x 256 x 128`` instead of ``512 x 512 x 192``)
so that one window fits a shared 8 GB GPU or modest host RAM; it is recorded in the hashed
model configuration. Weights load with ``torch.load(weights_only=True)`` after a size and
SHA-256 check; TorchScript is never loaded.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import resource
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, field_validator

DEVICE_ENV = "THORAXBENCH_DETECTOR_DEVICE"
DETECTOR_PACKAGES = ("torch", "torchvision", "monai")


class DetectorParams(BaseModel):
    """Inference settings (``options.detector`` of the model YAML; part of its hash)."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    roi_size_xyz: tuple[int, int, int] = (256, 256, 128)
    overlap: float = Field(default=0.25, ge=0.0, lt=1.0)
    score_thresh: float = Field(default=0.02, ge=0.0, le=1.0)
    topk_candidates_per_level: int = Field(default=1000, ge=1)
    nms_thresh: float = Field(default=0.22, gt=0.0, le=1.0)
    detections_per_img: int = Field(default=300, ge=1)
    device: str = Field(default="auto", pattern=r"^(auto|cpu|cuda)$")
    amp: bool = True
    min_free_gpu_mb: int = Field(default=3000, ge=0)

    @field_validator("roi_size_xyz")
    @classmethod
    def _valid_roi(cls, value: tuple[int, int, int]) -> tuple[int, int, int]:
        if any(n < d or n % d for n, d in zip(value, (16, 16, 8), strict=True)):
            raise ValueError("ROI sizes must be positive multiples of (16, 16, 8)")
        return value

    def resolved_device_request(self) -> str:
        """Device request after the ``THORAXBENCH_DETECTOR_DEVICE`` override."""
        override = os.environ.get(DEVICE_ENV, "").strip().lower()
        return override if override in {"auto", "cpu", "cuda"} else self.device


@dataclass
class Detections:
    """Raw detector output in RAS voxel coordinates plus runtime measurements."""

    boxes: npt.NDArray[np.float64]
    scores: npt.NDArray[np.float64]
    meta: dict[str, Any] = field(default_factory=dict)


class DetectorBackend(Protocol):
    """What the adapter needs from a detection network (real or stub)."""

    def detect(self, volume_xyz: npt.NDArray[np.float32]) -> Detections:
        """Detect nodules in a RAS ``(x, y, z)`` volume scaled to [0, 1]."""
        ...


def detector_packages_available() -> bool:
    """Whether the optional ``detector`` extra is importable (no import side effects kept)."""
    return all(importlib.util.find_spec(name) is not None for name in DETECTOR_PACKAGES)


def _peak_rss_bytes() -> int:
    """Peak resident set size of this process (Linux ``ru_maxrss`` is in KiB)."""
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def _reset_peak_rss() -> bool:
    """Reset the kernel's peak-RSS counter (Linux ``clear_refs`` 5); False if unsupported."""
    try:
        Path("/proc/self/clear_refs").write_text("5", encoding="ascii")
    except OSError:
        return False
    return True


def _vm_hwm_bytes() -> int | None:
    try:
        for line in Path("/proc/self/status").read_text(encoding="ascii").splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) * 1024
    except OSError, ValueError, IndexError:
        return None
    return None


class RetinaNetBackend:
    """Bundle network on CPU or CUDA; one instance per (weights, params, device)."""

    def __init__(self, weights: Path, params: DetectorParams) -> None:
        self.params = params
        self.torch: Any = importlib.import_module("torch")
        retinanet: Any = importlib.import_module("monai.apps.detection.networks.retinanet_network")
        detector_mod: Any = importlib.import_module(
            "monai.apps.detection.networks.retinanet_detector"
        )
        anchors: Any = importlib.import_module("monai.apps.detection.utils.anchor_utils")
        resnet: Any = importlib.import_module("monai.networks.nets.resnet")
        torch = self.torch
        self.device = self._choose_device()
        backbone = resnet.resnet50(
            spatial_dims=3, n_input_channels=1, conv1_t_stride=[2, 2, 1], conv1_t_size=[7, 7, 7]
        )
        extractor = retinanet.resnet_fpn_feature_extractor(backbone, 3, False, [1, 2], None)
        network = retinanet.RetinaNet(
            spatial_dims=3,
            num_classes=1,
            num_anchors=3,
            feature_extractor=extractor,
            size_divisible=[16, 16, 8],
            use_list_output=False,
        )
        state = torch.load(str(weights), map_location="cpu", weights_only=True)
        network.load_state_dict(state)
        network.to(self.device)
        generator = anchors.AnchorGeneratorWithAnchorShape(
            feature_map_scales=[1, 2, 4],
            base_anchor_shapes=[[6, 8, 4], [8, 6, 5], [10, 10, 6]],
        )
        detector = detector_mod.RetinaNetDetector(
            network=network,
            anchor_generator=generator,
            spatial_dims=3,
            num_classes=1,
            size_divisible=[16, 16, 8],
        )
        detector.set_target_keys(box_key="box", label_key="label")
        detector.set_box_selector_parameters(
            score_thresh=params.score_thresh,
            topk_candidates_per_level=params.topk_candidates_per_level,
            nms_thresh=params.nms_thresh,
            detections_per_img=params.detections_per_img,
        )
        detector.set_sliding_window_inferer(
            roi_size=list(params.roi_size_xyz),
            overlap=params.overlap,
            sw_batch_size=1,
            mode="constant",
            device="cpu",
            sw_device=self.device,
        )
        detector.eval()
        self.detector = detector
        self.lock = threading.Lock()

    def _choose_device(self) -> str:
        torch = self.torch
        request = self.params.resolved_device_request()
        if request == "cpu":
            return "cpu"
        if not torch.cuda.is_available():
            if request == "cuda":
                raise RuntimeError("CUDA requested for the detector but not available")
            return "cpu"
        if request == "cuda":
            return "cuda"
        free, _total = torch.cuda.mem_get_info()
        return "cuda" if free >= self.params.min_free_gpu_mb * 1024 * 1024 else "cpu"

    def detect(self, volume_xyz: npt.NDArray[np.float32]) -> Detections:
        """Run sliding-window inference and report device, timing and peak memory."""
        torch = self.torch
        with self.lock:
            cuda = self.device == "cuda"
            amp = cuda and self.params.amp
            rss_reset = _reset_peak_rss()
            if cuda:
                torch.cuda.reset_peak_memory_stats()
            image = torch.from_numpy(np.ascontiguousarray(volume_xyz))[None]
            start = time.perf_counter()
            with torch.inference_mode():
                if amp:
                    with torch.autocast("cuda", dtype=torch.float16):
                        out = self.detector([image], use_inferer=True)
                else:
                    out = self.detector([image], use_inferer=True)
            if cuda:
                torch.cuda.synchronize()
            elapsed = time.perf_counter() - start
            boxes = out[0]["box"].detach().float().cpu().numpy().astype(np.float64)
            scores = out[0]["label_scores"].detach().float().cpu().numpy().astype(np.float64)
            meta: dict[str, Any] = {
                "device": self.device,
                "device_name": torch.cuda.get_device_name() if cuda else "cpu",
                "amp_float16": amp,
                "torch_threads": int(torch.get_num_threads()),
                "network_s": round(elapsed, 3),
                "torch_version": str(torch.__version__),
                "peak_rss_bytes": _vm_hwm_bytes() if rss_reset else None,
                "process_peak_rss_bytes": _peak_rss_bytes(),
                "cuda_peak_allocated_bytes": int(torch.cuda.max_memory_allocated())
                if cuda
                else None,
                "cuda_peak_reserved_bytes": int(torch.cuda.max_memory_reserved()) if cuda else None,
            }
        return Detections(boxes=boxes.reshape(-1, 6), scores=scores.reshape(-1), meta=meta)


_BACKENDS: dict[tuple[str, str], DetectorBackend] = {}
_BACKENDS_LOCK = threading.Lock()


def cached_backend(weights: Path, weights_sha256: str, params: DetectorParams) -> DetectorBackend:
    """Reuse one loaded network per verified weights hash and parameter set."""
    key = (weights_sha256, params.model_dump_json() + params.resolved_device_request())
    with _BACKENDS_LOCK:
        backend = _BACKENDS.get(key)
        if backend is None:
            backend = RetinaNetBackend(weights, params)
            _BACKENDS[key] = backend
        return backend
