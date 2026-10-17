# AGENTS.md — working rules for humans and AI agents

This file is the operational contract for anyone (human or AI coding agent) changing
ThoraxBench Local. The *why* lives in [`Vision.md`](Vision.md); the *how/when* lives in
[`docs/plan.md`](docs/plan.md). If anything here conflicts with Vision.md, Vision.md wins
and this file must be fixed.

## 0. Resuming work

1. Read `docs/plan.md`, especially *Current activity* and *Next steps*.
2. Run `git log --oneline -20`.
3. Run `git status`.
4. Read `Vision.md` and `docs/architecture.md` before changing the design.

**Checkpoint:** identify the current task, completed work and uncommitted changes before
editing. Preserve existing work. Record decisions and handover details in the repository;
do not leave essential information only in chat or temporary files.

## 0.2 Handover for another agent framework (2026-10-17)

Any framework can continue from the repository alone. Read this section, then
`docs/plan.md` → *Current activity* (work plan W1–W7) and `docs/status-2026-10-17.md`.

**Verified engine checkpoint:** `981e1ec` v0.4.9 is pushed. Its full gate passed
829 tests / 97.84% coverage and GitHub Actions run `39043586041` passed. W1/P6,
W2/W3/W6 and the older calibration port are integrated. Do not merge the old worker
branches blindly. No delegated worker is running; both stopped at their service usage
limit. Preserve worktrees and stashes as recovery copies until the user chooses cleanup.

A real calibration study completed through the GUI job API in 40.93 s: nineteen detector
candidates (eight at the existing 0.5 cutoff), previews for twelve candidates and a verified
616855-byte offline HTML download. Local artifacts, including `verification.json`, remain
under ignored `data/results/ui/7747a176-39c1-43d4-8fb9-c45329998929/`. Never commit their
patient pixels. This is an execution check, not accuracy or a new independent study.
The loopback preview now runs from main, replacing the old calibration-clean preview.
Check the process and active jobs before restarting; saved reports survive, in-memory
jobs/download links do not. See [the usage review](docs/model-usage-review-2026-10-17.md).

**Parallel worktrees** (all under `.claude/worktrees/`, git branch `worktree-agent-<id>`).
"locked" means a Claude Code agent was still running there at handover; a lock is only a
git marker (`git worktree unlock <path>`). Inspect each with `git -C <path> log --oneline
main..HEAD` and `git -C <path> status` before merging. Merge with
`git merge --no-ff <branch>`, keep `main`'s version in `src/thoraxbench/__init__.py` on
conflict, then `scripts/commit.sh "<message>"` (bumps, full gate, pushes).

| Worktree id | Work item | State at handover | Next action |
|---|---|---|---|
| `agent-a2713de6be2350cab` | W1 image-path sanity gate (`thoraxbench sanity`, `configs/experiments/sanity/`) | committed through `37f59e7`; P6 recovered by lead | Compare main before reuse; bounded S1/S3 complete; expanded controls/parity open |
| `agent-a97e30bcce02518f3` | W2 MONAI detector baseline + W6 sourced review | integrated `535ee24` | Keep as recovery copy; weights only under ignored `data/` |
| main checkout | W3 job layer (`src/thoraxbench/api/jobs.py`, `abortable_http.py`) | committed/pushed `da473be`, full gate green | Preserve the shared queue and truthful stage-boundary cancellation during integration |
| `agent-aebf84a0219298401` | Older session: calibration fitting on the calibration phase, training-overlap tagging, E005–E008 configs (commit `a0b01d7`) | **ported by lead**, base `9e27cef` (old) | Do not reapply blindly; main contains the port with opt-in fitting and legacy export tests |
| `agent-a8afbe19832769108` | Older session: docs edits (DATA_POLICY, README, SECURITY, architecture, reproducibility) | uncommitted, base `9e27cef` | Probably superseded by later commits; diff against `main` before discarding |
| `agent-a9841ef98b05e6b4f` | E001-coverage / P5 | merged (`bcea332`) | Remove the worktree |
| `.pipeline/calibration-clean`, `.pipeline/evidence-clean` | detached clean checkouts for isolated runs | kept as recovery copies; preview replaced by main | Keep until replaced deliberately |

**Other state:** an old `commit.sh` stash (base `9453bbe`, 2026-10-16 16:16) appears
superseded; the user decides before it is dropped. Ignored real data lives in `data/`
(LIDC-IDRI 60, NSCLC-Radiogenomics 27 patients); runs in other checkouts use
`THORAXBENCH_DATA_DIR=<repo>/data`. Ollama at `localhost:11434` holds MedGemma 1.5 Q4/Q8 and
general VLM controls; 8 GB VRAM, one GPU job at a time.

## W2 detector handover (2026-10-17)

The optional `monai-lung-nodule` adapter and `CandidateCropView` are available. Follow
`docs/detector-baseline.md` for explicit checksum-pinned setup. Never auto-download weights
or run training. Detector scores are uncalibrated; LIDC rows must retain training-overlap
labels. The adapted SciPy input grid and smaller ROI are not upstream benchmark parity.
Live detector review includes sourced candidates, source-slice navigation and bounded illustrative
crops in UI/HTML; Markdown lists candidates. VLM verification remains gated separately.
Never silently repair invalid detector boxes/scores or render nonfinite crop centres.

## 0.1 Current priority

Current recovery/review handover: `docs/model-recovery-plan-2026-10-17.md` and
`docs/review-current-2026-10-17.md`. Preserve the original port8000 session reports.
Bounded completion does not establish recognition; keep failed visual gates visible.

Useful detector output is available for research review. Three calibration checks at the
existing 0.5 cutoff produced eleven proposals, eight reference matches and three unmatched;
LIDC training overlap remains **yes**. P6 and T2 failed readiness. Do not enable VLM filtering
or describe constant responses as proof that the image path is ignored. Preserve explicit
source labels, limitations and the sealed holdout.

**Direction (user decision, 2026-10-17):** follow `docs/approach-review-2026-10-17.md` and
`docs/plan.md` → *Next steps*: image-path sanity gate → official MedGemma protocol →
supervised detector reference baseline (inference only, overlap-flagged) → VLM crop
verification at lesion level → a usable detect → verify → review workflow in UI and CLI →
honest RQ1 report. Study-level E002–E004 sweeps and QLoRA are on hold until a visual signal
exists. Never present a detector score on LIDC as unbiased: LUNA16-trained weights overlap
LIDC. Label every finding with its source (detector, VLM, heuristic). Detector weights stay
in ignored `data/`, downloaded only by an explicit command. Status: `docs/status-2026-10-17.md`.

**Working rules (2026-10-17):** the work plan W1–W7 lives in `docs/plan.md` → *Current
activity*. Keep subagents to a minimum for budget reasons: finish and merge running agents
before starting new ones. Engine/GPU agents work in their own git worktree with
`THORAXBENCH_DATA_DIR` pointing at the main `data/` and commit with
`scripts/commit.sh --no-push`; the lead merges, runs the full gate and pushes. Only one GPU
job at a time. Never run `scripts/commit.sh` in a checkout where another agent is editing:
it stashes their unstaged work. W3 now queues analysis, comparison and acknowledged model pulls through one worker.
All long-running UI processing (analysis, comparison,
pulls, detector, verification) goes through the server-side job layer, stays visible on
every page and can be cancelled while queued; a running stop must state honestly whether
the provider may continue in the background.

The CLI engine and frozen pilot holdout are available. The **local UI MVP** is implemented
(2026-10-15): maintain its tested research workflow around the existing engine and keep
model-quality limitations visible. **User update (2026-10-16):** targeted UX improvements are now authorized after a full
review: study discovery/search, mobile flow, model setup, session-preserving navigation,
result context, translated labels and delayed accessible tooltips. The review and acceptance
checks are in `docs/ux-review-2026-10-16.md`. Advanced reference overlays and unrelated
UI features remain deferred. A read-only **Evaluation** section over benchmark outputs (runs, comparison, per-case reference vs. prediction, case detail) is implemented (`src/thoraxbench/api/evaluation.py`, 2026-10-16, user-delegated); it never starts inference, writes files or reads sealed data, and re-checks the split guard per open. Benchmark artifacts store no prepared image pixels, so the case detail shows the recorded image count and captions and says so; never re-render or substitute images there. Browser tests use `thoraxbench.synthetic_runs` (real runner over phantoms; scripted, labelled vision outputs). Precision work follows `docs/fine-tuning-plan.md`. The WP8 benchmark runner and the E000 development baseline exist. Benchmark requests
use the experiment's configured labels. Preserve each invocation in its own timestamp/hash/UUID
output folder; never overwrite previous partial or full runs. Persist each terminal
case/variant before proceeding. Refuse resume after code/configuration, data/index/split,
model/prompt/runtime identity changes or integrity failure; never weaken these checks. The two-study calibration
readiness smoke produced three abstentions and one scorable response that missed its
reference nodule. New benchmark invocations preserve per-case raw-response/request/provenance
artifacts and atomic checkpoints. Resume only pending units after strict identity and
integrity checks; terminal failures/abstentions stay preserved. Next: output reliability on
calibration data before the full E001–E004 experiments. A later bounded Q4/P2 diagnostic
returned two scorable responses but copied heuristic candidate text, omitted a known label
and supplied out-of-range image references. Anatomy sampling retains landmarks beyond `n`;
use uniform sampling for a strict small-image diagnostic and inspect actual image counts. Follow
the ranked gaps in
`docs/vision_traceability.md`. See `docs/plan.md` → *Priority* and *Next steps*.
Keep `manual.html` and `manual.pdf` synchronized with user-facing configuration and commands.

UI defaults are **English and light mode**, independent of browser preferences. Offer
persistent English/German and light/dark switches. Every action, field label and result
metric needs concise translated help via accessible hover/focus tooltips. The About page
names Marcel Petrick as author, explains the research purpose, links to the canonical GitHub
repository for forks/issues/contributions with translated help, and lists used libraries,
installed versions and license information. UI text is translated; generated research
reports remain English until separately specified.

Use synthetic studies for browser tests and screenshots. Never commit patient images or
rendered slices of real CT studies. Screenshots of the code-generated synthetic phantom
(`scripts/capture_screenshots.py` → `docs/assets/`) are allowed (2026-10-16, consistent
with DATA_POLICY.md, which bans renders and screenshots of real studies). Test the complete
demo → viewer → analysis → result/download flow,
keyboard help, preference persistence and both UI languages/themes with Playwright.
Show live elapsed request time separately from recorded engine-stage timings. Recommended-
model comparison is opt-in and sequential, preserves partial failures/abstentions/skips,
and never equates cross-model scores or agreement with accuracy. Test with mocked models.
Show rough wait estimates as workstation guesses or local request-history estimates, never
as measured inference progress, benchmark latency or guaranteed deadlines. Persist only
numeric durations keyed by model/image count. Model downloads are explicit configured-tag
Ollama pulls after terms acknowledgement. Show current-layer bytes accurately. Keep HTTP
services and gated weights on a manual provider-approved setup path; never bypass access.
Offer direct new-tab HTML review beside downloads for completed and abstained/partial
outputs. Reuse registered, guarded result URLs; inline disposition applies only to HTML.
Keep application CSP strict and allow embedded image/style content only under the report's
script/network-blocking policy. Distinguish deterministic Input QC, model image assessment
and usable-reading status; preserve per-call truncation diagnostics without recovering
incomplete findings. Configured comparisons start with detector/heuristic baselines and
use the explicit Qwen no-think control; availability is not a quality recommendation.
Offer self-contained HTML exports with embedded previews and experimental findings. Use
actual prepared model images; label heuristic source-slice previews as illustrations. Model
image numbers follow one-based captions; heuristic source slice indices are zero-based.
Never invent finding-to-image associations when evidence is absent or invalid. HTML must
escape model text, work offline, and remain under ignored `data/results/`; validate
export destinations before inference and recheck download paths against symlink escapes.
Model failures/abstentions must remain explicit; never present smoke tests as accuracy
benchmarks. Create development/sealed splits before real-study indexing or analysis.

A possible **40 GB VRAM runner and LAN inference** is documentation-only for tomorrow.
Keep the current loopback endpoint guard intact; implementation and remote verification
follow the proposed design in `docs/lan-runner.md` when resumed.

## 1. Non-negotiables

1. **Research use only.** Never add text, UI, or output that claims clinical validity,
   diagnosis, treatment suitability, or medical-device status (Vision §28). Every
   user-facing output carries the research-only disclaimer, identifies this as a self-made
   experimental tool, and states that findings may be incorrect, incomplete or misleading
   and are not professional medical advice or a basis for diagnosis/treatment decisions.
2. **No medical data in Git.** DICOM, NIfTI, rendered slices of real studies, model weights,
   archives and secrets never get committed. `scripts/check_no_medical_data.sh` enforces this in the
   pipeline. Raw data lives in `data/` (git-ignored, 10 GB budget).
3. **The sealed split stays sealed.** The 20 % sealed-validation patients
   (`data/sealed/`, hash-only manifest in `manifests/splits/`) must never be read by
   development, prompt tuning, calibration fitting, threshold fitting or tests. Only
   a future `thoraxbench benchmark --unseal` workflow with a *frozen* experiment config
   may touch them. `thoraxbench benchmark` exists and reads development cases only;
   `--unseal` is not implemented and is refused (exit status 2).
   Never weaken `thoraxbench.splits.guard`.
4. **License gate first.** No acquisition code may run for a dataset whose registry status
   (`configs/datasets/*.yaml`) is not `approved*`. Never inherit a license from another
   collection on the same host.
5. **Local only.** Inference goes to local endpoints (Ollama, local HTTP services). Never
   add a cloud inference call or any telemetry.

## 2. Workflow

1. Work directly on `main`.
2. Make one logical change.
3. Update `README.md`, `AGENTS.md` and `docs/plan.md` in the same change when their content
   is affected. Keep `manual.html` and `manual.pdf` synchronized with user-facing behavior.
4. Update *Current activity* and the work-package status in `docs/plan.md`.
5. Re-read the complete diff.
6. Check the design against `Vision.md` and `docs/architecture.md`.
7. Check edge cases and tests. Refine the change where needed.
8. Commit only through `scripts/commit.sh "<type>(<scope>): <message>"`.

**Checkpoint:** the commit script bumps the version, runs the full `./localPipeline.sh`,
commits only after a green gate, then pushes. The default bump is patch; use `--minor`
for a major feature. Use `--staged` to commit only staged changes; the script temporarily
stashes other work while the gate runs.

**Recovery:** if the gate fails, inspect `.pipeline/<stage>.log`, fix the cause and retry.
The script reverts its version bump and makes no commit. Never skip a stage to pass.

README badges must link to verifiable evidence. Keep dependency and coverage snapshots
current. Do not imply a publication workflow or clinical accuracy from a passing CI run.

* Conventional commit types: `feat fix docs test refactor perf build ci chore style`.
* GitHub Actions (`.github/workflows/local-pipeline.yml`) run `./localPipeline.sh`. Keep
  both green; never skip a stage to get a commit through.

### Documentation instructions

Apply the flight-manual writing style throughout repository documentation:

* Use short active sentences and consistent terms.
* Put one action in each procedural step. State prerequisites before the steps.
* Show exact current commands and their working directory.
* Give a checkpoint with the expected result and a recovery action for likely failures.
* Label planned commands and historical examples. Do not present them as current features.
* Preserve research specifications, reference tables, citations, licensing and recorded
  measurements. Rewrite instructions without turning reference material into medical advice.
* Keep limitations and the self-made-tool disclaimer visible. Do not claim formal
  Simplified Technical English compliance.

## 3. Code rules

* Python 3.14, `src/` layout, managed with `uv` (`uv sync --all-groups`; CI uv 0.13.1).
  Pin exact versions in `pyproject.toml`, including build-system requirements (Hatchling
  1.32.4). Registry dependency checks include runtime, development, build and locked transitives.
* `ruff format`, `ruff check` and `mypy --strict` must pass. No blanket `# type: ignore`
  or `noqa` without a reason in a comment.
* Every source file starts with the SPDX header:

  ```python
  # SPDX-License-Identifier: GPL-3.0-or-later
  # Copyright (C) 2026 Marcel Petrick <mail@marcelpetrick.it>
  ```

* Coverage must stay ≥ 95 % (`fail_under` in `pyproject.toml`).
* Tests: `tests/unit` (pure functions, synthetic phantoms), `tests/integration` (multiple
  modules, filesystem, mocked HTTP), `tests/e2e` (CLI end to end and web UI through
  Playwright). Tests that need a running Ollama or real data are marked `live` and are
  excluded from the pipeline.
* Tests use synthetic DICOM phantoms generated in code (`src/thoraxbench/synthetic.py`), never real
  patient data.
* Every artifact that affects results (prompt, preprocessing transform, sampling strategy,
  scoring) is versioned and hashed into the run provenance (Vision §24).
* Preserve available manifest/reference, scoring/schema and prepared-input hashes. Leave
  unavailable identity fields empty rather than inventing them. Collect direct header
  identifiers in memory for output redaction, including cached studies; never persist
  that identifier collection or claim OCR/anonymity. Keep pseudonym keys stable for guards.

## 4. Repository map

| Path | Content |
|---|---|
| `src/thoraxbench/` | the framework (CLI, dicom, preprocess, sampling, adapters, schemas, splits, scoring, calibration, reports, api/web UI) |
| `src/thoraxbench/acquisition/` | `thoraxbench acquire`: NBIA client, license/budget/split gates, manifests, checksums |
| `src/thoraxbench/benchmark/` | `thoraxbench benchmark`: experiment config, development-split runner, report |
| `src/thoraxbench/privacy.py` | DICOM header audit (`thoraxbench privacy audit`) and output path redaction |
| `src/thoraxbench/study_access.py` | shared CLI/API study-input guard |
| `src/thoraxbench/ontology/labels.yaml` | canonical label ontology with native-term mappings (packaged data) |
| `src/thoraxbench/synthetic.py` | synthetic DICOM phantoms for tests and demos |
| `configs/` | datasets registry, models, prompts (YAML) |
| `configs/experiments/` | benchmark experiment configs (E000 heuristic baseline, E001–E004 MedGemma) |
| `manifests/` | acquisition manifests, split manifests (IDs/hashes only), model manifests |
| `scripts/` | small documented helper scripts (see `scripts/README.md`) |
| `docs/` | architecture, datasets, model cards, results, reproducibility, plan, traceability |
| `SECURITY.md`, `DATA_POLICY.md` | security controls and medical-data rules |
| `data/` | **git-ignored** raw/normalized/cache/rendered/results data |

## 5. Useful commands

```bash
uv sync --all-groups                 # create/refresh .venv
./localPipeline.sh --fast            # quick gate while iterating
./localPipeline.sh                   # full gate (what CI runs)
scripts/commit.sh "feat(dicom): …"   # bump + gate + commit + push
uv run thoraxbench --help            # CLI
uv run thoraxbench acquire <id> --dry-run            # plan + budget verdict, no download
uv run thoraxbench privacy audit data/demo/mvp       # header identifiers, never values
uv run thoraxbench benchmark configs/experiments/E000_heuristic_hu_baseline.yaml --limit 2
```

Run commands from the repository root.

Current scoring treats missing confidence and uncertain presence as unavailable. Task E
reports coverage and omissions; Task G records its eligible-study denominator. Prompt
captions are one-based. Historical aggregate results retain their original definitions.

## Planned public demo recording

Follow `docs/linkedin-video-plan.md` for the two LinkedIn pilot scripts and delivery settings.
Recording and recorder implementation wait for the user's explicit trigger and a successful
readiness rehearsal. Use synthetic data only, preserve a full original take, label edited
waits, and retain genuine failures/abstentions. Verify actual prepared-image counts; anatomy
sampling can exceed `n`. Never imply clinical usefulness or model accuracy.

## Visual evidence reliability

Constrained Ollama prompts P2–P4 require valid one-based prepared-image evidence for a
positive prediction. Remove invalid/duplicate references, retain raw responses, and mark
unsupported positives unavailable before scoring. Valid numeric references are not proof
of visual correctness. Preserve P0/P1 control semantics and heuristic source-slice indices.
Use the versioned `include_cues` view parameter for heuristic-context ablations; record the
actual context sent to the model, including empty context. Never refill a deliberate
ablation with heuristic summaries in serialized analysis.

Evidence eligibility uses the shared implied presence probability at the default 0.5
cutoff, including low-confidence absent verdicts that imply a positive probability.
`include_cues` accepts only YAML booleans; null, numbers and strings are refused.

## Sanity diagnostic handover (2026-10-17)

`thoraxbench sanity` is implemented; use `docs/sanity.md`. Preserve completed diagnostic
artifacts and historical definitions. The S2 smoke is one group, not a passed full gate.
S4 selected-slab calibration results are not detection accuracy. Full S1/T2 and official
runtime parity remain open. The sanity command checkpoints each request but has no resume
option. Keep GPU runs sequential and calibration/sealed boundaries intact.

P6 uses the normal model factory through `adapters/p6.py` and the dedicated
`medgemma1.5-q4-p6` configuration. It requires exactly one prepared image and keeps
reasoning/answer calls and unavailable logprobs explicit. Do not fabricate image citations
or treat a single uniformly sampled slice as a whole-study detection result. See
`docs/p6.md`. P0–P5 remain unchanged.

Calibration fitting is opt-in through experiment `calibration` settings. Fit calibration
records only; apply to internal-test records only. Keep raw 0.5 metrics beside fitted
metrics and retain map parameters. Never reinterpret historical unknown training overlap.
