# ThoraxBench Local — Implementation Plan

This plan turns [`Vision.md`](Vision.md) into a working product. Decisions recorded
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

### Full thorax review and plain-language outcome — 2026-10-20

User review of a real-study MedGemma report (v0.5.6): "useless, I can't find any value".
Confirmed causes: (1) 4 single 1 mm slices of 317 (`uniform`, two outside the lungs);
(2) the model answered positive for all 16 labels (yes-bias), each listed as a separate
abstention line instead of one clear verdict; (3) detector/HU baseline were not part of
the run, so no usable signal existed; (4) the full disclaimer is repeated three times;
(5) privacy: the shareable report prints the real SeriesInstanceUID.

**Goal:** one "Full thorax review" run that covers every lung/thorax slab, checks all
labels, shows progress, and ends with a plain-language outcome: what was found (where,
how well supported), what was not flagged, what could not be assessed, and what to show a
radiologist. One short disclaimer line in app/report; the full text lives once in the repo.

Phase A — report clarity (lead, inline; separate commit):
- [x] A1 Remove SeriesInstanceUID/patient identifiers from human-facing reports (keep hashes).
- [x] A2 Outcome box first: verdict + coverage ("checked 4 of 317 slices, 1 %") + next step.
- [x] A3 Detect all-positive/constant output: one line "unusable: answered yes to all N
  labels (yes-bias)" instead of N repeated abstention lines.
- [x] A4 One-line disclaimer in UI/report; full text once in `docs/DISCLAIMER.md`.
- [x] A5 Groom outcomes: ranked "look here" findings first; low-score detector candidates
  collapsed ("7 low-score candidates hidden, score < 0.1"); educational context below.
- [x] A6 Report switchable EN/DE (HTML toggle; same data, translated labels and texts).
- [x] A7 Verdict of at most three sentences on top. Default: deterministic template from the
  structured outcome (always available, EN/DE). Optional "LLM summary": a local text-only
  call that receives only the structured outcome JSON, never images; accepted only if every
  number, label and side it mentions exists in that JSON, otherwise the template is shown.
- [x] A8 App result panel leads with the verdict (EN/DE, follows the language switch) and a
  "Rephrase with local LLM" button; the source line says fixed wording, LLM, or why the LLM
  text was rejected. E2E checks the verdict in both languages.
- Phase A evidence: Markdown/HTML open with a ≤3-sentence verdict (`reports/outcome.py`,
  EN/DE templates) and coverage; yes-bias collapses N abstention lines into one; detector
  candidates below 0.5 are counted, not listed; HTML has a CSS-only EN/DE switch; one short
  disclaimer (full text in `docs/DISCLAIMER.md`); SeriesInstanceUID/patient ID removed from
  the readable report and its embedded JSON (the JSON download keeps them). Optional
  `POST /api/results/{id}/summary` (`use_llm`) lets local `medgemma1.5-q4` rephrase the facts
  only; text with new numbers, findings, causal/diagnostic words or >3 sentences falls back
  to the template. Unit/integration: 908 passed before the gate.

Phase C — thorax-review focus and model guidance (lead):
- [x] C0 **Parser inversion fix (critical).** `present: false, confidence: 0.0` (MedGemma's
  way to say "absent") was read as P(present) = 1.0, so all 16 negatives became unsupported
  positives and the run abstained — including the user's real-study MedGemma run, which the
  lead first misreported as a yes-bias. The yes/no answer now sets the direction, confidence
  only the strength (0.5 = unknown), contradictions add a warning; bare numbers and P6
  logprobs keep P(present) semantics. Earlier "constant positive" MedGemma conclusions
  (status 2026-10-17, readiness checks) must be re-run before they are cited.
- [x] M1 Manual page 20 "Thorax review" (verdict, EN/DE switch, LLM wording, fit markers,
  detector-first full review, weak cues); 20-page Chromium PDF, pages 1 and 20 reviewed.
- [x] REL v0.6.0: notes in `docs/releases/v0.6.0.md`; publish only after the gate, push and
  exact-commit CI pass, with wheel, sdist, manual, helper and SHA256SUMS verified after upload.
  B7 evidence: phantom (detector finds nodule, MedGemma all-absent) and calibration runs in
  `docs/model-test-runs-2026-10-20.md`; full real-study review accuracy remains unmeasured.
- [x] R2 `/code-review` (v0.5.4…HEAD), all 9 findings fixed: a stop during a detector/HU-only
  review is reported as cancelled; the selected detector config is used; yes-bias text counts
  only unsupported positives; German sides reuse `outcome.SIDES`; a positive at exactly 0.5
  stays positive; results store `qc.width_mm` so app and report verdicts give the same sides;
  confidence contradictions collapse into one warning; a GPU lock keeps jobs and the LLM
  rewording apart; the short disclaimer now names a self-made experimental tool and possible
  incorrect, incomplete or misleading findings (AGENTS.md updated for it and the EN/DE
  report switch); one shared `side_of_x` replaces three copies.
- [x] R1 Branch review (v0.5.4…d4988f6), all findings fixed: (1) HU-only look-here entries are
  weak cues and never decide the verdict (real scans got "findings to review" from density
  noise); (2) the full review also runs with the detector or HU baseline only, the image-model
  sweep is optional and the UI no longer recommends MedGemma; (3) the optional LLM verdict
  falls back to the template while a GPU job runs; (4) a failed detector run no longer
  recommends running the detector.
- [x] C0b Full review: a slab-level self-abstention ("only one slice visible") no longer
  discards the per-label answers; P7 1.1.0 asks for `abstain: false` and null per label.
- [x] C1 Evidence-based fit marker per model (`fit` 1–3 + reason in `configs/models/*.yaml`):
  dropdown sorted by fit with 1️⃣/2️⃣/3️⃣ prefix, translated status line, API exposes it.
- [x] C2 Group the dropdown: thorax-review models first; general-purpose VLMs under a
  "research controls" group (kept for benchmarking, not the default path).
- [x] C3 Test runs of every installed model on the synthetic demo (known planted lesions)
  and one calibration case (never the holdout); record a results table and adjust `fit` only
  on evidence.

Phase B — full thorax review job (isolated worker; separate commits):
- [x] B1 Coverage sweep over lung z-range plus mediastinal/upper-abdomen margin as
  contiguous slabs, visited coarse-to-fine (ends, middle, quarters, … until all covered).
- [x] B2 One multi-label query per slab (all labels, yes/no + evidence); about 60–70 slabs
  for a 317 mm scan, roughly 10–15 min with MedGemma Q4 on this workstation.
- [x] B3 Aggregate per label across neighbouring slabs: localized clusters become findings;
  a label positive on most slabs is reported as "not informative (constant answer)".
- [x] B4 Combine whole-volume MONAI candidates, HU cues and VLM clusters into one ranked
  "look here" list with slice range, side, sources and agreement.
- [x] B5 Live progress: after the first slab, show measured time per image and
  "k of n images left, about M min" (updated after every image); cancel keeps partial results.
- [x] B6 Outcome summary + rule-based next steps (existing guideline rules only).
- [x] B7 Validate on synthetic lesions and calibration cases only (never the holdout);
  record honestly whether VLM clusters add anything over the detector.
- Phase B evidence (isolated worker, integrated by the lead): `thorax_sweep` strategy
  (5 mm slabs over lung range +10/−30 mm, coarse-to-fine order, ≤96 slabs), prompt P7
  (one slab, all labels, null when not visible), `full-review` job with HU baseline and MONAI
  once, label clustering with constant-answer detection (>60 % per label, >85 % overall),
  ranked look-here list, measured s/image + remaining images/time, cancel keeps a partial
  result, EN/DE outcome panel, `docs/full-review.md`. Worker suite: 1052 passed. Live smoke
  (synthetic phantom, MedGemma Q4, 8 slabs): ~35 s/image, no usable label answers; open.
- C3 interim (API test runs, 3 studies each: synthetic phantom, LIDC-0027 nodules,
  LIDC-0306 no nodules): MONAI found the phantom nodule (0.998) and 0027 (0.998) but scored
  0.77 on 0306 (false alarm); HU baseline over-reports on real scans (pneumothorax etc.);
  MedGemma Q4 abstained on all; P6 answered all 16 labels positive on all three; Llama 3.2
  Vision abstained in ~4 s. Fit tiers confirmed so far.

Expectation: the detector is the only component with demonstrated signal. Full coverage
does not make a small VLM accurate; the summary must say so when its answers are constant.

### Vendor private header values and UI red-team — 2026-10-19

The user's operator scan (`dcom_evaluator.py --scan-headers --check-import`) located all
317 rejected headers in one group: private tag `(01F1,1026)`, 6 declared/available bytes,
`BytesLengthException`, implicit VR. pydicom's tag-specific ELSCINT1 entry types this
*Pitch* as FD (8 bytes); the generic ELSCINT1 entry is DS. Strict full conversion therefore
rejected whole valid slices (probably a complete series).

- [x] Importer: `read_header` keeps undecodable **private** values as raw `UN` bytes and
  counts them as `discovery.private_values_raw`; public tags stay strict. The privacy audit
  still sees the private tag. Diagnostics allowlists include the new counter.
- [x] Evaluator: private-only conversion errors stay in `error_groups` but count as
  readable (`counts.private_values_raw`); single-file status follows the same rule. Import
  results add `qc_warning_count` (previously only parser `warning_count` was shown next to
  the `input_qc_warnings` limitation).
- [x] Tests: synthetic implicit-VR ELSCINT1 series loads all 32 slices with no warnings;
  public mistyped values are still rejected; evaluator scan/single-file regressions. Related
  suites 40/40 passed. No private file was read by the agent.
- [x] Importer fix committed `5e2769a` v0.5.2: full gate GREEN, exact-commit CI
  `39329540433` passed. Idle preview (empty job queue) restarted on v0.5.2, port 8002.
- [x] Operator re-check on v0.5.5 (user-run, JSON shared): all files readable,
  `header_errors: 0`, `private_values_raw` equal to the former error count, import succeeded
  with adequate QC and no QC warnings; the formerly excluded axial series is now listed.
- [x] Redacted case note and checker guide: `docs/wiki/Checking-a-real-DICOM-folder.md`
  (no path, name or acquisition values), linked from README. GitHub wiki is enabled but has
  no first page, so its git repo does not exist yet; mirror the page once one is created.
- [x] UI/UX red-team (isolated worker, synthetic data only): 8 findings fixed — stale study
  after failed folder open, unexplained disabled Run (translated, live reason), progress
  placement/announcement noise, untranslated folder error, header warnings worded as
  failures, folder jobs looking like model results, field-level path error, inconsistent
  study label. Worker: 362 e2e/integration + 649 unit passed. Remaining items are listed in
  [the review](review-ui-redteam-2026-10-19.md). Integrated as a separate gated commit.
- [x] UI commit `36c062e` v0.5.3: full gate GREEN (tests 353 s), exact-commit CI
  `39332366712` passed.
- [x] Manuals: HTML adds the blocked-Run reason line and vendor private values /
  `qc_warning_count`; Chromium-printed 19-page PDF, pages 4 and 18 visually reviewed.
- [x] Manual commit `e09e1d5` v0.5.4: gate GREEN, exact-commit CI `39348579922` passed.
- [x] Release v0.5.4 published (former v0.5.1 draft retargeted to `e09e1d5`); wheel, sdist,
  manual and helper replaced and verified against the downloaded SHA256SUMS.
- [x] App smoke on v0.5.4 (port 8002, detector extras restored, weights verified): synthetic
  implicit-VR ELSCINT1 folder imported 64/64 slices (`private_values_raw: 64`, no warnings,
  QC adequate); MONAI job succeeded in 31 s with 0 candidates on the phantom; offline HTML
  200. Execution check only, not accuracy. Smoke jobs were cleared.
- [x] Remaining UI review items (screen-reader text language switch, keyboard-reachable
  disabled downloads, untranslated codeless hints, mobile job notice, Jobs table at 360 px):
  fixed as findings 9–13, covered by `tests/e2e/test_ui_leftovers.py`; released as v0.6.1.

### Root cleanup and diagnostic scan handover — 2026-10-19

Current task: finish the local-import diagnostics ticket and keep the repository root
focused on standard entry points. The lead owns integration, final validation and release.

- [x] Move vision, data policy, agent environment and both operator manuals under `docs/`.
  Update relative links, including release notes and the recording helper's manual path.
- [x] Document `scripts/dcom_evaluator.py`: single-file header inspection, bounded
  `--scan-headers` folder summaries and explicit `--scan-headers --check-import` loading.
  Nineteen synthetic helper tests passed; no private source was inspected by agents.
- [x] Integrate measured loading counters, translated live UI feedback and bounded
  sanitized JSON/journal events. Preserve warnings, source-image readiness and holdout checks.
- [x] Regenerate `docs/manual.pdf` with separate diagnostic and durable-log pages.
  Visually reviewed pages 18–19: commands, warnings and footers fit without clipping.
- [x] Run the complete local gate, make the gated commit, push, and check exact-commit CI
  (`6e1ddb3`, CI `39327963402` passed).
- [x] Publish only after these checks pass; refresh the preview only when its queue is idle
  (published as v0.5.4; preview refreshed with an empty queue).

Baseline: `cff030d` v0.5.0 passed public CI. This follow-up targets v0.5.1 and is
committed only after the complete `scripts/commit.sh --no-push` gate passes. Inspect
`git log -1` and `.pipeline/diagnostics-final-commit.log` for the resulting commit and gate
record. Every new commit must update this plan in the same change, including evidence and
remaining work. Preserve all current changes,
recovery stashes and saved outputs. Do not run additional private-data inspection or
inference for this cleanup. MedGemma recognition readiness and full benchmark sweeps remain
open; a successful folder import does not establish model accuracy.


### Operator diagnostics and loading feedback — 2026-10-19

User requested a private, locally run `dcom_evaluator.py` within ten minutes, durable logs
and live loading feedback. The lead owns the header helper and job/logging integration;
two isolated workers supplied actual core counters and translated UI progress. Their work
is integrated and frozen; the lead owns the combined gate and release. Do not
inspect the private Downloads study. Observe only the user's server job/log metadata.
The user's v0.5.0 import succeeded in about 79 seconds with 317 byte-length header errors.

- [x] D1: implement one-file stdout JSON diagnostics, with values/paths omitted by default.
  Ten synthetic subprocess/core tests cover malformed tags, privacy, bounds and sealed
  guards. Independent review fixed argument echoing and the optional-pixel guard.
- [x] D2: add bounded actual header/discovery/pixel/QC counters through the shared queue.
- [x] D3: add durable bounded job logs and an optional journal launch procedure.
- [x] D4: integrate/review, run the full gate, refresh the idle preview and publish a tested
  GitHub release. v0.5.0 is committed at `cff030d`; CI `39322252887` passed. Its release
  draft was retargeted and published as v0.5.4 after the follow-up checks passed.

Diagnostics integration checkpoint: 71 focused core/browser/API checks passed; 28 privacy,
rotation, guard and parser checks passed. A real synthetic user-service run completed in
0.20 s with 43 JSON events spanning all six operations. Journald received matching events;
log mode is 0600. The test service was stopped. No private image was read. Review fixed
copied-sealed pixel access, disabled query-bearing HTTP access logs, and corrected path
counter units. Route-arrival waits also remove a scheduling assumption from existing
browser tests. The 19-page HTML/PDF manual was generated; final diagnostic/log pages were visually reviewed.

Release target: v0.5.1 after the full local gate, push and exact-commit GitHub CI. Replace
the unpublished v0.5.0 draft assets with the new build, verify uploaded checksums, then
publish. Refresh the preview only when its queue is idle and restore optional detector
packages after the locked base-environment gate. Preserve all saved reports and worker
recovery stashes. Both new worker worktrees are clean; integrated patches remain in
`recovery: folder progress backend/UI integrated 2026-10-19` stashes. The user then supplied two readable single-file reports. They do not locate the rejected
headers. The release gate was stopped before commit to add an explicit operator-run
header-only folder scan with aggregate error groups and opaque series/orientation counts.
No private files are read by agents. The lead continues journal/privacy checks in parallel;
the isolated backend worker owns the scan extension and synthetic tests. A second real
synthetic journal smoke confirms folder-query paths are omitted (HTTP 200). The commit script and exact-commit CI enforce D4's
release acceptance; publication and preview verification follow those green gates.

### Local DICOM folder opening — 2026-10-19

User request: add folder-path drag/drop, consider the UI, implement it and open the new
version. The previous video delivery is committed/pushed at `688ac0c` (v0.4.19); 895
local tests and GitHub Actions passed. Main and recovery worktrees were clean at start.

- [x] F1: add guarded directory browsing and session-only local study registration through
  the shared processing queue. Reuse CLI header/split checks before loading pixels.
- [x] F2: add accessible path drag/drop, paste/open and an in-app folder browser, with
  English/German help and both themes. Keep indexed study selection available.
- [x] F3: review sealed/symlink/copy boundaries, queue cancellation, reloads, errors and
  responsive UX. Run synthetic end-to-end folder → viewer → analysis → HTML checks.
- [x] F4: synchronize README, architecture, AGENTS and HTML/PDF manuals; run the full
  commit gate, push the feature and open the new local UI.

Functional checkpoint (2026-10-19, 22:28 CEST): guarded registration, folder drag/drop,
extensionless inputs, strict lazy-header validation and traceable diagnostics are integrated.
Synthetic EN/DE folder → viewer → actual analysis → offline HTML checks passed. A malformed
synthetic header reproduces the reported pydicom failure; malformed files are excluded
before series selection, while corrupt selected-series pixels still fail explicitly.
No files in the user's forbidden private folder were inspected. Its reported counts alone
do not establish whether its selected series is usable.

F3 integration checkpoint (22:33 CEST): Local selection, viewer readiness/failure/retry,
QC blocking and previous-study protection are implemented. Twenty-six focused browser
checks pass, including actual extensionless folder → engine → offline HTML and real
failure-trace downloads. Cached slices perform no header rescans when source and split
policy are unchanged. New pixel loads, source changes and split-policy changes still
require full header guards. Successful warning traces retain aggregate parser categories.
Independent integrated review found no additional guard/privacy/cancellation blockers;
eighteen cache-policy/diagnostic checks passed. README, architecture, AGENTS and the
17-page HTML/PDF manuals are synchronized; the new manual page was visually reviewed.
Supplementary `reviewBranch` checkpoint (22:39 CEST): the committed comparison is empty
because main and origin/main both point to `688ac0c`. The actual pending patch received
independent backend and frontend reviews. Backend review found no additional blocker.
Frontend review identified a stale import-completion race: delayed folder A selection could
unblock Run after folder B started. The release was stopped before commit and its version
bump reverted. Add a generation guard and delayed A/B regression. Also preserve the failed-import block
when search text does not select a new study, and retain the current slice during
unrelated search while its image is pending/failed. The existing UX-01 acceptance check
confirmed that slice 5 incorrectly reset to 32. Fix these three confirmed review findings,
then rerun the full gate.
The initial three findings and a fourth confirmed stale-library-refresh path are fixed. Import continuations use an input-intent generation guard;
new input/selection intentions also stop following earlier import jobs without cancelling
server work. Search alone retains the failed-import block. Unchanged-study search preserves
the slice. Added regressions cover delayed completion, failure, pending POST, running-import
manual selection and language-switch recovery. See [the review](review-local-folders-2026-10-19.md).
The focused folder/readiness/diagnostic/acceptance suite passes 39/39; an additional
delayed-refresh regression checks that old inventory cannot replace a newly opened folder. The full
release gate is rerun against the fixed tree; a failed gate creates no commit.

F4 release acceptance is enforced by `scripts/commit.sh`: commit only after all pipeline
stages pass, then push. Preserve the idle preview job snapshot before restarting; restore
the optional detector environment after the locked base-environment gate.
Both local-folder worker worktrees are clean. Their integrated patches remain in named
`recovery: local-folder backend/UI integrated into main 2026-10-19` stashes; keep them
until deliberate cleanup. No running worker or additional GPU task remains.

Delegate backend and frontend to two isolated worktrees. The lead owns integration,
independent review, documentation, full gate and the local preview. No real study is
needed for tests. Do not upload/copy files, infer automatically, weaken sealed guards,
or persist absolute paths in browser storage/job snapshots. Browser folder APIs can hide
absolute paths; support local file-URI/plain-text drops and explain the folder-browser
fallback. Never guess a path from a relative FileSystemEntry name.


### Leftover cleanup and video reframing — 2026-10-19

Four historical dirty worktrees are now clean. Their tracked and untracked files were
verified in named recovery stashes; old stashes/worktrees/data remain preserved.
See [the cleanup inventory](worktree-cleanup-2026-10-19.md). One ad hoc identifier HMAC
proposal needs a separate reviewed port; no obsolete source patch was blindly merged.

The user rejected the first fixed-crop edits because they cut off interface content.
The media commit was stopped before creating a commit. Both cuts now start with a
complete context view followed by a smooth pan/zoom to the full relevant panel.
Each scene was reviewed at overview, transition and focus. Forty-nine focused tests
pass, plus synthetic decoded-frame corner checks and complete real-cut decode checks.
Both revised videos are under `media/`, with exact-path/hash exceptions to the 2 MB gate.
Tampered approved bytes and an unrelated oversized file are correctly refused.
The final full commit gate must pass before publication.

### Media publication — user instruction, 2026-10-19

Copy the two reviewed cuts into top-level `media/` and commit/push them with TCIA
credits, SRT captions and SHA-256 checksums. This explicit instruction supersedes the
local-only Git restriction for these two files only. Preserve the ignored originals.
Run the full commit gate. No LinkedIn upload is authorized. See [media](../media/README.md).

### Finish plan — 2026-10-19

Checkpoint: clean engine `d171803` (v0.4.17) recorded the genuine 4K Chromium tour.
The full gate passed 872 tests /97.87% coverage. Core recovery, result tabs, About
metadata, dependency refresh and review repairs are complete. MedGemma requests now
finish but still fail useful-reading readiness; recognition remains open.

The selected MONAI calibration recording succeeded: 80.108 seconds server elapsed,
19 proposals, 8 at the existing 0.5 cutoff and 12 illustrated. The full 168.7-second
master and actual offline report remain under ignored `data/results/linkedin/`.
The first failed take is preserved. X11 isolation fixed inherited Wayland routing.
Visual review found square-cut captions overlapping footage; the renderer now reserves
separate header, footage and caption areas. This is a presentation repair, not a change
to detector output. See [the delivery record](video-delivery-2026-10-19.md).

- [x] V1: recorder `ba66639` passed independent review and its full gate: 858 tests,
  97.84% coverage, including 25 synthetic recorder regressions. Subsequent recording is complete below.
- [x] V2: integrated `dc206c5` (v0.4.16), synchronized the 16-page manual; full gate
  passed 871 tests /97.87% coverage.
- [x] V3: restore detector extras, start the clean committed UI and record one genuine
  Chromium tour of the authorized calibration case; preserve original/failed takes.
- [x] V4: inspect the take, render two 30-second cuts, verify all 900 frames per cut,
  captions, credits, readable framing and recorded source/model identity.
- [x] V5: record delivery paths, limitations and final review. Final handover uses the
  full commit/push gate; verify the resulting GitHub Actions run before closing the session.
  At this checkpoint no real frames were committed. The later media instruction above
  authorizes only the two reviewed cuts; nothing is uploaded to LinkedIn.

The recorder worker and independent reviewer have finished. The lead owns
all live inference/capture. Keep GPU jobs sequential and the frozen 20% sealed. VLM
recognition, official-runtime parity and unbiased evaluation remain separate scientific
follow-up; do not describe them as completed by this video task.


- **User-triggered video (2026-10-17):** produce two 30-second LinkedIn draft cuts and
  retain the complete original Chrome/Chromium tour. The user explicitly requests the
  real previously reviewed MONAI calibration example and excludes the heuristic; this
  overrides the earlier synthetic-only recording preference for these local drafts.
  Verify current TCIA/CC-BY attribution first, preserve training-overlap/selected-case
  limits, keep every real frame under ignored `data/results/linkedin/`, and do not upload.
  No sealed or internal-test access. Recorder/editor work is delegated; root owns the
  real rehearsal, recording, frame review and final verification.

- **Recovery integration (2026-10-17):** integrate atomic runtime commits `924a147` /
  `941c536` and UI/About commits `6b919ee` / `5aec0e3`. Independent cross-review found
  two concrete regressions: detector-roster cancellation wording and empty-first-pass
  generation diagnostic indexing. Both are repaired with synthetic regressions. See
  [the current review](review-current-2026-10-17.md). The fixed Q4 calibration pair
  and Q8 calibration pairs terminate without length stops (179–227 tokens), but three
  reports abstain and the remaining result is a positive on the annotation-negative
  control. All four ran from clean `941c536`; recognition readiness still fails. Recognition readiness remains failed/pending, not inferred
  from completion. Preserve the old port8000 session and its registered reports.
- **Requested housekeeping:** GitHub About updated with 🫁 and ten grounded topics
  ([metadata record](github-about-2026-10-17.md)). All27 direct pins and 106 registry
  packages checked; an isolated dependency gate passed with two direct and three
  compatible transitive updates. Integrate that separate commit after this UI merge,
  then run the combined gate and publish the measured model results. UI/runtime
  integration `a12b867` is pushed: full gate 846 tests /97.87% coverage.

- **Recorded report review (2026-10-17):** add direct new-tab HTML opening beside
  offline downloads in results, comparison rows/combined export and partial/abstained Jobs
  steps. Reuse registered output IDs and recheck guarded paths. Report-only CSP permits
  embedded images/styles and blocks scripts/network; the application policy stays strict.
  Separate deterministic Input QC, model image assessment and usable-reading status;
  expose truncation reasons and recorded generation diagnostics. Configured comparison
  starts with detector/heuristic baselines and uses the explicit Qwen no-think control.
  Validate synthetic EN/DE desktop/mobile flows, inline downloads and path protections.
  Runtime integration uses Q4/Q8 P5 schema-v2, uniform raw axial 896-pixel inputs,
  no cues/coronal/MIP views and repeatable focused CLI labels; UI counts remain overrides.
  These are completion/input fixes, not established recognition readiness.
  Model recovery and live checks are tracked in [the recovery plan](model-recovery-plan-2026-10-17.md).

- **About contribution link (complete, 2026-10-17, `6b919ee`):** added the canonical GitHub
  repository link with translated EN/DE text and keyboard/hover help. Open it in a new tab
  with `noopener noreferrer`. Replace the stale benchmark-pending description with the
  implemented study/candidate/recorded-benchmark workflow. Refresh the synthetic About
  screenshot and synchronized operator manual; run the normal commit gate.

- **Verified engine checkpoint (2026-10-17):** v0.4.9 `981e1ec` is pushed. Full gate:
  829 tests / 97.84% coverage; GitHub Actions `39043586041` passed. W1/P6, W2/W3/W6,
  the S1 source-grouping regression and recovered calibration work are integrated.
  Both delegated workers stopped at their service usage limit. No agent or GPU run remains
  active. Recovery worktrees and stashes are preserved; do not reapply their old diffs.
- **Real GUI job API check:** clean v0.4.9 completed a calibration study in 40.93 s with
  nineteen detector candidates (eight at the existing 0.5 cutoff), previews for twelve
  candidates and an offline HTML download with embedded images. No browser screenshot
  used patient data. Saved report and verification metadata remain under ignored
  `data/results/ui/7747a176-39c1-43d4-8fb9-c45329998929/`. This repeats one earlier study;
  do not count it as an additional independent calibration case.
- **Useful-output evidence:** three calibration-only detector studies yield eleven proposals
  at the existing 0.5 cutoff: eight indexed-reference matches and three unmatched. Positive
  pair 77.31 s, annotation-negative control 27.92 s. LIDC overlap **yes**; no unbiased accuracy
  claim. Local offline image/text reports are in ignored `data/results/detector-review/`.
  See [the model-usage review](model-usage-review-2026-10-17.md).
- **MedGemma verdict:** S2 categorical gate fails; T2 Q4 binding is 5/20 and 1/20 (both fail).
  P6 one-image reasoning/extraction is implemented but all four synthetic sphere/control
  outputs were yes. Both window readiness gates fail. Do not enable VLM candidate filtering.
  Bounded synthetic S1/S3 are complete; expanded calibration controls and approved BF16
  parity remain scientific follow-up work.


- **W6 detector review (2026-10-17):** added manual detector setup/availability, optional
  dependency license inventory, sourced candidate table and source-slice navigation with
  English/German help. UI and offline HTML show bounded post-inference axial/coronal
  illustrations (first 12 candidates; every candidate remains in JSON/Markdown/table).
  No new inference thread or verifier is enabled. Invalid detector boxes/scores fail
  explicitly; nonfinite crop centres are refused. Synthetic UI/export tests exercise
  the path through the merged W3 job queue, including running-detector cancellation at a
  safe stage boundary. Optional VLM verification
  remains gated on image-path sanity and the official protocol.

- ✅ **Older calibration work recovered (2026-10-17):** ported the fitting core and
  synthetic tests from `a0b01d7` onto the detector baseline in an isolated checkout.
  Fitting is opt-in, uses calibration records only and applies to internal-test only.
  Raw metrics remain separate. Recorded overlap now reaches HTML/CSV/export manifests;
  E005–E008 planning files refuse execution before study access. Legacy read-only export
  validates original stored config bytes/hashes; strict resume remains unchanged.

- **W2 reference detector implementation (2026-10-17):** optional checksum-pinned MONAI
  LUNA16 RetinaNet inference adapter, explicit terms/weight helper, millimetre candidates,
  overlap-labelled per-dataset Task A/C reports and in-memory axial/coronal crop component.
  See [setup and limits](detector-baseline.md). Five existing local bundle files verify.
  A reduced synthetic CPU network/API smoke passed; default-ROI GPU calibration performance
  is now recorded in the usage review (two positive studies and one negative control). Synthetic adapter/geometry/scoring tests cover the
  pipeline without downloading weights. Detect → VLM verify → review remains an integration
  task. Do not claim unbiased LIDC accuracy or numerically identical upstream preprocessing.

- ✅ **W3 committed/pushed `da473be` (2026-10-17):** analysis, comparisons and
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
  | W1 | Image-path sanity gate (T0 layout audit, T2 position binding, S1 blank/noise/shuffle, S2 synthetic spheres, S3 description, S4 paired lesion/control slabs, optional bf16 parity) | lead integration | Core plus bounded S1/S2/S3/S4/T2 recorded; expanded controls/parity open | Results in `results.md`; gate verdict recorded; full gate green; merged by the lead |
  | W2 | Detector reference baseline (MONAI RetinaNet, inference only, overlap-flagged), lesion-level Task C, crop-export view | merged `535ee24` | Implemented; three calibration checks recorded | Explicit weight download, tests with stub network, calibration results, merged |
  | W3 | Job layer: server-side sequential queue, cancel/stop, persistent status bar on all pages and in the tab title, Jobs panel, fixed elapsed display | lead, main checkout | ✅ `da473be`, 680 tests / 98.28% | Playwright: navigate/reload keeps the running job visible; cancel works; docs/manual/screenshots refreshed |
  | W4 | Official-protocol prompt P6 (interleaved `SLICE k`, one label per query, P(yes)), non-constant-output readiness check | lead integration | Implemented single-image adaptation; readiness failed | No claim of official runtime parity |
  | W5 | VLM crop verification of detector candidates | after W2 + W4 | Gated: categorical readiness fails | Requires a successful calibrated-case verification gate |
  | W6 | Usable workflow: study → detector → candidates in viewer → optional VLM check → sourced findings → report, all through the W3 job layer; Evaluation shows these runs | detector review worker, after W2 + W3 | Detector review implemented and tested; VLM verification gated | Synthetic e2e in EN/DE, light/dark, mobile; source navigation and offline HTML; manual synchronized |
  | W7 | RQ1 report with overlap column; status/plan/AGENTS sync; self-review; worktree and stash cleanup proposal | lead | Interim report, source-grouping fix and self-review delivered; v0.4.9 gate/CI green | Final full gate, pushed |

- **Program status and approach check:** the detector workflow is available and tested.
  Bounded sanity runs and the literature/usage review are recorded. MedGemma verification
  remains gated; expanded calibration controls and approved BF16 parity are follow-up work.

- W4 P6 implementation (2026-10-17): isolated standard Ollama adapter supports one label
  per visual request, short reasoning then a constrained binary answer call with token
  logprobs. Dedicated one-image/no-cues configuration; missing/truncated outputs remain
  unavailable; both calls are retained. A shared readiness summary distinguishes
  categorical nonconstancy from score discrimination. Synthetic/mocked acceptance tests
  pass; v0.4.9 full gate and bounded live probes are recorded. This is a local adaptation,
  not HF/runtime parity or whole-study detection. See `docs/p6.md`.

- W1 bounded follow-up (2026-10-17): Q4 single/lung 30 mm synthetic gate completed: 0/10
  positive answers, 10/10 negative answers, 71.1 s. Categorical positive criterion fails
  despite probability-score separation. Full Q4 T2 completed with both layouts failing. Bounded S1 completed with fourteen categorical no answers; original raw output preserved. Narrowed configurations have separate IDs; no held-out inputs are used.
- W1 handover review (2026-10-17): sanity CLI/configs already committed in this worktree.
  Recovered completed S2 `--limit 1` synthetic smoke and S4 calibration paired-slab evidence;
  aggregate results and caveats are in `docs/results.md`. S1, full S2/T2, S3 review and
  runtime parity remain open. Parser robustness, rendered control-edge distance and
  single-image lesion metadata were corrected; historical evidence remains unchanged.
  Operator instructions: `docs/sanity.md`. No sealed/internal-test data or GPU job was
  needed for this handover review. Next: coordinate one GPU owner and run the missing
  bounded gates before resuming study-level sweeps.

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
- ✅ **Operator manual (user follow-up):** `docs/manual.html` and matching `docs/manual.pdf`,
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


Current executable workflow: detector → sourced candidate review → offline HTML. The
v0.4.9 gate and GitHub CI passed; a real calibration study also passed the GUI job API
and offline-download check. Scientific follow-up is expanded calibration controls and
approved HF parity. P6 failed readiness, so VLM verification stays disabled. The numbered
sequence below retains the approved research order and marks delivered parts explicitly.

Decision record 2026-10-17 (user-approved approach-review plan). All real-data runs use the
calibration phase only; each change is a separately hashed configuration.

1. 🔄 **Image-path sanity gate** (T0–T5 of the approach review, plus S1–S4): prompt layout
   audit, position binding (single message vs one message per image), real vs blank/noise/
   shuffled images, synthetic spheres 30/15/8 mm, free-text description, paired
   lesion/control 5 mm slabs with one yes/no question each (slice-level AUROC, yes-rate on
   controls). Optional HF bf16 parity if weights are available without new terms. Gate:
   if blank-vs-real or the 30 mm sphere fails in every format → failed readiness; separate runtime, task and model causes before assigning blame.
2. 🔄 **Official-style protocol prompt (P6; implemented single-image adaptation, readiness failed):** interleaved image + `SLICE k`, one label per query,
   short reasoning then constrained yes/no, P(yes) scoring from logprobs on short answers.
   The nonconstant-output criterion is implemented and failed. Official HF parity remains open.
3. ✅ **Detector reference baseline (implemented, overlap-limited calibration checks recorded):** MONAI `lung_nodule_ct_detection` (RetinaNet,
   Apache-2.0), inference only, weights in ignored `data/`. `possible_training_overlap: yes`
   on LIDC (LUNA16 ⊂ LIDC), out of distribution on NSCLC. Lesion-level Task C (sensitivity
   at 1/2/4/8 FP per scan) plus study-level max score.
4. ⏳ **VLM crop verification:** ≈64 mm lung-window crops (axial, optional coronal) around
   detector/heuristic candidates; "nodule vs vessel/none" per crop; score FP/scan at fixed
   sensitivity against the detector alone. Run only if step 1 shows crop-level signal.
5. ✅/🔄 **Usable detector workflow delivered; VLM verification remains gated:** choose
   study → run detector → review candidates, crops and source slices → inspect sourced
   findings and limitations → download offline HTML/Markdown. Evaluation shows stored
   detector benchmark runs. Synthetic e2e and real calibration API checks are recorded;
   screenshots/manual are synchronized. Per-candidate VLM verification is not enabled.

6. ✅ **Interim RQ1 report delivered:** honest result table (VLM study level, VLM slab/crop level, detector,
   heuristic) with overlap column; negative results stay visible.
7. ✅ Calibration fitting is opt-in and wired; overlap flags reach reports/exports;
   E005–E008 planning configurations refuse execution. Preserve the historical NSCLC
   index uncertainty. Real-model calibration benefit is not established.
8. On hold: E002–E004 study-level sweeps and QLoRA (`fine-tuning-plan.md`) until steps 1–4
   show a visual signal. Deferred: LAN/40 GB runner. Recording waits for the user's trigger.

## Self-review gates

* After every work package: full `./localPipeline.sh` green, then commit and push.
* After WP8 and at the end: walk through `docs/vision_traceability.md` (one row for every
  Vision section) and close any gaps.
