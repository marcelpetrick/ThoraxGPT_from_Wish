# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Supervised nodule-detector reference baseline behind the :class:`ThoraxModel` interface.

The MONAI ``lung_nodule_ct_detection`` RetinaNet (trained on LUNA16, a LIDC-IDRI subset)
returns millimetre nodule candidates with detection scores. The adapter turns them into:

* ``FindingsReport.lesions`` — every candidate (centre, box diameter, score) for Task C;
* one ``pulmonary_nodule`` finding whose implied probability is the **maximum candidate
  score** (``0`` without candidates), so the study-level Tasks A/B apply unchanged.

It fits the common protocol: ``prepare`` builds the bundle input in memory (no image files),
``infer`` runs the local network, ``parse`` validates the JSON. The prepared array stays on
the adapter instance between ``prepare`` and ``infer`` because :class:`PreparedInput`
metadata must stay JSON-serialisable. No network access happens here: missing or altered
weights make the model unavailable and never trigger a download.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from pydantic import ValidationError

from thoraxbench.adapters.base import ModelConfig, ModelUnavailableError
from thoraxbench.config import Settings
from thoraxbench.detectors.bundle import (
    BUNDLE_REPO,
    BUNDLE_REVISION,
    BUNDLE_VERSION,
    WEIGHTS_ITEM,
    WEIGHTS_SHA256,
    BundleIntegrityError,
    bundle_dir,
    verify_file,
    weights_path,
)
from thoraxbench.detectors.preprocess import (
    PREPROCESS_VERSION,
    BundleGeometry,
    bundle_input,
    candidates_from_boxes,
    preprocess_sha256,
)
from thoraxbench.detectors.retinanet import (
    DetectorBackend,
    DetectorParams,
    cached_backend,
    detector_packages_available,
)
from thoraxbench.schemas import (
    AnalysisRequest,
    Capabilities,
    FindingsReport,
    PreparedInput,
    RawOutput,
    side_of_x,
)
from thoraxbench.scoring.overlap import possible_training_overlap

LABEL = "pulmonary_nodule"
#: Candidates at or above this score count as "present" (bundle-independent convention).
PRESENT_AT = 0.5

BackendFactory = Callable[[Path, str, DetectorParams], DetectorBackend]


def _side(x_mm: float, width_mm: float) -> str:
    return side_of_x(x_mm, width_mm)


class MonaiDetectorModel:
    """The pretrained RetinaNet nodule detector (inference only)."""

    def __init__(
        self,
        config: ModelConfig,
        settings: Settings,
        *,
        backend_factory: BackendFactory | None = None,
    ) -> None:
        self.config = config
        self.id = config.id
        self.settings = settings
        self.params = DetectorParams.model_validate(config.options.get("detector", {}))
        self.backend_factory = backend_factory or cached_backend
        self._staged: tuple[str, npt.NDArray[np.float32], BundleGeometry, float] | None = None

    @property
    def weights(self) -> Path:
        """Pinned state-dict path inside the ignored data directory."""
        return weights_path(self.settings)

    def capabilities(self) -> Capabilities:
        """Capabilities declared in the model config."""
        return self.config.capabilities

    def _verified_digest(self) -> str:
        try:
            return verify_file(bundle_dir(self.settings), WEIGHTS_ITEM)
        except BundleIntegrityError as exc:
            msg = (
                f"model '{self.id}': {exc}; fetch explicitly with "
                "'uv run python scripts/fetch_monai_bundle.py --accept-terms'"
            )
            raise ModelUnavailableError(msg) from exc

    def available(self) -> bool:
        """Whether the optional packages are installed and the pinned weights verify."""
        if not detector_packages_available():
            return False
        try:
            self._verified_digest()
        except ModelUnavailableError:
            return False
        return True

    def describe(self) -> dict[str, Any]:
        """Weights identity for provenance (``digest`` = verified SHA-256 or ``None``)."""
        try:
            digest: str | None = self._verified_digest()
        except ModelUnavailableError:
            digest = None
        return {
            "digest": digest,
            "expected_sha256": WEIGHTS_SHA256,
            "bundle": BUNDLE_REPO,
            "bundle_version": BUNDLE_VERSION,
            "revision": BUNDLE_REVISION,
            "params": self.params.model_dump(mode="json"),
        }

    def prepare(self, study: Any, request: AnalysisRequest) -> PreparedInput:
        """Build the bundle input in memory and record geometry and overlap provenance."""
        volume = study.volume
        array, geometry = bundle_input(volume.hu, volume.spacing_mm)
        token = hashlib.sha256(array.tobytes()).hexdigest()
        width_mm = float((volume.hu.shape[2] - 1) * volume.spacing_mm[2])
        self._staged = (token, array, geometry, width_mm)
        return PreparedInput(
            view_id=self.config.view,
            view_version=PREPROCESS_VERSION,
            meta={
                "view_sha256": preprocess_sha256(),
                "input_sha256": token,
                "geometry": geometry.to_dict(),
                "dataset": study.dataset,
                # The detector receives no text context; record that instead of HU cues.
                "include_cues": False,
                "possible_training_overlap": possible_training_overlap(
                    self.config.family, study.dataset
                ),
            },
        )

    def infer(self, prepared: PreparedInput, request: AnalysisRequest) -> RawOutput:
        """Run the detector; failures become an explicit raw error (never invented output)."""
        start = time.perf_counter()
        staged = self._staged
        self._staged = None
        if staged is None or staged[0] != prepared.meta.get("input_sha256"):
            return RawOutput(error="detector input was not prepared by this adapter")
        _token, array, geometry, width_mm = staged
        try:
            digest = self._verified_digest()
            backend = self.backend_factory(self.weights, digest, self.params)
            detections = backend.detect(array)
            candidates = candidates_from_boxes(detections.boxes, detections.scores, geometry)
        except (ModelUnavailableError, RuntimeError, ValueError, OSError, ImportError) as exc:
            return RawOutput(
                error=f"{type(exc).__name__}: {exc}", latency_s=time.perf_counter() - start
            )
        top = candidates[0] if candidates else None
        probability = top.score if top else 0.0
        present = probability >= PRESENT_AT
        finding: dict[str, Any] = {
            "label": LABEL,
            "present": present,
            "confidence": round(probability if present else 1.0 - probability, 6),
            "description": (
                f"{len(candidates)} detector candidate(s); max score {probability:.3f}"
                if top
                else "no detector candidate above the score threshold"
            ),
            "source": "detector",
        }
        if top is not None:
            finding["size_mm"] = top.diameter_mm
            finding["laterality"] = _side(top.center_zyx_mm[2], width_mm)
        report = {
            "study_quality": {"adequate": True, "limitations": []},
            "findings": [finding] if not request.labels or LABEL in request.labels else [],
            "uncertainty": (
                "supervised LUNA16 RetinaNet; scores are detector scores, not calibrated "
                "probabilities; study probability = max candidate score"
            ),
            "abstain": False,
            "lesions": [c.model_dump(mode="json") for c in candidates],
        }
        return RawOutput(
            text=json.dumps(report),
            latency_s=time.perf_counter() - start,
            meta={
                "weights_sha256": digest,
                "bundle_revision": BUNDLE_REVISION,
                "n_candidates": len(candidates),
                "max_score": probability,
                "detector": detections.meta,
                "possible_training_overlap": prepared.meta.get("possible_training_overlap"),
            },
        )

    def parse(self, raw: RawOutput) -> FindingsReport:
        """Validate the detector JSON; errors and invalid output abstain explicitly."""
        if raw.error is not None:
            return FindingsReport(
                abstain=True, uncertainty=raw.error, parse_warnings=[f"model error: {raw.error}"]
            )
        try:
            return FindingsReport.model_validate(json.loads(raw.text))
        except (ValueError, ValidationError) as exc:
            return FindingsReport(
                abstain=True,
                uncertainty="invalid detector output",
                parse_warnings=[f"invalid detector output: {type(exc).__name__}"],
            )
