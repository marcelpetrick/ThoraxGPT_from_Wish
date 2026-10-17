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
| Data budget | 10 GB in `./data/` (git-ignored; enforced for `acquire`, not analysis/benchmark writes) |
| Hugging Face token | none — gated sources (CT-RATE, CT-CLIP weights) are registered as `pending_access` |

## Priority (user decision, 2026-10-15)

**Current priority (user decision, 2026-10-17):** the approach review
([`approach-review-2026-10-17.md`](approach-review-2026-10-17.md)) found the benchmark sound
but the zero-shot study-level small-VLM hypothesis very likely wrong. The user approved the
review's plan ("finish that plan, get it done") and asked for a finally usable workflow.
New order: (1) image-path sanity gate, (2) official MedGemma protocol, (3) supervised
detector reference baseline (overlap-flagged), (4) VLM crop verification of detector
candidates at lesion level, (5) usable end-to-end detect → verify → review workflow in the
UI and CLI, (6) honest RQ1 report. Study-level E002–E004 sweeps and QLoRA are on hold until
the gate passes. See *Next steps*.

**Earlier priority (user update, 2026-10-16):** complete engine reliability and the newly
requested UI/UX usability improvements. The user explicitly authorized a full UX review,
recommendations, plan, implementation, fresh screenshots and end-to-end verification.
This permits targeted study-library, navigation, feedback, help and results improvements;
advanced reference overlays and LAN inference remain deferred. The WP8 development runner, E000 baseline and bounded
Q4/Q8 calibration readiness smoke are complete. Per-case diagnostic evidence and
interruption-safe checkpoints are implemented. Resolve useful-output reliability on calibration data
before full E001–E004 experiments. Keep internal-test cases out of tuning.

The 2026-10-15 project review moved work from the UI back to WP8 → WP11. At that time the
scoring/calibration libraries were not wired into a pipeline; the runner now applies scoring
and the calibration library still has no fitted real-model workflow. See
`docs/review-2026-10-15.md` and the current ranked gaps in `docs/vision_traceability.md`.

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
   HuatuoGPT-Vision sit behind an HTTP service adapter contract, with an optional local service
   contract. They need weights or GPU memory we lack today, so they show up as
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
| 🔄 WP2 | Dataset research ✅, license registry ✅ (16 sources), pilot ✅ (LIDC 60 pts + NSCLC-Radiogenomics 27 pts, 6.7 GB), `thoraxbench acquire` ✅ (license/budget/split/checksum gates, mocked HTTP; first live NBIA run ⏳ operator) | 5, 6, 8, 27 | data agent |
| ✅ WPA | Architecture (C4 + flowcharts) in `docs/architecture.md` — before deeper work | 7, 17 | lead |
| 🔄 WP3 | Core: config/registry ✅, policy gate ✅, DICOM discovery/geometry/HU/QC ✅, synthetic phantoms ✅, CLI analysis MVP ✅, privacy header audit + output path redaction ✅ | 6, 8, 9, 29 | lead / agents |
| ✅ WP4 | Sampling S1–S6, windows, rendering views | 10 | agent |
| ✅ WP5 | Schemas, ontology, prompts P0–P4, adapters (Ollama, HTTP 3D service, mock) | 11, 12, 17, 19 | agent |
| 🔄 WP6 | Splits and sealing ✅ (CaseGuard, freeze), pilot holdout frozen ✅, development-only indexing ✅, leakage tracking ⏳ (audit: the pre-rebuild NSCLC index held 5 non-development entries)  | 14, 15, 16 | lead |
| ✅ WP7 | Scoring (A–G), calibration, bootstrap CIs, perf measurements, provenance | 13, 20, 21, 24 | agent |
| 🔄 WP8 | Benchmark runner ✅; configured-label requests and preserved run folders ✅; E000–E004 + separate calibration smoke configs ✅; E005–E008, compare ⏳ | 18, 25, 26 | agent |
| 🔄 WP9 | Local UI MVP ✅; live elapsed runtime + sequential model comparison ✅ (v0.2.0 released); approved synthetic screenshots ✅; advanced screens deferred | 18 | lead |
| ✖ WP10 | ~~Docker, compose, GHCR workflow~~ — dropped at the user's request | 17 | — |
| 🔄 WP11 | E000 heuristic baseline on 70 development cases ✅ (`docs/results.md`); Q4/Q8 calibration readiness smoke ✅ (poor usable-output rate); full E001–E004 ⏳ | 26, 32 | lead |
| 🔄 WP13 | Radiologist-style reading research → preprocessing (windows, MIP, coronal, HU cues) and the per-study English Markdown research report ✅ (term, plain language, educational severity/treatment context, prevalence, guideline context) | user request | research agent + lead |
| 🔄 WP12 | GitHub About + ten topics applied ✅; project review + course correction ✅; `docs/vision_traceability.md` ✅; closing ranked gaps ⏳ | all | lead |

## Current activity

- **W6 detector review (2026-10-17):** added manual detector setup/availability, optional
  dependency license inventory, sourced candidate table and source-slice navigation with
  English/German help. UI and offline HTML show bounded post-inference axial/coronal
  illustrations (first 12 candidates; every candidate remains in JSON/Markdown/table).
  No new inference thread or verifier is enabled. Invalid detector boxes/scores fail
  explicitly; nonfinite crop centres are refused. Synthetic UI/export tests exercise
  the path through the merged W3 job queue, including running-detector cancellation at a
  safe stage boundary. Optional VLM verification
  remains gated on image-path sanity and the official protocol.

- **W2 reference detector implementation (2026-10-17):** optional checksum-pinned MONAI
  LUNA16 RetinaNet inference adapter, explicit terms/weight helper, millimetre candidates,
  overlap-labelled per-dataset Task A/C reports and in-memory axial/coronal crop component.
  See [setup and limits](detector-baseline.md). Five existing local bundle files verify.
  A reduced synthetic CPU network/API smoke passed; default-ROI GPU/calibration performance
  is not yet measured in this handover. Synthetic adapter/geometry/scoring tests cover the
  pipeline without downloading weights. Detect → VLM verify → review remains an integration
  task. Do not claim unbiased LIDC accuracy or numerically identical upstream preprocessing.

- 🔄 **W3 committed/pushed `da473be` (2026-10-17):** analysis, comparisons and
  explicit Ollama pulls share a bounded server FIFO. Running jobs survive browser navigation
  and reload, expose stage/server elapsed and support cooperative stop with socket closure.
  Queued work cancels before provider access. Synthetic real-queue browser tests cover
  EN/light and DE/dark mobile flows; all 9 job API tests pass. Updated docs, 11 screenshots
  and the HTML/PDF operator manual. Model downloads now use the same cancellation controls.
  Self-review removed browser elapsed extrapolation after the first full gate exposed a
  timing race: displays now show measured server snapshots only, including after reconnect.

- **Historical initial Codex resumption checkpoint (2026-10-17; superseded above):** `main` at `ef2c73a` matches origin. Preserve
  the unfinished W3 job queue in the main checkout. W1 already has two unmerged commits
  (`62b32bd`, `8ce734d`), so audit existing calibration evidence before any new GPU run.
  W2 detector changes remain uncommitted in its own worktree. Two agents finish W1/W2;
  the lead owns W3, reviews integrations and runs the full gate before pushing. No agent
  from the preceding session is still active. Keep the older stash and all real data.

- 🔄 **Work plan (2026-10-17, user-approved; budget rule: finish running agents before
  starting new ones, keep parallel agents minimal):**

  | # | Work item | Where | State | Merge / done criterion |
  |---|---|---|---|---|
  | W1 | Image-path sanity gate (T0 layout audit, T2 position binding, S1 blank/noise/shuffle, S2 synthetic spheres, S3 description, S4 paired lesion/control slabs, optional bf16 parity) | agent, own worktree | 🔄 running | Results in `results.md`; gate verdict recorded; full gate green; merged by the lead |
  | W2 | Detector reference baseline (MONAI RetinaNet, inference only, overlap-flagged), lesion-level Task C, crop-export view | agent, own worktree | 🔄 running | Explicit weight download, tests with stub network, calibration results, merged |
  | W3 | Job layer: server-side sequential queue, cancel/stop, persistent status bar on all pages and in the tab title, Jobs panel, fixed elapsed display | lead, main checkout | ✅ `da473be`, 680 tests / 98.28% | Playwright: navigate/reload keeps the running job visible; cancel works; docs/manual/screenshots refreshed |
  | W4 | Official-protocol prompt P6 (interleaved `SLICE k`, one label per query, P(yes)), non-constant-output readiness check | lead or one agent after W1 | ⏳ | Starts only after W1 is merged; mode chosen from the T2 binding result |
  | W5 | VLM crop verification of detector candidates | after W2 + W4 | ⏳ | Only if W1 shows crop/slab-level signal |
  | W6 | Usable workflow: study → detector → candidates in viewer → optional VLM check → sourced findings → report, all through the W3 job layer; Evaluation shows these runs | detector review worker, after W2 + W3 | 🔄 detector review implemented; VLM verification gated | Synthetic e2e in EN/DE, light/dark, mobile; source navigation and offline HTML; manual synchronized |
  | W7 | RQ1 report with overlap column; status/plan/AGENTS sync; self-review; worktree and stash cleanup proposal | lead | ⏳ | Final full gate, pushed |

- 🔄 **Program status and approach check (2026-10-17):** full-program state, real-data
  verdict and the decision plan are in [the status report](status-2026-10-17.md). Running:
  image-path sanity tests, a paired lesion/control slab test (calibration only) and a web
  review of whether the small-VLM approach is viable. Direction is decided after these.
- 🔄 **Completion plan (user request, 2026-10-16 evening):** the user asked for a full
  resume, UX completion, refreshed screenshots, end-to-end tests, a real-data recognition
  check, a fine-tuning strategy and a rethink of the UI for the evaluation workflow, and
  delegated the decisions to the agent. Order:
  1. ✅ Commit the parallel work in logical gated commits (split guards, inadequate-study
     abstention, model manifests, cohort exports/compare, UX implementation).
  2. ✅ Verified the eight UX findings against their acceptance checks (2026-10-16, v0.3.23,
     commit `63bba61`; gate: 619 tests, 99 % coverage). Evidence
     per finding is in the UX review (Markdown and HTML). New browser checks:
     `tests/e2e/test_web_ui_acceptance.py` (10 tests) beside `tests/e2e/test_web_ui.py` (20).
     Gaps fixed: refresh/search reset the slice and could keep a removed study's stale
     position; the empty library suggested only the demo; unavailable models were not
     selectable, so selection could not lead to their setup row; Escape-dismissed help
     reopened on pointer jitter; leaving the tooltip skipped the hover grace. Added a
     translated running-request notice on other pages. Tooltip: 650 ms show delay, 180 ms
     hover grace, per-trigger stable descriptions — kept (typical 500–800 ms range).
  3. ✅/🔄 **Real-data recognition check (2026-10-17, v0.3.21–0.3.24 worktree, merged):**
     `thoraxbench coverage` shows the earlier diagnostics put 0–26 % of calibration LIDC
     nodules on attached images; the chosen lung_extent / 24 images / 5 mm slabs covers
     96.1 % within context. Strict prompt P5 (fixed-length findings, bounded text, fixed
     confidence steps, `IMAGE k` captions, no heuristic context, 896 px) removed truncation,
     invalid image numbers, omissions and copied cue text: Q8 20/20 and Q4 18/20 usable on 10
     LIDC calibration cases. **But the model still does not recognize the findings:** Q8 was
     constant (both labels present at 0.95, images 1–4); Q4 nodule AUROC 0.64 (n=9); cited
     images missed the nodules (Q8 1/28, Q4 0/8). Recognition, not formatting, is now the
     blocker. Next: non-constant-output readiness check; one question per label and
     per-image captions; reviewed no-think `qwen3-vl:4b` control config (it currently
     thinks and exhausts the budget); E002–E004 stay blocked until a calibration-only check
     shows two-class discrimination. See `docs/results.md`.
  4. ✅ Fine-tuning/adaptation strategy recorded in `docs/fine-tuning-plan.md` (research
     only; no training before recognition passes; calibration split only). Its cheapest
     items (coverage, strict schema, captions, no cues, 896 px) are implemented in step 3.
  5. ✅ **Evaluation section (decided 2026-10-16, user delegated; implemented v0.4.0, gate: 641 tests, 99 % coverage):**
     read-only `/evaluation` page and `GET /api/evaluation/*` (`api/evaluation.py`) over
     `data/results/benchmark/<experiment>/<run>/`. Runs list (experiment, config hash, start
     time, state with reason, variants, status counts); descriptive comparison through
     `benchmark/compare.py`; per-case table (dataset, case, phase, variant, status, reference,
     prediction, warnings, evidence verdict) filterable by status, evidence and variant; case
     detail with parsed and plain-text raw response, per-finding evidence check and image
     information. Every open passes `load_completed_run` (integrity + current split guard);
     non-development rows are skipped and counted; symlinked/unsafe folders are ignored.
     **Limitation:** benchmark artifacts store no prepared image pixels, so the case detail
     shows the recorded sent-image count and captions and says so (no re-render). Storing
     prepared images is an engine change for a later decision. Evidence: 17 integration
     tests (`tests/integration/test_evaluation_api.py`) and 5 browser tests
     (`tests/e2e/test_evaluation_ui.py`) over `thoraxbench.synthetic_runs` (real runner over
     phantoms; scripted, labelled vision outputs). "Analyze one study" remains the first mode.
  Housekeeping: an older `commit.sh` stash (16:16, base `9453bbe`) is kept, not dropped;
     its content appears superseded by later commits — the user decides.
  6. ✅ Refreshed (2026-10-17): all 11 synthetic captures in `docs/assets/` via
     `scripts/capture_screenshots.py` (7 workbench shots plus 4 new Evaluation shots from a
     second temporary `thoraxbench.synthetic_runs` tree; selectors fixed for grouped study
     options and translated finding names). README, `docs/ui.md` and `scripts/README.md`
     list them. `manual.html` gained an Evaluation sheet (10 / STORED RUN REVIEW), the
     "Analyze one study" label, the model-setup route and tooltip behaviour; `manual.pdf`
     was re-printed with headless Chromium (13 A4 pages, one per sheet, checked by sheet
     height). Full e2e suite (demo → viewer → analysis → result/download, About and back,
     Evaluation, EN/DE, light/dark, 390 px): 35 browser tests green, then the full gate.
     Self-review found and fixed one Evaluation bug: a finding without kept references
     showed "In range: yes"; it now shows "n/a" (regression assertion added).
- 🔄 **User-authorized UX completion (2026-10-16):** eight confirmed should-fix findings
  and acceptance checks are recorded in [the UX review](ux-review-2026-10-16.md) and
  [offline HTML review](ux-review-2026-10-16.html). Prioritize library discovery/search,
  mobile study → viewer → model order, educational result context, nearby model setup,
  session-preserving About navigation, delayed accessible tooltips, result settings
  identity and translated finding names. Add library-source health/count metadata and
  shared report-derived educational display codes. Refresh synthetic screenshots and
  README snippets after implementation. Run synthetic browser flows in both languages,
  both themes and mobile, plus the full gate and self-review. The eight findings are
  verified (completion plan item 2); the screenshot and manual refresh is item 6.
- ✅ **Local preview for the user:** stable v0.3.15 runs on loopback port 8000 from
  `.pipeline/calibration-clean`, with the repository's original `data/` library. The
  inventory contains 48 LIDC-IDRI and 22 NSCLC development studies plus the demo. The
  initial isolated demo-only data directory was corrected. Live synthetic demo → viewer
  → HU analysis → downloadable HTML was verified. Keep this preview running until replaced
  deliberately after a green gate. Do not take screenshots of its real development studies.
- 🔄 **Parallel completion:** cohort HTML/CSV exports and comparison have 39 focused tests;
  all 15 model manifests have 31 offline validation tests. Shared split/freeze path guards
  now reject unsafe identifiers and symlink escapes before file reads (25 targeted tests).
  The evidence/context fix passed the full gate and is pushed as v0.3.16 (`5c16ba1`).
  Its bounded cue-ablation run is in progress from a separate clean checkout; model outcomes
  remain inspectable. Tooltip delay is 650 ms and passed its focused browser regression.

- 🔄 **Resumed completion work (2026-10-16):** clean starting point `c509525`, v0.3.15.
  The corrected uniform two-image diagnostic completed from an isolated clean checkout:
  two scorable responses in 49.6 s, but both still copied heuristic candidates and used
  invalid source-slice references. Add bounded image schemas and explicit unavailable
  predictions for unsupported constrained positives; preserve raw responses. Add a hashed
  heuristic-context ablation with unchanged images. Parallel work closes cohort HTML/CSV,
  read-only run comparison, model manifests, and the UI target-versus-actual count fix.
  Full E001–E004, sealed access, gated weights and LAN remain outside this work. Recording
  still waits for a specific trigger and readiness. Commit each verified logical change.

- ⏳ **LinkedIn recording waits for the user's trigger:** two scripts are ready in
  [the recording plan](linkedin-video-plan.md): a 60-second square introduction and a
  90-second 4:5 walkthrough. Both introduce Marcel, explain practical research value and
  show the project URL and limitations. Planned exports: 1080×1080 / 1080×1350 MP4,
  H.264/AAC, 30 fps, subtitles, thumbnail and preserved uncut original. Synthetic data
  only. Rehearse genuine inference and verify the actual image count before capture.
  Recording automation and recording remain pending; nothing was recorded or published.
- ✅ **Current verification:** v0.3.14's full local gate passed: **470 tests, 98.46% coverage**.
  Main engine integration `ec929c4` also passed GitHub Actions. Corrected uniform two-image
  configuration has not run live. Full E001–E004 remain deferred pending output reliability.

- ✅ **Bounded calibration diagnostic (2026-10-16):** clean `ec929c4`, Q4/P2, one
  calibration case per dataset: two scored responses, zero abstentions/failures, 99.0 s
  active wall time. Both repeated heuristic candidate text and used out-of-range image
  references. Requested-label coverage was 2/3 known references. The anatomy strategy
  actually prepared nine images per case despite `n: 2`; that parameter is a fill target,
  not a landmark cap. Corrected the next diagnostic configuration to `uniform`, `n: 2`.
  The corrected configuration has not run live. Preserve the original run and hash;
  do not call this detection accuracy or full-sweep readiness. See `docs/results.md`.

- ✅ **Engine durability and documentation integration (2026-10-16):** scoring/caption
  corrections and redacted provider diagnostics are committed and pushed. Added immutable
  terminal case artifacts, atomic checkpoints and explicit identity-validated resume.
  Total runtime includes active input hashing/loading and excludes resume downtime.
  Documentation audit and synchronized manuals include the normal `ollama run` auto-pull
  path and optional browser download. Full local gate passed: **470 tests, 98.46% coverage**, including 11 browser tests,
  build, clean-wheel installation and dependency audit. Commit `ec929c4` is pushed.

Updated with every commit (newest first). **If a session breaks, the next agent resumes
from here**: read this section and *Next steps*, then `git log --oneline | head -20`.

- ✅ **Scoring/caption corrections (2026-10-16, resumed work):** unavailable presence or
  confidence is no longer imputed as a definite prediction. Task E reports prediction
  coverage/omissions; Task G exposes its eligible false-reassurance denominator. Captions
  use one-based numbering; affected prompt versions are bumped. Historical measurements
  retain their original definitions. Durable benchmark artifacts/checkpoints were the next task; they are now implemented.
- 🔄 **Resumed engine work (2026-10-16):** implement durable per-case analysis artifacts,
  complete redacted provider requests/responses and atomic benchmark checkpoints with
  explicit, identity-validated resume. Preserve completed, failed, abstained and missing-index
  units; never overwrite another invocation or retry terminal units silently. Add input,
  scoring/reference and available manifest hashes. Collect direct identifying header values
  in memory for output redaction. Correct missing-confidence scoring and caption numbering;
  version affected prompt artifacts and preserve historical aggregate measurements.
  Synthetic/mocked verification comes first. Do not launch full E001–E004 sweeps, download
  weights, change UI features, enable LAN inference or read sealed studies.
  Documentation and both manuals are being synchronized with the final command contract.
- ⏸ **User-requested restart handover (2026-10-16, 10:11 CEST):** pause after this
  plan commit and push (historical request; resumed by the user below). Completed work is published through v0.3.9 (`9453bbe`);
  its full local gate and GitHub Actions passed: **386 tests, 99.18% coverage**.
  The working tree was clean before this handover update. No experiment is running.
  The user has now explicitly resumed this work. Start with durable per-case raw-response/provenance artifacts
  and incremental benchmark checkpoints, then investigate structured-output reliability
  on calibration cases only. Keep UI feature work frozen, LAN work deferred and the
  sealed holdout untouched. Use `TMPDIR=/var/tmp/thoraxbench-pipeline-mpetrick` for
  checks while shared `/tmp` is full. No model download or full E001–E004 sweep is queued.
- ✅ **MedGemma readiness smoke (2026-10-16):** clean v0.3.8 commit `3af797f`, separate
  `E001_calibration_smoke.yaml`, calibration-only 1 case per dataset, 4×256 px axial
  inputs, 2 labels, Q4/Q8. Wall time **290.8 s**. Q4: 0 scored / 2 empty-output abstentions.
  Q8: 1 scored (reference nodule missed) / 1 generation-limit abstention. No accuracy or
  quantization winner is established. Raw score artifacts stay under ignored
  `data/results/benchmark/E001-smoke/`; aggregate evidence is in `docs/results.md`.
  Do not expand to full E001–E004 until useful-output reliability is addressed.
- ✅ **Benchmark fixes pushed:** v0.3.8 (`3af797f`), configured label/prompt requests,
  unique preserved result directories and output preflight before inference. Both manuals
  are synchronized. Full gate **386 tests, 99.18% coverage** including 11 browser tests;
  build, wheel, dependency audit and GitHub Actions passed.
- ✅ **Outcome published:** v0.3.9 (`9453bbe`) records the measured outcome and priorities.
  Next engine
  task: preserve complete per-case raw responses/provenance and incremental checkpoints,
  then diagnose empty/truncated responses on calibration cases. Current benchmark output
  stores scores/warnings/fingerprints, not full raw responses; interruption has no checkpoint.
- ✅ **Screenshots and handover:** v0.3.7 pushed; full gate **379 tests, 99.17% coverage**,
  including all 11 Playwright tests, build, clean wheel and dependency audit.
- ✅ **Initial state at resumption (2026-10-16):** `main` v0.3.6 (`03754d1`) matches
  GitHub. Public v0.2.0 exists with both manuals. Preserve and review the pending synthetic
  screenshots reviewed; DATA_POLICY now records the approved synthetic exception. All seven
  views are generated without real patient data; mocked states and timings are disclosed.
  The full gate failed because shared `/tmp` is full (16 GB tmpfs). Retry with
  `TMPDIR=/var/tmp/thoraxbench-pipeline-mpetrick ./localPipeline.sh`; do not delete unrelated temp files.
  Browser acceptance works here. Benchmark fixes follow before inference: pass the configured label
  list to analysis, and preserve each invocation in its own output folder. Both are next.
- ⏳ **Next bounded experiment:** separately named calibration-only Q4/Q8 smoke, small
  image budget, one case per dataset. No BF16 pull and no holdout access. Full E001–E004
  sweeps follow only after usable output and memory/context limits are demonstrated.

- ✅ **Historical sandbox handover (2026-10-15; pushed and released since then):**
  `thoraxbench benchmark` runner with E000–E004 configs; E000 heuristic baseline on 70
  development cases (macro AUROC 0.51 — a constant-output control, not accuracy; see
  `docs/results.md`). `thoraxbench acquire` with license, budget, split and checksum gates;
  `--verify` hashes development patients only. `thoraxbench privacy audit` and output path
  redaction. New SECURITY.md, DATA_POLICY.md, docs/reproducibility.md,
  docs/vision_traceability.md, screenshot script. Sandboxed checks (2026-10-15): headers,
  datagate, format, lint, strict types, build, wheel and audit pass; 368 tests pass with
  99.17 % coverage excluding the 11 Playwright tests. The sandbox blocks Chromium, Ollama,
  push and `gh`. At the user's request the queued changes were committed locally with plain
  `git commit` (version bumps as `commit.sh` would do) because `commit.sh` could not pass the
  Playwright stage in that sandbox. GitHub now contains these commits and public v0.2.0
  with both manuals. Current verification is recorded above; do not repeat publication.

- ✅ **UI extension v0.2.0 — released (historical sandbox gate, 2026-10-15):**
  sync/headers/datagate/format/lint/types pass, 287 tests pass, coverage 98.90 %; the 11
  Playwright tests could not start Chromium inside the agent sandbox (Unix sockets blocked)
  and awaited an unrestricted full gate then. Commit `083971a` is now public as v0.2.0
  with both manuals. Delivered: show browser
  elapsed waiting time during inference, distinct from recorded engine stages. Add an opt-in
  switch to run available recommended local models sequentially, preserving per-model
  errors/abstentions, skipped availability and partial successes. Present findings side by
  side without claiming accuracy; provide an offline combined HTML review. Synthetic/mocked
  browser tests only; update both operator manuals and Markdown docs before full gate.
  Add rough planning ranges and browser-local measured runtime history; estimates are not
  deadlines or model progress. Every UI control, field, status and metric gets translated
  hover/focus help. Add explicit configured-Ollama download actions with terms acknowledgment
  and actual progress; explain gated/separate-service prerequisites without bypassing access.
  Apply short, direct flight-manual-style instructions across Markdown and HTML/PDF docs.
  Review architecture/code/docs, fix confirmed issues, then full gate/commit/push and publish
  a public GitHub source release with manuals. LAN inference remains deferred.
- ✅ **Repository presentation:** applied research-focused GitHub About and ten discovery
  topics using `githubAbout`; expanded README badges after inspecting myLastFmPlayer and
  Cullendula. Badge claims link to measured coverage, strict types, pinned FastAPI, local
  inference, research scope and HTML/PDF manuals. GitHub CI passed for v0.1.0. GitHub Release
  automation and package publication are not implemented. The user now requests a manual
  public source release after the current extension passes all checks.
- ✅ **Dependency maintenance:** registry audit verified exact pins for runtime/dev/build
  requirements and latest stable non-yanked releases. Update Hatchling 1.29.0 → 1.32.4
  and CI uv 0.12.18 → 0.13.1; runtime/dev pins and locked transitive versions are current.
  Full commit gate uses uv 0.13.1. Registry sources: [Hatchling](https://pypi.org/project/hatchling/1.32.4/)
  and [uv](https://pypi.org/project/uv/0.13.1/). No runtime/dev or transitive update was needed.
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
  acquisition is implemented; a standalone automatic data-budget CLI remains pending.
- ✅ **HTML review polish (user follow-up):** prominent per-finding educational severity
  and review context, responsive review layout, and explicit self-made-tool/no-professional-
  advice disclosure: available knowledge may be wrong, incomplete or misleading. Missing
  confidence stays uncertain in UI, HTML and Markdown; no fabricated certainty.
- ✅ **UI MVP release verification:** 272 non-live tests, 98.98% coverage; formatting,
  lint and strict typing pass. Browser acceptance covers both languages/themes, keyboard
  help, offline downloads and explicit model failure/abstention states. The commit script
  repeats the full build/wheel/audit gate. Manuals contain no patient images.
- ⏳ **After the current comparison extension:** resume with the separately scheduled LAN
  runner tomorrow, then calibration and benchmark work below. Preserve loopback and sealed
  guards until that work is authorized.
- ✅ **CLI MVP landed:** v0.0.29 (`fb7d7b7`) pushed; full gate **225 tests, 98.94% coverage**,
  build, clean wheel and audit passed. Editable installation matches the source version.
- ✅ **Requested demonstrator:** `demo-data data/demo/user-test` then `analyze` using
  `heuristic-hu`: adequate QC, no abstention, right 12 mm nodule (uncalibrated score 0.79),
  right fluid region (score 1.00), **0.465 s analysis stages** excluding DICOM loading,
  provenance/report/export. Actual synthetic artifacts remain in `data/results/user-test/`;
  public record in `docs/mvp-test.md`, schematic in `docs/assets/mvp-walkthrough.svg`.
- ⏳ **Tomorrow:** `docs/lan-runner.md` proposes models for 40 GB VRAM and trusted LAN
  Ollama connection. Runner calls, runner downloads and LAN policy changes remain deferred;
  the current UI may offer explicitly initiated local-Ollama weight downloads.
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

## Ideas and wishes (recorded 2026-10-16)

User wishes, in their words where possible, with status:

| Wish | Status / decision |
|---|---|
| "Does it recognize what it should?" on the given medical data | 🔄 Not yet: latest calibration run 4/4 abstentions; bounded diagnostics continue (calibration only) |
| "How could the models be fine-tuned for the best and most precise results?" | ⏳ Strategy document `docs/fine-tuning-plan.md`; training waits for output reliability |
| Is the UI/UX best adapted to the medical-model and evaluation workflow, or rethink it? | Decided: keep the single-study workbench, add a read-only Evaluation section (FiftyOne/MLflow-style run and per-case error browsing) |
| Tooltip bug solved, with a bit more delay | ✅ in implementation: 650 ms delay, hoverable, per-control descriptions; verification in step 2 |
| Refresh all screenshots and docs | ⏳ After all UI changes (step 6) |
| End-to-end testing | ⏳ Step 6 plus focused Playwright tests per finding |
| LinkedIn recording | ⏳ Waits for the user's explicit trigger |
| LAN / 40 GB VRAM runner | ⏳ Deferred until resumed explicitly |

Ideas not yet scheduled (need a separate decision):

* Reader-study mode (blinded case queue, radiologist annotations) in the style of
  grand-challenge.org reader studies — only with a qualified reviewer.
* Image overlays of model evidence on the viewer (advanced reference overlays stay deferred).
* Classical nodule CAD or a small supervised 3D detector trained on calibration LIDC
  annotations as a stronger baseline than the HU heuristic.
* Fitted calibration (Platt/isotonic) once enough scorable outputs exist.

## Next steps (in order)

Decision record 2026-10-17 (user-approved approach-review plan). All real-data runs use the
calibration phase only; each change is a separately hashed configuration.

1. 🔄 **Image-path sanity gate** (T0–T5 of the approach review, plus S1–S4): prompt layout
   audit, position binding (single message vs one message per image), real vs blank/noise/
   shuffled images, synthetic spheres 30/15/8 mm, free-text description, paired
   lesion/control 5 mm slabs with one yes/no question each (slice-level AUROC, yes-rate on
   controls). Optional HF bf16 parity if weights are available without new terms. Gate:
   if blank-vs-real or the 30 mm sphere fails in every format → model capability limit.
2. ⏳ **Official protocol prompt (P6):** interleaved image + `SLICE k`, one label per query,
   short reasoning then constrained yes/no, P(yes) scoring from logprobs on short answers.
   Add a non-constant-output readiness criterion. Only then rerun E001-schema-style checks.
3. 🔄 **Detector reference baseline:** MONAI `lung_nodule_ct_detection` (RetinaNet,
   Apache-2.0), inference only, weights in ignored `data/`. `possible_training_overlap: yes`
   on LIDC (LUNA16 ⊂ LIDC), out of distribution on NSCLC. Lesion-level Task C (sensitivity
   at 1/2/4/8 FP per scan) plus study-level max score.
4. ⏳ **VLM crop verification:** ≈64 mm lung-window crops (axial, optional coronal) around
   detector/heuristic candidates; "nodule vs vessel/none" per crop; score FP/scan at fixed
   sensitivity against the detector alone. Run only if step 1 shows crop-level signal.
5. ⏳ **Usable workflow (user request):** one guided path in UI and CLI — choose study →
   run detector → review candidate list with crops and positions in the viewer → optional
   VLM verification per candidate → findings with clear source (detector / VLM / heuristic),
   limitations and overlap flags → offline HTML/Markdown report download. Evaluation section
   shows detector and verification runs. Synthetic e2e tests, refreshed screenshots/manual.
6. ⏳ **RQ1 report:** honest result table (VLM study level, VLM slab/crop level, detector,
   heuristic) with overlap column; negative results stay visible.
7. ⏳ Close remaining ranked gaps: calibration fitting, overlap column in all reports,
   E005–E008 configurations. Preserve the historical NSCLC index uncertainty.
8. On hold: E002–E004 study-level sweeps and QLoRA (`fine-tuning-plan.md`) until steps 1–4
   show a visual signal. Deferred: LAN/40 GB runner. Recording waits for the user's trigger.

## Self-review gates

* After every work package: full `./localPipeline.sh` green, then commit and push.
* After WP8 and at the end: walk through `docs/vision_traceability.md` (one row for every
  Vision section) and close any gaps.
