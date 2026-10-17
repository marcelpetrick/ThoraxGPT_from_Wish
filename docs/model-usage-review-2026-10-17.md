# Useful-output review — 2026-10-17

Research use only. This self-made experimental tool may produce incorrect, incomplete or
misleading findings. It is not professional medical advice or a basis for diagnosis or treatment.

## Decision

Use the optional supervised MONAI detector to propose reviewable locations. Keep MedGemma
experimental. Do not let its current answers discard detector candidates or claim that a
study is negative. The detector → candidate table → source slice → offline HTML workflow
is implemented. VLM verification is gated, not silently substituted with heuristic text.

## What was wrong, and what remains unknown

| Question | Verified finding | Action |
|---|---|---|
| Did the model receive the relevant anatomy? | Early sparse sampling covered only 0–26% of indexed nodules. The revised coverage check reaches 96.1%. | Preserve actual image counts and prepared-input hashes. Coverage is not recognition. |
| Were the HU windows wrong? | Our MedGemma RGB channels already match Google's executable CT example: −1024…1024, −135…215 and 0…80 HU. | Keep rescaling and provenance. Window changes alone have not solved the failure. |
| Is our runtime identical to the official example? | No. Our Ollama GGUF Q4/Q8 runtime and image/message layout differ from Hugging Face BF16 and its multimodal chat processor. | Do not claim runtime parity. Official BF16 parity remains open; gated access is not bypassed. |
| Does multi-image citation binding work? | Q4 T2: interleaved 5/20 and single-message 1/20 correct; both fail the predeclared 18/20 gate. | P6 requires exactly one image. Numeric citations alone do not prove correct visual evidence. |
| Does one focused question fix categorical output? | No. P6 sphere/control checks below remain constant-positive. | Keep both calls and abstentions; do not enable candidate filtering. |
| Are images entirely ignored? | Not established. Earlier 40 paired-slab runs show score discrimination despite poor categorical behavior. | Separate score signal, categorical readiness and localization. Avoid a causal claim unsupported by tests. |

Google's [official CT notebook](https://github.com/Google-Health/medgemma/blob/main/notebooks/high_dimensional_ct_hugging_face.ipynb)
uses uniformly selected raw axial images (up to 85), image/`SLICE k` interleaving in one
user message, a focused condition query, and a short argument ending in `Final Answer`.
Its example uses greedy Hugging Face generation with a 2000-token limit. It is not a
validated lung-nodule detector recipe. Our earlier multi-label strict JSON, MIP/slab views
and Ollama message layout were application choices, not an exact reproduction.

MedGemma is Google's medical adaptation of Gemma 3; local GGUF packaging is a separate
runtime conversion. Check the exact configured source, tag, digest and terms rather than
attributing third-party packaging to Google. See the [official model card](https://huggingface.co/google/medgemma-1.5-4b-it).

A visual token budget can motivate crops, but it does not impose a hard physical minimum
lesion size: features may encode structures smaller than a nominal token footprint.
Neither quantization nor a broken projector has been isolated as the cause.

## Actual local runs

All real studies below were checked against the calibration split before access. Internal
test and sealed patients were not used. Scores and cutoffs were not fitted on these cases.

| Run | Wall time | Outcome | Interpretation |
|---|---:|---|---|
| E013 detector, one positive calibration study per dataset | 77.31 s | At existing 0.5 score cutoff: LIDC 8 candidates / 7 matched references; NSCLC 2 / 1 | Eight indexed references matched; two unmatched proposals. LIDC training overlap is **yes**. |
| Detector, annotation-negative LIDC calibration control | 27.92 s | One proposal at 0.5; four at candidate floor 0.02 | Unmatched is not an adjudicated false positive. Sparse/unmarked findings remain possible. |
| Combined three-study detector check | Separate invocations | 11 proposals at 0.5: 8 matched, 3 unmatched | A small reviewability check, not unbiased accuracy. No references below 6 mm in the positive pair. |
| Q4 S2, 30 mm synthetic sphere vs control, ten each | 71.1 s | 0/10 positive answers, 10/10 control-negative answers | Categorical readiness fails despite score separation. |
| Q4 T2, two layouts, twenty permutations each | 812.0 s | 5/20 and 1/20 correct | Multi-image binding fails. |
| P6, one 30 mm synthetic sphere/control pair, two windows | 10.81 s | All four answers yes; conditional P(yes) 0.978–0.990 | Both window gates fail; one pair cannot estimate generalization. |

P6 MedGemma-RGB control/sphere scores were 0.98957/0.98724; lung-window scores were
0.97754/0.98320. The extraction call sees only the first call's argument. Its probability
is conditional on that text, not an independent visual assessment or calibrated certainty.
The P6 probe records a dirty integration checkout plus exact source/configuration hashes;
it is not a clean-release benchmark. T2's startup manifest likewise records its actual
source/configuration identity; later edits do not turn it into a P6 run.

The detector positive pair produced 27 candidates at its 0.02 proposal floor, eight matched
references and nineteen unmatched. The fixed 0.5 cutoff gives a more manageable review
list, but is not a validated clinical threshold. Approximate project lesion matching uses
`max(reference diameter / 2, 5 mm)`; it is not the official LUNA16 challenge scorer.
The pinned weights SHA-256 is
`b5e79231466adae93a6fe8e8594029e9add142914e223b879aa0343bb2402d01`.
Peak recorded CUDA allocation was about 1.46 GiB (reservation 1.58 GiB); the positive
studies took about 31 and 36 seconds in the inference stage on this 8 GB workstation.
Adapted SciPy resampling and the configured ROI do not establish upstream preprocessing parity.

Local artifacts remain under ignored `data/results/benchmark/E013-luna16-bundle/` and
`data/results/detector-review/`. The latter contains `lidc_idri.html`,
`nsclc_radiogenomics.html` and `negative-control.html` in the timestamped invocation
folder, with embedded candidate illustrations and matching text. No patient pixels or
identifiers are included in this document or Git.

## Reproduce the useful path

Prerequisites: repository root, approved development index and split, pinned detector
weights explicitly acquired after terms review. See [detector setup](detector-baseline.md).

```bash
uv run --extra detector python scripts/fetch_monai_bundle.py --verify
uv run --extra detector thoraxbench serve
```

Open the printed loopback URL. Select a development study and `monai-lung-nodule`. Run
analysis. Review the sourced candidate table and use “Show source slice”. Download the
self-contained HTML report. Keep one GPU job active; use the shared Jobs panel to stop.
The default candidate floor includes low-score proposals. Inspect scores instead of treating
every candidate as an established finding.

For a bounded calibration benchmark:

```bash
uv run --extra detector thoraxbench benchmark configs/experiments/E013_luna16_bundle.yaml --limit 1
```

For the synthetic P6 diagnostic, with the configured model already installed:

```bash
uv run python scripts/probe_p6.py --window both
```

Checkpoint: the detector produces millimetre locations, source labels and reviewable crops;
P6 preserves failures rather than manufacturing evidence. Each diagnostic creates its own
ignored output folder. Never use the sealed split to tune this workflow.

## Remaining scientific work

Extend the completed bounded S1/S3 controls to real calibration examples and, if approved
weights become available, perform official BF16 runtime parity. Require nonconstant calibrated-case answers and defensible visual evidence
before enabling VLM crop verification. A useful detector reference baseline is available
now; a reliable MedGemma verifier is not. Broader sweeps, QLoRA and LAN inference remain
on hold. The current RQ1 answer is limited to this runtime, these tasks and these calibration
checks; it is not a verdict on every medical foundation model.

## Bounded follow-up and RQ1 interim answer

Clean commit `76927e9` (v0.4.8) completed S1 in 132.6 s: fourteen requests, all categorical
answers no, across sphere/control and real/grey/noise/no-image conditions. Actual nonempty
inputs each contained four images. Scores varied; constant answers do not establish an
ignored image path. A summary grouping bug combined sphere/control records within the
same phantom pair. The raw fourteen records were preserved. The fix groups perturbations
by source input key; a regression test keeps both sources separate. Corrected post-hoc
aggregation has four source/layout rows under ignored `data/results/sanity-review/` and
records the original result and aggregation source hashes. The original artifact is unchanged.

S3 `--limit 1` completed twelve single-image descriptions in 118.4 s on the same clean
commit: a matched synthetic sphere/control pair, two windows and three models. Q4 correctly
described chest/lung/nodule for the sphere in RGB, but described the lung-window sphere as
an abdomen with no abnormality. Q8 also misidentified anatomy and hallucinated findings on
controls. Qwen called the phantom a symbolic graphic. These are qualitative synthetic
observations, not validated description scores or evidence for real-study accuracy.

This motivated one separately recorded P6 full-field check at the known synthetic target
plane with 5 mm MIP context. It took 24.07 s; all four answers were again yes. RGB
control/sphere scores were 0.96059/0.98022. Both categorical gates failed. Its identity
records a dirty diagnostic checkout and exact source/script hashes. No thresholds were
chosen from these pairs. The new script options allow reproduction:

```bash
uv run python scripts/probe_p6.py --view full --slab-mm 5 --window both
```

**RQ1 interim answer:** useful study-level MedGemma CT accuracy has not been established.
Output coverage and JSON reliability improved, but categorical decisions and visual binding
remain unreliable on these bounded checks. Some image-dependent signal exists, so a blanket
claim that MedGemma cannot see CT is unsupported. The supervised detector provides usable
research candidate review now, with its training overlap and sparse-reference limits.
Official-runtime parity, real candidate verification and sealed evaluation remain open.

## Real GUI job API verification — 2026-10-17

Clean commit `981e1ec` (v0.4.9) completed one existing LIDC calibration study through
`POST /api/jobs`, model `monai-lung-nodule`. Polling reached `succeeded`; the report did
not abstain and recorded no raw error. End-to-end client wall time, including polling
and HTML download, was **40.93 s**. This repeats an earlier calibration study; it does
not increase the independent study count or establish accuracy. LIDC training overlap
remains **yes**. Browser tests and screenshots still use synthetic studies only.

| Check | Recorded result |
|---|---|
| Candidate source | All nineteen candidates labelled detector |
| Existing 0.5 cutoff | Eight candidates; no threshold fitting |
| Previews | First twelve candidates, axial/coronal illustrations |
| Offline download | HTTP 200, 616855 bytes, embedded PNG pixels present |
| Environment | ThoraxBench 0.4.9, PyTorch 2.14.1, MONAI 1.6.1; CUDA and detector availability true |
| Pinned bundle | All five files passed size/SHA-256 verification; no download during inference |

The local saved run is `data/results/ui/7747a176-39c1-43d4-8fb9-c45329998929/`.
`result.json`, `report.md`, `report.html` and `verification.json` remain ignored. Patient
pixels and case identifiers are not reproduced here. Open the local `report.html` offline;
registered HTTP download links expire when the server restarts. Other machines must
produce their own run. Setup commands are in [the detector guide](detector-baseline.md).
