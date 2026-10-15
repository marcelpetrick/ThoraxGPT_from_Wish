# AGENTS.md — working rules for humans and AI agents

This file is the operational contract for anyone (human or AI coding agent) changing
ThoraxBench Local. The *why* lives in [`Vision.md`](Vision.md); the *how/when* lives in
[`docs/plan.md`](docs/plan.md). If anything here conflicts with Vision.md, Vision.md wins
and this file must be fixed.

## 0. Resuming work

A new session/agent starts by reading `docs/plan.md` (*Current activity* and *Next steps*),
then `git log --oneline | head -20` and `git status`. Everything needed to continue is in the
repository; nothing important may live only in a chat or a temp directory.

## 0.1 Current priority

The CLI engine and frozen pilot holdout are available. The **local UI MVP** is implemented
(2026-10-15): maintain its tested research workflow around the existing engine and keep
model-quality limitations visible. Benchmark and advanced review work remain open.
See `docs/plan.md` → *Priority*.
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
   `thoraxbench benchmark --unseal` with a *frozen* experiment config may touch them.
   Never weaken `thoraxbench.splits.guard`.
4. **License gate first.** No acquisition code may run for a dataset whose registry status
   (`configs/datasets/*.yaml`) is not `approved*`. Never inherit a license from another
   collection on the same host.
5. **Local only.** Inference goes to local endpoints (Ollama, local HTTP services). Never
   add a cloud inference call or any telemetry.

## 2. Workflow

* Work directly on `main`. One logical change per commit (atomic).
* Commit only through `scripts/commit.sh "<type>(<scope>): <message>"` (add `--staged` to
  commit just the staged hunks; the rest is stashed while the gate runs). It bumps the
  version (patch by default, `--minor` for a major feature), runs `./localPipeline.sh`,
  commits only when the pipeline is green, and pushes.
* README badges link to verifiable evidence. Keep dependency/coverage snapshots current;
  do not imply a release workflow or clinical accuracy from CI status.
* **Living docs:** `README.md`, `AGENTS.md` and `docs/plan.md` are updated *in the same
  commit* as any change that affects what they describe (features, commands, scripts,
  pipeline stages, status of work packages). A commit that leaves them stale is incomplete.
* **Plan log:** `docs/plan.md` → *Current activity* names what is being worked on right now
  and is updated with every commit; the work-package table status (✅ 🔄 ⏳ ✖) too.
* **Review before every commit:** re-read the diff, reconsider the design against
  Vision.md and `docs/architecture.md`, check edge cases and tests, refine, *then* commit.
* Conventional commit types: `feat fix docs test refactor perf build ci chore style`.
* GitHub Actions (`.github/workflows/local-pipeline.yml`) run `./localPipeline.sh`. Keep
  both green; never skip a stage to get a commit through.

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
