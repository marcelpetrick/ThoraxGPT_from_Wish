# ThoraxBench Local — Implementation Plan

This plan turns [`Vision.md`](../Vision.md) into a working product. Decisions recorded
here are binding until changed by a later commit to this file.

## Environment facts (2026-10-15)

| Item | Value |
|---|---|
| Python | 3.14 (managed with `uv`) |
| Ollama | 0.40.4, local server `http://localhost:11434` |
| GPU | NVIDIA RTX A2000 Laptop, 8 GB VRAM |
| RAM | 31 GB |
| Data budget | 10 GB in `./data/` (git-ignored, enforced by `thoraxbench data budget`) |
| Hugging Face token | none — gated sources (CT-RATE, CT-CLIP weights) are registered as `pending_access` |

## Key decisions

1. **Package**: `thoraxbench` under `src/`, built with hatchling, one version source
   (`src/thoraxbench/__init__.py`). Semver: every commit bumps patch
   (`scripts/bump_version.sh patch`), major features bump minor.
2. **Branch**: work directly on `main`; repo `marcelpetrick/ThoraxGPT_from_Wish` (created by the user; public, so the data-policy gate is extra strict).
3. **License**: GPL-3.0-or-later, SPDX headers in every source file.
4. **Data**: open TCIA collections only (no token available). LIDC-IDRI (CC BY 3.0) is the
   primary pilot dataset. Further sources are registered with their license status;
   gated ones stay `pending_terms_review`/`pending_access` and can never be acquired.
5. **Split policy**: deterministic patient-level, label-stratified 80 % development
   (calibration + internal test) / 20 % **sealed** validation. The sealed IDs are written to
   `data/sealed/` and to a hash-only manifest in Git. Every dataset loader filters the sealed
   IDs out unless a frozen experiment config is run with `--unseal`. A
   `SealedAccessError` guard and tests make this hard to get wrong by accident.
6. **Models**: the Ollama adapter is the main runtime (MedGemma 1.5 Q4/Q8, plus general VLM
   controls that fit in 8 GB VRAM). 3D-native models (CT-CLIP, M3D-LaMed, CT-CHAT, RadFM) and
   HuatuoGPT-Vision sit behind an HTTP service adapter contract, with a reference service
   container. They need weights or GPU memory we lack today, so they show up as
   "unavailable" without blocking anything.
7. **Stack**: pydicom + numpy for DICOM/HU, Pillow for rendering, pydantic for schemas,
   Typer for the CLI, FastAPI + Jinja2 for the local web UI, httpx for Ollama,
   pytest/pytest-cov/ruff/mypy/Playwright for quality gates.
8. **Docker**: dropped for this project at the user's request (2026-10-15). Everything runs
   locally against the host Ollama server; 3D-model services are plain local HTTP processes.

## Work packages

Status: ✅ done · 🔄 in progress · ⏳ open · ✖ dropped

| # | Package | Vision § | Owner |
|---|---|---|---|
| ✅ WP0 | Repo bootstrap: LICENSE, README, AGENTS.md, pyproject, `localPipeline.sh`, CI, version script | 7, 30, 31-M0 | lead |
| 🔄 WP1 | Model research and Ollama pulls (MedGemma Q4/Q8, controls), feasibility of 3D models | 4, 22 | research agent |
| 🔄 WP2 | Dataset research, license registry, acquisition of a ≤10 GB LIDC-IDRI pilot | 5, 6, 8, 27 | data agent |
| ✅ WPA | Architecture (C4 + flowcharts) in `docs/architecture.md` — before deeper work | 7, 17 | lead |
| 🔄 WP3 | Core: config/registry ✅, policy gate ✅, DICOM discovery/geometry/HU/QC ✅, synthetic phantoms ✅ | 6, 8, 9 | lead / agents |
| ⏳ WP4 | Sampling S1–S6, windows, rendering views | 10 | agent |
| ⏳ WP5 | Schemas, ontology, prompts P0–P4, adapters (Ollama, HTTP 3D service, mock) | 11, 12, 17, 19 | agent |
| 🔄 WP6 | Splits and sealing ✅ (CaseGuard, freeze), leakage tracking ⏳ | 14, 15, 16 | lead |
| ⏳ WP7 | Scoring (A–G), calibration, bootstrap CIs, perf measurements, provenance | 13, 20, 21, 24 | agent |
| ⏳ WP8 | Benchmark runner, experiments E001–E008 configs, compare, reports | 18, 25, 26 | agent |
| 🔄 WP9 | Web UI (concept ✅ in `docs/ui.md`: CLI = engine, local FastAPI+Jinja2+HTMX UI = review layer), implementation, Playwright e2e, screenshot | 18 | lead |
| ✖ WP10 | ~~Docker, compose, GHCR workflow~~ — dropped at the user's request | 17 | — |
| ⏳ WP11 | Real runs on the pilot data (dev split only), benchmark report | 26, 32 | lead |
| 🔄 WP13 | Radiologist-style reading research → preprocessing (windows, MIP, coronal, HU cues) and the per-study English Markdown clinical report (term, plain language, severity, treatment need, prevalence, follow-up) | user request | research agent + lead |
| ⏳ WP12 | `/reviewBranch`, fixes, `/githubAbout`, final Vision checklist | all | lead |

## Current activity

Updated with every commit (newest first). **If a session breaks, the next agent resumes
from here**: read this section and *Next steps*, then `git log --oneline | head -20`.

- ✅ UI ideation + concept: `docs/ui.md` (decision: CLI is the engine; local-only web UI
  with FastAPI + Jinja2 + vendored HTMX for review; Playwright e2e + README screenshot).
- ✅ Data pilot downloaded (outside Git): LIDC-IDRI 60 patients 4.3 GB, NSCLC-Radiogenomics
  27 patients 2.4 GB (both CC BY 3.0), checksummed; registry + docs being committed.
- 🔄 Wrap-up requested by the user: all workers commit their green state; the lead lands each
  branch with `scripts/land_branch.sh <branch>`.
- 🔄 Fan-out of parallel work packages (git worktrees, landed on `main` by the lead):
  WP4 preprocess/sampling/views · WP5 prompts/adapters/parsing · WP7 scoring/calibration/perf.
- 🔄 Lead: WP6 splits + sealing guard, then WP2 integration (`thoraxbench acquire`, LIDC labels).
- 🔄 Background research (results arrive as notes and are then committed to `docs/`):
  WP1 Ollama model survey + MedGemma 1.5 pulls → `docs/model_cards.md`;
  WP2 dataset licenses + LIDC-IDRI pilot download into `data/raw/` → `docs/datasets.md`,
  `configs/datasets/*.yaml`; WP13 radiologist reading practice + findings knowledge base →
  `docs/reading_practice.md`, `src/thoraxbench/ontology/clinical_kb.yaml`.
- ✅ WP13 research: `docs/reading_practice.md`, clinical knowledge base + Fleischner/Lung-RADS
  rules (`ontology/clinical.py`, `ontology/guidelines.py`); report rendering still open.
- ✅ WP6 splits + sealed guard (`splits/`).
- ✅ Schemas + ontology (v0.0.7), DICOM loader + phantoms (v0.0.6), registry (v0.0.5),
  architecture (v0.0.3), bootstrap (v0.0.1).

## Next steps (in order)

1. Land WP4/WP5/WP7 branches; WP6 splits + sealing guard.
2. Commit research outputs (model cards, dataset registry YAMLs, reading practice, clinical KB).
3. `thoraxbench acquire` (TCIA client, manifests, budget, de-id audit) + LIDC XML label loader;
   build the study index for the downloaded pilot and freeze the 80/20 split.
4. Clinical Markdown study report (WP13) + `thoraxbench analyze`.
5. Benchmark runner, experiment configs E001–E008, `compare`, benchmark report (WP8).
6. Web UI per `docs/ui.md` + Playwright e2e + real screenshot (WP9).
7. Real runs on the development split with MedGemma Q4/Q8 + controls (WP11).
8. `/reviewBranch`, fixes, `/githubAbout`, Vision traceability check (WP12).

## Self-review gates

* After every work package: full `./localPipeline.sh` green, then commit and push.
* After WP8 and at the end: walk through `docs/vision_traceability.md` (one row for every
  Vision section) and close any gaps.
