# Fine-tuning and precision plan (research)

Research use only. This self-made tool is not professional medical advice. Its findings
may be incorrect, incomplete or misleading. Do not use them for diagnosis or treatment.

**Status:** proposal, 2026-10-16. Only the cue ablation it references has run (4/4 abstentions); the rest is unrun. Figures marked *estimate*
are calculations, not measurements. Binding rules stay in `AGENTS.md`, `DATA_POLICY.md`
and Vision §14–§16: weights stay frozen in phase 1, and fine-tuning is a separate,
later track that starts only after a clean E001–E004 development baseline exists.

## 1. What limits precision today

| # | Limit | Evidence | Consequence |
|---|---|---|---|
| L1 | **Unusable outputs.** | E001-smoke: Q4 gave 2/2 empty-output abstentions; Q8 hit the generation limit once. Q4/P2 diagnostics: model copied heuristic candidate text and cited source-slice numbers as image evidence (`docs/results.md`). | Little or nothing can be scored. Any metric is dominated by format failures. |
| L2 | **The lesion is not in the attached images.** | Runs used 2–9 axial images at 256 px. A 6 mm nodule covers about 5 of roughly 300 slices, so two uniform slices include it only about 3 % of the time (*estimate*). | No prompt or fine-tune can detect what was not shown. Sampling caps sensitivity. |
| L3 | **Input differs from MedGemma's CT training input.** | The MedGemma 1.5 report feeds up to 85 equidistant axial slices at 896×896, uses three-window RGB (which the repo matches) and puts a text "SLICE k" marker before each slice. Gemma 3 always encodes an image as 256 tokens at 896². | 256 px images are upscaled, which loses small nodules at the same token cost. The repo's captions contain source-slice numbers ("slice idx/nz"), which invites the invalid evidence references seen so far. |
| L4 | **Heuristic context leaks into answers.** | P2 received HU-cue text and the model copied it. The v0.3.16 `E001-cue-ablation` then gave 4/4 abstentions with and without cues. | Positive answers can come from the rules, not from the images. |
| L5 | **Confidence is uncalibrated and coarse.** | Answers are mostly 0.0 or 1.0. Reports use a fixed 0.5 threshold, and calibrators exist only as a library (traceability §14 and §20). | Precision cannot be tuned to a chosen operating point. |
| L6 | **Too little data, and labels confounded with dataset.** | Calibration is 56 patients (LIDC 38, NSCLC 18). Internal test is 14 (10/4); sealed is 17 (12/5). NSCLC has no nodule negatives; LIDC has the only negatives (16 in the whole development set) and one mass. | Study-level learning risks learning "which collection is this" instead of findings. Internal-test 95 % CIs are about ±0.25. |
| L7 | **Lesion-level scoring (Task C) is not wired.** | The heuristic reports slice indices, not mm centres. | Precision at lesion level (false positives per scan) cannot be measured yet. |
| L8 | **Possible training overlap.** | The MedGemma model card names no TCIA/LIDC data, but its training includes PMC-OA figures and an undisclosed internal CT set. LUNA16 consists of 888 LIDC-IDRI scans. | `possible_training_overlap` is *unknown* for MedGemma, and *yes* for any LUNA16-trained detector evaluated on LIDC. |

## 2. Options ranked by expected gain against effort on this workstation

Hardware: RTX A2000 Laptop (8 GB VRAM), 31 GB RAM, Ollama 0.40.4. Gain is the expected
effect on *usable, precise* nodule/mass output. Effort includes code and run time.

| Rank | Option | Expected gain | Effort | Fits 8 GB? | Main risk |
|---|---|---|---|---|---|
| 1 | Output reliability: tighten the schema and captions (§2.1) | High for usable-output rate; prerequisite for everything else | Low | Yes | Ollama may silently ignore unsupported schema keywords |
| 2 | Input fidelity: 896 px renders, more slices, MIP slabs, check lesion coverage (§2.2) | High; removes the cap set by L2/L3 | Low–medium | Yes; context/KV cache is the constraint | Longer runs (estimate 1–3 min per case) |
| 3 | Ask one question per label (the official CT-RATE evaluation queried each condition separately) | Medium | Low | Yes | Run time × number of labels |
| 4 | Calibration: temperature/Platt scaling, fitted thresholds, logprobs if Ollama exposes them | Medium for precision at a fixed sensitivity | Low (library exists) | Yes (CPU) | 56 patients only supports 1–2-parameter calibrators; no isotonic |
| 5 | Two stages: a candidate detector proposes locations, then the VLM checks crops or MIP patches to remove false positives | Medium–high for precision | Medium | Yes | Error compounds across stages; needs Task C |
| 6 | Frozen embedding probe: MedSigLIP-448 slice/slab embeddings plus logistic regression or a small attention pool, trained on LIDC lesion labels | Medium | Medium | Yes (about 0.9 GB in bf16) | HAI-DEF terms; small low-contrast lesions are hard for pooled embeddings |
| 7 | Small supervised 3D detector (MONAI RetinaNet), trained from scratch on calibration-split LIDC annotations | Highest ceiling for nodule localisation and precision | Medium–high | Training: the bundle says ≥16 GB at a 192×192×80 patch; 8 GB needs a smaller patch, batch 1 and mixed precision (*estimate*) | 38 patients is small; the pretrained LUNA16 bundle overlaps LIDC |
| 8 | Few-shot prompting with calibration-patient examples | Low / uncertain | Low | Context-limited (256 tokens per image) | The example patient must be excluded from its own query |
| 9 | **QLoRA of MedGemma 1.5 4B** (§2.3) | Uncertain; may be zero or negative with 56 patients | High | Borderline | Overfitting, shortcut learning, re-quantisation erasing gains, HAI-DEF derivative terms |
| 10 | 3D models (CT-CLIP probes, M3D-LaMed, RadFM, CT-CHAT) | Unknown | High | Blocked: gated weights / VRAM | A 2026 frozen-encoder benchmark finds small focal lesions hard for all such encoders |
| 11 | RL fine-tuning (official GRPO notebook) | n/a | Very high | No (needs repeated generation plus training) | Not pursued |

### 2.1 Output reliability (cheapest; do first)

The Ollama adapter already sends `format: <JSON schema>`, with `temperature 0`, `seed 0`,
`num_ctx 16384` and `num_predict 4096`. Each change below goes in its own hashed config or
prompt version:

- **Fixed-length findings.** Set `findings` `minItems`/`maxItems` to the number of labels. Add `additionalProperties: false`. Give `description`, `uncertainty`, `impression[]` and `incidental_findings[]` a `maxLength`/`maxItems` so generation cannot run to the token limit.
- **Answers first.** Put `findings` before free text in property order, so truncation cuts prose rather than answers.
- **Probe the grammar.** Check with a synthetic request that 0.40.4 actually enforces the integer `maximum` and `maxItems` limits. The llama.cpp grammar converter ignores unsupported keywords without warning. Keep the post-parse evidence guard either way.
- **Captions without source-slice numbers.** Variant: no "slice idx/nz" in captions. Optionally send one user message per image with a short `IMAGE k` caption, as an Ollama approximation of the official interleaved "SLICE k" format. Verify the chat template renders the messages in order.
- **No heuristic context.** `E001-cue-ablation` has run (4/4 abstentions either way); make `include_cues: false` the default for VLM evaluation. Cues stay as a separate control.
- **Diagnose Q4 empty output.** Check `done_reason`, empty `message.content` and the `think` setting in the preserved raw responses before changing prompts.

### 2.2 Input fidelity

- **Render at 896 px.** Gemma 3 uses 256 tokens per image at any input size, so 896 px renders cost no extra tokens, only bigger PNGs.
- **Measure coverage before running the model.** On the 38 LIDC calibration patients, compute the fraction of reference nodules (≥3 mm) that fall on at least one attached slice or slab, for each strategy, n and slab setting. This uses LIDC XML only (`labels/lidc.py`) and needs no GPU. Choose configurations from this number, not from model output.
- **Use the MIP strategy that already exists** (`MipSlabs`; 5–10 mm slabs help separate nodules from vessels) together with the official RGB windows. Try a lung-window variant separately.
- **Context limit.** At `num_ctx 16384`, about 55 images fit. Test 24/32/48 images, and `num_ctx 24576` with `OLLAMA_KV_CACHE_TYPE=q8_0` plus flash attention. Record peak VRAM. Do not offload to CPU silently.

### 2.3 QLoRA of MedGemma 1.5 4B: memory, time, data (*estimates*)

Setup: Hugging Face `transformers`/`peft`/`bitsandbytes` (or Unsloth). NF4 base, LoRA r=16
on the language-model linear layers, vision tower frozen. Batch 1, gradient checkpointing,
paged 8-bit AdamW. Up to 4 images at 896 px (1,024 image tokens) plus about 350 text tokens.

| Component | VRAM (estimate) |
|---|---:|
| Language-model weights except embeddings, NF4 (about 3.2B params) | ~1.8 GB |
| Token embeddings / tied LM head, bf16 (262k × 2560) | ~1.3 GB |
| SigLIP vision tower, bf16 (0.4B), frozen | ~0.85 GB (~0.3 GB if 4-bit) |
| LoRA weights + gradients + 8-bit optimiser states | ~0.3 GB |
| Activations (checkpointed, about 1.4k tokens) | 0.5–1.0 GB |
| Logits: full fp32 1.4k × 262k / chunked loss on answer tokens only | 1.5 GB / ≤0.3 GB |
| CUDA context, fragmentation, display | 0.6–0.9 GB |
| **Total** | **~5.5–6.5 GB with chunked loss; >7.5 GB without** |

- **Verdict:** borderline but plausible only with chunked or answer-only loss, batch 1 and ≤4 images. First measure `torch.cuda.max_memory_allocated` in a 10-step dry run on synthetic phantoms.
- **Time (estimate):** about 4–10 s per sample on the laptop A2000. 1,000 samples × 3 epochs takes about 3.5–8 h per run; 5-fold patient-level CV takes 1–2 days.
- **Export:** merge the adapter in bf16 on the CPU (about 9 GB RAM), convert with llama.cpp `convert_hf_to_gguf.py` (text model plus mmproj), quantise to Q4_K_M/Q8_0, and load with `ollama create`. Re-quantising can erase small LoRA gains, so always evaluate the GGUF that is actually served.
- **The data problem:** 56 calibration patients, with nested folds leaving about 45 for training, is far too few for study-level supervision of a 4B model. The main lever is **lesion-level examples from LIDC reader XML**: positive slabs centred on nodules ≥3 mm, matched negative slabs from the same patients (vessels, normal lung), plus augmentation (flips, slab offsets, window jitter). That gives several hundred to about 1,000 correlated examples (*estimate*).
  - Train the nodule task within LIDC only, so the collection cannot stand in for the label.
  - Treat masses (mostly NSCLC) separately, or leave them out of training.
  - Effective sample size is still about the number of patients. Expect large variance between folds.
- **Licence:** a LoRA or merged model is a *Model Derivative* under the HAI-DEF terms. Hosting it counts as distribution. Keep it local, never commit weights (`DATA_POLICY.md`), and publish only aggregate outputs.

## 3. Leakage-safe protocol

1. **Training and fitting (calibration phase only).** Everything learned — LoRA, detector, probe, calibrator, threshold, prompt/view choice, few-shot examples — is fit on the 56 calibration patients. Hyperparameters are chosen by patient-level 5-fold CV stratified by dataset *inside* calibration. Training data builders must load studies through `CaseGuard` and `check_phase`. Add a test that a sealed ID raises `SealedAccessError` in the builder.
2. **Selection (internal test, used once).** At most two frozen candidates, each evaluated once on the 14 internal-test patients. Record every look in `docs/results.md` with config hash and date. After a look, no change may be justified by internal-test results. A later candidate must be motivated by calibration evidence, and its report must state that the internal test was already used.
3. **Final run (sealed, only with `--unseal`).** One frozen experiment: `freeze_experiment`/`verify_freeze` over config, model/adapter/GGUF digests, calibrator parameters and code commit. Run once with `thoraxbench benchmark --unseal` (still to be implemented; today it is refused with exit 2). No reruns after seeing results. With 17 sealed patients, report CIs and do not claim generalisation.
4. **Hashed identity for every change.** A new experiment YAML and/or model YAML for each change. Fine-tuned model configs carry a `training:` block: training-config SHA-256, calibration patient-hash list from `manifests/splits/` (hashes only), data-builder source hash, base model digest, adapter SHA-256, served GGUF/Ollama digest, seed, library versions. Calibrators are saved as JSON (`to_dict`) and hashed into run provenance. The runner's strict resume checks already refuse identity drift.
5. **Overlap column.** Add `possible_training_overlap` to every table (gap 8):
   - MedGemma on LIDC/NSCLC: *unknown*.
   - LUNA16-pretrained detector on LIDC: *yes* (LUNA16 is 888 LIDC scans and very likely includes sealed patients). Use it only on NSCLC-Radiogenomics, or train from scratch.
   - CT-CLIP on these collections: *no* (CT-RATE only, as documented).
   - Patient membership in LUNA16 may only be checked inside the guard, returning counts, never IDs.
6. **Experiment numbering.** E000–E004 stay. Vision reserves E005–E008. Readiness diagnostics keep the `E00x-<suffix>` form (like `E001-cue-ablation`). The adaptation track starts at E009.

## 4. Next experiments and acceptance criteria

| ID | What | Data | Acceptance criterion (pre-registered) |
|---|---|---|---|
| E001-schema | Tightened schema, fixed-length findings, captions without source-slice numbers, no cues; Q4 and Q8 | Calibration, `--limit 1`, then all 56 | ≥95 % of case×label predictions present and schema-valid; 0 out-of-range evidence; 0 generation-limit stops; 0 copied heuristic text |
| E001-coverage | Lesion-coverage measurement (no model) across strategy × n × slab × 896 px | LIDC calibration XML | Smallest config that fits the context with ≥90 % of reference nodules covered |
| E002–E004 | Run as already configured, plus the E001-schema/coverage settings as new hashed variants | Development per Vision | Usable-output rate from E001-schema maintained; results recorded with overlap column |
| E009 | Calibration and thresholds (temperature/Platt; logprob probabilities if 0.40.4 exposes them) | Fit in CV on calibration | Brier and ECE better than raw in CV; AUROC unchanged; threshold set for PPV at sensitivity 0.80 |
| E010 | Per-label questions and 896 px/MIP input against the best E002/E003 variant | Calibration CV | Nodule AUROC 95 % CI lower bound >0.5 and above E000 (0.524); PPV at sensitivity 0.80 reported |
| E011 | Wire Task C (mm centres) and FROC | Calibration LIDC | Scorer tests pass; E000 and the VLM produce FROC curves |
| E012 | MedSigLIP slab-embedding probe | Calibration CV, LIDC lesion labels | Slab-level AUROC CI lower bound >0.6; study-level result compared with E010 |
| E013 | MONAI RetinaNet from scratch (smaller patch, mixed precision); optional VLM false-positive filter | Calibration CV; NSCLC-only test for the LUNA16 bundle | Peak VRAM ≤7.5 GB measured; CV sensitivity reported at 1/2/4 FP per scan; useful if ≥0.6 at 4 FP/scan (well below published LUNA16 numbers, which used far more data) |
| E014 | QLoRA MedGemma 4B, **only after E001–E004 baseline and E001-schema pass** | Calibration CV only | 10-step dry run ≤7.5 GB; paired-bootstrap CV improvement over the frozen best ≥0.05 AUROC with CI excluding 0; usable-output rate not lower. Otherwise drop |

**Stop rules:**
- Do not run E002–E004 or E010+ until E001-schema passes.
- Do not run QLoRA if E001-coverage stays below 90 %; fix sampling first.
- Every candidate goes through the internal test once and the sealed holdout once, per §3.

## 5. Sources

- MedGemma 1.5 Technical Report (CT data, 85 slices at 896², RGB windows, CT-RATE eval): https://arxiv.org/abs/2604.05081
- MedGemma Technical Report: https://arxiv.org/abs/2507.05201
- MedGemma model card (training datasets, "expected to fine-tune", 896²/256 tokens): https://developers.google.com/health-ai-developer-foundations/medgemma/model-card
- MedGemma overview: https://developers.google.com/health-ai-developer-foundations/medgemma
- HAI-DEF Terms of Use (Model Derivatives, Distribution): https://developers.google.com/health-ai-developer-foundations/terms
- Official notebooks (LoRA SFT, RL, high-dimensional CT): https://github.com/google-health/medgemma/tree/main/notebooks
- Gemma 3 Technical Report (fixed-resolution SigLIP, 256 tokens): https://arxiv.org/abs/2503.19786 · https://ai.google.dev/gemma/docs/capabilities/vision
- QLoRA: https://arxiv.org/abs/2305.14314 · Unsloth Gemma 3: https://unslothai.substack.com/p/google-gemma-3-now-in-unsloth
- QLoRA of MedGemma-4b-it example (r=16, A100): https://arxiv.org/abs/2608.08896
- Ollama structured outputs: https://ollama.com/blog/structured-outputs · llama.cpp grammars: https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md
- MedSigLIP model card: https://developers.google.com/health-ai-developer-foundations/medsiglip/model-card
- MONAI lung nodule detection bundle (LUNA16, ≥16 GB training): https://huggingface.co/monai-test/lung_nodule_ct_detection · https://catalog.ngc.nvidia.com/orgs/nvidia/teams/monaitoolkit/models/monai_lung_nodule_ct_detection
- LUNA16 data (888 LIDC scans, ≥3/4 readers): https://luna16.grand-challenge.org/Data/ · Setio et al. 2017: https://arxiv.org/abs/1612.08012
- CT-CLIP: https://github.com/ibrahimethemhamamci/CT-CLIP · CT-FM: https://arxiv.org/abs/2501.09001
- Frozen-feature benchmark of 3D CT foundation models: https://arxiv.org/abs/2608.05960
- Calibration: Guo et al. 2017 https://arxiv.org/abs/1706.04599 · Niculescu-Mizil & Caruana 2005 https://www.cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf

## 6. Limitations

Research use only. This is not professional medical advice and not a clinical
validation plan. All results come from 87 patients in two public TCIA collections, and the
data volumes listed above limit every conclusion. A higher score here does not make any
configuration suitable for diagnosis or treatment.
