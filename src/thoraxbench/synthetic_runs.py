# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Synthetic, checkpointed benchmark invocations for tests, demos and documentation captures.

The real development runner processes code-generated DICOM phantoms (never patient data)
through the real split guard and index. The heuristic experiment runs the actual HU
baseline. The "vision" experiment uses a scripted analyzer instead of a model: every raw
response states that no model ran. It exists only to exercise abstentions, failures,
evidence-reference checks and parse warnings in the read-only Evaluation view.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from thoraxbench.analysis import AnalysisResult, _check_image_evidence, analyze_study
from thoraxbench.benchmark.config import load_experiment
from thoraxbench.benchmark.runner import run_experiment
from thoraxbench.config import REPO_ROOT, Settings
from thoraxbench.dicom import discover_series
from thoraxbench.index import build_index
from thoraxbench.schemas import AnalysisRequest, Finding, FindingsReport, StudyQuality
from thoraxbench.splits import CaseRecord, Phase, make_split, save_split
from thoraxbench.study import Study
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series

DATASET = "lidc_idri"
INDEXED = ("SYNTH-P1", "SYNTH-P2", "SYNTH-P3", "SYNTH-P4")
NOT_INDEXED = "SYNTH-P5"
SEALED = "SYNTH-SEALED"
LABELS = ["pulmonary_nodule", "pulmonary_mass"]
SCRIPTED_IMAGES = 4
SCRIPTED_NOTE = "SYNTHETIC scripted response for UI tests; no model ran. <b>not markup</b>"
_NODULE = """<unblindedReadNodule><noduleID>1</noduleID><roi><imageZposition>0.0</imageZposition>
<inclusion>TRUE</inclusion><edgeMap><xCoord>40</xCoord><yCoord>40</yCoord></edgeMap>
<edgeMap><xCoord>44</xCoord><yCoord>40</yCoord></edgeMap></roi></unblindedReadNodule>"""
_XML = (
    '<?xml version="1.0"?><LidcReadMessage xmlns="http://www.nih.gov">'
    "<readingSession>{}</readingSession></LidcReadMessage>"
)


@dataclass(frozen=True)
class SyntheticBenchmarks:
    """Settings that read the synthetic tree, and the completed invocation folders."""

    settings: Settings
    runs: list[Path]


def _require_isolated(root: Path) -> None:
    if root.resolve().is_relative_to(REPO_ROOT.resolve()):
        msg = "synthetic benchmarks need a directory outside the repository checkout"
        raise ValueError(msg)


def _write_studies(settings: Settings) -> None:
    spec = PhantomSpec(shape=(40, 64, 64), spacing_mm=(5.0, 5.0, 5.0), nodule_radius_mm=8.0)
    hu = make_phantom(spec)
    raw = settings.data_path("raw", DATASET)
    labels = raw / "_labels" / "xml_selected"
    labels.mkdir(parents=True)
    for index, patient in enumerate(INDEXED):
        staging = write_dicom_series(
            hu,
            settings.data_path("staging", patient),
            spec.spacing_mm,
            patient_id=patient,
            include_scout=False,
        )
        series = discover_series(staging)[0]
        (raw / patient).mkdir()
        staging.rename(raw / patient / series.series_uid)
        nodule = _NODULE if index in {0, 2} else ""
        (labels / f"{series.series_uid}.xml").write_text(_XML.format(nodule), encoding="utf-8")
    # An empty development folder becomes an explicit not-indexed case; the sealed folder
    # stays empty and is never listed, opened or scored.
    (raw / NOT_INDEXED).mkdir()
    (raw / SEALED).mkdir()


def _write_split(settings: Settings) -> None:
    records = [
        CaseRecord(dataset=DATASET, patient_id=patient, case_id=patient)
        for patient in (*INDEXED, NOT_INDEXED, SEALED)
    ]
    for seed in range(500):
        split = make_split(records, DATASET, salt=f"synthetic-evaluation-{seed}")
        if (
            split.cases(Phase.SEALED) == [SEALED]
            and split.cases(Phase.CALIBRATION)
            and split.cases(Phase.INTERNAL_TEST)
        ):
            save_split(split, settings.data_dir, settings.manifests_dir)
            return
    msg = "no deterministic synthetic split salt satisfied the phase layout"  # pragma: no cover
    raise RuntimeError(msg)  # pragma: no cover


def _scripted(case_id: str, model_id: str) -> tuple[FindingsReport, dict[str, Any]] | None:
    """Return a deterministic scripted report and its raw JSON, or None for a failure."""
    position = INDEXED.index(case_id)
    q8 = model_id.endswith("q8")
    if q8 and position == 3:
        return None
    findings: list[dict[str, Any]]
    quality = True
    if position == 0:
        findings = [
            {"label": "pulmonary_nodule", "present": True, "confidence": 0.82}
            | {"evidence_images": [2, 3]}
        ]
    elif position == 1:
        findings = [{"label": "pulmonary_nodule", "present": None, "confidence": None}]
        quality = q8
    elif position == 2:
        findings = [
            {"label": "pulmonary_nodule", "present": True, "confidence": 0.7}
            | {"evidence_images": [2, 2, 7]},
            {"label": "pulmonary_mass", "present": True, "confidence": 0.6},
        ]
    else:
        findings = [
            {"label": "pulmonary_nodule", "present": False, "confidence": 0.9},
            {"label": "pulmonary_mass", "present": False, "confidence": 0.8},
        ]
    raw = {"study_quality": {"adequate": quality}, "findings": findings, "note": SCRIPTED_NOTE}
    report = FindingsReport(
        study_quality=StudyQuality(
            adequate=quality,
            limitations=[] if quality else ["scripted: prepared images marked inadequate"],
        ),
        findings=[Finding.model_validate(item) for item in findings],
    )
    if not quality:
        report.abstain = True
        report.parse_warnings.append("model marked prepared study inadequate")
    _check_image_evidence(report, SCRIPTED_IMAGES, required=True)
    if not report.abstain and all(report.label_probability(label) is None for label in LABELS):
        report.abstain = True
        report.parse_warnings.append("no available requested-label predictions returned")
    return report, raw


def scripted_analyzer(
    study: Study,
    model_id: str,
    settings: Settings,
    *,
    request: AnalysisRequest | None = None,
    prompt_id: str | None = None,
    view_overrides: dict[str, Any] | None = None,
) -> AnalysisResult:
    """Pretend to be a vision model with fixed outputs; never contacts a model runtime."""
    scripted = _scripted(study.case_id, model_id)
    if scripted is None:
        msg = "scripted synthetic runtime failure (no model ran)"
        raise RuntimeError(msg)
    report, raw = scripted
    base = analyze_study(study, "heuristic-hu", settings, view_overrides=view_overrides)
    captions = [
        f"Image {number}: synthetic axial slice {number * 8} (lung window)"
        for number in range(1, SCRIPTED_IMAGES + 1)
    ]
    perf = base.perf.model_copy(update={"n_images": SCRIPTED_IMAGES})
    return base.model_copy(
        update={
            "model_id": model_id,
            "request": request or AnalysisRequest(prompt_id=prompt_id or "P2"),
            "report": report,
            "raw_text": json.dumps(raw, indent=2),
            "raw_error": None,
            "raw_meta": {"scripted": True},
            "image_captions": captions,
            "slice_indices": [number * 8 for number in range(1, SCRIPTED_IMAGES + 1)],
            "context": "",
            "perf": perf,
            "provenance": base.provenance.model_copy(update={"model_id": model_id}),
        }
    )


def _experiment(folder: Path, name: str, body: dict[str, Any]) -> Path:
    path = folder / f"{name}.yaml"
    path.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    return path


def build_synthetic_benchmarks(root: Path, **overrides: Any) -> SyntheticBenchmarks:
    """Create synthetic studies, a split, an index and two completed benchmark invocations.

    *root* must be empty or absent and lie outside the repository, because the split
    manifest is written below ``root/repo/manifests``. Extra keyword arguments override
    :class:`Settings` fields such as ``ollama_url``.
    """
    _require_isolated(root)
    repo = root / "repo"
    repo.mkdir(parents=True)
    (repo / "configs").symlink_to(REPO_ROOT / "configs", target_is_directory=True)
    settings = Settings(repo_root=repo, data_dir=root / "data", **overrides)
    _write_studies(settings)
    _write_split(settings)
    build_index(DATASET, settings)
    experiments = root / "experiments"
    experiments.mkdir()
    common = {"datasets": [DATASET], "labels": LABELS, "n_boot": 0}
    baseline = _experiment(
        experiments,
        "SYNTH-E000",
        {
            "id": "SYNTH-E000",
            "title": "Synthetic HU baseline over phantoms",
            "model": "heuristic-hu",
        }
        | common,
    )
    vision = _experiment(
        experiments,
        "SYNTH-E001",
        {
            "id": "SYNTH-E001",
            "title": "Synthetic scripted vision outputs (no model ran)",
            "model": "medgemma1.5-q4",
            "prompt": "P2",
            "variants": [
                {"id": "q4-p2", "model": "medgemma1.5-q4"},
                {"id": "q8-p2", "model": "medgemma1.5-q8"},
            ],
        }
        | common,
    )
    first = run_experiment(load_experiment(baseline), settings)
    second = run_experiment(load_experiment(vision), settings, analyze=scripted_analyzer)
    runs = [result.output_dir for result in (first, second) if result.output_dir is not None]
    return SyntheticBenchmarks(settings, runs)
