# AGENTS.md — working rules for humans and AI agents

This file is the operational contract for anyone (human or AI coding agent) changing
ThoraxBench Local. The *why* lives in [`Vision.md`](Vision.md); the *how/when* lives in
[`docs/plan.md`](docs/plan.md). If anything here conflicts with Vision.md, Vision.md wins
and this file must be fixed.

## 1. Non-negotiables

1. **Research use only.** Never add text, UI, or output that claims clinical validity,
   diagnosis, treatment suitability, or medical-device status (Vision §28). Every
   user-facing output carries the research-only disclaimer.
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
* Commit only through `scripts/commit.sh "<type>(<scope>): <message>"`. It bumps the
  version (patch by default, `--minor` for a major feature), runs `./localPipeline.sh`,
  commits only when the pipeline is green, and pushes.
* Conventional commit types: `feat fix docs test refactor perf build ci chore style`.
* GitHub Actions (`.github/workflows/local-pipeline.yml`) run `./localPipeline.sh`. Keep
  both green; never skip a stage to get a commit through.

## 3. Code rules

* Python 3.14, `src/` layout, managed with `uv` (`uv sync --all-groups`). Pin exact
  versions in `pyproject.toml`.
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
