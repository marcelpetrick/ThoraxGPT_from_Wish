#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
"""Bounded P6 check: matched synthetic 30 mm sphere/control crops, one condition per call."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import numpy as np

from thoraxbench import __version__
from thoraxbench.adapters.factory import load_model
from thoraxbench.adapters.p6 import P6OllamaModel, nonconstant_readiness
from thoraxbench.analysis import DISCLAIMER
from thoraxbench.benchmark.sanity_inputs import render_axial
from thoraxbench.config import Settings
from thoraxbench.provenance import git_state, sha256_of_file, sha256_of_obj
from thoraxbench.reports.html_report import require_results_path
from thoraxbench.schemas import AnalysisRequest, PreparedInput
from thoraxbench.study import load_study_dir
from thoraxbench.synthetic import PhantomSpec, make_phantom, write_dicom_series
from thoraxbench.views import CandidateCropView
from thoraxbench.views.builders import render_slice_png


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="medgemma1.5-q4-p6")
    parser.add_argument("--reasoning-tokens", type=int, choices=range(1, 513), default=192)
    parser.add_argument("--window", choices=["medgemma", "lung", "both"], default="both")
    parser.add_argument("--view", choices=["crop", "full"], default="crop")
    parser.add_argument("--slab-mm", type=float, choices=[0.0, 5.0], default=0.0)
    args = parser.parse_args()
    if args.view == "crop" and args.slab_mm:
        parser.error("--slab-mm is supported for --view full only")
    return args


def main() -> int:
    args = _arguments()
    settings = Settings()
    print(DISCLAIMER, flush=True)
    folder = settings.data_path("results", "p6-probe", str(uuid4()))
    require_results_path(folder / "manifest.json", settings)
    model = load_model(args.model, settings)
    if not isinstance(model, P6OllamaModel):
        raise SystemExit("Select a P6 model configuration")
    if not model.available():
        raise SystemExit("The configured P6 tag is unavailable; no download is started")
    model.config = model.config.model_copy(
        update={
            "options": model.config.options
            | {
                "p6": model.config.options.get("p6", {})
                | {"reasoning_tokens": args.reasoning_tokens}
            }
        }
    )
    windows = ["medgemma", "lung"] if args.window == "both" else [args.window]
    package = Path(__file__).resolve().parents[1] / "src" / "thoraxbench"
    commit, dirty = git_state(settings.repo_root)
    identity = {
        "schema_version": 1,
        "purpose": "Synthetic selected-plane/crop readiness; no patient data or accuracy claim",
        "version": __version__,
        "git_commit": commit,
        "git_dirty": dirty,
        "source_sha256": sha256_of_obj(
            {str(p.relative_to(package)): sha256_of_file(p) for p in sorted(package.rglob("*.py"))}
        ),
        "script_sha256": sha256_of_file(Path(__file__)),
        "model": model.describe(),
        "effective_config": model.config.model_dump(mode="json"),
        "prompt_sha256": model.prompt.sha256,
        "windows": windows,
        "view": args.view,
        "slab_mm": args.slab_mm,
        "crop_mm": 64 if args.view == "crop" else None,
        "size": 896,
        "n_inputs": 2 * len(windows),
        "disclaimer": DISCLAIMER,
    }
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "manifest.json").write_text(json.dumps(identity, indent=2))
    print(f"Artifacts: {folder}", flush=True)
    request = AnalysisRequest(labels=["pulmonary_nodule"], prompt_id="P6")
    records = []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="thoraxbench-p6-synthetic-") as temporary:
        for positive in [False, True]:
            spec = PhantomSpec(nodule_radius_mm=15.0 if positive else 0.0)
            name = "sphere" if positive else "control"
            path = Path(temporary) / name
            write_dicom_series(make_phantom(spec), path, spec.spacing_mm, include_scout=False)
            study = load_study_dir(path, dataset="synthetic", case_id=name)
            nz, ny, nx = spec.shape
            dz, dy, dx = spec.spacing_mm
            centre = (0.35 * nz * dz, 0.5 * ny * dy, 0.28 * nx * dx)
            crop = CandidateCropView(crop_mm=64, size=896).crop_hu(study.volume, centre, "axial")
            for window in windows:
                image = (
                    render_slice_png(np.rint(crop).astype(np.int16), window, 896)
                    if args.view == "crop"
                    else render_axial(
                        study.volume.hu, round(0.35 * nz), args.slab_mm, dz, window=window, size=896
                    )
                )
                prepared = PreparedInput(
                    view_id=f"synthetic_{args.view}_probe_v2",
                    view_version="1",
                    images=[image],
                    image_captions=[
                        "SLICE 1: single axial CT crop, 64 mm field of view"
                        if args.view == "crop"
                        else "SLICE 1: single axial CT image"
                    ],
                    meta={
                        "include_cues": False,
                        "window": window,
                        "view": args.view,
                        "slab_mm": args.slab_mm,
                        "known_synthetic_target_plane": True,
                    },
                )
                raw = model.infer(prepared, request)
                report = model.parse(raw)
                diagnostic = raw.meta.get("label_diagnostics", [{}])[0]
                record = {
                    "synthetic_reference": positive,
                    "window": window,
                    "image_sha256": hashlib.sha256(image).hexdigest(),
                    "prepared": prepared.model_dump(mode="json", exclude={"images"}),
                    "raw": raw.model_dump(mode="json"),
                    "report": report.model_dump(mode="json"),
                    "answer": diagnostic.get("answer"),
                    "p_yes": diagnostic.get("p_yes"),
                    "reason": diagnostic.get("reason") or raw.error,
                }
                records.append(record)
                (folder / f"{name}-{window}.json").write_text(json.dumps(record, indent=2))
                print(f"{name}/{window}: {diagnostic} {raw.error or ''}", flush=True)
    result = {
        "wall_s": time.perf_counter() - started,
        "readiness_by_window": {
            window: nonconstant_readiness(
                [
                    (r["synthetic_reference"], r["answer"], r["p_yes"])
                    for r in records
                    if r["window"] == window
                ]
            )
            for window in windows
        },
        "identity_sha256": sha256_of_obj(identity),
        "disclaimer": DISCLAIMER,
    }
    (folder / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
