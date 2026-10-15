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
| Data budget | 10 GB in `./data/` (git-ignored; configured limit, acquisition/budget CLI still pending) |
| Hugging Face token | none — gated sources (CT-RATE, CT-CLIP weights) are registered as `pending_access` |

## Priority (user decision, 2026-10-15)

**Delivered (user update, 2026-10-15):** a polished, tested **local UI MVP** around
`analyze`, plus a documented test walkthrough, model-selection chart and reproducible
synthetic result. The CLI prototype and frozen holdout are committed (`fb7d7b7`, v0.0.29).

1. UI defaults: **light mode and English**; persistent dark/light and English/German
   switches; translated accessible hover/focus tooltips on actions, labels and metrics.
2. About: author Marcel Petrick, purpose/research disclaimer, project license, installed
   library versions and licenses. Guided study → model → findings/report/download workflow.
3. Keep engine results honest: heuristic demo works; local MedGemma transport works but
   useful CT prediction and accuracy are unproven. Show errors/abstentions explicitly.
4. Respect the frozen patient holdout in CLI, indexer and UI; synthetic data for tests.
5. Document 40 GB VRAM model candidates and an optional trusted LAN Ollama architecture;
   **implementation and remote checks wait until tomorrow**. Loopback-only inference stays.
6. Benchmark/calibration and the full review UI follow the tested MVP. Current user request
   brings the UI MVP forward from the earlier engine-first schedule.

## Key decisions

1. **Package**: `thoraxbench` under `src/`, built with hatchling, one version source
   (`src/thoraxbench/__init__.py`). Semver: every commit bumps patch
   (`scripts/bump_version.sh patch`), major features bump minor.
2. **Branch**: work directly on `main`; repo `marcelpetrick/ThoraxGPT_from_Wish` (created by the user; public, so the data-policy gate is extra strict).
3. **License**: GPL-3.0-or-later, SPDX headers in every source file.
4. **Data**: open TCIA collections only (no token available). LIDC-IDRI (CC BY 3.0) is the
   primary pilot dataset. Further sources are registered with their license status;
   gated ones stay `pending_terms_review`/`pending_access` and can never be acquired.
5. **Split policy**: deterministic pseudorandom patient-level 80 % development
   (calibration + internal test) / 20 % **sealed holdout**, independent of labels for the
   pilot (user request). Whole-patient rounding applies. The sealed IDs are written to
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
9. **UI MVP defaults:** English/light, persistent EN/DE and light/dark switches, accessible
   tooltips, About attribution and dependency-license inventory; no CDN or telemetry.
10. **LAN runner proposal:** document today, implement/test tomorrow; preserve the current
    loopback guard until an explicit private-host allowlist design is implemented.

## Work packages

Status: ✅ done · 🔄 in progress · ⏳ open · ✖ dropped

| # | Package | Vision § | Owner |
|---|---|---|---|
| ✅ WP0 | Repo bootstrap: LICENSE, README, AGENTS.md, pyproject, `localPipeline.sh`, CI, version script | 7, 30, 31-M0 | lead |
| ✅ WP1 | Model research and Ollama pulls (MedGemma Q4/Q8, controls), feasibility of 3D models | 4, 22 | research agent |
| 🔄 WP2 | Dataset research ✅, license registry ✅ (16 sources), pilot ✅ (LIDC 60 pts + NSCLC-Radiogenomics 27 pts, 6.7 GB), `thoraxbench acquire` port ⏳ | 5, 6, 8, 27 | data agent |
| ✅ WPA | Architecture (C4 + flowcharts) in `docs/architecture.md` — before deeper work | 7, 17 | lead |
| 🔄 WP3 | Core: config/registry ✅, policy gate ✅, DICOM discovery/geometry/HU/QC ✅, synthetic phantoms ✅, CLI analysis MVP ✅ | 6, 8, 9 | lead / agents |
| ✅ WP4 | Sampling S1–S6, windows, rendering views | 10 | agent |
| ✅ WP5 | Schemas, ontology, prompts P0–P4, adapters (Ollama, HTTP 3D service, mock) | 11, 12, 17, 19 | agent |
| 🔄 WP6 | Splits and sealing ✅ (CaseGuard, freeze), pilot holdout frozen ✅, development-only indexing ✅, leakage tracking ⏳ | 14, 15, 16 | lead |
| ✅ WP7 | Scoring (A–G), calibration, bootstrap CIs, perf measurements, provenance | 13, 20, 21, 24 | agent |
| ⏳ WP8 | Benchmark runner, experiments E001–E008 configs, compare, reports | 18, 25, 26 | agent |
| ✅ WP9 | Local UI MVP: guided workbench, EN/DE + light/dark + tooltips + About, offline illustrated exports and Playwright e2e; advanced review/benchmark screens deferred | 18 | lead |
| ✖ WP10 | ~~Docker, compose, GHCR workflow~~ — dropped at the user's request | 17 | — |
| ⏳ WP11 | Real runs on the pilot data (dev split only), benchmark report | 26, 32 | lead |
| 🔄 WP13 | Radiologist-style reading research → preprocessing (windows, MIP, coronal, HU cues) and the per-study English Markdown research report ✅ (term, plain language, educational severity/treatment context, prevalence, guideline context) | user request | research agent + lead |
| ⏳ WP12 | `/reviewBranch`, fixes, `/githubAbout`, final Vision checklist | all | lead |

## Current activity

Updated with every commit (newest first). **If a session breaks, the next agent resumes
from here**: read this section and *Next steps*, then `git log --oneline | head -20`.

- ✅ **Local GUI MVP and illustrated exports:** guided study/viewer/model/results flow,
  English/light defaults, persistent EN/DE and light/dark, accessible translated help,
  About attribution and installed dependency licenses. CLI and GUI share development
  guards; failures and abstentions remain visible. Two design proposals are in `docs/ui.md`.
  Synthetic CLI reproduction saved JSON, Markdown and offline illustrated HTML under
  `data/results/ui-completion/` (0.388 s recorded analysis stages; no accuracy claim).
- ✅ **Export review:** actual prepared vision inputs are embedded; heuristic source-slice
  illustrations are explicitly labeled. Invalid/missing evidence remains unresolved;
  all model text is escaped. Results-path checks reject symlink escapes before inference
  and on download. P4 uses one-based model image numbering, version 1.0.1.
- ✅ **Operator manual (user follow-up):** root `manual.html` and matching `manual.pdf`,
  with configuration, startup, synthetic walkthrough, output interpretation and recovery.
  Uses short, direct maintenance-manual-style instructions. Document actual commands only;
  acquisition and automatic data-budget CLI are still pending.
- ✅ **HTML review polish (user follow-up):** prominent per-finding educational severity
  and review context, responsive review layout, and explicit self-made-tool/no-professional-
  advice disclosure: available knowledge may be wrong, incomplete or misleading. Missing
  confidence stays uncertain in UI, HTML and Markdown; no fabricated certainty.
- ✅ **UI MVP release verification:** 272 non-live tests, 98.98% coverage; formatting,
  lint and strict typing pass. Browser acceptance covers both languages/themes, keyboard
  help, offline downloads and explicit model failure/abstention states. The commit script
  repeats the full build/wheel/audit gate. Manuals contain no patient images.
- ⏳ **Current activity / next session:** UI MVP, illustrated review and operator manuals
  are complete. Resume with the separately scheduled LAN runner tomorrow, then calibration
  and benchmark work below. Preserve loopback and sealed guards until that work is authorized.
- ✅ **CLI MVP landed:** v0.0.29 (`fb7d7b7`) pushed; full gate **225 tests, 98.94% coverage**,
  build, clean wheel and audit passed. Editable installation matches the source version.
- ✅ **Requested demonstrator:** `demo-data data/demo/user-test` then `analyze` using
  `heuristic-hu`: adequate QC, no abstention, right 12 mm nodule (uncalibrated score 0.79),
  right fluid region (score 1.00), **0.465 s analysis stages** excluding DICOM loading,
  provenance/report/export. Actual synthetic artifacts remain in `data/results/user-test/`;
  public record in `docs/mvp-test.md`, schematic in `docs/assets/mvp-walkthrough.svg`.
- ⏳ **Tomorrow:** `docs/lan-runner.md` proposes models for 40 GB VRAM and trusted LAN
  Ollama connection. No remote calls, downloads or policy changes are authorized today.
- ✅ **Environment checked:** Python 3.14.8, locked dependencies installed; Ollama reachable
  with MedGemma Q4/Q8 and qwen3-vl:4b; NVIDIA A2000 has 8 GB VRAM. Root filesystem now has
  ~13 GB available: old disk-full blocker resolved. All 12,724 dataset checksums pass;
  checksum manifests and license snapshots match Git. Playwright Chromium is installed.
  Refreshed editable package metadata (previously stale at 0.0.9).
- ✅ **Random patient holdout frozen (user request):** metadata-only pseudorandom split,
  independent of labels. LIDC: 48 development (38 calibration + 10 internal test), 12 holdout;
  NSCLC: 22 development (18 calibration + 4 internal test), 5 holdout (nearest whole patient
  to 20%). Split refuses replacement. Only salted patient hashes are committed; holdout IDs
  remain ignored in `data/sealed/`. No holdout file was read during verification.
- ✅ **Development smoke:** indexed one authorized real LIDC development study and ran the
  HU heuristic baseline successfully (adequate QC, 0.11 s inference/parse with cached cues).
  Local artifacts: `data/results/mvp-real-development/{result.json,report.md}`.
  Full non-live gate passed 225 tests at 98.94% coverage. No measured benchmark accuracy
  is claimed.
- ✅ **Live Ollama transport smoke:** synthetic single-label input, 256 px, one sampled
  slice plus a MIP view: completed in 49.5 s (46.2 s Ollama total), recorded actual model
  digest. The model returned empty findings; engine now treats empty label predictions as
  abstention. Full-label run exceeded 4000 generated tokens and was stopped; a 4096-token
  default bounds subsequent runs, preserving truncated output as an abstention. This proves
  installed weights/inference work, not useful CT detection or accuracy.
  Smoke artifacts: `data/results/mvp-medgemma-bounded/` (local only).
- ✅ **Test data available (outside Git, `data/raw/`):** LIDC-IDRI 60 patients (40 with nodules
  ≥3 mm, 20 without) + NSCLC-Radiogenomics 27 patients with tumour SEG; synthetic DICOM phantoms
  for tests/demos (`thoraxbench.synthetic`).
- ✅ LIDC reader-XML parser → consensus lesions + study labels (`labels/lidc.py`).
- ✅ WP4 sampling S1–S6 + MIP slabs, views (MedGemma RGB per official notebook, lung, multi-window,
  contact sheet, CT-CLIP/M3D tensors), `Study` with HU volume cache; heuristic baseline wired to
  real HU cues. Smoke-tested on a real LIDC study (load 5 s, cues 10 s, view 1.5 s).
- ✅ WP1 model research: MedGemma 1.5 Q4/Q8 pulled, ~270 tokens and ~3 s prefill per image on
  the A2000; gemma3:4b pulled as same-architecture control (`docs/model_cards.md`).
- ✅ WP5 prompts P0–P4, parsing, adapters (Ollama, HTTP 3D service, heuristic) landed.
- ✅ UI ideation + concept: `docs/ui.md` (decision: CLI is the engine; local-only web UI
  with FastAPI + Jinja2 + local vanilla JavaScript for review; Playwright e2e + README screenshot).
- ✅ Data pilot downloaded (outside Git): LIDC-IDRI 60 patients 4.3 GB, NSCLC-Radiogenomics
  27 patients 2.4 GB (both CC BY 3.0), checksummed; registry (`configs/datasets/`) + `docs/datasets.md` + `manifests/datasets/` committed.
- ✅ WP7 scoring (tasks A–G, bootstrap), calibration (sealed-safe), perf, provenance landed.
- ✅ WP13 research: `docs/reading_practice.md`, clinical knowledge base + Fleischner/Lung-RADS
  rules (`ontology/clinical.py`, `ontology/guidelines.py`); research report rendering complete.
- ✅ WP6 splits + sealed guard (`splits/`).
- ✅ Schemas + ontology (v0.0.7), DICOM loader + phantoms (v0.0.6), registry (v0.0.5),
  architecture (v0.0.3), bootstrap (v0.0.1).

## Next steps (in order)

1. Tomorrow: implement/test the optional trusted LAN endpoint mode with an explicit allowlist;
   inventory the 40 GB runner, verify candidate models and actual VRAM under bounded context.
2. Improve bounded MedGemma predictions on calibration cases; use internal development test
   for evaluation only, preserve the sealed holdout. Document useful output and failures.
3. Expand guarded development indexes; port acquisition into `thoraxbench acquire` with
   license/budget/checksum gates. Add split/leakage audits as benchmarking expands.
4. Benchmark runner + frozen experiment configs E001–E004 (+ E008 external), compare/reports.
5. Real development experiments and measured results in `docs/results.md`.
6. Advanced UI: overlays, coronal/MIP, run comparison after benchmark output exists.
7. Review, GitHub About/topics and Vision traceability check (WP12).

## Self-review gates

* After every work package: full `./localPipeline.sh` green, then commit and push.
* After WP8 and at the end: walk through `docs/vision_traceability.md` (one row for every
  Vision section) and close any gaps.
