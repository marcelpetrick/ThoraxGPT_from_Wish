# ThoraxBench Local: model research (2026-10-15)

Hardware: RTX A2000 Laptop 8 GB, Ollama 0.40.4, Python 3.14.7 (torch not installed; PyPI has torch up to 2.14.1, which has cp314 wheels; torch has shipped 3.14 wheels since 2.9).
**Status:** sections 1, 2, 4 and 5 are done. Section 3 is done for MedGemma. **The qwen3-vl:4b smoke test was NOT run** because the lead ran out of budget.

> Research use only. This self-made experimental tool is not medical advice from a
> qualified healthcare professional. Findings can be incorrect, incomplete or misleading.
> Do not use outputs for diagnosis or treatment decisions.

## How to use these historical notes

This page records the original 2026-10-15 research pass. Preserve its measured values and
citations. For current installation status, use [model selection](model_selection.md).

1. Check the current configuration under `configs/models/`.
2. Run `uv run thoraxbench models` from the repository root.
3. Follow [the current synthetic run procedure](mvp-test.md).
4. Record any failure or abstention beside successful results.

**Checkpoint:** the configured tag and actual installed model match. Synthetic transport
success does not establish CT detection accuracy.

**Recovery:** if a historical script or artifact is absent, use the maintained procedure.
The scratchpad names below are historical references, not files shipped by the repository.
Do not download weights solely because they appear in a research table; check terms,
capacity and the intended experiment first.

## 1. Vision models available through Ollama

| Tag | Size | Ctx | Fits 8 GB | Multi-image | License | Source |
|---|---|---|---|---|---|---|
| medgemma1.5:4b-it-q4_K_M (= :4b, :latest) | 3.3 GB | 128K | yes (measured) | yes, 85 images measured | Health AI Developer Foundations (HAI-DEF) terms ("other"), HF gated | https://ollama.com/library/medgemma1.5/tags |
| medgemma1.5:4b-it-q8_0 | 5.0 GB | 128K | yes (measured) | yes, 85 images measured | HAI-DEF | same |
| medgemma1.5:4b-it-bf16 | 8.6 GB | 128K | NO (would spill to CPU) | - | HAI-DEF | same |
| medgemma:4b-it-q4_K_M / q8_0 / bf16 (v1) | 3.3 / 5.0 / 8.6 GB | 128K | q4/q8 yes | yes (Gemma3) | HAI-DEF | https://ollama.com/library/medgemma/tags |
| medgemma:27b-it-q4_K_M | 17 GB | 128K | no | - | HAI-DEF | same |
| qwen3-vl:4b (already pulled; has "thinking" capability, so send `think:false`) | 3.3 GB | 256K | yes | yes | Apache-2.0 (upstream) | https://ollama.com/library/qwen3-vl/tags |
| qwen3-vl:4b-instruct-q8_0 | 5.1 GB | 256K | yes | yes | Apache-2.0 | same |
| qwen3-vl:2b-instruct | 1.9 GB | 256K | yes | yes | Apache-2.0 | same |
| qwen3-vl:8b-instruct | 6.1 GB | 256K | tight (little room for KV/images) | yes | Apache-2.0 | same |
| gemma3:4b (q4_K_M) / gemma3:4b-it-qat | 3.4 / 4.0 GB | 128K | yes | yes | Gemma terms | https://ollama.com/library/gemma3/tags |
| qwen2.5vl:3b / 7b | 3.2 / 6.0 GB | 125K | yes / tight | yes | Qwen (3b: research license; 7b: Apache-2.0) | https://ollama.com/library/qwen2.5vl/tags |
| granite3.2-vision:2b | 2.4 GB | 16K | yes | not documented | Apache-2.0 (IBM HF card) | https://ollama.com/library/granite3.2-vision |
| llama3.2-vision:11b (pulled) | 7.8 GB | - | partly offloaded | Ollama supports 1 image per request for mllama | Llama 3.2 Community License | - |

- The Ollama library has **no medical VLMs other than MedGemma.** The vision search page (https://ollama.com/search?c=vision) lists none.
- **Best general control for the comparison:** `gemma3:4b-it-q4_K_M`. It has the same architecture and SigLIP 896 vision encoder as MedGemma 1.5, so it is the clean "medical tuning vs. none" ablation. **It is not pulled yet** (3.4 GB, within the allowed ≤4 GB); recommend `ollama pull gemma3:4b-it-q4_K_M`.

### Medical VLMs as importable GGUF from Hugging Face (not tested)
- **Lingshu-7B** (Qwen2.5-VL-7B architecture, MIT): https://huggingface.co/mradermacher/Lingshu-7B-GGUF has Q4_K_M at 4.68 GB plus a separate mmproj-Q8_0 at 0.85 GB.
  - Ollama's new engine generally needs the vision tower inside the model, not a separate mmproj GGUF. A safer route is `ollama create --quantize q4_K_M` from the safetensors in https://huggingface.co/lingshu-medical-mllm/Lingshu-7B, but that import is unverified.
  - About 5.5 GB plus KV: fits, but tightly.
- **HuatuoGPT-Vision-7B-Qwen2.5VL** (Apache-2.0, base Qwen2.5-VL-7B-Instruct): https://huggingface.co/FreedomIntelligence/HuatuoGPT-Vision-7B-Qwen2.5VL.
  - The only GGUF is tensorblock's, at Q2_K/Q3_K_M quality only, which is too lossy.
  - Same import caveat as Lingshu.
  - The original HuatuoGPT-Vision-7B (Qwen2-7B + LLaVA-1.5, custom `cli.py`) has no GGUF.
- **MedGemma 1.5 GGUFs:** https://huggingface.co/unsloth/medgemma-1.5-4b-it-GGUF (Q4_K_M 2.49 GB, Q8_0 4.13 GB, mmproj-F16 0.85 GB). These are useful for llama.cpp, but the Ollama library tags are simpler.

## 2. Pulled
- `medgemma1.5:4b-it-q4_K_M`: digest 433252621ab1, 3.3 GB
- `medgemma1.5:4b-it-q8_0`: digest d6ae3cddb663, 5.0 GB
- No control model was pulled. gemma3:4b-it-q4_K_M is recommended (see section 1).

## 3. Smoke tests (POST /api/chat, format=json, temperature 0, seed 0, think=false)
- **Historical script:** `smoke.py` in the research scratchpad, not a maintained repository command. It inserted a random nonce in the system message so the KV prefix cache could not shrink `prompt_eval_count`.
- **Historical images:** synthetic 512x512 grayscale PNGs (circles on black) in the scratchpad's `img/`. No patient images were used.

| Model | N img | num_ctx | prompt_eval_count | prefill s | eval_count | eval s | JSON valid | /api/ps size_vram | nvidia-smi peak |
|---|---|---|---|---|---|---|---|---|---|
| mg1.5 q4_K_M | 1 | 8192 | 329 | 3.2 | 20 | 0.6 | yes | 3.04 GB | - |
| mg1.5 q4_K_M | 2 | 8192 | 634-636 | 6.2 (warm); first call 64.9 s wall incl. 33 s load | 30 | 1.3 | yes | 3.04 GB (100% GPU) | - |
| mg1.5 q4_K_M | 4 / 8 / 16 | 8192 | 1139 / 2220 / 4380 | 12.2 / 24.3 / 48.5 | ~20 | ~0.65 | yes | 3.04 GB | - |
| mg1.5 q4_K_M | **85** | 24576 | **23011** | **263.8** | 21 | 1.3 | yes | 2.90 GB | **4292 MiB** |
| mg1.5 q8_0 | 2 | 8192 | 635 | 6.2 (warm); 10.9 cold | 37 | 1.7 | yes | 4.53 GB | 5520 MiB |
| mg1.5 q8_0 | 8 | 8192 | 2217 | 24.2 | 20 | 1.2 | yes | 4.53 GB | 5520 MiB |
| mg1.5 q8_0 | **85** | 24576 | 23009 | **528.4** | 21 | 1.7 | yes | 4.54 GB | **5856 MiB** |
| qwen3-vl:4b | - | - | NOT RUN | | | | | | |

Findings:
- **Multi-image works.** All 85 images fit in one request, and the model correctly reported `n_images_seen: 85`. Ollama 0.40.4 imposed no image cap; the limit is `num_ctx`.
- **Cost per image:** about **270 prompt tokens** (256 Gemma3 soft tokens plus about 14 wrapper/boundary tokens). The text overhead was about 60 tokens.
  - Budget for the official 85-slice recipe: 85 × 270 ≈ 23k tokens, so use `num_ctx` ≥ 24576 (32768 if the prompt is longer).
- **Prefill is the bottleneck,** at about **3.0 s per image** on the A2000 for q4. The vision encoder dominates, and generation is fast (about 16–24 tok/s).
  - q8_0 took twice as long at 85 images (528 s vs 264 s). At 2–8 images the two quantizations were equal.
  - A full 85-slice case therefore costs about 4.5 min (q4) or 9 min (q8). Plan the benchmark runtime accordingly, or use fewer slices (for example 32 slices ≈ 1.6 min).
- **Repeats are deterministic:** identical output on repeated calls with temperature 0 / seed 0.
- **Schema compliance is weak.** `format:"json"` guarantees valid JSON but not the schema. MedGemma returned malformed structure for the 2-image task: it dropped the second image and printed the "larger" key's placeholder as a string. Use `format: <JSON schema>` (structured outputs) and validate the result.
- The first load from disk took 33 s (q4) and 14 s (q8).

## 4. 3D comparators: feasibility on 8 GB GPU + Python 3.14

| Model | Weights | Gated / license | Size | VRAM estimate | Py3.14 / 8 GB verdict |
|---|---|---|---|---|---|
| CT-CLIP | HF dataset ibrahimhamamci/CT-RATE, `models/CT-CLIP-Related/CT-CLIP_v2.pt` (also CT_VocabFine_v2.pt, CT_LiPro_v2.pt) | **Gated** (accept terms + share contact); CC-BY-NC-SA 4.0 | 1.77 GB each (v1 `models_deprecated/*.pt` 9.2 GB) | Inference on one 480×480×240 volume: likely 4–7 GB fp16 (estimate, not measured; README says only "Inference can be done in smaller GPUs") | **Feasible-ish.** Zero-shot classification only, no text generation. Pure torch plus repo packages `transformer_maskgit` and `CT_CLIP`. Pins are old (CT-CHAT lists torch 2.4.0, numpy 1.26.4, which have no 3.14 wheels), so it needs unpinning. **Moderate effort, medium risk.** |
| CT-CHAT | same dataset, `models/CT-CHAT/{llama_3.1_8b,mistral_7b,vicuna_13b,llama_3.1_70b}`: LoRA adapter (671 MB) + non_lora_trainables.bin (1.09 GB / 302 MB) on base LLMs | Gated; CC-BY-NC-SA; Llama base gated by Meta | 8B base about 16 GB bf16 | README: "smaller models need 1 A100". 4-bit 8B LLM about 5–6 GB plus CT-ViT encoder → over 8 GB likely | **Not feasible in practice.** LLaVA fork that pins torch 2.4/transformers 4.44 (no 3.14), needs bitsandbytes 4-bit + encoder; would need a separate venv with Python 3.12. Only consider later. |
| M3D-LaMed-Phi-3-4B | HF GoodBaiBai88/M3D-LaMed-Phi-3-4B | Not gated; Apache-2.0 (code MIT) | about 16.2 GB F32 safetensors (4 shards) + mm_projector.bin 220 MB (repo also has a duplicate 16.2 GB model.bin) | bf16 about 8 GB weights → **does not fit**; 4-bit (bitsandbytes) about 3–4 GB → fits | **Possible with effort.** Needs `trust_remote_code=True` (modeling_m3d_lamed.py, 85 KB, custom generate with seg). Input 1×32×256×256 min-max [0,1]. Custom code targets old transformers. Py3.14 compatibility unknown; 4-bit untested. **Best 3D candidate.** |
| RadFM | HF chaoyi-wu/RadFM: pytorch_model.zip 49.9 GB (split zip) | MIT | 14B-class, about 50 GB | README: "at least one Nvidia A100 (80GB)" | **Infeasible.** |
| HuatuoGPT-Vision-7B | HF FreedomIntelligence/HuatuoGPT-Vision-7B (Qwen2-7B + LLaVA-1.5); -Qwen2.5VL variant | Apache-2.0 | about 16 GB bf16 | 4-bit about 5–6 GB | **2D only, not 3D.** Better used as an Ollama/GGUF 2D control via the Qwen2.5VL variant (import unverified). |

Sources:
- https://github.com/ibrahimethemhamamci/CT-CLIP
- https://github.com/ibrahimethemhamamci/CT-CHAT
- https://huggingface.co/datasets/ibrahimhamamci/CT-RATE
- https://github.com/BAAI-DCAI/M3D
- https://huggingface.co/GoodBaiBai88/M3D-LaMed-Phi-3-4B
- https://github.com/chaoyi-wu/RadFM
- https://huggingface.co/FreedomIntelligence/HuatuoGPT-Vision-7B

## 5. Official MedGemma 1.5 CT preprocessing reference

Use this section as an upstream implementation reference. It is not a command sequence
for the current workbench. Preserve the upstream sampling, windows and prompt details
when comparing implementations. Record any deviation in the view configuration and provenance.

The client-side code is in **notebooks/high_dimensional_ct_hugging_face.ipynb**: https://github.com/Google-Health/medgemma/blob/main/notebooks/high_dimensional_ct_hugging_face.ipynb
- The Model Garden notebook (high_dimensional_ct_model_garden.ipynb) sends `{"type":"image_dicom"}` and windows on the server.
- It uses the same instruction and query text, the same 85-slice sampling, `temperature: 0` and `max_tokens: 500`.

1. **Slice order:** sort DICOM instances by `InstanceNumber`.
2. **Slice sampling:** if there are more than 85 slices, sample 85 uniformly:
   `MAX_SLICE = 85; dicom_instances = [dicom_instances[int(round(i /(MAX_SLICE) * (len(dicom_instances)-1)))] for i in range(1, MAX_SLICE + 1)]`
   - Note that i starts at 1, so the first slice is skipped and the last is included.
3. **Convert to HU:** `pydicom.pixels.apply_rescale(dcm.pixel_array, dcm)`.
4. **Windowing:** three windows stacked as RGB channels.
   - `window_clips = [(-1024, 1024), (-135, 215), (0, 80)]`
     - **R = wide window [-1024, 1024]** (W 2048 / L 0)
     - **G = mediastinum/soft-tissue window [-135, 215]** (W 350 / L 40)
     - **B = brain window [0, 80]** (W 80 / L 40)
   - Each channel: `clip(min,max)` → `-min` → `/(max-min)` → `*255` → `np.round(...).astype(np.uint8)`
   - There is **no lung window.** The notebook calls this "wide, mediastinum(chest), brain".
5. **Image size:** the notebook does not resize; it keeps the native 512×512. The HF processor (Gemma3 / SigLIP) then resizes each image to **896×896 → 256 image tokens**.
6. **Encoding:** `format = "jpeg"` (PNG is an allowed option), base64 data URI `data:image/jpeg;base64,...`.
7. **Prompt structure:** a single user turn; no system message.
   ```
   content = [ {"type":"text","text": instruction} ]
   for slice_number, ct_slice in enumerate(slices, 1):
       content += [ {"type":"image","image": <jpeg>}, {"type":"text","text": f"SLICE {slice_number}"} ]
   content += [ {"type":"text","text": query_text} ]
   ```
   - instruction = "You are an instructor teaching medical students. You are analyzing a contiguous block of CT slices from the center of the abdomen. Please review the slices provided below carefully."
   - query_text = "\n\nBased on the visual evidence in the slices provided above, is this image a good teaching example of liver pathology? Comment on hypodense lesions or other hepatic irregularities. Do not comment on findings outside the liver. Please provide your reasoning and conclude with a 'Final Answer: yes' or 'Final Answer: no'."
8. **Generation:** `do_sample=False`, `max_new_tokens=2000` (HF), bf16 weights.

**Mapping to Ollama:** the interleaved "image, SLICE n" layout cannot be expressed exactly. Ollama `/api/chat` attaches `images` to a message, not inline at positions.
- **Approximation A:** send one user message per slice, each carrying one image and content "SLICE n", followed by a final text message. Consecutive user turns are rendered as separate turns.
- **Approximation B:** one message with all 85 images and the text "SLICE 1..85" listed afterwards.
- Neither has been tested yet. Option A matches the official order more closely. Use `/api/generate` with `raw:true` and a hand-built Gemma3 template for an exact reproduction (needs testing).
- **Budget:** about 23k tokens and `num_ctx` 24576–32768. Measured at 85 images: 264 s prefill (q4) and 528 s (q8).

## Calibration-only pipeline check (2026-10-16)

The later E001-smoke run used the shared benchmark runner on two development calibration
studies with Q4/Q8, four 256-pixel axial inputs and two labels. Q4 abstained on both. Q8
scored one response (missed the reference nodule), then hit its generation limit. The run
took 290.8 seconds; it does not establish accuracy or a quantization winner. See
[the complete measured setup and limitations](results.md).

## Optional MONAI reference detector (2026-10-17)

`monai-lung-nodule` is an inference-only LUNA16 RetinaNet adapter, not a VLM.
[Setup, pinned provenance and limitations](detector-baseline.md) describe the explicit
weight command, adapted preprocessing, source-labelled candidates and LIDC training overlap.
A reduced synthetic CPU API smoke passed; no default-ROI calibration/GPU accuracy claim
is established. Candidate crops support later verification, which requires integration.
