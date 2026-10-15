# ThoraxBench Local — Architecture

This document describes ThoraxBench Local with the [C4 model](https://c4model.com/)
(Context → Containers → Components → Code) plus flowcharts for the main workflows.
Diagrams are Mermaid, so GitHub renders them directly.

Source of requirements: [`Vision.md`](../Vision.md). Section references (§) point there.

---

## 1. System context (C4 level 1)

```mermaid
C4Context
    title ThoraxBench Local — system context

    Person(researcher, "Researcher", "Runs analyses and benchmarks, reviews errors and reports")

    System(tb, "ThoraxBench Local", "Local framework: ingest → preprocess → infer → parse → score → report")

    System_Ext(ollama, "Ollama server", "Local LLM/VLM runtime (MedGemma 1.5, general VLM controls)")
    System_Ext(svc3d, "Local 3D model services", "Optional PyTorch HTTP services: CT-CLIP, M3D-LaMed, CT-CHAT, RadFM, HuatuoGPT-Vision")
    System_Ext(tcia, "TCIA NBIA API", "Official public download API for approved collections (LIDC-IDRI, NSCLC-Radiogenomics, …)")
    System_Ext(hf, "Hugging Face Hub", "Gated datasets/weights (CT-RATE, CT-CLIP) — only with the user's own token")

    Rel(researcher, tb, "CLI / local web UI")
    Rel(tb, ollama, "HTTP /api/chat, /api/ps, /api/show", "localhost only")
    Rel(tb, svc3d, "HTTP /v1/infer", "localhost only")
    Rel(tb, tcia, "Downloads approved collections", "HTTPS, license-gated")
    Rel(tb, hf, "Downloads gated data if approved + token present", "HTTPS")
```

Data that never leaves the machine: CT pixels, rendered images, predictions, labels.
The only outbound traffic is the acquisition of approved datasets (§2.1, §29).

---

## 2. Containers (C4 level 2)

```mermaid
C4Container
    title ThoraxBench Local — containers

    Person(researcher, "Researcher")

    System_Boundary(tb, "ThoraxBench Local (one Python 3.14 package: thoraxbench)") {
        Container(cli, "CLI", "Typer", "thoraxbench analyze | benchmark | compare | acquire | split | datasets | models | report | serve")
        Container(web, "Local web UI", "FastAPI + Jinja2", "Study browser, model runner, findings, score, export")
        Container(core, "Core library", "Python", "Registry, DICOM, preprocessing, sampling, adapters, scoring, calibration, reports")
        ContainerDb(data, "Data directory", "Filesystem (git-ignored)", "data/raw, cache, rendered, labels, splits, sealed, results — 10 GB budget")
        ContainerDb(repo, "Versioned configs + manifests", "Git", "configs/*.yaml, prompts, split manifests (hashes), acquisition manifests")
    }

    System_Ext(ollama, "Ollama", "localhost:11434")
    System_Ext(svc3d, "3D model services", "localhost:8011-8014")

    Rel(researcher, cli, "uses")
    Rel(researcher, web, "browser on 127.0.0.1:8000")
    Rel(cli, core, "calls")
    Rel(web, core, "calls")
    Rel(core, data, "reads/writes")
    Rel(core, repo, "reads configs, writes manifests")
    Rel(core, ollama, "infer")
    Rel(core, svc3d, "infer")
```

---

## 3. Components (C4 level 3) — the `thoraxbench` package

```mermaid
C4Component
    title thoraxbench core library — components

    Container_Boundary(core, "thoraxbench") {
        Component(config, "config", "pydantic-settings style", "Paths, endpoints, budget; env THORAXBENCH_*")
        Component(registry, "registry", "YAML + pydantic", "Dataset/model registry, license status, policy gate")
        Component(ingest, "ingest", "httpx", "Source-specific acquisition (TCIA), checksums, manifests, budget, de-id audit")
        Component(dicom, "dicom", "pydicom + numpy", "Series discovery/selection, geometry, HU volume, QC")
        Component(preprocess, "preprocess", "numpy/scipy", "Windows, masks, MIP/coronal, deterministic HU cues")
        Component(sampling, "sampling", "numpy", "S1–S6 slice-selection strategies (versioned)")
        Component(views, "views", "Pillow/numpy", "Model-specific inputs: medgemma_ct_v1, generic_multislice_v1, ct_clip_v1, m3d_lamed_v1")
        Component(prompts, "prompts", "YAML templates", "P0–P4, versioned + hashed")
        Component(adapters, "adapters", "httpx", "ThoraxModel interface: Ollama, HTTP 3D service, HU-heuristic baseline")
        Component(parsing, "parsing", "pydantic", "Robust JSON extraction → FindingsReport")
        Component(ontology, "ontology", "YAML", "Canonical labels, dataset mappings, clinical knowledge base")
        Component(labels, "labels", "xml/csv", "Reference labels per dataset (e.g. LIDC XML)")
        Component(splits, "splits", "hashlib", "Patient-level stratified 80/20 split, sealing guard")
        Component(scoring, "scoring", "numpy/sklearn", "Tasks A–G metrics, bootstrap CIs, FROC")
        Component(calibration, "calibration", "sklearn", "Thresholds, temperature, isotonic, abstention")
        Component(perf, "perf + provenance", "psutil/nvidia-smi", "Latency/VRAM/RAM, hashes, git commit, hardware")
        Component(benchmark, "benchmark", "Python", "Experiment runner, resumable results, compare")
        Component(reports, "reports", "Jinja2/Markdown", "Benchmark report + per-study clinical Markdown report")
    }

    Rel(ingest, registry, "checks status before any download")
    Rel(dicom, preprocess, "HU volume")
    Rel(preprocess, sampling, "masks + cues")
    Rel(sampling, views, "slice indices")
    Rel(views, adapters, "prepared input")
    Rel(prompts, adapters, "prompt text")
    Rel(adapters, parsing, "raw output")
    Rel(parsing, scoring, "FindingsReport")
    Rel(labels, scoring, "ground truth")
    Rel(splits, benchmark, "allowed case IDs")
    Rel(benchmark, scoring, "predictions")
    Rel(scoring, reports, "metrics")
    Rel(ontology, reports, "clinical knowledge")
```

### Component responsibilities and contracts

| Module | Key types / functions | Notes |
|---|---|---|
| `config` | `Settings` (`data_dir`, `ollama_url`, `data_budget_bytes`, `services`) | env prefix `THORAXBENCH_` |
| `registry` | `DatasetEntry`, `DatasetStatus`, `load_registry()`, `require_acquirable(entry)` → `PolicyError` | statuses from §6 plus `pending_access` |
| `ingest` | `TciaClient`, `acquire(dataset_id, plan)`, `write_manifest()`, `check_budget()`, `audit_deid()` | resumable, checksum-verified, raw immutable |
| `dicom` | `discover_series(root)`, `select_series()`, `load_volume(series)` → `Volume` | `Volume.hu: int16[z,y,x]`, `spacing_mm`, `qc` |
| `preprocess` | `apply_window()`, `lung_mask()`, `body_mask()`, `mip_slab()`, `coronal()`, `hu_cues(volume)` | canonical HU never altered (§9.3) |
| `sampling` | `SamplingStrategy` (`id`, `version`, `select(volume, cues) -> list[int]`), S1–S6 | deterministic; seed recorded if used |
| `views` | `ViewBuilder.build(volume, indices) -> PreparedInput` | `PreparedInput.images: list[bytes]`, `meta` |
| `prompts` | `PromptTemplate` (`id`, `version`, `sha256`, `render(labels, n_images)`) | P0–P4 |
| `adapters` | `ThoraxModel` protocol: `prepare`, `infer`, `parse`, `capabilities` (§17) | `OllamaModel`, `HttpServiceModel`, `HeuristicModel` |
| `parsing` | `extract_json(text)`, `parse_findings(raw, ontology)` → `FindingsReport` | never invents findings; invalid → abstain |
| `ontology` | `Label`, `ONTOLOGY`, `map_native(dataset, term)`, `ClinicalKB` | mapping back to native terms (§12) |
| `labels` | `load_reference(dataset, case)` → `ReferenceLabels` | LIDC XML parser: nodules, size, reader count |
| `splits` | `make_split()`, `SplitManifest`, `CaseGuard.allowed(phase)` → `SealedAccessError` | patient-level, label-stratified, deterministic hash |
| `scoring` | `task_a()`…`task_g()`, `bootstrap_ci()`, `froc()` | patient-level bootstrap |
| `calibration` | `fit_thresholds()`, `TemperatureScaler`, `IsotonicCalibrator`, `abstention_curve()` | fitted only on development data |
| `perf`, `provenance` | `measure()` context manager, `RunProvenance` | §21, §24 |
| `benchmark` | `ExperimentConfig`, `run_experiment()`, `compare_runs()` | results in `data/results/<run_id>/` |
| `reports` | `render_benchmark_report()`, `render_study_report()` | Markdown/HTML/CSV/JSON |

---

## 4. Code level (C4 level 4) — the adapter interface

```mermaid
classDiagram
    class ThoraxModel {
        <<protocol>>
        +id: str
        +capabilities() Capabilities
        +prepare(study: Study, request: AnalysisRequest) PreparedInput
        +infer(prepared: PreparedInput, request: AnalysisRequest) RawOutput
        +parse(raw: RawOutput) FindingsReport
        +available() bool
    }
    class OllamaModel {
        +model_tag: str
        +view: ViewBuilder
        +prompt: PromptTemplate
    }
    class HttpServiceModel {
        +base_url: str
        +service: "ct_clip | m3d_lamed | ct_chat | radfm | huatuo"
    }
    class HeuristicModel {
        +deterministic HU-cue baseline
    }
    ThoraxModel <|.. OllamaModel
    ThoraxModel <|.. HttpServiceModel
    ThoraxModel <|.. HeuristicModel
    class FindingsReport {
        +study_quality
        +findings: list~Finding~
        +negative_findings
        +incidental_findings
        +impression
        +urgent_flags
        +uncertainty
        +abstain: bool
    }
    ThoraxModel ..> FindingsReport
```

---

## 5. Flowcharts

### 5.1 Acquisition (§8)

```mermaid
flowchart TD
    A[configs/datasets/&lt;id&gt;.yaml] --> B{status approved*?}
    B -- no --> X[PolicyError: refuse to download]
    B -- yes --> C{budget left in data/?}
    C -- no --> Y[BudgetError]
    C -- yes --> D[Official API: TCIA NBIA getSeries / getImage]
    D --> E[unzip into data/raw/&lt;id&gt;/&lt;patient&gt;/&lt;series&gt;/ read-only]
    E --> F[sha256 manifest + license snapshot]
    F --> G[DICOM tag audit: de-identification sanity check]
    G --> H[normalized study index data/index/&lt;id&gt;.json]
    H --> I[manifests/datasets/&lt;id&gt;.json committed: counts + hashes only]
```

### 5.2 Single-study analysis (`thoraxbench analyze`, §18)

```mermaid
flowchart LR
    S[DICOM folder] --> D1[discover series<br/>headers only]
    D1 --> D2[select chest CT series<br/>deterministic, reason recorded]
    D2 --> D3[geometry: sort, spacing,<br/>duplicates, gaps]
    D3 --> D4[HU volume + QC]
    D4 --> Q{QC adequate?}
    Q -- no --> AB[abstain with reasons]
    Q -- yes --> P1[lung/body masks<br/>HU cues]
    P1 --> P2[sampling strategy S1–S6]
    P2 --> P3[model view: windows,<br/>MIP slabs, coronal]
    P3 --> M[model adapter<br/>Ollama / 3D service / heuristic]
    M --> PA[parse → FindingsReport]
    PA --> R1[result.json + provenance]
    PA --> R2[clinical Markdown report<br/>term, severity, treatment,<br/>prevalence, follow-up]
```

### 5.3 Benchmark with sealed validation (§14–§16)

```mermaid
flowchart TD
    E[experiment YAML] --> F{phase}
    F -- development --> G[CaseGuard: development IDs only]
    F -- sealed --> H{config frozen?<br/>hash matches freeze file<br/>and --unseal given}
    H -- no --> Z[SealedAccessError]
    H -- yes --> I[CaseGuard: sealed IDs]
    G --> J[run model per case<br/>resume, measure perf]
    I --> J
    J --> K[predictions.jsonl]
    K --> L[score tasks A–G<br/>bootstrap CIs]
    L --> M[calibration fit<br/>development only]
    M --> N[benchmark report<br/>MD + HTML + CSV + JSON]
    N --> O[compare runs]
```

### 5.4 Split creation and sealing

```mermaid
flowchart LR
    A[study index] --> B[group by patient]
    B --> C[stratify by primary label]
    C --> D[deterministic order:<br/>sha256 of salt + patient ID]
    D --> E[80 % development<br/>split into calibration/internal-test]
    D --> F[20 % sealed validation]
    F --> G[data/sealed/&lt;dataset&gt;.json<br/>IDs, read-only]
    F --> H[manifests/splits/&lt;dataset&gt;.json<br/>hashed IDs + counts]
    E --> I[data/splits/&lt;dataset&gt;.json]
```

### 5.5 Radiologist-style reading model

The preprocessing imitates how radiologists read chest CT (see `docs/reading_practice.md`):
a fixed search pattern by anatomy, several standard windows (lung, mediastinum, bone),
thin-slab MIPs for nodules, coronal reformats for craniocaudal extent, and deterministic HU
measurements. These measurements (emphysema %LAA-950, fluid-density pleural collections,
dense calcifications) are recorded as *evidence cues*. The model gets the cues as context but
they are never counted as a model finding on their own.

```mermaid
flowchart TD
    V[HU volume] --> W1[lung window -600/1500]
    V --> W2[mediastinal window 40/400]
    V --> W3[bone window 400/1800]
    V --> M1[lung mask -400 HU]
    M1 --> C1[%LAA-950 emphysema cue]
    M1 --> C2[high-density lung clusters → nodule/consolidation candidates]
    V --> C3[fluid 0–20 HU dependent pleural collections]
    V --> C4[calcium &gt;130 HU in vessel/coronary region]
    W1 & W2 & W3 --> R[multi-window RGB slices + MIP slabs + coronal]
    C1 & C2 & C3 & C4 --> K[cue summary in prompt + report evidence]
    R --> MOD[model]
    K --> MOD
```

---

## 6. Deployment view

Everything runs on one workstation. There is no Docker image (dropped at the user's request);
the framework is a Python package installed with `uv`.

```mermaid
flowchart LR
    subgraph Workstation
        U[Browser] -->|127.0.0.1:8000| W[thoraxbench serve]
        T[Terminal] --> C[thoraxbench CLI]
        W --> L[thoraxbench core]
        C --> L
        L -->|localhost:11434| O[Ollama + GPU]
        L -.optional.-> S[3D model service :8011-8014]
        L --> D[(data/ 10 GB budget)]
    end
```

---

## 7. Cross-cutting decisions

| Concern | Decision |
|---|---|
| Reproducibility | Every run writes `run.json` with git commit, config/prompt/preprocess/split hashes, model digest, hardware, driver (§24). |
| Determinism | No random slice selection; Ollama `temperature=0`, `seed=0`. |
| Safety | Disclaimer in CLI output, UI banner and every report; abstention is a first-class result. |
| Privacy | No telemetry; logs redact paths/DICOM values; only de-identified research data. |
| Extensibility | New model = YAML in `configs/models/` + adapter class; new dataset = YAML + label loader. |
| Testing | Synthetic DICOM phantoms; Ollama mocked via `respx`; Playwright for the UI. |
