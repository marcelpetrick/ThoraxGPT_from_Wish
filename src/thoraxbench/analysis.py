# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Single-study analysis: study → model view → local inference → parsed findings.

This is what ``thoraxbench analyze`` and the benchmark runner call for every case. It records
timings per stage (Vision §21) and a provenance record (Vision §24) next to the result.
"""

from __future__ import annotations

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
from thoraxbench.adapters.ollama import OllamaModel
from thoraxbench.config import Settings
from thoraxbench.perf import PerfRecord, measure
from thoraxbench.privacy import Redactor, settings_redactor
from thoraxbench.provenance import RunProvenance, sha256_of_obj
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


def _resolver(overrides: dict[str, Any]) -> ViewResolver:
    def resolve(view_id: str, params: dict[str, Any]) -> ViewBuilderLike | None:
        return default_view_resolver(view_id, {**params, **overrides})

    return resolve


def analyze_study(
    study: Study,
    model_id: str,
    settings: Settings,
    *,
    request: AnalysisRequest | None = None,
    prompt_id: str | None = None,
    view_overrides: dict[str, Any] | None = None,
    client: httpx.Client | None = None,
) -> AnalysisResult:
    """Run *model_id* on *study* and return the parsed, timed, provenance-stamped result.

    Inadequate studies abstain before rendering or inference. Runtime failures and
    invalid model responses remain inspectable in the returned result.
    """
    if request is not None and prompt_id is not None and request.prompt_id != prompt_id:
        msg = "request.prompt_id and prompt_id must agree"
        raise ValueError(msg)
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
            with m.stage("preprocess"):
                _ = study.cues
                prepared = model.prepare(study, req)
            with m.stage("inference"):
                raw = model.infer(prepared, req)
            with m.stage("parse"):
                report = model.parse(raw)
                if not report.abstain and not report.findings and not report.negative_findings:
                    report.abstain = True
                    report.parse_warnings.append("no label predictions returned")
    perf = m.record
    perf.input_bytes = prepared.input_bytes
    perf.n_images = len(prepared.images)
    perf.tokens_generated = raw.tokens_generated
    perf.failed = raw.error is not None or report.abstain
    perf.error = raw.error
    identity = model.describe() if isinstance(model, OllamaModel) and study.qc.adequate else {}
    provenance = RunProvenance.collect(
        settings.repo_root,
        model_id=model_id,
        model_hash=identity.get("digest"),
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
        context=prepared.context or (study.cues.summary() if study.qc.adequate else ""),
        qc=study.qc.to_dict(),
        perf=perf,
        provenance=provenance,
    )
    return redact_result(result, settings_redactor(settings))


_REDACTED_FIELDS = ("report", "raw_text", "raw_error", "raw_meta", "view_meta", "context", "perf")


def redact_result(result: AnalysisResult, redactor: Redactor) -> AnalysisResult:
    """Redact absolute paths and identifier values in free-text and metadata fields (§29).

    Result keys (dataset, case, patient pseudonym, series UID) and provenance hashes stay
    unchanged, so scoring and split checks are unaffected. Prepared images are kept.
    """
    data = redactor.redact_obj(result.model_dump(mode="json", include=set(_REDACTED_FIELDS)))
    data["report"] = FindingsReport.model_validate(data["report"])
    data["perf"] = PerfRecord.model_validate(data["perf"])
    return result.model_copy(update=data)
