# ThoraxBench Local — Vision

> **Status:** Project vision / research specification  
> **Primary goal:** Build a fully self-hosted, reproducible research system for evaluating local multimodal and 3D medical-AI models on thoracic CT studies.  
> **Initial anchor model:** MedGemma 1.5 4B via Ollama.  
> **Project mode:** Research and benchmarking only; not a clinical diagnostic device.

---

## How to read and implement this specification

This document defines research goals. It is not the current operator runbook.
Use [the HTML manual](manual.html) for supported commands and
[the plan](docs/plan.md) for implementation status.

Adopted implementation decisions (2026-10-15) clarify the original proposals below:

- The user created the public `ThoraxGPT_from_Wish` repository. The original private-repo
  proposal remains historical context; public-data restrictions apply now.
- The user dropped Docker. Run from the source checkout with Python 3.14 and `uv`.
  The diagrams and example `container_digest` field below describe optional target
  isolation/provenance, not a supported Docker deployment.
- CT-RATE access is pending. LIDC-IDRI and NSCLC-Radiogenomics are the downloaded pilot.
- The pilot uses frozen metadata-only pseudorandom patient splits independent of labels:
  80% development (calibration/internal test), 20% sealed holdout, with whole-patient rounding.
  Stratification and CT-RATE's official splits remain research designs for later cohorts.
- The local UI MVP and exploratory output comparison were brought forward. Targeted UX
  work and local DICOM folder opening were subsequently authorized by the user.
  Development reference scoring exists in the CLI benchmark; advanced review, full
  E001–E004 sweeps and frozen holdout evaluation remain open.
- Benchmark invocations preserve terminal raw-response/request/provenance artifacts and
  atomic checkpoints. Explicit resume requires unchanged identity and valid integrity.
  The small calibration smoke demonstrated poor output readiness, not an accuracy result.
- Inference is loopback-only. A trusted LAN runner is a separate proposal, not current behavior.

Before implementing a requirement:

1. Read the relevant section and its cited source.
2. Check the current work package in `docs/plan.md`.
3. Define the expected output and failure/abstention behavior.
4. Implement the smallest complete change through the shared core.
5. Verify it using synthetic tests and the repository quality gate.
6. Record result-affecting versions and hashes in provenance.

**Checkpoint:** the change preserves local inference, license approval and patient-level
separation. A test or smoke run establishes software behavior, not medical accuracy.
**Recovery:** preserve failures and unmet prerequisites. Never bypass a guard to finish a run.
Use short active instructions, one action per step, exact commands and explicit checkpoints
throughout documentation. Preserve research tables, caveats and citations.

## 1. Vision

ThoraxBench Local will be an end-to-end local research platform that accepts a thoracic CT study, preprocesses it into one or more model-specific representations, asks one or more local AI models to identify abnormalities, converts the outputs into a common structured schema, and scores the outputs against reference labels, radiology reports, annotations, or segmentations.

The project is deliberately broader than “run one model on a few CT screenshots.” It should answer:

1. How much clinically relevant information can a small, locally hosted multimodal model recover from a thoracic CT study?
2. Which input representation works best for 2D/multi-image VLMs such as MedGemma?
3. How do those models compare with CT-native 3D models such as CT-CLIP, CT-CHAT, M3D-LaMed, and RadFM?
4. Which thoracic abnormalities are detected reliably, which are missed, and which are hallucinated?
5. Can prompt design, deterministic preprocessing, study-level slice selection, and probability calibration improve performance without fine-tuning model weights?
6. How much does quantization affect medical-image performance?
7. How robust are models when moving from one dataset/hospital distribution to another?
8. Can all inference, preprocessing, scoring, and report generation remain local so that no patient data needs to leave the machine?

The first release is a benchmark and experimentation framework, not a product for patient care.

---

## 2. Core principles

### 2.1 Local-first

All CT pixel data and inference remain on the workstation/server. Internet access is used only to obtain approved public/research datasets, documentation, source code, model weights, and metadata.

### 2.2 Study-level evaluation

A thoracic CT is a 3D study, not a single JPEG. We will preserve volume order, orientation, spacing, Hounsfield Units, reconstruction metadata, and study identity whenever the source dataset provides them.

### 2.3 Reproducibility over ad-hoc prompting

Every run must record:

- dataset and case ID;
- exact model ID and hash;
- quantization;
- preprocessing version;
- sampling strategy;
- prompt template version;
- decoding settings;
- runtime and hardware;
- raw model output;
- parsed structured result;
- ground truth version;
- scoring version.

### 2.4 No benchmark leakage

We will distinguish clearly between:

- **Development / calibration set** — may be inspected and used to tune prompts, thresholds, slice-selection strategy, output parsing, and calibration.
- **Validation set** — used for model/configuration selection after development.
- **Sealed test set** — never used for prompt or threshold tuning. It is evaluated only after a configuration is frozen.
- **External test set** — preferably from a different dataset/source to measure domain shift.

Splits must be performed at the **patient level**, never at the slice level.

### 2.5 Research-use and licensing discipline

The project must not assume that “publicly visible on the internet” means “permitted for bulk download, dataset construction, redistribution, or model training.” A private GitHub repository does not override copyright, data-use agreements, website terms, or privacy law.

We will ingest a source only after recording:

- source URL / DOI;
- owner/provider;
- license or data-use agreement;
- allowed purposes;
- commercial/non-commercial restrictions;
- derivative-work restrictions;
- redistribution restrictions;
- attribution requirements;
- access/gating requirements;
- privacy/re-identification restrictions.

The repository will contain **no bulk CT data**. It will contain acquisition code, manifests, checksums, provenance, and local paths. Raw data stays in a separate data directory ignored by Git.

---

## 3. Initial research questions

### RQ1 — MedGemma as a local CT reader

How accurately can MedGemma 1.5 4B identify thoracic findings when given a deterministic multi-image representation of a full CT study?

### RQ2 — Input representation

Compare:

- uniformly sampled axial slices;
- anatomy-aware slice sampling;
- lung-window images only;
- multi-window RGB encoding;
- multiple window-specific images;
- montage/contact-sheet representations;
- higher slice counts versus lower slice counts;
- selected key slices versus broad volume coverage.

### RQ3 — Quantization

Compare the same MedGemma checkpoint under:

- Q4_K_M;
- Q8_0;
- BF16 where hardware allows.

Measure both diagnostic metrics and performance/VRAM/latency.

### RQ4 — 2D/multi-image VLM versus native 3D model

Compare MedGemma with models that ingest a true 3D representation.

### RQ5 — Calibration

Determine whether per-label thresholding, temperature scaling, isotonic calibration, prompt calibration, and abstention rules improve reliability on the validation and external-test sets.

### RQ6 — Model complementarity

Test whether a small ensemble performs better than any single model, e.g.:

- CT-CLIP for pathology probabilities;
- MedGemma for report-style interpretation;
- segmentation/localization model for evidence;
- final deterministic fusion layer.

---

## 4. Model portfolio

The benchmark should expose every model behind a common local interface rather than requiring every model to run inside Ollama.

### Tier A — Ollama-native baseline

#### MedGemma 1.5 4B

Primary baseline.

Current Ollama package characteristics at project inception:

- architecture: Gemma 3 family;
- multimodal image input;
- approximately 4.3B parameters in the Ollama metadata;
- 128K context;
- Q4_K_M package around 3.3 GB;
- Q8_0 package around 5.0 GB;
- BF16 package around 8.6 GB.

Why it is important:

- explicitly supports high-dimensional medical imaging representations, including CT/MRI;
- very easy local deployment;
- small enough for ordinary workstation GPUs;
- ideal anchor for reproducible quantization experiments.

Initial model IDs:

```text
medgemma1.5:4b-it-q4_K_M
medgemma1.5:4b-it-q8_0
medgemma1.5:4b-it-bf16
```

### Tier B — CT-native / 3D comparators

#### CT-CLIP

A chest-CT-specific foundation model trained around full 3D chest CT volumes and radiology text. It supports abnormality classification across the CT-RATE label space. The official repository describes 18-pathology inference and provides pretrained checkpoints.

Use in ThoraxBench:

- 3D chest-CT classification baseline;
- pathology probability source;
- ensemble component;
- reference for what is gained by true volumetric encoding.

Runtime:

- PyTorch/Transformers-style local service;
- not expected to be an Ollama model;
- smaller-GPU inference is possible according to the project, while training is much more demanding.

#### CT-CHAT

A CT-CLIP-based visual-language system designed for 3D chest CT, with VQA/report-style capabilities.

Use in ThoraxBench:

- native 3D generative comparator;
- report-generation comparator;
- VQA comparator.

Caveat:

The official project lists high GPU requirements for the released configurations. We should first benchmark whether the smaller release is practical on our target hardware before treating it as a default local model.

#### M3D-LaMed-Phi-3-4B

A roughly 4B-class multimodal 3D medical model. The project supports 3D medical-image tasks including VQA, report generation, positioning, and segmentation. Its published quick-start preprocesses a 3D input to approximately `1 x 32 x 256 x 256`.

Use in ThoraxBench:

- lightweight native-3D comparator;
- especially interesting because its parameter count is close to MedGemma 1.5 4B;
- useful test of 3D-native input versus 2D/multi-image VLM input at similar model scale.

Runtime:

- local Transformers/PyTorch service;
- potentially vLLM-compatible depending on checkpoint/runtime support;
- not assumed to work through Ollama.

#### RadFM

An older generalist radiology model designed for both 2D and 3D medical imagery.

Use in ThoraxBench:

- historical 3D/radiology baseline;
- lower priority than CT-CLIP/CT-CHAT/M3D because integration is less modern.

### Tier C — Medical 2D/multi-image comparators

#### HuatuoGPT-Vision 7B / Qwen2.5-VL variant

Medical VLM trained using PubMedVision. It is not specifically a volumetric CT model but provides a useful “medical VLM trained on broad medical imagery” baseline.

Use:

- rendered-slice or montage baseline;
- test whether medical VLM training alone is enough without CT-native volume modeling.

### Tier D — General-purpose VLM control

At least one strong general VLM should be included as a negative/control comparison. This helps quantify how much medical specialization contributes beyond general visual reasoning.

Selection criteria:

- local runnable;
- image input;
- deterministic API;
- fits target GPU;
- permissive enough for research benchmarking.

---

## 5. Dataset strategy

We will start with datasets that already contain de-identified thoracic CT and structured labels, radiology reports, annotations, segmentations, or diagnoses.

### 5.1 Primary dataset: CT-RATE

Why:

- very large chest CT collection;
- non-contrast thoracic CT;
- radiology reports;
- multi-abnormality labels;
- natural match for CT-CLIP and MedGemma CT evaluation;
- large enough for calibration, validation, and a held-out test program.

Published project description reports:

- 25,692 CT volumes;
- 21,304 unique patients;
- additional reconstruction variants expanding the volume count;
- multi-abnormality labels;
- paired radiology reports;
- authors' patient-level train/validation split.

License/data use:

- CT-CLIP/CT-CHAT project states CC BY-NC-SA for its released elements;
- the associated Hugging Face access flow includes research/non-commercial and privacy restrictions.

ThoraxBench rule:

- treat it as **gated, non-commercial research data**;
- do not redistribute raw images or derived bulk data unless clearly permitted;
- preserve the official patient split for reproducibility, then create an internal calibration/validation subdivision only within the allowed training cohort.

### 5.2 LIDC-IDRI

Why:

- 1,010 subjects;
- thoracic CT;
- extensive lung-nodule annotations from multiple radiologists;
- diagnosis information for a subset;
- excellent lesion-level benchmark for nodules.

License:

- TCIA lists the images and annotations under CC BY 3.0, with required citation/attribution.

Use:

- nodule detection/localization benchmark;
- patient-level external test set;
- reader-agreement experiments;
- size-stratified performance analysis.

### 5.3 RadGenome-ChestCT

Why:

- grounded chest-CT reports;
- anatomy-aware labels/regions;
- useful for anatomical grounding and localized findings;
- derived from the CT-RATE ecosystem.

Important licensing note:

The Hugging Face metadata indicates CC BY 4.0, while the dataset card also carries terms copied from CT-RATE that restrict use to academic/research/educational purposes and prohibit commercial exploitation. Therefore we will treat it conservatively as **research-only until the terms are reconciled**.

Use:

- anatomy-grounded evaluation;
- region-specific findings;
- question answering;
- report factuality.

### 5.4 NSCLC-Radiogenomics (TCIA)

Why:

- CT/PET/segmentations;
- clinical data;
- NSCLC cohort;
- useful external-domain cancer test set.

TCIA currently lists images/segmentations and associated data under CC BY 3.0.

Use:

- external cancer-domain evaluation;
- localization/segmentation-aware analysis;
- domain-shift testing.

### 5.5 NSCLC-Radiomics / related TCIA cohorts

Why:

- additional thoracic CT with tumor structures and clinical metadata;
- useful for external validation and segmentation tests.

Licensing varies by collection. Example: NSCLC-Radiomics is listed as CC BY-NC 3.0.

ThoraxBench rule:

- each collection gets its own registry entry and license decision;
- never inherit permissions from another TCIA collection merely because the hosting platform is the same.

### 5.6 MosMedData

Why:

- thoracic CT with COVID-related findings;
- useful distribution-shift and infectious-disease benchmark.

License:

- CC BY-NC-ND 3.0 according to the published dataset information.

Use cautiously:

- evaluation only at first;
- no redistribution of modified data;
- inspect the NoDerivatives implications before publishing any transformed subset.

### 5.7 DeepLesion — candidate, not automatic ingestion

DeepLesion provides tens of thousands of annotated CT lesions across body regions and can add difficult lesion examples. However, it is not exclusively thoracic and its exact current use/redistribution terms must be verified before ingestion.

Status: `candidate / license-review-required`.

---

## 6. Data registry

Every source is defined in `configs/datasets/*.yaml`.

Example:

```yaml
id: lidc_idri
name: LIDC-IDRI
provider: TCIA
modality: CT
anatomy: thorax
license: CC-BY-3.0
access: public
redistribution: allowed_with_attribution
patient_level_split_required: true
source_url: "https://www.cancerimagingarchive.net/collection/lidc-idri/"
raw_format: DICOM
labels:
  - nodules
  - nodule_characteristics
  - subset_diagnosis
citation_required: true
status: approved
```

Possible statuses:

```text
approved
approved_noncommercial
approved_eval_only
pending_terms_review
rejected
```

No acquisition command runs for a dataset whose status is not approved.

---

## 7. Repository and data layout

Proposed repository name:

```text
thoraxbench-local
```

Initially private.

### Repository

```text
thoraxbench-local/
├── Vision.md
├── README.md
├── LICENSE
├── SECURITY.md
├── DATA_POLICY.md
├── pyproject.toml
├── uv.lock / requirements.lock
├── docker-compose.yml
├── .env.example
├── .gitignore
│
├── configs/
│   ├── datasets/
│   ├── models/
│   ├── prompts/
│   ├── preprocessing/
│   └── experiments/
│
├── src/thoraxbench/
│   ├── cli/
│   ├── ingest/
│   ├── dicom/
│   ├── preprocess/
│   ├── sampling/
│   ├── adapters/
│   │   ├── ollama_medgemma.py
│   │   ├── ct_clip.py
│   │   ├── ct_chat.py
│   │   ├── m3d_lamed.py
│   │   └── huatuo_vl.py
│   ├── schemas/
│   ├── calibration/
│   ├── scoring/
│   ├── reports/
│   └── api/
│
├── tests/
├── scripts/
│   ├── acquire/
│   ├── verify/
│   └── benchmark/
│
├── manifests/
│   ├── datasets/
│   ├── splits/
│   └── models/
│
├── experiments/
│   └── README.md
│
└── docs/
    ├── architecture.md
    ├── datasets.md
    ├── model_cards.md
    ├── benchmarking.md
    └── reproducibility.md
```

### Local data directory — not committed

```text
/data/thoraxbench/
├── raw/
├── normalized/
├── cache/
├── rendered/
├── labels/
├── reports/
├── splits/
└── results/
```

`.gitignore` must block raw and derived medical image data by default.

---

## 8. Acquisition pipeline

We should not build a generic crawler that indiscriminately downloads CT images from arbitrary websites.

Instead, acquisition is source-specific and reproducible:

```text
registry entry
    ↓
terms/license gate
    ↓
official API / official download tool / approved repository
    ↓
checksum verification
    ↓
raw immutable storage
    ↓
metadata inventory
    ↓
local de-identification sanity check
    ↓
normalized study index
```

Each acquisition run generates a manifest containing:

```json
{
  "dataset": "lidc_idri",
  "source_version": "2020-09-21",
  "downloaded_at": "...",
  "files": 0,
  "bytes": 0,
  "sha256_manifest": "...",
  "license_snapshot": "...",
  "tool_version": "..."
}
```

For gated Hugging Face datasets, credentials stay outside Git and are supplied via environment variables or the local Hugging Face credential store.

---

## 9. DICOM / volume preprocessing

A shared canonical representation is required before model-specific transforms.

### 9.1 Study discovery

For each permitted DICOM tree:

1. Apply the study-access guard before loading study data.
2. Read headers before pixel data.
3. Group instances by StudyInstanceUID and SeriesInstanceUID.
4. Identify CT series.
5. Exclude localizers, scouts and clearly unsuitable series.
6. Record contrast, reconstruction, kernel and slice thickness when available.
7. Select the intended chest series deterministically.
8. Retain the selection decisions in metadata.

**Checkpoint:** selection is reproducible and its reason is recorded. If geometry or
coverage is inadequate, preserve QC limitations and allow abstention. Do not silently
substitute another patient, sealed case or unsupported series.

### 9.2 Geometry

Normalize:

- orientation;
- slice order;
- image position;
- pixel spacing;
- slice spacing;
- gantry/orientation edge cases;
- duplicate slices;
- missing slices.

### 9.3 Intensities

Convert stored pixels to Hounsfield Units using DICOM rescale metadata when applicable.

Do **not** normalize away HU semantics in the canonical representation.

### 9.4 Model-specific views

Create separate adapters rather than one universal rendered representation.

Examples:

- `medgemma_ct_v1` — implementation based as closely as possible on Google's official high-dimensional CT preprocessing/reference notebook;
- `ct_clip_v1` — reproduce official CT-CLIP volume normalization;
- `m3d_lamed_v1` — shape/normalize as required by the M3D reference implementation;
- `generic_multislice_v1` — controlled baseline for non-CT-specific VLMs.

### 9.5 Quality-control metadata

Record:

- number of slices;
- voxel spacing;
- axial coverage;
- HU min/max/percentiles;
- presence of large gaps;
- body-region confidence;
- contrast flag when inferable;
- reconstruction kernel;
- selected series reason;
- preprocessing warnings.

Low-quality/ambiguous studies can be marked for abstention instead of silently processed.

---

## 10. Input sampling experiments for MedGemma

Because MedGemma receives images rather than a raw 3D tensor through Ollama, slice selection is itself a research variable.

Initial strategies:

### S1 — Uniform-N

Select N axial slices uniformly through the thorax.

Test:

```text
N = 8, 16, 24, 32, 48, 64
```

### S2 — Lung-extent sampling

Identify lung-containing z-range using a simple threshold/body mask or a dedicated lung segmentation model, then sample only within lung extent.

### S3 — Multi-window representation

Generate medically meaningful window representations following the official MedGemma CT reference pipeline where possible.

### S4 — Anatomy-balanced sampling

Ensure coverage of:

- apices;
- upper lobes;
- carina;
- hila;
- heart/mediastinum;
- lower lobes;
- costophrenic angles;
- upper abdomen visible on chest CT.

### S5 — Two-stage slice selection

A cheap detector/encoder selects candidate slices with unusual features; MedGemma receives both uniform context slices and candidate slices.

### S6 — Contact sheets

Create fixed-grid montages. This will be tested but not assumed superior because downscaling may destroy small lesions.

Every strategy is frozen into a versioned transform and benchmarked independently.

---

## 11. Standardized output schema

All generative models should be asked for JSON matching one common schema.

Example:

```json
{
  "study_quality": {
    "adequate": true,
    "limitations": []
  },
  "findings": [
    {
      "label": "pulmonary_nodule",
      "present": true,
      "confidence": 0.78,
      "laterality": "right",
      "region": "upper_lobe",
      "size_mm": null,
      "evidence_images": [11, 12],
      "description": "..."
    }
  ],
  "negative_findings": [],
  "incidental_findings": [],
  "impression": ["..."],
  "urgent_flags": [],
  "uncertainty": "...",
  "abstain": false
}
```

The model must be allowed to say “uncertain” or abstain.

We will never force a binary diagnosis when image quality or model confidence is inadequate.

---

## 12. Initial abnormality ontology

The first common label layer should map to CT-RATE's 18-condition classification task where feasible, then extend with dataset-specific labels.

High-level categories should include at least:

### Lung parenchyma

- pulmonary nodule;
- pulmonary mass;
- consolidation;
- ground-glass opacity;
- atelectasis;
- emphysema;
- fibrosis/interstitial abnormality;
- bronchiectasis;
- cavitation where supported.

### Pleura

- pleural effusion;
- pneumothorax;
- pleural thickening/mass where supported.

### Mediastinum / nodes

- mediastinal or hilar lymphadenopathy;
- mediastinal mass where supported.

### Cardiovascular

- cardiomegaly;
- aortic abnormality where labels support it;
- coronary calcification as an exploratory/incidental label where reliably annotated.

### Skeletal / chest wall

- fracture;
- suspicious osseous lesion;
- chest-wall abnormality.

### Devices / postoperative findings

Dataset-dependent and separated from pathology scoring unless labels are reliable.

The canonical ontology must retain a mapping back to each dataset's native terms so that no false precision is introduced by label conversion.

---

## 13. Benchmark tasks

### Task A — Study-level multi-label abnormality detection

Input: full thoracic CT study.  
Output: presence/probability for each label.

Metrics:

- AUROC per label;
- AUPRC per label;
- macro/micro F1;
- sensitivity;
- specificity;
- PPV/NPV;
- balanced accuracy;
- sensitivity at fixed specificity points;
- confidence intervals via patient-level bootstrap.

### Task B — Calibration

Metrics:

- Brier score;
- Expected Calibration Error;
- calibration curves;
- per-label reliability diagrams;
- negative log likelihood where probabilistic outputs exist.

Compare:

- raw model confidence;
- fitted calibration from development/calibration data;
- validation performance;
- sealed-test performance.

### Task C — Nodule detection/localization

Using LIDC-IDRI and other annotated sources.

Metrics:

- lesion-level sensitivity;
- false positives per scan;
- FROC;
- size-stratified sensitivity;
- reader-agreement-aware analysis.

### Task D — Segmentation / localization

Where a model produces masks or boxes:

- Dice;
- IoU;
- Hausdorff distance where useful;
- center-distance / hit-rate for lesions.

### Task E — Report generation

Compare generated structured findings/impression with reference report/labels.

Metrics should emphasize clinical factuality rather than generic text similarity:

- label agreement extracted from reference and generated report;
- RadGraph-style relation/entity scoring where practical;
- contradiction count;
- omission count;
- hallucinated positive finding count;
- human/radiologist review for a selected subset if available.

BLEU/ROUGE may be reported only as secondary descriptive metrics.

### Task F — VQA / targeted questioning

Examples:

- Is pleural effusion present?
- Is there a pulmonary nodule?
- Which side/lobe?
- Is pneumothorax present?
- What is the dominant abnormality?

Use exact-match or ontology-aware scoring where possible.

### Task G — Abstention and safety

Measure:

- performance at different abstention rates;
- error rate among high-confidence predictions;
- frequency of fabricated measurements;
- false reassurance rate;
- false urgent-flag rate.

---

## 14. Calibration versus training

For phase 1, **do not fine-tune model weights**.

The “training” portion of the dataset will be called the **development/calibration set** and may be used for:

- prompt design;
- few-shot example selection if tested;
- slice-selection design;
- image-count selection;
- output schema design;
- threshold fitting;
- confidence mapping;
- temperature scaling;
- isotonic regression;
- ensemble weighting;
- parser debugging.

The model weights remain frozen.

Fine-tuning becomes a later, separate experimental track only after a clean baseline exists.

This separation is essential because otherwise we cannot tell whether improvement came from a genuinely better model or from fitting the benchmark.

---

## 15. Proposed split policy

### CT-RATE

Respect the official patient-level train/validation separation.

Within the official training cohort, create deterministic patient-level splits such as:

```text
Development/calibration: 80%
Internal validation:      20%
Official validation:      sealed primary test
```

The exact percentages may be adjusted after inspecting label prevalence, but all splits must be stratified where feasible and frozen by manifest.

### LIDC-IDRI

Create a patient-level external benchmark. Do not tune against the cases selected as final nodule test.

### Cross-dataset external testing

At least one entire dataset/source should remain untouched during prompt/calibration work. This is our strongest test of generalization.

---

## 16. Leakage controls

Medical datasets can overlap indirectly through derivative datasets.

The project will track:

- parent dataset;
- derived dataset;
- patient IDs when cross-source mapping is known;
- report provenance;
- model pretraining exposure if documented.

Examples:

- RadGenome-ChestCT is linked to the CT-RATE ecosystem and cannot be treated as independent external data.
- CT-CLIP was trained on CT-RATE, so CT-RATE training performance is not a zero-shot external evaluation for CT-CLIP.

Every benchmark table should include a column:

```text
possible_training_overlap: yes / no / unknown
```

---

## 17. Model adapter API

All local models implement the same interface.

Conceptually:

```python
class ThoraxModel:
    def prepare(self, study): ...
    def infer(self, prepared, request): ...
    def parse(self, raw_output): ...
    def capabilities(self): ...
```

Capabilities include:

```json
{
  "3d_native": false,
  "multi_image": true,
  "classification": true,
  "report_generation": true,
  "localization": false,
  "segmentation": false,
  "probabilities": false
}
```

### Ollama adapter

The MedGemma adapter uses the local Ollama HTTP API and sends only local rendered images and prompts.

### PyTorch service adapters

3D models run in dedicated local processes/containers to isolate dependency conflicts.

Possible topology:

```text
thoraxbench-api
   ├── ollama:11434                -> MedGemma
   ├── ctclip-service:8011         -> CT-CLIP
   ├── m3d-service:8012            -> M3D-LaMed
   └── optional-ctchat:8013        -> CT-CHAT
```

No cloud inference endpoint is required.

---

## 18. End-to-end user workflow

The following are target interfaces. `benchmark`, CLI `compare` and the example
`--request` option are not implemented in the current MVP. Do not run them as current
instructions. Use [the manual](manual.html#commands) for exact supported commands.

Target CLI:

```bash
thoraxbench analyze /path/to/dicom-study \
  --model medgemma1.5-q8 \
  --request full-thorax \
  --output result.json
```

Target benchmark command:

```bash
thoraxbench benchmark \
  --experiment configs/experiments/medgemma_q8_ctrate_v1.yaml
```

Target comparison:

```bash
thoraxbench compare \
  results/medgemma_q4 \
  results/medgemma_q8 \
  results/m3d_4b \
  results/ct_clip
```

Target local web UI:

1. Select a permitted local study.
2. Inspect the metadata and chosen CT series.
3. Inspect sampled slices or a 3D preview when supported.
4. Select a model.
5. Configure the request.
6. Run locally.
7. Inspect status, findings and uncalibrated confidence.
8. Inspect reference overlays when implemented and available.
9. Inspect reference-label scores when ground truth and scoring are available.
10. Export the requested research artifacts.

**Checkpoint:** unsupported target features remain clearly deferred. Current output
comparison does not compute ground-truth accuracy or establish consensus. A failed model
or missing reference must remain explicit.

The UI must visibly state that outputs are experimental research results and not medical advice.

---

## 19. Prompt strategy

Prompts are versioned artifacts, not freehand text pasted during evaluation.

Example goals:

- systematic review by anatomy;
- explicit positive and negative findings;
- avoid unsupported measurement;
- require uncertainty;
- request evidence slice indices;
- enforce JSON;
- separate observation from interpretation.

Prompt variants:

```text
P0: minimal open-ended
P1: structured anatomical checklist
P2: label-constrained classification
P3: label-constrained + evidence requirement
P4: two-pass finding then impression
```

We will compare prompts only on development/calibration data, freeze the winner, then evaluate on sealed test data.

---

## 20. Confidence handling

Generative VLM confidence is not automatically a calibrated probability.

Therefore:

- raw self-reported confidence is recorded but never assumed calibrated;
- binary decisions use thresholds fitted only on calibration data;
- models that expose logits/probabilities use those preferentially;
- model ensembles use calibrated probability sources where possible;
- confidence calibration is evaluated explicitly.

A model that cannot estimate reliable confidence may still produce findings but should not be ranked as calibrated.

---

## 21. Performance measurements

For every model/configuration record:

- total study latency;
- preprocessing latency;
- model inference latency;
- parsing latency;
- peak VRAM;
- peak system RAM;
- model disk size;
- rendered input size;
- number of images/slices supplied;
- tokens generated;
- failures/timeouts;
- throughput studies/hour.

This allows useful plots such as:

```text
clinical metric vs VRAM
clinical metric vs latency
clinical metric vs number of slices
Q4 vs Q8 vs BF16
2D/multi-image vs native 3D
```

---

## 22. Hardware target

### Minimum useful pilot

- modern NVIDIA GPU with ~12 GB VRAM;
- 32 GB RAM;
- NVMe storage.

Suitable for MedGemma 1.5 4B quantized experiments and small pilot datasets.

### Preferred workstation

- 24–32 GB GPU VRAM;
- 64 GB RAM;
- 2–4 TB fast NVMe for active datasets/caches;
- additional bulk storage for full datasets.

This target gives headroom for MedGemma BF16/Q8 plus more demanding PyTorch comparators.

### Large 3D-model experiments

Some CT-CHAT configurations and training workflows may require substantially more GPU memory. Those are optional and should not block the core project.

---

## 23. Storage strategy

Large medical datasets will quickly reach hundreds of GB to multiple TB.

Rules:

1. raw data is immutable;
2. normalized/derived data is reproducible from raw data plus transform version;
3. caches can be deleted and regenerated;
4. Git stores only manifests/configuration/code;
5. each dataset directory contains a local copy of its terms/license metadata;
6. checksums are generated after acquisition;
7. no raw CT volume is pushed to GitHub by default.

Suggested mounts:

```text
/data/raw        large bulk storage
/data/cache      fast NVMe
/models          model weights
/results         experiment outputs
```

---

## 24. Reproducibility

Every benchmark result must be reconstructable.

Store:

```json
{
  "git_commit": "...",
  "dataset_manifest_hash": "...",
  "split_manifest_hash": "...",
  "model_hash": "...",
  "container_digest": "...",
  "prompt_hash": "...",
  "preprocess_hash": "...",
  "seed": 0,
  "hardware": "...",
  "driver": "...",
  "cuda": "..."
}
```

Random slice selection is avoided for final benchmarks. If randomness is scientifically useful, the seed is fixed and reported.

---

## 25. Benchmark report

A standard report should contain:

1. experiment purpose;
2. dataset and split;
3. patient/study counts;
4. label prevalence;
5. model/version/quantization;
6. preprocessing and slice-selection configuration;
7. prompts;
8. primary metrics;
9. per-label metrics;
10. calibration plots;
11. confusion matrices;
12. latency/VRAM;
13. representative true positives;
14. representative false positives;
15. representative false negatives;
16. hallucination examples;
17. uncertainty/abstention analysis;
18. domain-shift analysis;
19. limitations;
20. full provenance hashes.

Generated reports should avoid publishing CT images unless the source license explicitly permits that form of redistribution.

---

## 26. First experimental matrix

### Experiment E001 — MedGemma quantization

Dataset: small CT-RATE calibration subset + sealed subset.

Compare:

```text
MedGemma 1.5 4B Q4_K_M
MedGemma 1.5 4B Q8_0
MedGemma 1.5 4B BF16
```

Hold preprocessing and prompt constant.

### E002 — Slice count

```text
8 / 16 / 24 / 32 / 48 / 64 slices
```

Hold model and prompt constant.

### E003 — Sampling strategy

```text
uniform
lung-range
anatomy-balanced
two-stage candidate selection
```

### E004 — Prompt strategy

Compare P0–P4 on calibration only.

### E005 — 4B versus 4B

```text
MedGemma 1.5 4B
M3D-LaMed-Phi-3-4B
```

This is one of the most important experiments because model size is similar while image representation differs radically.

### E006 — VLM versus CT classifier

```text
MedGemma 1.5
CT-CLIP
```

Compare common study-level labels.

### E007 — Ensemble

Fuse calibrated CT-CLIP probabilities with MedGemma structured findings.

### E008 — External generalization

Freeze everything using CT-RATE-derived development data, then evaluate on LIDC-IDRI / TCIA cohorts for overlapping tasks without retuning.

---

## 27. Data acquisition phases

### Phase A — small pilot

Download enough data to validate the entire software chain before committing multiple terabytes.

Suggested:

- 50–200 CT-RATE studies if access/subsetting permits;
- 50–100 LIDC-IDRI patients;
- labels/annotations for those cases.

Goal: prove ingest -> preprocess -> inference -> parse -> score -> report.

### Phase B — medium benchmark

Scale to roughly 1,000–3,000 studies with balanced label sampling where licensing and storage allow.

Goal: reliable model-selection/calibration experiments.

### Phase C — full research benchmark

Acquire complete approved datasets, preserve official splits, and run sealed evaluations.

Goal: final benchmark tables and external-domain analysis.

---

## 28. Safety and intended use

ThoraxBench Local is a self-made experimental research system created with AI assistance.
It is not medical advice from a qualified healthcare professional. Available knowledge,
models and findings may be incorrect, incomplete or misleading. Do not use outputs for
diagnosis or treatment decisions. Every user-facing output must carry this limitation.

Educational severity or typical attention is reference context. An absent, uncertain or
low-rated finding does not establish that no professional review is needed.

It must not claim:

- clinical validation;
- FDA/CE medical-device status;
- suitability for autonomous diagnosis;
- suitability for treatment decisions;
- replacement of a radiologist.

Model output should be treated as experimental predictions.

If real clinical DICOM is ever introduced later, a separate privacy/security review is required before use. The initial project should use de-identified research datasets only.

---

## 29. Privacy and security

Even publicly distributed research medical datasets deserve conservative handling.

Controls:

- no re-identification attempts;
- no joining with external personal data;
- no public bucket exposure;
- no telemetry containing CT pixels;
- local-only inference by default;
- redact file paths and DICOM metadata from public logs when they may contain sensitive values;
- verify de-identification assumptions with automated DICOM-tag audits;
- secrets never committed;
- downloaded data access restricted to the local research environment.

---

## 30. GitHub strategy

Start as a private repository.

Commit:

- source code;
- prompts;
- model adapters;
- dataset registry;
- split manifests containing research IDs only where allowed;
- checksums;
- aggregate benchmark results;
- documentation.

Do not commit:

- DICOM studies;
- NIfTI volumes;
- bulk rendered slices;
- gated dataset archives;
- model weights that prohibit redistribution;
- credentials/tokens;
- sensitive source metadata.

User-approved exception (2026-10-19): the two reviewed, attributed public-calibration
demo videos in `media/pilot-A.mp4` and `media/pilot-B.mp4` may be committed and pushed.
This does not authorize other real-image assets, raw volumes, full takes or LinkedIn
uploads. Retain the selected-case, training-overlap and research-only disclosures.

Before making the repository public, run a license/data audit and remove anything that cannot be redistributed.

---

## 31. Milestones

### M0 — Repository bootstrap

- private repo;
- `Vision.md`;
- project skeleton;
- Python environment;
- Docker Compose;
- CI for unit tests/linting;
- data-policy gate.

### M1 — MedGemma local proof of concept

- Ollama running locally;
- MedGemma 1.5 Q4 and Q8 pulled;
- image-input API tested;
- deterministic JSON output parser;
- single-study local demo.

### M2 — DICOM pipeline

- series discovery;
- HU conversion;
- orientation/spacing handling;
- slice selection;
- rendered MedGemma input;
- QC report.

### M3 — First dataset

- approved CT-RATE access;
- pilot subset;
- labels imported;
- immutable split manifests;
- E001–E004 runnable.

### M4 — LIDC external benchmark

- approved download;
- nodule annotations parsed;
- lesion-level scoring;
- external evaluation.

### M5 — Native 3D comparator

- M3D-LaMed 4B integration;
- CT-CLIP integration;
- common output adapter;
- E005/E006.

### M6 — Reporting UI

- local web UI;
- study browser;
- model selector;
- side-by-side comparison;
- benchmark report generation.

### M7 — Full benchmark

- frozen v1 protocol;
- full sealed evaluation;
- reproducible results;
- documented limitations.

---

## 32. Definition of success for v1

A successful v1 does **not** mean “AI diagnoses CTs perfectly.”

It means:

1. a user can point the system at an approved local thoracic CT dataset;
2. data never needs to leave the machine for inference;
3. the system reproducibly preprocesses whole CT studies;
4. at least MedGemma 1.5 4B, CT-CLIP, and one native-3D generative model can be evaluated through one framework;
5. patient-level calibration/test separation is enforced;
6. study-level and lesion-level metrics can be computed where labels allow;
7. latency/VRAM are measured;
8. errors and hallucinations are reviewable case by case;
9. results can be reproduced from manifests/configs/hashes;
10. licenses and provenance for every dataset/model are auditable.

---

## 33. Immediate implementation order

This is the original research sequence. Follow `docs/plan.md` for the current task order.
The user-approved changes above supersede the private-repo, Docker and delayed-UI proposals.
Keep each step's outcome in the plan before starting its dependent work:

```text
1. Create private repo + skeleton
2. Install/pin Ollama and Python environment
3. Pull MedGemma 1.5 Q4 + Q8
4. Reproduce the official MedGemma CT preprocessing approach
5. Implement canonical Study object + DICOM loader
6. Define common JSON findings schema
7. Build MedGemma adapter
8. Register CT-RATE + LIDC-IDRI licenses/metadata
9. Acquire a small approved pilot subset
10. Freeze patient-level development/test manifests
11. Run E001–E004
12. Integrate M3D-LaMed 4B
13. Integrate CT-CLIP
14. Run cross-model benchmark
15. Add local UI/reporting
16. Scale data volume only after the pipeline is stable
```

This order avoids spending days downloading terabytes before the benchmark path is proven.

---

## 34. Initial source registry / references

These primary sources were checked while drafting the vision. Before acquisition:

1. Verify the specific source's current terms.
2. Save a terms/license snapshot and its provenance.
3. Confirm the registry approval and access requirements.

**Checkpoint:** approval applies to that collection only. If terms conflict or access is
missing, record the unresolved prerequisite and stop acquisition.

### Models

- MedGemma 1.5 model card — Google Health AI Developer Foundations  
  https://developers.google.com/health-ai-developer-foundations/medgemma/model-card

- MedGemma 1.5 Ollama registry  
  https://ollama.com/library/medgemma1.5

- MedGemma official high-dimensional CT notebook  
  https://github.com/Google-Health/medgemma/blob/main/notebooks/high_dimensional_ct_model_garden.ipynb

- CT-CLIP  
  https://github.com/ibrahimethemhamamci/CT-CLIP

- CT-CHAT  
  https://github.com/ibrahimethemhamamci/CT-CHAT

- M3D / M3D-LaMed  
  https://github.com/BAAI-DCAI/M3D

- M3D-LaMed-Phi-3-4B checkpoint  
  https://huggingface.co/GoodBaiBai88/M3D-LaMed-Phi-3-4B

- RadFM  
  https://github.com/chaoyi-wu/RadFM

- HuatuoGPT-Vision  
  https://github.com/FreedomIntelligence/HuatuoGPT-Vision

### Datasets

- CT-RATE / CT-CLIP dataset information  
  https://github.com/ibrahimethemhamamci/CT-CLIP

- RadGenome-ChestCT  
  https://huggingface.co/datasets/RadGenome/RadGenome-ChestCT

- LIDC-IDRI, TCIA  
  https://www.cancerimagingarchive.net/collection/lidc-idri/

- NSCLC-Radiogenomics, TCIA  
  https://www.cancerimagingarchive.net/collection/nsclc-radiogenomics/

- NSCLC-Radiomics, TCIA  
  https://www.cancerimagingarchive.net/collection/nsclc-radiomics/

- MosMedData publication/repository references  
  Verify the authoritative dataset host and current terms before acquisition.

- DeepLesion, NIH  
  https://www.nih.gov/news-events/news-releases/nih-clinical-center-releases-dataset-32000-ct-images

---

## 35. Current evidence guiding the project

At the time of this specification:

- Ollama distributes MedGemma 1.5 4B with image input and Q4/Q8/BF16 variants, making it an unusually practical local medical VLM baseline.
- Google's published MedGemma 1.5 evaluation includes 3D CT tasks and reports improvement over MedGemma 1 on CT-RATE, but performance remains far from a basis for autonomous clinical use.
- CT-CLIP is explicitly designed around 3D chest CT and CT-RATE and therefore provides a more task-specific comparator than generic VLMs.
- M3D-LaMed-Phi-3-4B provides a useful same-scale 3D-native comparison to MedGemma 1.5 4B.
- LIDC-IDRI remains a strong openly licensed thoracic CT resource for lesion-level nodule evaluation.

The project is therefore intentionally designed to test both convenience-oriented local VLMs and models that preserve volumetric inductive bias.

---

## 36. Final project statement

**ThoraxBench Local will be a local-first, license-aware, reproducible thoracic-CT AI laboratory.**

It will not try to prove that one chatbot can replace a radiologist. It will systematically measure what current small and medium open/local models can and cannot detect when given medically sensible representations of full CT studies, using clean patient-level splits, multiple independent datasets, rigorous calibration, volumetric comparators, and auditable metrics.

The most important deliverable is not a single accuracy number. It is a framework in which every result can be traced back to the exact CT study, model, preprocessing method, prompt, output, ground truth, and score—and in which all sensitive data and inference remain under local control.
