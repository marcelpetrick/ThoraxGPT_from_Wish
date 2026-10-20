# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Full thorax review: every slab of the chest, every label, one image per model call (B2).

The run is: HU heuristic once on the whole volume → MONAI detector once (when available) →
one P7 query per :class:`~thoraxbench.sampling.ThoraxSweep` slab in coarse-to-fine order →
aggregation and ranking (:mod:`thoraxbench.fullreview.aggregate`). The engine reports
progress after every slab and stops between slabs when asked; a stopped run returns its
partial result with coverage. The summary never contains SeriesInstanceUIDs, patient
identifiers or paths; model text is redacted like every other analysis output.
"""

from __future__ import annotations

import hashlib
import io
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from PIL import Image

from thoraxbench.adapters.base import ModelUnavailableError, ThoraxModel, load_model_config
from thoraxbench.adapters.factory import load_model
from thoraxbench.analysis import _check_image_evidence, analyze_study
from thoraxbench.config import Settings
from thoraxbench.fullreview.aggregate import (
    Candidate,
    SlabAnswers,
    StudyLevelCue,
    aggregate_labels,
    next_steps,
    rank_look_here,
    thresholds,
    verdict_of,
)
from thoraxbench.ontology import load_ontology
from thoraxbench.privacy import settings_redactor
from thoraxbench.provenance import RunProvenance, sha256_of_obj
from thoraxbench.sampling import Selection, ThoraxSweep
from thoraxbench.schemas import AnalysisRequest, FindingsReport, PreparedInput, side_of_x
from thoraxbench.study import Study
from thoraxbench.views import MultiSliceView, get_view, render_slice_png

PROMPT_ID = "P7"
DETECTOR_ID = "monai-lung-nodule"
HEURISTIC_ID = "heuristic-hu"
RUNNER_VERSION = "1"
#: Stop early when this many slabs in a row fail before any slab answered (runtime down).
MAX_INITIAL_FAILURES = 3
#: Edge length of the retained downscaled copy of each model image (HTML evidence).
THUMBNAIL_PX = 320
#: Labels the HU heuristic reports per slice location (via nodule candidates).
_LOCATED_HU_LABELS = frozenset({"pulmonary_nodule", "pulmonary_mass"})
_WINDOW_NAMES = {
    "medgemma": "MedGemma RGB (wide/soft-tissue/narrow)",
    "lung": "lung window W1500/L-600",
}

StageCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int, float | None], None]


@dataclass
class FullReviewRun:
    """Summary JSON plus downscaled model images keyed by cranial slab position."""

    summary: dict[str, Any]
    thumbnails: dict[int, bytes] = field(default_factory=dict)

    @property
    def partial(self) -> bool:
        """Whether fewer slabs than planned were visited."""
        return bool(self.summary["coverage"]["partial"])


def _thumbnail(png: bytes) -> bytes:
    image = Image.open(io.BytesIO(png))
    image.thumbnail((THUMBNAIL_PX, THUMBNAIL_PX), Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _window(view: Any) -> tuple[str, int]:
    """Render mode of the model's configured view: MedGemma RGB or lung window."""
    if not isinstance(view, MultiSliceView):
        raise ModelUnavailableError("full thorax review needs a 2D image model view")
    return ("medgemma" if view.mode == "medgemma" else "lung"), view.size


def _slab_answers(
    report: FindingsReport, labels: list[str]
) -> tuple[dict[str, bool | None], dict[str, str], dict[str, str]]:
    answers: dict[str, bool | None] = {}
    evidence: dict[str, str] = {}
    sides: dict[str, str] = {}
    for label in labels:
        p = report.label_probability(label)
        answers[label] = None if p is None else p >= 0.5
        finding = next((f for f in report.findings if f.label == label), None)
        if answers[label] and finding is not None:
            if finding.description:
                evidence[label] = " ".join(finding.description.split())[:160]
            sides[label] = finding.laterality.value
    return answers, evidence, sides


def _baselines(
    study: Study,
    settings: Settings,
    *,
    detector_id: str | None,
    announce: StageCallback,
    stop: Callable[[], bool],
) -> tuple[list[Candidate], list[StudyLevelCue], dict[str, Any], dict[str, Any]]:
    """HU heuristic and (if available) the detector, each once on the whole volume."""
    dz = float(study.volume.spacing_mm[0])
    candidates: list[Candidate] = [
        Candidate(
            source="hu",
            label="pulmonary_mass" if c.diameter_mm >= 30.0 else "pulmonary_nodule",
            slice_index=c.z_index,
            side=c.side,
            size_mm=round(c.diameter_mm, 1),
        )
        for c in study.cues.nodule_candidates
    ]
    announce("heuristic")
    heuristic = analyze_study(study, HEURISTIC_ID, settings)
    cues = [
        StudyLevelCue(
            label=f.label, side=f.laterality.value, description=" ".join(f.description.split())
        )
        for f in heuristic.report.findings
        if f.label not in _LOCATED_HU_LABELS
        and (p := f.presence_probability()) is not None
        and p >= 0.5
    ]
    heuristic_info = {
        "status": "abstained" if heuristic.report.abstain else "completed",
        "nodule_candidates": len(candidates),
        "positive_labels": [c.label for c in cues],
        "seconds": round(heuristic.perf.total_s, 3),
    }
    detector_info: dict[str, Any] = {"status": "not_configured", "candidates": 0}
    configured = (
        detector_id is not None
        and (settings.configs_dir / "models" / f"{detector_id}.yaml").is_file()
    )
    if configured and detector_id is not None and not stop():
        model = load_model(detector_id, settings)
        if not model.available():
            detector_info = {"status": "unavailable", "candidates": 0}
        else:
            announce("detector")
            result = analyze_study(study, detector_id, settings)
            lesions = result.report.lesions or []
            width_mm = float((study.volume.hu.shape[2] - 1) * study.volume.spacing_mm[2])
            failed = result.report.abstain or result.raw_error is not None
            for lesion in [] if failed else lesions:
                index = round(lesion.center_zyx_mm[0] / dz)
                if not 0 <= index < study.volume.shape[0]:
                    continue
                candidates.append(
                    Candidate(
                        source="detector",
                        label="pulmonary_nodule",
                        slice_index=index,
                        side=side_of_x(lesion.center_zyx_mm[2], width_mm),
                        score=round(lesion.score, 4),
                        size_mm=round(lesion.diameter_mm, 1)
                        if lesion.diameter_mm is not None
                        else None,
                    )
                )
            detector_info = {
                "status": "failed" if failed else "completed",
                "candidates": 0 if failed else len(lesions),
                "seconds": round(result.perf.total_s, 3),
                "possible_training_overlap": result.view_meta.get(
                    "possible_training_overlap", "unknown"
                ),
            }
    elif configured:
        detector_info = {"status": "skipped", "candidates": 0}
    return candidates, cues, heuristic_info, detector_info


def run_full_review(  # noqa: PLR0915 - one staged, linear engine pipeline
    study: Study,
    model_id: str,
    settings: Settings,
    *,
    client: httpx.Client | None = None,
    model: ThoraxModel | None = None,
    detector_id: str | None = DETECTOR_ID,
    strategy: ThoraxSweep | None = None,
    on_stage: StageCallback | None = None,
    on_progress: ProgressCallback | None = None,
    should_stop: Callable[[], bool] | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> FullReviewRun:
    """Review every slab of *study* with *model_id* and aggregate a plain outcome.

    *model* injects an adapter (tests); otherwise *model_id* loads with prompt P7.
    *on_progress* receives ``(visited, total, seconds_per_image)`` before the first slab and
    after every slab; *should_stop* is polled between slabs. Neither callback may raise.
    """
    announce = on_stage or (lambda _stage: None)
    progress = on_progress or (lambda _done, _total, _rate: None)
    stop = should_stop or (lambda: False)
    started = clock()
    config = load_model_config(model_id, settings.configs_dir / "models")
    # The image-model slab sweep is optional: with the detector or HU baseline selected, the
    # review runs the whole-volume tools only (the detector is the component with signal).
    image_model = model is not None or config.adapter == "ollama"
    if not image_model and config.adapter not in {"monai_detector", "heuristic"}:
        raise ModelUnavailableError("full thorax review needs an image model or the detector")
    # A selected detector configuration is the one to run, not the default detector.
    detector_id = model_id if config.adapter == "monai_detector" else detector_id
    vlm: ThoraxModel | None = None
    window, size = "lung", 0
    if image_model:
        window, size = _window(get_view(config.view, **config.view_params))
        vlm = model or load_model(model_id, settings, prompt_id=PROMPT_ID, client=client)
    ontology = load_ontology()
    labels = ontology.ids(core_only=True)
    names = {lb.id: lb.name for lb in ontology.labels}
    request = AnalysisRequest(prompt_id=PROMPT_ID, labels=labels)
    sweep = strategy or ThoraxSweep()
    volume = study.volume
    adequate = bool(study.qc.adequate)
    selection = (
        sweep.select(volume, study.cues)
        if adequate and image_model
        else Selection([], [], slab_bounds=[])
    )
    total = len(selection.indices)
    candidates: list[Candidate] = []
    cues: list[StudyLevelCue] = []
    heuristic_info: dict[str, Any] = {"status": "not_run"}
    detector_info: dict[str, Any] = {"status": "not_run", "candidates": 0}
    if adequate:
        candidates, cues, heuristic_info, detector_info = _baselines(
            study, settings, detector_id=detector_id, announce=announce, stop=stop
        )
    prompt_sha = getattr(getattr(vlm, "prompt", None), "sha256", None)
    identity = vlm.describe() if adequate and vlm is not None and hasattr(vlm, "describe") else {}
    slabs: list[dict[str, Any]] = []
    answered: list[SlabAnswers] = []
    thumbnails: dict[int, bytes] = {}
    durations: list[float] = []
    failures_before_answer = 0
    runtime_failed = False
    if adequate:
        announce("slabs")
    # Without a slab sweep the baselines are the whole run; a stop requested meanwhile
    # (which may have skipped the detector) must still end the job as stopped.
    stopped = vlm is None and stop()
    progress(0, total, None)
    for visited, position in enumerate(selection.visit_order):
        if stop() or vlm is None:
            stopped = vlm is not None
            break
        lo, hi = selection.slab_bounds[position]
        tag = selection.tags[position]
        t0 = clock()
        hu2d = volume.hu[lo:hi].max(axis=0)
        png = render_slice_png(hu2d, window, size)
        thickness = (hi - lo) * float(volume.spacing_mm[0])
        caption = (
            f"IMAGE 1: axial, {_WINDOW_NAMES[window]}, {thickness:.0f} mm MIP slab, "
            f"slab {position + 1} of {total} from cranial to caudal, level: {tag}"
        )
        prepared = PreparedInput(
            view_id=config.view,
            view_version=f"full-review-{RUNNER_VERSION}",
            images=[png],
            image_captions=[caption],
            slice_indices=[selection.indices[position]],
            meta={"strategy": sweep.id, "strategy_sha256": sweep.sha256, "n_images": 1},
        )
        raw = vlm.infer(prepared, request)
        if stop() and raw.error is not None:
            stopped = True  # the stop aborted this request; it was never answered
            break
        report = vlm.parse(raw)
        if raw.error is None and report.abstain and report.findings:
            # A study-level self-abstention ("only one slice visible") is expected for a
            # single slab; the per-label answers for this image are kept.
            report.abstain = False
            report.parse_warnings.append("slab self-abstention ignored; per-label answers kept")
        _check_image_evidence(report, 1, required=True)
        elapsed = clock() - t0
        durations.append(elapsed)
        status = "error" if raw.error is not None else "abstained" if report.abstain else "answered"
        entry: dict[str, Any] = {
            "position": position,
            "slice_lo": lo,
            "slice_hi": hi - 1,
            "center": selection.indices[position],
            "level": tag,
            "visit": visited + 1,
            "status": status,
            "seconds": round(elapsed, 3),
            "image_sha256": hashlib.sha256(png).hexdigest(),
            "positives": [],
            "warnings": report.parse_warnings[:5],
        }
        thumbnails[position] = _thumbnail(png)
        if status == "answered":
            values, evidence, sides = _slab_answers(report, labels)
            answered.append(SlabAnswers(position, lo, hi, values, evidence, sides))
            entry["positives"] = [label for label in labels if values[label]]
            entry["unanswered"] = [label for label in labels if values[label] is None]
            failures_before_answer = 0
        else:
            entry["error"] = (raw.error or "; ".join(report.parse_warnings))[:200]
            failures_before_answer += 1 if status == "error" and not answered else 0
        slabs.append(entry)
        rate = sum(durations) / len(durations)
        progress(visited + 1, total, rate)
        if not answered and failures_before_answer >= MAX_INITIAL_FAILURES:
            runtime_failed = True
            break
    announce("aggregate")
    aggregate = aggregate_labels(answered, labels)
    clusters = [c for s in aggregate.labels.values() for c in s.clusters]
    slab_slices = (selection.slab_bounds[0][1] - selection.slab_bounds[0][0]) if total else 1
    look_here = rank_look_here(
        clusters,
        candidates,
        cues,
        slab_slices=slab_slices,
        spacing_z_mm=float(volume.spacing_mm[0]),
    )
    verdict = verdict_of(
        look_here,
        answered_slabs=len(answered),
        model_constant=aggregate.model_constant,
        detector_completed=detector_info.get("status") == "completed",
        study_adequate=adequate,
    )
    by_status: dict[str, list[str]] = {
        key: [lbl for lbl, s in aggregate.labels.items() if s.status == key]
        for key in ("flagged", "not_informative", "no_flags", "unanswered")
    }
    covered = [selection.slab_bounds[0][0], selection.slab_bounds[-1][1] - 1] if total else None
    visited_count = len(slabs)
    summary: dict[str, Any] = {
        "kind": "full_review",
        "version": RUNNER_VERSION,
        "model_id": model_id,
        "prompt_id": PROMPT_ID,
        "verdict": verdict,
        "study_quality_adequate": adequate,
        "coverage": {
            "slabs_total": total,
            "slabs_visited": visited_count,
            "slabs_answered": len(answered),
            "fraction_answered": round(len(answered) / total, 4) if total else 0.0,
            "partial": visited_count < total,
            "stopped": stopped,
            "runtime_failed": runtime_failed,
            "slab_mm": selection.slab_mm,
            "slices_total": int(volume.shape[0]),
            "covered_slices": covered,
            "lung_slices": list(study.cues.lung_z_extent)
            if adequate and study.cues.lung_z_extent
            else None,
        },
        "timing": {
            "seconds_per_image": round(sum(durations) / len(durations), 3) if durations else None,
            "total_s": round(clock() - started, 3),
        },
        "labels": labels,
        "label_names": {lbl: names.get(lbl, lbl) for lbl in labels},
        "per_label": {
            lbl: {
                "status": s.status,
                "answered": s.answered,
                "positives": s.positives,
                "positive_rate": None if s.positive_rate is None else round(s.positive_rate, 4),
                "clusters": [vars(c) for c in s.clusters],
            }
            for lbl, s in aggregate.labels.items()
        },
        "labels_flagged": by_status["flagged"],
        "labels_not_informative": by_status["not_informative"],
        "labels_no_flags": by_status["no_flags"],
        "labels_unanswered": by_status["unanswered"],
        "model_constant": aggregate.model_constant,
        "overall_positive_rate": None
        if aggregate.overall_positive_rate is None
        else round(aggregate.overall_positive_rate, 4),
        "look_here": [item.to_dict() for item in look_here],
        "next_steps": next_steps(look_here, verdict, names),
        "detector": detector_info,
        "heuristic": heuristic_info,
        "slabs": sorted(slabs, key=lambda s: s["position"]),
    }
    summary["provenance"] = RunProvenance.collect(
        settings.repo_root,
        model_id=model_id,
        model_hash=identity.get("digest") if isinstance(identity, dict) else None,
        prompt_hash=prompt_sha,
        input_hash=sha256_of_obj(
            {
                "canonical_hu_sha256": hashlib.sha256(volume.hu.tobytes()).hexdigest(),
                "shape": volume.shape,
                "spacing_mm": volume.spacing_mm,
            }
        ),
        preprocess_hash=sha256_of_obj(
            {
                "strategy": sweep.id,
                "strategy_version": sweep.version,
                "strategy_sha256": sweep.sha256,
                "window": window,
                "size": size,
                "runner_version": RUNNER_VERSION,
                "cues": study.cues.version if adequate else "not-run",
            }
        ),
        config_hash=sha256_of_obj(
            {"model": config.model_dump(mode="json"), "thresholds": thresholds()}
        ),
        seed=config.options.get("ollama", {}).get("seed", 0),
    ).model_dump(mode="json") | {
        "strategy": {"id": sweep.id, "version": sweep.version, "params": sweep.params},
        "strategy_sha256": sweep.sha256,
        "thresholds": thresholds(),
    }
    redacted = settings_redactor(settings, study.identifiers).redact_obj(summary)
    if not isinstance(redacted, dict):  # pragma: no cover - redact_obj preserves shape
        raise TypeError("redaction changed the summary shape")
    return FullReviewRun(redacted, thumbnails)
