# Measured results

Research use only. This self-made tool is not professional medical advice. Its findings
may be incorrect, incomplete or misleading. Do not use them for diagnosis or treatment.

This file records measured benchmark runs. Each entry names the experiment config, its
hash, the data state and the exact command. Run artifacts stay in the git-ignored
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

## E001-smoke — calibration-only MedGemma readiness (2026-10-16)

**Outcome:** Q4 returned no label predictions on both studies. Q8 produced one scorable
response that missed the reference nodule, then reached the generation limit on the other
study. This is a limited readiness check, not the full E001 experiment, an accuracy
estimate, or evidence that either model is suitable for clinical use.

### Reproduce the setup

Prerequisites: frozen splits and development indexes exist. Local Ollama has the configured
Q4 and Q8 tags. Start in the repository root.

```bash
uv run thoraxbench benchmark configs/experiments/E001_calibration_smoke.yaml --limit 1
```

**Checkpoint:** four model/case outcomes, two variants, and a new unique result directory.
Inspect failures and abstentions before considering larger sweeps. Previous runs stay intact.

| Setup | Recorded value |
|---|---|
| Source | v0.3.8, commit `3af797f72c53c51a31fc817f81c6cb17eabb653f`, `git_dirty: false` |
| Experiment | `E001-smoke`, distinct from the full 32-slice E001 |
| Config SHA-256 | `9349919a6437c91c9b073097f50b026f2ee9caa487f4765403b62d05724f3c85` |
| Selection | First calibration case in frozen split order from each of LIDC-IDRI and NSCLC-Radiogenomics; 2 studies total |
| Requested/scored labels | `pulmonary_nodule`, `pulmonary_mass` |
| Inputs | Anatomy sampling, 4 axial images at 256 pixels, MedGemma RGB view, no coronal input |
| Prompt | P3; SHA-256 `c41bb11f1ef993ca3a92708428b9f2f455c7d5b7d5388e1bb3eae2d3485ab179` |
| Preprocess hash | `140e42d77cc37b18e7ac903bf09ce937b1e38588b85fbc4808e274413e42dc5e` |
| Q4 model digest | `433252621ab154668b5d8be6aff6c1b771bacba045e46e6193da8d6ad1630f2c` |
| Q8 model digest | `d6ae3cddb6633585549af18435fd19eb9bfecb886d14006f160bee33621ab95a` |
| Hardware | NVIDIA RTX A2000 8 GB laptop GPU; driver 610.57.04; Python 3.14.7 |
| Bootstrap | Disabled (`n_boot: 0`); no confidence intervals |
| Total experiment wall time | 290.8 s |

Both indexes contained only development entries (48 LIDC and 22 NSCLC), with zero missing
selected cases. Dataset, index and split hashes are in the local result. The current run
used calibration cases only; it did not open the sealed holdout or the internal test set.

### Observed outcomes

| Variant | Scored | Abstained | Failed status | Variant wall time, excluding study loading | Reason |
|---|---:|---:|---:|---:|---|
| Q4 | 0 | 2 | 0 | 57.4 s | Both: `no label predictions returned` |
| Q8 | 1 | 1 | 0 | 227.2 s | LIDC parsed/scored; NSCLC: `generation token limit reached` |

The runner currently categorizes generation-limit errors as abstentions. A zero `failed`
count therefore does not mean every inference produced usable predictions. Variant time
includes analysis and provenance collection, but excludes study loading. Engine-stage
totals were 57.1 s for Q4 and 227.0 s for Q8. Total experiment time also includes loading,
selection and scoring; these timings do not establish a quantization speed ranking.

In Q8's one scorable response, both requested presence scores were 0.0. The reference
nodule was missed (one false negative); the absent mass was correctly negative (one true
negative). Several natural-language negative-finding terms were ignored with parser
warnings. Q4 supplied no decisions to score. AUROC is undefined: each label has at most
one scored reference class. The NSCLC mass reference was unknown and was not scored.

### Saved evidence and next action

The local JSON and Markdown files are under:

```text
data/results/benchmark/E001-smoke/
  20261016T071937.440984Z-9349919a6437-d5ba670f73444f77a7bc7d0068840d12/
    result.json
    report.md
```

These files contain development identifiers and stay outside Git. This aggregate record
contains no case identifiers or images. The runner currently saves score fields, warnings
and fingerprints; it does not retain complete per-case raw responses and has no incremental
checkpoint. Add durable raw-response/provenance artifacts before larger model sweeps.

Inspect output/schema reliability and image coverage on calibration data before launching
the full E001–E004 experiments. Four sampled images can omit study-level lesions. This
two-study sample cannot assess generalization, compare quantization accuracy, or establish
clinical performance. This run did not assess pretraining overlap.

## Method-change note (2026-10-16)

The historical E000 and E001-smoke tables above retain their original scoring definitions
and saved values. They have not been recomputed with later code. In the current engine,
missing confidence or uncertain presence is unavailable, not an invented probability of
0, 0.5 or 1. Task E counts missing known-reference predictions as omissions and reports
prediction coverage. Task G reports the number of studies eligible for false-reassurance
scoring; unavailable predictions cannot establish reassurance. Current provenance records
identify the scoring implementation by its source hash.

Current prompt rendering uses one-based image captions consistently. P0–P3 are version
1.0.1 and P4 is 1.0.2. Their hashes differ from the smoke setup above. Old aggregate-only
runs do not contain enough raw provider evidence to reconstruct their failures in detail.
Use the new durable per-case artifacts for future diagnostics. Do not describe old results
as measurements of these revised methods or compare them as controlled before/after runs.

## Q4/P2 calibration diagnostic — output inspection (2026-10-16)

This is a two-case readiness diagnostic, not an accuracy benchmark. No sealed or internal-test
case was used. Code was clean v0.3.13 (`ec929c4`). The installed Q4 digest was
`433252621ab154668b5d8be6aff6c1b771bacba045e46e6193da8d6ad1630f2c`.

Command from the repository root, using the historical configuration bytes at that commit:

```bash
uv run thoraxbench benchmark configs/experiments/E001_calibration_diagnostic.yaml --limit 1
```

| Item | Observed result |
|---|---|
| Config SHA-256 | `33c76f8327ca73b188afaf32ca9599262442c43c7cd6230b30dec535560e0d07` |
| Setup | Q4, P2, 256 px, anatomy sampling, `n: 2`, no coronal |
| Actual inputs | **Nine images per case**: anatomy retains landmarks beyond its fill target |
| Cases | One calibration case per dataset; two scored, zero abstained/failed/not-indexed |
| Active wall time | 99.0 s, including input hashing/loading |
| Provider HTTP request time | 50.3 s and 37.2 s; one response per case |
| Known-reference prediction coverage | 2 of 3 (66.7%); one omission |
| Label output | Both reference-positive nodules predicted positive at confidence 1.0; no usable known-negative mass prediction |
| Evidence validity | Both outputs used source-slice numbers outside the nine prepared-image captions |

Both responses repeated nodule-candidate descriptions from the deterministic heuristic
context. Those are not independent visual detections or validated lesion measurements.
The displayed confidence 1.0 is not calibrated. There are no negative nodule examples,
AUROC is undefined, and the perfect F1 over the two available nodule predictions does not
establish useful detection performance. Current rendering must continue refusing invalid
finding-to-image associations. No full E001–E004 sweep is justified by this result.

The complete requests, decoded provider responses, parsed reports and provenance were
checkpointed under ignored `data/results/benchmark/E001-diagnostic/`. Nothing from the
case artifacts is published here beyond aggregate observations. Existing artifact bytes
remain unchanged.

**Configuration correction:** the current diagnostic uses `uniform` with `n: 2` to request
a strict small axial selection. Its hash differs from this historical run. It has not run
live yet. Recheck actual prepared inputs before the next calibration diagnostic. This
configuration change does not isolate the effects of prompt, sampling, input count or
heuristic context.

## Corrected uniform two-image diagnostic (2026-10-16)

A clean isolated checkout of v0.3.15 (`c509525`) ran the corrected configuration with
`--limit 1`, using the same local Q4 digest recorded above. Configuration SHA-256:
`ef5c47faaa4ac848f41f77a023681d51a1c49b07185ed775893cfadd9137b405`.

| Observation | Result |
|---|---|
| Actual prepared images | Two per case, uniform sampling, 256 px, no coronal |
| Cases | One calibration case per dataset; two scored, no abstentions/failures/not-indexed |
| Active wall time | 49.6 s |
| Provider request time | 20.0 s and 21.9 s |
| Known-reference coverage | 2/3; the known-negative mass label was unavailable |
| Evidence | Both positive outputs cited source-slice numbers outside the two attached images |
| Heuristic context | Both copied deterministic nodule-candidate text and precise sizes |

The run confirms actual image-count control, not visual detection reliability. These
responses were recorded before the new evidence validation: their historical scored status
and outputs are unchanged. Under the new constrained-positive guard, the unsupported
positives would be unavailable. Do not recompute or relabel the old artifacts in place.

The isolated checkout used the shared ignored data directory through `THORAXBENCH_DATA_DIR`
and this checkout's locked Python environment. It did not read internal-test or sealed
cases. Complete requests/responses/provenance remain under ignored E001-diagnostic outputs.
The next bounded check holds images fixed and changes only heuristic prompt context.

## E001-cue-ablation — heuristic-context ablation (2026-10-16)

This is a two-case, two-variant readiness diagnostic, not an accuracy benchmark. An
isolated clean checkout of v0.3.16 (`5c16ba1`, not dirty) ran it with `--limit 1`. It used
one calibration case per dataset. No internal-test or sealed case was read.

```bash
uv run thoraxbench benchmark configs/experiments/E001_cue_ablation.yaml --limit 1
```

| Item | Observed result |
|---|---|
| Config SHA-256 | `9d8f5a8e24533c056750c70a867e261e65761ffff5977b7075b34441571868a2` |
| Setup | Q4 (`433252621ab1…`), P2 1.0.2 (`f5741b3999c9…`), anatomy target `n: 9`, 256 px, no coronal |
| Actual inputs | Nine axial images per case in both variants |
| Variants | `with_cues` (HU summary in context) and `without_cues` (empty context) |
| Case outcomes | 4/4 abstained; 0 scored, 0 failed |
| Provider requests | 39.0 s and 72.1 s with cues; 49.7 s and 74.3 s without cues |
| Total experiment wall time | 241.3 s |
| Stop reason | `done_reason: stop` for all four; 129–149 generated tokens; no truncation |
| Prompt tokens | 3936–3942 with cues; 3757 without cues |

All four responses were schema-valid JSON. Every requested label had `"present": null`
with `"confidence": 0.0` and no evidence images. Three of four responses set
`study_quality.adequate: false` ("The study is inadequate." or "Incomplete coverage of the
apex"). The descriptions often said "No evidence of … in the images" while the verdict
stayed `null`. Both reference cases are nodule-positive, so the model returned no
usable decision on a known-positive label in either variant.

Removing heuristic context removed copied candidate text, but it did not produce a
visual decision. The P2 rule "use null when visibility is insufficient" plus 256-pixel
images is a likely cause. This run cannot separate those effects. A later geometric check
(E001-coverage below) shows that the anatomy setting places reference lesions on an
attached image for only about a quarter of calibration LIDC lesions. In the LIDC case of
this run, four of seven reference lesions intersected an attached slice under the
spherical approximation, yet the model still returned `null`.

The case artifacts, requests and responses stay under ignored
`data/results/benchmark/E001-cue-ablation/`.

## E001-coverage — reference-lesion coverage of sampled inputs (2026-10-16)

This measurement uses no model and reads no DICOM pixels. It uses the development index
geometry (slice count, spacing, cached HU cues and LIDC reader-XML consensus lesions
≥3 mm) of the **38 LIDC calibration patients** only. `CaseGuard` selects the calibration
phase; other index entries are skipped before validation. It runs the same strategy code
and slab arithmetic as the image view. The anatomy indices it computes reproduced the
nine slices of the E001-cue-ablation run.

```bash
uv run thoraxbench coverage lidc_idri --output data/results/coverage/E001-coverage-lidc-calibration.json
```

Definitions:

* **Lesion covered:** the lesion's z-extent (centre ± diameter/2) intersects at least one
  prepared slice or MIP slab. **Centre covered:** a prepared image contains the centre slice.
* **Max rendered slab:** thickest slab actually rendered, after rounding to whole slices.
  A nominal 10 mm slab renders as 15 mm on 3 mm volumes.
* **Prompt tokens:** estimate = 1000 + 325 × images, from measured P2 prompt counts
  (1522 tokens with 2 images, 3779 with 9). **Fits:** estimate + 1024 generation tokens
  ≤ `num_ctx` 16384.
* 51 reference lesions (43 ≥6 mm) in 24 nodule-positive calibration studies.

Selected rows (the full 70-row table is in the ignored JSON):

| Setting | Images (mean/max) | Max rendered slab | Est. tokens | Lesions covered | Centre covered | Positive studies covered |
|---|---:|---:|---:|---:|---:|---:|
| `uniform`, n 2 (E001-diagnostic) | 2/2 | 3 mm | 1650 | 0/51 (0.0%) | 0/51 | 0/24 |
| `anatomy`, n 9 (E001-cue-ablation) | 9/9 | 3 mm | 3925 | 13/51 (25.5%) | 5/51 | 9/24 |
| `uniform`, n 9, 10 mm slab | 9/9 | 15 mm | 3925 | 30/51 (58.8%) | 19/51 | 17/24 |
| `mip_slabs`, n 9 (auto-widened slabs) | 9/9 | 42.5 mm | 3925 | 51/51 (100%) | 50/51 | 24/24 |
| `lung_extent`, n 16, 5 mm slab | 16/16 | 9 mm | 6200 | 41/51 (80.4%) | 25/51 | 21/24 |
| `lung_extent`, n 16, 10 mm slab | 16/16 | 15 mm | 6200 | 50/51 (98.0%) | 39/51 | 23/24 |
| `lung_extent`, n 24, no slab | 24/24 | 3 mm | 8800 | 41/51 (80.4%) | 11/51 | 20/24 |
| **`lung_extent`, n 24, 5 mm slab** | 24/24 | 9 mm | 8800 | **49/51 (96.1%)** | 36/51 | 23/24 |
| `anatomy`, n 24, 5 mm slab | 24/24 | 9 mm | 8800 | 46/51 (90.2%) | 37/51 | 21/24 |
| `lung_extent`, n 24, 10 mm slab | 24/24 | 15 mm | 8800 | 51/51 (100%) | 49/51 | 24/24 |
| `mip_slabs`, n 32, 10 mm | 28.6/32 | 15 mm | 11400 | 51/51 (100%) | 51/51 | 24/24 |
| `uniform`, n 48, no slab | 48/48 | 3 mm | 16600 (does not fit) | 48/51 (94.1%) | 22/51 | 24/24 |

**Pick:** the smallest setting with ≥90 % lesion coverage that fits the context and keeps
rendered slabs ≤12.5 mm is `lung_extent`, n 24, 5 mm view slab (96.1 %). If 15 mm
rendered slabs are acceptable, `lung_extent`, n 16, 10 mm slab reaches 98.0 % with
fewer images.

Interpretation:

* All earlier MedGemma diagnostics showed the model few or no reference lesions.
  `uniform` with n 2 selects the first and last slice of the volume and covered **no**
  calibration lesion. Their abstentions and misses say nothing about visual detection.
* Wide auto-widened MIP slabs reach 100 % geometrically, but a 25–40 mm MIP can hide a
  small nodule among vessels. Coverage is necessary, not sufficient, for visibility.
* The z-extent is a spherical approximation of reader contours. NSCLC tumour masks are
  not included. These are aggregate geometric counts, not model results.
