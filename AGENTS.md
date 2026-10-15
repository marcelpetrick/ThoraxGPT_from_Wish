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

## 0.1 Current priority

The CLI engine and frozen pilot holdout are available. The **local UI MVP** is implemented
(2026-10-15): maintain its tested research workflow around the existing engine and keep
model-quality limitations visible. **UI feature work is frozen after v0.2.0** (fixes and
docs only). The next priority is the WP8 benchmark runner and a reference-scored development
baseline (WP11). See `docs/plan.md` → *Priority*.
Keep `manual.html` and `manual.pdf` synchronized with user-facing configuration and commands.

UI defaults are **English and light mode**, independent of browser preferences. Offer
persistent English/German and light/dark switches. Every action, field label and result
metric needs concise translated help via accessible hover/focus tooltips. The About page
names Marcel Petrick as author, explains the research purpose, and lists used libraries,
installed versions and license information. UI text is translated; generated research
reports remain English until separately specified.

Use synthetic studies for browser tests and screenshots. Do not commit patient images or
rendered CT slices. Test the complete demo → viewer → analysis → result/download flow,
keyboard help, preference persistence and both UI languages/themes with Playwright.
Show live elapsed request time separately from recorded engine-stage timings. Recommended-
model comparison is opt-in and sequential, preserves partial failures/abstentions/skips,
and never equates cross-model scores or agreement with accuracy. Test with mocked models.
Show rough wait estimates as workstation guesses or local request-history estimates, never
as measured inference progress, benchmark latency or guaranteed deadlines. Persist only
numeric durations keyed by model/image count. Model downloads are explicit configured-tag
Ollama pulls after terms acknowledgement. Show current-layer bytes accurately. Keep HTTP
services and gated weights on a manual provider-approved setup path; never bypass access.
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
2. **No medical data in Git.** DICOM, NIfTI, rendered slices, model weights, archives and
   secrets never get committed. `scripts/check_no_medical_data.sh` enforces this in the
   pipeline. Raw data lives in `data/` (git-ignored, 10 GB budget).
3. **The sealed split stays sealed.** The 20 % sealed-validation patients
   (`data/sealed/`, hash-only manifest in `manifests/splits/`) must never be read by
   development, prompt tuning, calibration fitting, threshold fitting or tests. Only
   the planned `thoraxbench benchmark --unseal` workflow with a *frozen* experiment config
   may touch them. That benchmark command is not implemented in the current MVP.
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
* Tests use synthetic DICOM phantoms generated in code (`tests/phantoms.py`), never real
  patient data.
* Every artifact that affects results (prompt, preprocessing transform, sampling strategy,
  scoring) is versioned and hashed into the run provenance (Vision §24).

## 4. Repository map

| Path | Content |
|---|---|
| `src/thoraxbench/` | the framework (CLI, ingest, dicom, preprocess, sampling, adapters, schemas, splits, scoring, calibration, reports, api/web UI) |
| `src/thoraxbench/ontology/labels.yaml` | canonical label ontology with native-term mappings (packaged data) |
| `src/thoraxbench/synthetic.py` | synthetic DICOM phantoms for tests and demos |
| `configs/` | datasets registry, models, prompts, preprocessing, experiments (YAML) |
| `manifests/` | acquisition manifests, split manifests (IDs/hashes only), model manifests |
| `scripts/` | small documented helper scripts (see `scripts/README.md`) |
| `docs/` | architecture, datasets, model cards, benchmarking, reproducibility, plan, traceability |
| `data/` | **git-ignored** raw/normalized/cache/rendered/results data |

## 5. Useful commands

```bash
uv sync --all-groups                 # create/refresh .venv
./localPipeline.sh --fast            # quick gate while iterating
./localPipeline.sh                   # full gate (what CI runs)
scripts/commit.sh "feat(dicom): …"   # bump + gate + commit + push
uv run thoraxbench --help            # CLI
```
