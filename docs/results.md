# Measured results

Research use only. This self-made tool is not professional medical advice. Its findings
may be incorrect, incomplete or misleading. Do not use them for diagnosis or treatment.

This file records measured benchmark runs. Each entry names the experiment config, its
hash, the data state and the exact command. Raw outputs stay in the git-ignored
`data/results/benchmark/<experiment-id>/` directory.

## E000 — heuristic HU pipeline baseline (2026-10-15)

**What this is.** A *pipeline baseline of a deterministic HU heuristic*. It shows that the
WP8 path works end to end: development index → guarded study load → analysis → structured
parse → reference scoring → report. It is **not model accuracy**, not a VLM result and not a
sealed-holdout result. The `heuristic-hu` control applies fixed Hounsfield-unit rules; it
has no learned component.

### Setup

| Item | Value |
|---|---|
| Experiment | `E000` — `configs/experiments/E000_heuristic_hu_baseline.yaml` |
| Config SHA-256 (file bytes) | `88b359e61cc99774b24b9a7d858bcec04c68a3951a5d0c3325b0e7b76a394918` |
| Model | `heuristic-hu` (rules version 1, view `hu_cues`); no prompt, no model hash |
| Preprocess hash | `d2dbc2164fffb6692f167a3f592a4bdd69e1715daac489ee37aa14df24f1749b` |
| Split | development only (calibration + internal_test phases); sealed holdout untouched |
| Datasets | LIDC-IDRI, NSCLC-Radiogenomics |
| Scored labels | `pulmonary_nodule`, `pulmonary_mass` (the only indexed reference labels) |
| Threshold | 0.5 for both labels (fixed, not tuned) |
| Bootstrap | 1000 patient-level resamples, seed 0, percentile 95 % CI |
| Split manifest hash (combined) | `3699677e279660aa706e728845ea7408d42b1974bc7fb9d9683640675c7d25f8` |
| Dataset manifest + index hash (combined) | `dc007f21256856fad17abba510e2e1ea9118a39dbb98c625899571a4141a0e7f` |
| Code state | `413dfaa` with uncommitted changes (`git_dirty: true`); package version 0.1.2 |
| Hardware | x86_64 CPU, no GPU; Python 3.14.7 |

Command (working directory: repository root):

```bash
.venv/bin/thoraxbench benchmark configs/experiments/E000_heuristic_hu_baseline.yaml
```

**Checkpoint:** the command prints `E000 [base]: scored 70, abstained 0, failed 0,
not_indexed 0` and writes `data/results/benchmark/E000/result.json` and `report.md`.

**Index state.** Both development indexes were rebuilt with `thoraxbench index lidc_idri`
and `thoraxbench index nsclc_radiogenomics` immediately before the run (about 10 minutes).
Before the rebuild, the LIDC-IDRI index held 1 of 48 development cases. The previous
NSCLC-Radiogenomics index held 5 entries that are not in the frozen development split. The
runner ignores such entries by design (counted, never opened, never scored); after the
rebuild the count is 0.

### Case counts

| Dataset | Development cases | Scored | Abstained | Failed | Not indexed |
|---|---:|---:|---:|---:|---:|
| LIDC-IDRI | 48 | 48 | 0 | 0 | 0 |
| NSCLC-Radiogenomics | 22 | 22 | 0 | 0 | 0 |
| **Total** | **70** | **70** | **0** | **0** | **0** |

By phase: calibration 56, internal_test 14. No failure or abstention occurred. Because an
inadequate study forces an abstention, zero abstentions also means every study passed
quality control.

Reference labels per label (unknown labels are excluded per label):

| Label | Known | Positive | Negative | Unknown |
|---|---:|---:|---:|---:|
| `pulmonary_nodule` | 54 | 38 (LIDC 32, NSCLC 6) | 16 (LIDC) | 16 (NSCLC mass cases) |
| `pulmonary_mass` | 64 | 17 (LIDC 1, NSCLC 16) | 47 (LIDC) | 6 (NSCLC nodule cases) |

### Task A — study-level labels

| Label | n | AUROC (95 % CI) | Sensitivity (95 % CI) | Specificity (95 % CI) | F1 (95 % CI) | PPV | NPV | TP/FP/TN/FN |
|---|---:|---|---|---|---|---:|---:|---|
| `pulmonary_nodule` | 54 | 0.524 [0.422, 0.647] | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | 0.826 [0.729, 0.898] | 0.704 | n/a | 38/16/0/0 |
| `pulmonary_mass` | 64 | 0.500 [0.500, 0.500] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.000 [0.000, 0.000] | n/a | 0.734 | 0/0/47/17 |

Macro F1 0.413, micro F1 0.697, macro AUROC 0.512. Sensitivity at specificity 0.80, 0.90
and 0.95 is 0.0 for both labels.

### Task B, E and G

| Label | Brier | ECE | NLL |
|---|---:|---:|---:|
| `pulmonary_nodule` | 0.268 | 0.247 | 0.909 |
| `pulmonary_mass` | 0.208 | 0.116 | 0.623 |

* Raw rule scores; no calibrator was fitted. The case phase is stored per case for a later
  calibration-phase fit.
* Factuality: label agreement 0.720 (85 agreements, 33 contradictions, 16 hallucinated
  positives, 0 omissions over 118 known reference labels).
* Abstention rate 0.000; high-confidence error rate 0.302 (53 decisions); false reassurance
  rate 0.296; fabricated-measurement rate 0.229 (16 of 70 reported sizes on
  reference-negative studies).
* Task C (lesion localisation) is not scored: the heuristic reports slice indices, not
  millimetre lesion centres.

### Runtime

Total wall time 87.1 s for 70 studies on CPU. Rule evaluation and parsing took 4.5 s; the
rest is guarded DICOM loading. The index rebuild (cue extraction) took about 10 minutes and
is not part of the benchmark runtime.

### Interpretation and limitations

* The rules flag `pulmonary_nodule` as present in **all 70 studies** (dense candidates of
  3–30 mm; these probably include vessels and other dense structures) and
  `pulmonary_mass` in **none**. The nodule sensitivity of 1.0 is therefore a
  constant-positive artefact; specificity is 0.0. AUROC near 0.5 for both labels shows that
  the rule scores do not rank cases usefully.
* Reference labels are nearly single-class per dataset: NSCLC-Radiogenomics has no
  negatives, and LIDC-IDRI provides the only nodule negatives (16) and one mass positive.
  Degenerate bootstrap intervals such as [1.000, 1.000] reflect this, not precision.
* 70 development cases from two collections are a small sample. Results do not transfer to
  other scanners, populations or labels.
* The run used uncommitted code (`git_dirty: true`); the config hash and provenance
  fingerprint identify the setup, the commit alone does not.
* This baseline is the reference point that VLM runs (E001–E004, MedGemma via local Ollama)
  must be compared against through the same runner. No VLM was run: Ollama was not reachable.
* This baseline is numbered E000 so that E001–E004 keep the Vision §26 numbering. E001
  (MedGemma Q4/Q8/BF16 quantization) is configured but not run.
