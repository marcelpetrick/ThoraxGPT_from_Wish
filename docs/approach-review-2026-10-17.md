# Approach review: can a local 4B VLM detect lung nodules on CT? (2026-10-17)

Research use only. This document is not medical advice. The tools and models it discusses
are not validated for diagnosis or treatment. Claims marked **[unverified]** come from secondary
sources or my own reasoning and were not checked against primary data.

Current evidence and operator commands: [model-usage review](model-usage-review-2026-10-17.md).
The proposal below predates the detector and P6 runs. Its causal hypotheses are not
confirmed by constant categorical answers alone.

## 1. Verdict

**Partially wrong. The benchmark is sound; the working hypothesis is not.**

- *Sound:* a reproducible, leakage-controlled, local benchmark of what open VLMs do with
  thoracic CT (Vision §1). That includes reporting an honest negative result.
- *Very likely wrong:* expecting MedGemma 1.5 4B, quantized and zero-shot, to give a useful
  study-level "nodule present" answer from about 24 sampled 2D slabs. Published evidence (§2)
  puts MedGemma's CT nodule performance near chance, even in Google's own setup.
- *Not yet decidable from our data:* whether our pipeline makes things worse. Our input
  format differs from the one MedGemma was trained and evaluated on in four ways (§4). A
  half-day sanity battery (§5) must separate "the model cannot" from "the model cannot see".

Our own evidence (calibration split, n ≤ 10, see `docs/results.md` E001-schema):
96 % lesion coverage, 896 px, strict P5 schema. Q8 answers the same template every time
(nodule and mass present, 0.95, IMAGE 1–4). For Q4, nodule AUROC is 0.64 (n 9, 95 % CI
roughly ±0.35). Cited images contain the lesion in 1/28 (Q8) and 0/8 (Q4) cases, less often
than chance.

## 2. Published evidence on VLMs and foundation models for nodules on CT

| Source | Setting | Number |
|---|---|---|
| MedGemma 1.5 tech report, Table 4 ([arXiv 2604.05081](https://arxiv.org/abs/2604.05081)) | Internal CT Dataset 1, 7 conditions incl. "suspicious lung nodules", **balanced** binary, macro accuracy | MedGemma 1.5 4B **61.1 %**, MedGemma 1 4B 58.2, Gemma 3 4B 54.5, Qwen3-VL 4B 52.8, Gemini 3 Pro 61.0 (chance = 50 %) |
| Same report, Table 5 / App. A | CT-RATE validation, 18 labels, macro F1 | MedGemma 1.5 4B **26.9**, MedGemma 1 23.5, Gemini 3 Flash 8.5 |
| Same report §2.3.1, §3.2.1 | Official protocol | ≤85 axial slices at 896², three-window RGB, **images interleaved with `SLICE k` text**, **one query per condition**, free reasoning then "Final Answer: yes/no" |
| NV-Reason-CT ([arXiv 2609.27511](https://arxiv.org/abs/2609.27511)), Tables 3, A1, A2 | Independent re-evaluation, official checkpoint and prompt, CT-RATE | MedGemma 1.5 macro-F1 0.303; **lung nodule F1 0.166**. Lung nodule AUROC of 3D models: Pillar-0 0.794, VoxelFM 0.786, NV-Reason-CT 0.780, RadFM 0.632, CT-SSG 0.626, M3D-LaMed 0.594, CT-CLIP zero-shot 0.572, Merlin (official checkpoint) 0.494 |
| Same, report-derived F1 for lung nodule | Report-generation models | CT2Rep 0.029, CT-CHAT 0.443, NV-Reason-CT 0.687 |
| "Big, Bright, or Invisible" ([arXiv 2608.05960](https://arxiv.org/abs/2608.05960)) | 10 frozen 3D CT encoders, linear probe / kNN / zero-shot | Small, low-contrast focal lesions are hard for **all** encoders. Skill value (the paper's own metric): solid nodule 0.26, ground-glass 0.05, part-solid 0.02. The authors blame globally pooled embeddings |
| Nishio et al., AJR 2026 ([AuntMinnie summary](https://www.auntminnie.com/clinical-news/digital-x-ray/article/15831864/vlms-miss-most-lung-nodules-on-chest-xrays)) | JSRT chest X-ray, 154 nodules (mean 17 mm) + 93 normal, zero-shot | MedGemma-4b-it sensitivity **5.2 %**, specificity 100 %. Qwen3-VL-8B 7.8 %. Best (LLaVA-Rad) 27.3 % |
| Frontiers Digit. Health 2026 ([PMC12887855](https://pmc.ncbi.nlm.nih.gov/articles/PMC12887855/)) | 83 chest X-rays, 9 models | Best accuracy 0.711 (MedRAX, BiomedCLIP); general VLMs AUC 0.57–0.63 |
| ProbMed, "Worse than Random?" ([arXiv 2405.20421](https://arxiv.org/abs/2405.20421)) | Medical VQA with adversarial pairs | GPT-4o/GPT-4V/Gemini Pro below random on specialised diagnostic questions; weak visual understanding is the bottleneck |
| Blank-image ablations ([arXiv 2511.19220](https://arxiv.org/abs/2511.19220), [arXiv 2606.17710](https://arxiv.org/abs/2606.17710)) | Medical VQA / chest X-ray | Accuracy drops only 2–9 pp for several frontier VLMs when the image is replaced by a blank. Models give confident descriptions of findings that are not there |
| MedGemma 1.5 model card ([HF](https://huggingface.co/google/medgemma-1.5-4b-it)) | Limitations | "has not been evaluated in use cases that involve comprehension of multiple images"; outputs "require independent verification" |

Reading: the published bias runs both ways. Independent CT-RATE runs show MedGemma mostly
answering "no" for nodules (low F1). Our P5 runs show "yes" almost every time. Both fit an
answer driven by the prompt and label prior rather than by the image. No study I found
reports MedGemma *detecting* small nodules on LIDC/LUNA from slices **[searched; none found]**.

## 3. Is a 4B quantized VLM over sampled slices plausible at all?

**Token-budget intuition (calculation, [unverified] for exact FOV):** Gemma 3 / MedGemma encode
every 896² image as 4096 SigLIP patches, average-pooled to **256 tokens** (16×16). At a
typical 320–380 mm field of view, one token covers about 20–24 mm. A 6 mm nodule fills
about 7 % of one token, and on a single slice it looks like a vessel seen end-on. A
radiologist tells them apart by scrolling through 3D. The model sees a few pooled 2D tokens.
This is not a hard resolution limit; features can encode smaller structures. Cropping
changes the nominal footprint: a 64 mm crop at 896² gives about
4 mm per token.

**What works (supervised detection on LIDC/LUNA16):**

| Method | Result | Data / compute |
|---|---|---|
| nnDetection ([arXiv 2106.00817](https://arxiv.org/abs/2106.00817)) | LUNA16 CPM **0.930** (sensitivity 0.950 at 1 FP/scan, 0.985 at 8) | 888 LUNA16 scans, 10-fold CV; developed on RTX 2080 Ti (11 GB); about 2 days per fold ([README](https://github.com/MIC-DKFZ/nnDetection)) |
| Liu et al. 2019 + FP reduction (in nnDetection table) | CPM 0.952 | LUNA16 |
| MONAI `lung_nodule_ct_detection` (RetinaNet, [model card](https://huggingface.co/monai-test/lung_nodule_ct_detection)) | Fold 0: mAP 0.852, AR(IoU 0.1) 1.0 | LUNA16; training needs at least 16 GB; patch 192×192×80; Apache-2.0. **Trained on LIDC subset → overlap with our data** |
| 3D VLMs / encoders (above) | Study-level nodule AUROC 0.49–0.79 on CT-RATE | 25k–70k CT volumes, multi-GPU |

Conclusion: study-level nodule detection is solved by **supervised 3D detectors trained on
hundreds of annotated scans**, not by generalist VLMs. With 38 LIDC calibration patients
and 8 GB VRAM, we cannot train a competitive detector from scratch. We can *run* an
existing one (inference with sliding window fits 8 GB **[estimate]**).

## 4. Runtime and format: could Ollama be hiding the images?

Known or likely differences from the official protocol (§2, row 3):

1. **No interleaving.** One `/api/chat` message carries 24 images. An Ollama contributor
   states that the server "tokenizes the images and prepends them to the start of the
   prompt. They don't have any identifiers" ([ollama#8513](https://github.com/ollama/ollama/issues/8513)).
   Related: image "bleed" across multiple images with Gemma 3 ([ollama#13586](https://github.com/ollama/ollama/issues/13586)).
   If this holds for 0.40.4, our `IMAGE k` captions in the text cannot be tied to particular
   images, and evidence numbers are guesses (which would explain the 1–4 pattern)
   **[unverified for our version; test T0]**. The official notebook alternates
   image, `SLICE k`, image, … ([notebook](https://github.com/google-health/medgemma/blob/main/notebooks/high_dimensional_ct_hugging_face.ipynb)).
2. **No reasoning.** MedGemma 1.5 was evaluated with "write out your argument, then
   Final Answer". It also has a thinking mode (`<unused94>thought`, [ollama#15754](https://github.com/ollama/ollama/issues/15754)).
   Our JSON grammar forces the answer from the first token.
3. **Multi-label in one query** instead of one yes/no question per condition.
4. **Quantization/runtime.** Q4_K_M/Q8_0 GGUF in place of the bf16 transformers model. 4-bit
   quantization can cost grounding while headline VQA scores look unchanged
   ([GPR, NeurIPS 2026](https://neurips.cc/virtual/2026/170017); [GHOST-Q](https://arxiv.org/abs/2609.29999)).
   Q4 and Q8 behaving alike points away from the quantization *level*, though not from the
   runtime.
5. **Distribution shift.** 5 mm MIP slabs and lung-extent sampling are not the uniform raw
   axial slices MedGemma was trained on. This is minor, but it is untested.

Ollama does expose logprobs. Note [ollama#18163](https://github.com/ollama/ollama/issues/18163):
requesting logprobs can change greedy tokens on long generations. Use it on short yes/no
answers only.

## 5. Sanity tests first (gate; calibration or synthetic data only)

| ID | Test | Acceptance criterion |
|---|---|---|
| T0 | Prompt audit: `OLLAMA_DEBUG=2`, one synthetic request with 4 images. Record where image tokens land relative to the text | Document the layout. If images are prepended without markers → mark single-message evidence numbers as invalid by design |
| T1 | Describe: 12 single slices (apex, arch, carina, heart, liver dome; calibration only). Ask which structures are visible | ≥10/12 correct anatomical level, and a different description per level |
| T2 | Position binding: 4 images, one replaced by a synthetic image with a large bright disk. "Which IMAGE shows the disk?" 20 permutations; single-message vs one-message-per-image vs HF interleaved | ≥18/20 correct in the mode used for benchmarks. Chance is 5/20 |
| T3 | Blank vs real: all-black, uniform gray, noise and real image sets with the P5 prompt | Blank/gray must give `adequate: false` or no positive label. Identical output fails this readiness check; it does not alone prove that images are ignored |
| T4 | Synthetic lesion: insert spheres (+40 HU, 30/15/8 mm) into lung on a synthetic phantom or a calibration-negative slice. Single image and a 64 mm crop; per-label yes/no | 30 mm: ≥9/10 yes, correct side ≥8/10. Paired uninserted image: ≥8/10 no. Report the smallest size that still passes |
| T5 | Swap: real positive vs negative calibration cases, same prompt | Answers must differ in ≥1 class (the "non-constant output" gate already proposed in results.md) |
| T6 | Runtime parity: T1–T4 and the same 10 LIDC calibration cases through HF transformers bf16 with the official interleaved prompt (`device_map="auto"` with CPU offload on 8 GB, slow; [notebook](https://github.com/google-health/medgemma/blob/main/notebooks/high_dimensional_ct_hugging_face.ipynb)) | If HF passes T2–T4 and Ollama fails → fix the runtime or format. If both fail → it is a model capability limit |

Decision rule: if T3 or T4 (30 mm) fails in **every** runtime and format, stop study-level
VLM tuning and report RQ1 as negative.

## 6. Ranked recommendations

1. **Run the sanity battery (T0–T6).** Cheap (hours) and it decides everything else. Add
   T3/T5 as permanent gates in front of E001–E004.
2. **Match the official protocol.** Interleave image and `SLICE k` (one message per image,
   or the HF/llama.cpp interleaved path, checked against T0/T2). One label per query.
   Allow short reasoning, then a constrained yes/no. Score with P(yes) from logprobs, so
   AUROC does not depend on self-reported "confidence". Version as a new prompt (P6).
3. **Add a detector reference baseline.** MONAI RetinaNet LUNA16 bundle, inference only.
   Flag it `possible_training_overlap: yes` for LIDC. On NSCLC it is out of distribution.
   It shows what a supervised CAD reaches and supplies candidates. The HU heuristic stays
   as a control.
4. **Crop-level verification (if T4 passes on crops).** For each detector or heuristic
   candidate, crop about 48–64 mm (axial plus coronal/MIP). Ask "nodule vs vessel/none?"
   Score at lesion level (Task C): FP/scan at fixed sensitivity, compared with the detector
   alone. This plays to the token budget instead of fighting it.
5. **Reframe the deliverable.** "Local VLMs on thoracic CT: where they fail and why", with
   pre-registered gates, constant-output detection, image-ablation controls, and Gemma 3 4B
   as a general control. A documented negative result for RQ1 is a valid output.
6. **Deprioritise.** QLoRA on 56 patients (overfitting, dataset confounding); widening
   the study-level E002–E004 sweeps before the gate passes; 3D VLMs that do not fit 8 GB.

## 7. Risks and limits

- Tiny n: the calibration AUROC CIs are about ±0.3. Nothing here is an accuracy estimate.
  Do not tune on internal-test data; do not touch the sealed split.
- Dataset confounding: NSCLC has no nodule negatives, so study-level labels can
  reflect the source collection.
- Synthetic spheres are easier than real nodules. Passing T4 is necessary, not sufficient.
- HF bf16 with offload may take many minutes per case. Limit T6 to synthetic data and 10 cases.
- Overlap: LUNA16 detectors have seen LIDC. MedGemma's training data overlap is unknown.
- The Ollama placement claim (§4.1) comes from an issue comment, not documentation. T0 must
  confirm it for 0.40.4.
- Licences: HAI-DEF terms for MedGemma derivatives; Apache-2.0 for the MONAI bundle.

Research use only; not medical advice. No output of this project may inform diagnosis or
treatment.
