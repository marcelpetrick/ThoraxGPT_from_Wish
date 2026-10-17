# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Single-study analysis: study → model view → local inference → parsed findings.

This is what ``thoraxbench analyze`` and the benchmark runner call for every case. It records
timings per stage (Vision §21) and a provenance record (Vision §24) next to the result.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from thoraxbench.adapters.base import (
    ViewBuilderLike,
    ViewResolver,
    default_view_resolver,
    load_model_config,
)
from thoraxbench.adapters.factory import load_model
from thoraxbench.adapters.monai_detector import MonaiDetectorModel
from thoraxbench.adapters.ollama import OllamaModel
from thoraxbench.config import Settings
from thoraxbench.perf import PerfRecord, measure
from thoraxbench.privacy import Redactor, settings_redactor
from thoraxbench.provenance import (
    RunProvenance,
    scoring_source_hash,
    sha256_of_file,
    sha256_of_obj,
)
from thoraxbench.schemas import (
    AnalysisRequest,
    FindingsReport,
    PreparedInput,
    RawOutput,
    StudyQuality,
)
from thoraxbench.study import Study

DISCLAIMER = (
    "Research use only. ThoraxBench Local is a self-made experimental research tool, "
    "not medical advice from a qualified healthcare professional, not a diagnosis, "
    "and not a medical device. Outputs use available models and reference knowledge but "
    "may be incorrect, incomplete or misleading. Do not use them for diagnosis or treatment "
    "decisions. Any finding requires independent review by a qualified radiologist."
)


class AnalysisResult(BaseModel):
    """Everything produced for one study and one model."""

    dataset: str
    case_id: str
    patient_id: str
    series_uid: str
    model_id: str
    request: AnalysisRequest
    report: FindingsReport
    raw_text: str
    raw_error: str | None = None
    raw_meta: dict[str, Any] = Field(default_factory=dict)
    prepared_images: list[bytes] = Field(default_factory=list, exclude=True, repr=False)
    image_captions: list[str] = Field(default_factory=list)
    slice_indices: list[int] = Field(default_factory=list)
    view_meta: dict[str, Any] = Field(default_factory=dict)
    context: str = ""
    qc: dict[str, Any] = Field(default_factory=dict)
    perf: PerfRecord
    provenance: RunProvenance
    disclaimer: str = DISCLAIMER


def _dataset_hash(root: Path, kind: str, dataset: str) -> str | None:
    """Hash optional metadata without following an identifier or symlink outside its folder."""
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", dataset) is None:
        raise ValueError("dataset identifier is not a safe metadata key")
    folder = root.resolve() / kind
    path = folder / f"{dataset}.json"
    if not path.resolve().is_relative_to(folder):
        raise ValueError("dataset metadata path escapes its designated directory")
    return sha256_of_file(path) if path.is_file() else None


def _resolver(overrides: dict[str, Any]) -> ViewResolver:
    def resolve(view_id: str, params: dict[str, Any]) -> ViewBuilderLike | None:
        return default_view_resolver(view_id, {**params, **overrides})

    return resolve


def _check_image_evidence(report: FindingsReport, n_images: int, *, required: bool) -> None:
    """Keep model-image references in range; unsupported constrained positives are unknown.

    Raw responses remain unchanged for inspection. This validates reference bounds, not
    visual correctness. Source-slice references from the HU baseline never enter here.
    """
    for finding in report.findings:
        valid = list(dict.fromkeys(i for i in finding.evidence_images if 1 <= i <= n_images))
        if valid != finding.evidence_images:
            report.parse_warnings.append(
                f"{finding.label}: invalid or duplicate image references removed; "
                f"expected attached images 1..{n_images}"
            )
            finding.evidence_images = valid
        probability = finding.presence_probability()
        if required and probability is not None and probability >= 0.5 and not valid:
            finding.present = None
            finding.confidence = None
            report.parse_warnings.append(
                f"{finding.label}: positive has no valid attached-image evidence; "
                "prediction marked unavailable"
            )


def analyze_study(  # noqa: PLR0915 - one linear, staged engine pipeline
    study: Study,
    model_id: str,
    settings: Settings,
    *,
    request: AnalysisRequest | None = None,
    prompt_id: str | None = None,
    view_overrides: dict[str, Any] | None = None,
    client: httpx.Client | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> AnalysisResult:
    """Run *model_id* on *study* and return the parsed, timed, provenance-stamped result.

    Inadequate studies abstain before rendering or inference. Runtime failures and
    invalid model responses remain inspectable in the returned result. *on_stage* is
    called with ``preprocess``, ``inference`` and ``parse`` before each stage starts; the
    UI job queue uses it to show the current stage and to stop at stage boundaries (an
    exception it raises propagates unchanged).
    """
    announce = on_stage or (lambda _stage: None)
    if request is not None and prompt_id is not None and request.prompt_id != prompt_id:
        msg = "request.prompt_id and prompt_id must agree"
        raise ValueError(msg)
    dataset_hash = _dataset_hash(settings.manifests_dir, "datasets", study.dataset)
    split_hash = _dataset_hash(settings.manifests_dir, "splits", study.dataset)
    reference_hash = _dataset_hash(settings.data_dir, "index", study.dataset)
    config = load_model_config(model_id, settings.configs_dir / "models")
    chosen_prompt = prompt_id or (request.prompt_id if request else config.prompt or "P3")
    req = request or AnalysisRequest(prompt_id=chosen_prompt)
    model = load_model(
        model_id,
        settings,
        prompt_id=chosen_prompt,
        client=client,
        view_resolver=_resolver(view_overrides or {}),
    )
    with measure() as m:
        if not study.qc.adequate:
            prepared = PreparedInput(view_id=config.view, view_version="not-run")
            raw = RawOutput(error="study failed quality control; inference skipped")
            report = FindingsReport(
                abstain=True,
                study_quality=StudyQuality(adequate=False, limitations=study.qc.limitations),
                parse_warnings=[raw.error or "inadequate study"],
            )
        else:
            announce("preprocess")
            with m.stage("preprocess"):
                _ = study.cues
                prepared = model.prepare(study, req)
            announce("inference")
            with m.stage("inference"):
                raw = model.infer(prepared, req)
            announce("parse")
            with m.stage("parse"):
                report = model.parse(raw)
                if not report.study_quality.adequate:
                    report.abstain = True
                    report.parse_warnings.append("model marked prepared study inadequate")
                if isinstance(model, OllamaModel):
                    _check_image_evidence(
                        report, len(prepared.images), required=model.prompt.label_constrained
                    )
                if not report.abstain and not report.findings and not report.negative_findings:
                    report.abstain = True
                    report.parse_warnings.append("no label predictions returned")
                elif not report.abstain:
                    requested = req.labels or sorted(
                        {f.label for f in report.findings} | set(report.negative_findings)
                    )
                    if not any(report.label_probability(label) is not None for label in requested):
                        report.abstain = True
                        report.parse_warnings.append(
                            "no available requested-label predictions returned"
                        )
    perf = m.record
    perf.input_bytes = prepared.input_bytes
    perf.n_images = len(prepared.images)
    perf.tokens_generated = raw.tokens_generated
    perf.failed = raw.error is not None or report.abstain
    perf.error = raw.error
    identity = (
        model.describe()
        if isinstance(model, OllamaModel | MonaiDetectorModel) and study.qc.adequate
        else {}
    )

    tensor = prepared.tensor_path
    provenance = RunProvenance.collect(
        settings.repo_root,
        model_id=model_id,
        model_hash=identity.get("digest"),
        dataset_manifest_hash=dataset_hash,
        split_manifest_hash=split_hash,
        ground_truth_hash=reference_hash,
        scoring_hash=scoring_source_hash(),
        input_hash=sha256_of_obj(
            {
                "images": [hashlib.sha256(image).hexdigest() for image in prepared.images],
                "tensor": sha256_of_file(Path(tensor)) if tensor is not None else None,
                "context": prepared.context,
                "canonical_hu_sha256": hashlib.sha256(study.volume.hu.tobytes()).hexdigest(),
                "shape": study.volume.shape,
                "spacing_mm": study.volume.spacing_mm,
            }
        ),
        seed=config.options.get("ollama", {}).get("seed", 0),
        config_hash=sha256_of_obj(
            {
                "model": config.model_dump(mode="json"),
                "request": req.model_dump(),
                "view_overrides": view_overrides or {},
            }
        ),
        prompt_hash=raw.meta.get("prompt_sha256"),
        preprocess_hash=sha256_of_obj(
            {k: prepared.meta.get(k) for k in ("view_sha256", "strategy_sha256")}
            | {
                "view": prepared.view_id,
                "version": prepared.view_version,
                "cues": study.cues.version if study.qc.adequate else "not-run",
                "params": config.view_params | (view_overrides or {}),
            }
        ),
    )
    result = AnalysisResult(
        dataset=study.dataset,
        case_id=study.case_id,
        patient_id=study.patient_id,
        series_uid=study.volume.series_uid,
        model_id=model_id,
        request=req,
        report=report,
        raw_text=raw.text,
        raw_error=raw.error,
        raw_meta=raw.meta | {"model_identity": identity},
        prepared_images=prepared.images,
        image_captions=prepared.image_captions,
        slice_indices=prepared.slice_indices,
        view_meta={k: v for k, v in prepared.meta.items() if k != "cues"},
        context=prepared.context
        if prepared.meta.get("include_cues") is False
        else prepared.context or (study.cues.summary() if study.qc.adequate else ""),
        qc=study.qc.to_dict(),
        perf=perf,
        provenance=provenance,
    )
    return redact_result(result, settings_redactor(settings, study.identifiers))


_REDACTED_FIELDS = (
    "request",
    "report",
    "raw_text",
    "raw_error",
    "raw_meta",
    "view_meta",
    "context",
    "perf",
    "qc",
    "image_captions",
)


def redact_result(result: AnalysisResult, redactor: Redactor) -> AnalysisResult:
    """Redact absolute paths and identifier values in free-text and metadata fields (§29).

    Result keys (dataset, case, patient pseudonym, series UID) and provenance hashes stay
    unchanged, so scoring and split checks are unaffected. Prepared images are kept.
    """
    data = redactor.redact_obj(result.model_dump(mode="json", include=set(_REDACTED_FIELDS)))
    data["request"] = AnalysisRequest.model_validate(data["request"])
    data["report"] = FindingsReport.model_validate(data["report"])
    data["perf"] = PerfRecord.model_validate(data["perf"])
    return result.model_copy(update=data)
