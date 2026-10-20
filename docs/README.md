# Documentation

## Use the app

| Document | What it answers |
|---|---|
| [Operator manual](manual.html) ([PDF](manual.pdf)) | Setup, a first run, every screen, troubleshooting |
| [Opening a local DICOM folder](local-folders.md) | Path drop, paste or browse; what the loader checks |
| [Checking a real DICOM folder](wiki/Checking-a-real-DICOM-folder.md) | Run `scripts/dcom_evaluator.py` before importing; a redacted case note |
| [Full thorax review](full-review.md) | Whole-chest job, progress and remaining time, the "look here" list |
| [Nodule detector setup](detector-baseline.md) | The recommended MONAI detector: explicit weight setup and caveats |
| [Model test runs](model-test-runs-2026-10-20.md) | Why each model has its 1️⃣ / 2️⃣ / 3️⃣ fit marker |
| [Disclaimer](DISCLAIMER.md) | The full research-use statement (EN/DE) |
| [Research workflows](research-workflows.md) | CLI, model setup, cohorts, sealed holdout, benchmarks |

## Research design and evidence

| Document | Content |
|---|---|
| [Vision](Vision.md) | Research goals and intended use |
| [Architecture](architecture.md) | C4 architecture |
| [Model selection](model_selection.md) / [model cards](model_cards.md) | Which models, why, and their licenses |
| [Results](results.md) | Measured benchmark runs with config hash and limitations |
| [Benchmarking](benchmarking.md) / [reproducibility](reproducibility.md) | Running, resuming and repeating experiments |
| [Datasets](datasets.md) / [data policy](DATA_POLICY.md) | License gate, data budget, patient split, sealed holdout |
| [Calibration](calibration.md), [sanity checks](sanity.md), [P6 protocol](p6.md) | Development-only diagnostics |
| [Approach review](approach-review-2026-10-17.md) / [fine-tuning plan](fine-tuning-plan.md) | Can a small local VLM find nodules? Options and limits |
| [Vision traceability](vision_traceability.md) | Vision section → implementation and evidence |
| [UI design](ui.md), [reading practice](reading_practice.md), [LAN runner proposal](lan-runner.md) | Design notes and proposals |

## Project history

Dated reviews and status reports record what was true on that day; newer documents and the
[plan](plan.md) supersede them. Release notes are in [`releases/`](releases/).

- Status and reviews: [status 2026-10-17](status-2026-10-17.md),
  [review 2026-10-15](review-2026-10-15.md), [review 2026-10-17](review-current-2026-10-17.md),
  [local folders review](review-local-folders-2026-10-19.md),
  [UI red-team](review-ui-redteam-2026-10-19.md), [UX review](ux-review-2026-10-16.md),
  [model usage review](model-usage-review-2026-10-17.md),
  [model recovery plan](model-recovery-plan-2026-10-17.md), [MVP test](mvp-test.md)
- Maintenance: [dependency review 2026-10-17](dependency-review-2026-10-17.md),
  [dependency review 2026-10-19](dependency-review-2026-10-19.md),
  [worktree cleanup](worktree-cleanup-2026-10-19.md),
  [agent environment](agent-environment.md), [GitHub About text](github-about-2026-10-17.md)
- Media: [video delivery](video-delivery-2026-10-19.md),
  [video plan](linkedin-video-plan.md)
