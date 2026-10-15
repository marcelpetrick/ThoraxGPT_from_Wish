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

## Priority (user decision, 2026-10-15)

**Now:** (a) test data and (b) a first runnable end-to-end prototype — `thoraxbench analyze
<dicom-dir> --model <id>` producing findings JSON + the English Markdown clinical report on a
real LIDC study with a local Ollama model. *Then* flesh out (benchmark, calibration, UI).


1. **Engine first.** The end-to-end engine must work and give good, measured results before
   any UI work: ingest → preprocess → sample → infer → parse → score → clinical report.
2. **Locally hosted models on Ollama** are the runtime that matters. MedGemma 1.5 (Q4/Q8) and
   general VLM controls are benchmarked for real on the pilot development split. 3D PyTorch
   services stay optional adapters.
3. The UI (WP9, `docs/ui.md`) follows only after the engine produces results.

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
| ✅ WP1 | Model research and Ollama pulls (MedGemma Q4/Q8, controls), feasibility of 3D models | 4, 22 | research agent |
| 🔄 WP2 | Dataset research ✅, license registry ✅ (16 sources), pilot ✅ (LIDC 60 pts + NSCLC-Radiogenomics 27 pts, 6.7 GB), `thoraxbench acquire` port ⏳ | 5, 6, 8, 27 | data agent |
| ✅ WPA | Architecture (C4 + flowcharts) in `docs/architecture.md` — before deeper work | 7, 17 | lead |
| 🔄 WP3 | Core: config/registry ✅, policy gate ✅, DICOM discovery/geometry/HU/QC ✅, synthetic phantoms ✅ | 6, 8, 9 | lead / agents |
| ✅ WP4 | Sampling S1–S6, windows, rendering views | 10 | agent |
| ✅ WP5 | Schemas, ontology, prompts P0–P4, adapters (Ollama, HTTP 3D service, mock) | 11, 12, 17, 19 | agent |
| 🔄 WP6 | Splits and sealing ✅ (CaseGuard, freeze), leakage tracking ⏳ | 14, 15, 16 | lead |
| ✅ WP7 | Scoring (A–G), calibration, bootstrap CIs, perf measurements, provenance | 13, 20, 21, 24 | agent |
| ⏳ WP8 | Benchmark runner, experiments E001–E008 configs, compare, reports | 18, 25, 26 | agent |
| 🔄 WP9 | Web UI (concept ✅ in `docs/ui.md`: CLI = engine, local FastAPI+Jinja2+HTMX UI = review layer), implementation, Playwright e2e, screenshot | 18 | lead |
| ✖ WP10 | ~~Docker, compose, GHCR workflow~~ — dropped at the user's request | 17 | — |
| ⏳ WP11 | Real runs on the pilot data (dev split only), benchmark report | 26, 32 | lead |
| 🔄 WP13 | Radiologist-style reading research → preprocessing (windows, MIP, coronal, HU cues) and the per-study English Markdown clinical report (term, plain language, severity, treatment need, prevalence, follow-up) | user request | research agent + lead |
| ⏳ WP12 | `/reviewBranch`, fixes, `/githubAbout`, final Vision checklist | all | lead |

## Current activity

Updated with every commit (newest first). **If a session breaks, the next agent resumes
from here**: read this section and *Next steps*, then `git log --oneline | head -20`.

- 🔄 **Lead, now:** first end-to-end prototype — `analysis.py` (study → view → model → parsed
  findings, perf + provenance) ✍️ written, next: `reports/study_report.py` (English Markdown:
  medical term, plain language, severity, treatment need, prevalence, guideline follow-up) and CLI
  commands `analyze`, `index`, `split`, `demo-data`, `models`, `datasets`.
- ✅ **Test data available (outside Git, `data/raw/`):** LIDC-IDRI 60 patients (40 with nodules
  ≥3 mm, 20 without) + NSCLC-Radiogenomics 27 patients with tumour SEG; synthetic DICOM phantoms
  for tests/demos (`thoraxbench.synthetic`).
- 🔄 **Running now:** study index build for `lidc_idri` (60) and `nsclc_radiogenomics` (27):
  loads every study once, derives reference labels (LIDC reader XML / NSCLC DICOM-SEG) and HU
  cues → `data/index/<dataset>.json` (log: `.pipeline/build_index.log`, ~15 s per study).
  Code: `src/thoraxbench/index.py`, `labels/nsclc.py` (being committed with tests).
- ⛔ **Blocker waiting for the user:** the root partition `/` is 100 % full because the system
  Ollama service stores models in `/usr/share/ollama/.ollama/models`. Fix (needs sudo, run once):
  `sudo scripts/move_ollama_models_to_home.sh` → models move to `/home/ollama/models` via
  `OLLAMA_MODELS`. The `gemma3:4b-it-q4_K_M` pull failed for that reason; retry it afterwards.
  MedGemma 1.5 Q4/Q8 are already pulled and usable.
- ✅ LIDC reader-XML parser → consensus lesions + study labels (`labels/lidc.py`).
- ✅ WP4 sampling S1–S6 + MIP slabs, views (MedGemma RGB per official notebook, lung, multi-window,
  contact sheet, CT-CLIP/M3D tensors), `Study` with HU volume cache; heuristic baseline wired to
  real HU cues. Smoke-tested on a real LIDC study (load 5 s, cues 10 s, view 1.5 s).
- ✅ WP1 model research: MedGemma 1.5 Q4/Q8 pulled, ~270 tokens and ~3 s prefill per image on
  the A2000; gemma3:4b pulled as same-architecture control (`docs/model_cards.md`).
- ✅ WP5 prompts P0–P4, parsing, adapters (Ollama, HTTP 3D service, heuristic) landed.
- ✅ UI ideation + concept: `docs/ui.md` (decision: CLI is the engine; local-only web UI
  with FastAPI + Jinja2 + vendored HTMX for review; Playwright e2e + README screenshot).
- ✅ Data pilot downloaded (outside Git): LIDC-IDRI 60 patients 4.3 GB, NSCLC-Radiogenomics
  27 patients 2.4 GB (both CC BY 3.0), checksummed; registry (`configs/datasets/`) + `docs/datasets.md` + `manifests/datasets/` committed.
- ✅ WP7 scoring (tasks A–G, bootstrap), calibration (sealed-safe), perf, provenance landed.
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

1. Land the WP4/WP5/WP7 worker branches (`scripts/land_branch.sh`).
2. Commit the dataset registry (`configs/datasets/*.yaml`) and `docs/datasets.md`; port the
   pilot downloader into `thoraxbench acquire` (license gate, budget, checksums, manifests).
3. LIDC XML → reference labels + lesions; NSCLC-Radiogenomics labels; study index; freeze the
   80/20 patient-level split (sealed 20 % stored in `data/sealed/`).
4. `thoraxbench analyze` end to end on a real study with an Ollama model + the English
   Markdown clinical report.
5. Benchmark runner + experiment configs E001–E004 (+ E008 external) + `compare` + report.
6. **Real runs on the development split** with Ollama models (MedGemma 1.5 Q4/Q8, qwen3-vl,
   other controls) + heuristic baseline; iterate on prompts/sampling on calibration only;
   document results in `docs/results.md`.
7. Web UI per `docs/ui.md` + Playwright e2e + real screenshot (WP9).
8. `/reviewBranch`, fixes, `/githubAbout`, Vision traceability check (WP12).

## Self-review gates

* After every work package: full `./localPipeline.sh` green, then commit and push.
* After WP8 and at the end: walk through `docs/vision_traceability.md` (one row for every
  Vision section) and close any gaps.
