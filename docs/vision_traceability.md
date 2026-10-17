# Vision traceability

Research use only. This self-made tool is not professional medical advice. Its findings
may be incorrect, incomplete or misleading. Do not use them for diagnosis or treatment.

**Date:** 2026-10-17 (detector, queued review, calibration fitting and bounded protocol checks).
**Base:** integrated `76927e9` (v0.4.8), full gate and GitHub CI green, plus the source-grouping
regression in this follow-up. Historical measurements retain their recorded versions.

## Purpose

This table maps every numbered section of [`Vision.md`](../Vision.md) (§1–§36) to the
current repository. Each status is based on code and tests, not on claims in other
documents. Use it for the WP12 self-review gate in [`docs/plan.md`](plan.md).

A passing test proves software behavior on synthetic data. It does not prove model
accuracy or clinical usefulness. Real-data evidence comprises E000's HU-heuristic development baseline and a two-study
calibration-only Q4/Q8 readiness smoke ([`docs/results.md`](results.md)). Q4 abstained twice;
Q8 missed the reference nodule in its only scorable response and truncated the other.
Later Q4/P2 diagnostics produced parseable responses but copied heuristic candidates and
cited invalid image numbers. The corrected uniform run used two images, 49.6 s and 2/3
known-reference prediction coverage. New constrained-positive validation makes unsupported
positives unavailable. The heuristic-context ablation abstained 4/4 with null verdicts.
E001-coverage showed the earlier diagnostics placed few or no reference lesions on attached
images. The strict P5/E001-schema runs with 96 % geometric lesion coverage produced
schema-valid, in-range output (Q8 20/20, Q4 18/20 usable) but constant or uninformative
answers on ten LIDC calibration studies. No result establishes clinical accuracy or generalization. The newer MONAI detector
provides sourced candidates and offline review: three calibration studies at the existing
0.5 cutoff produced eleven proposals, eight reference matches and three unmatched. LIDC
training overlap is known. Bounded S1/S2/T2/P6 readiness failures and S3 description
observations are recorded in `docs/model-usage-review-2026-10-17.md`.

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Implemented in `src/` and covered by tests. |
| 🔄 | Partially implemented. The gap column names what is missing. |
| ⏳ | Open. No working implementation in `src/`. |
| ✖ | Dropped by a recorded user decision (`docs/plan.md` → *Key decisions*). |
| n/a | Reference-only section (citations, evidence, statement, superseded order). |

"Library + tests" means the code exists and unit tests pass, but no CLI or UI workflow
applies it to real result sets yet.

## How to update this file

1. Update the affected row in the same change that alters the implementation.
2. Cite only paths that exist, except paths named explicitly as missing. Run this check
   from the repository root. It prints every cited path that does not exist:

   ```bash
   grep -oE '`[^` ]+`' docs/vision_traceability.md | tr -d '`' \
     | grep -E '/|\.(py|md|yaml|sh|json)$' | sort -u \
     | while read -r p; do [ -e "$p" ] || echo "missing: $p"; done
   ```

   Every printed path must appear in a row as a missing item.
3. Base the status on code and tests. Do not copy status from other documents.
4. Never cite or read any path under `data/sealed/`. Cite `manifests/splits/` instead.
5. Update the date line and the *Gaps ranked* list.

**Checkpoint:** 36 rows, one per Vision section, and every cited path exists.
**Recovery:** if a path moved, cite the new path. If it was removed, downgrade the status.

## Traceability table

| Vision § | Title | Status | Evidence | Gap / next action |
|---|---|---|---|---|
| 1 | Vision | 🔄 | End-to-end single-study chain: `src/thoraxbench/analysis.py`, `src/thoraxbench/cli/main.py` (`analyze`), `src/thoraxbench/api/app.py`; `tests/e2e/test_mvp_cli.py`, `tests/integration/test_analysis.py` | Cohort scoring exists for the development split (`thoraxbench benchmark`, `src/thoraxbench/benchmark/`); E000 and the separately configured calibration-only E001-smoke are recorded. RQ1 has an interim calibration-only report in `docs/model-usage-review-2026-10-17.md`; generalization remains open. |
| 2 | Core principles | 🔄 | Local-first: `src/thoraxbench/adapters/factory.py` (`require_local_endpoint`), `tests/unit/test_local_endpoints.py`. Study-level HU volumes: `src/thoraxbench/dicom/volume.py`. Provenance: `src/thoraxbench/provenance.py`. Patient-level split and sealed guard: `src/thoraxbench/splits/split.py`, `src/thoraxbench/splits/guard.py`, `tests/unit/test_splits.py`, `tests/integration/test_index.py`. License registry: `configs/datasets/`, `src/thoraxbench/registry/datasets.py`. Data gate: `scripts/check_no_medical_data.sh` | Analysis records available dataset/split manifests, reference-index bytes, scoring/schema source and prepared input hashes. Missing source files stay unavailable; these hashes do not validate labels or resolve pretraining overlap. Validation and external-test sets are defined only as phases, not used. |
| 3 | Initial research questions | ⏳ | Building blocks only: MedGemma configs `configs/models/medgemma1.5-q4.yaml`, `configs/models/medgemma1.5-q8.yaml`; sampling `src/thoraxbench/sampling/strategies.py`; calibrators `src/thoraxbench/calibration/calibrators.py` | RQ1 has bounded negative/limited-signal evidence; full accuracy and RQ2–RQ6 remain open. The benchmark runner exists; Full MedGemma sweeps E001–E004 remain gated; distinct readiness configurations have recorded runs. A two-study calibration-only MedGemma readiness run is recorded in `docs/results.md`; full E001–E004 and accuracy evaluation remain open. |
| 4 | Model portfolio | 🔄 | Tier A: `src/thoraxbench/adapters/ollama.py`, `configs/models/medgemma1.5-q4.yaml`, `configs/models/medgemma1.5-q8.yaml`, `configs/models/medgemma1.5-bf16.yaml`. Tier B/C contract: `src/thoraxbench/adapters/http_service.py`, `configs/models/ct-clip.yaml`, `configs/models/ct-chat.yaml`, `configs/models/m3d-lamed-4b.yaml`, `configs/models/radfm.yaml`, `configs/models/huatuo-vision-7b.yaml`. Tier D controls: `configs/models/gemma3-4b.yaml`, `configs/models/qwen3-vl-4b.yaml`. Tests: `tests/unit/test_adapters.py`. Research: `docs/model_cards.md`, `docs/model_selection.md` | Optional supervised MONAI detector: `src/thoraxbench/adapters/monai_detector.py`, `configs/experiments/E013_luna16_bundle.yaml`; local sourced review is implemented. No Tier B/C service process exists in the repository; those models report "unavailable". BF16 does not fit the 8 GB GPU. CT-CLIP weights are gated (`pending_access`). |
| 5 | Dataset strategy | 🔄 | 16 registry entries in `configs/datasets/` (e.g. `configs/datasets/ct_rate.yaml`, `configs/datasets/lidc_idri.yaml`, `configs/datasets/nsclc_radiogenomics.yaml`, `configs/datasets/mosmeddata_covid19_1110.yaml`, `configs/datasets/deeplesion.yaml`); pilot manifests `manifests/datasets/lidc_idri.json`, `manifests/datasets/nsclc_radiogenomics.json`; `docs/datasets.md` | CT-RATE (the primary dataset) is `pending_access`. Only LIDC-IDRI (60 patients) and NSCLC-Radiogenomics (27 patients) are on disk. RadGenome and MosMed are not acquired. |
| 6 | Data registry | ✅ | `src/thoraxbench/registry/datasets.py` (`DatasetStatus`, `require_acquirable`); `configs/datasets/`; `tests/unit/test_registry.py`, `tests/unit/test_registry_repo.py`, `tests/unit/test_pilot_split.py` (license check before scan) | Adds status `pending_access` beyond the Vision list. The gate guards `acquire`, `split` and `index` (see §8). |
| 7 | Repository and data layout | 🔄 | `src/thoraxbench/` package (cli, dicom, preprocess, sampling, adapters, schemas, calibration, scoring, reports, api); `configs/datasets/`, `configs/models/`, `configs/prompts/`; `manifests/datasets/`, `manifests/splits/`; `docs/architecture.md`, `docs/datasets.md`, `docs/model_cards.md`; `.gitignore`; `uv.lock`; `LICENSE` | Present since this refresh: `SECURITY.md`, `DATA_POLICY.md`, `docs/reproducibility.md`, `docs/results.md`, `configs/experiments/`, `src/thoraxbench/acquisition/` (the Vision ingest role), `src/thoraxbench/benchmark/`. Missing: `configs/preprocessing/`, `scripts/acquire/`, `scripts/verify/`, `scripts/benchmark/` (the CLI commands cover these roles), `experiments/`, `manifests/models/`. The operational guide is now `docs/benchmarking.md`. `docker-compose.yml` and `.env.example` are ✖ (Docker dropped). Data lives in `./data/`, not `/data/thoraxbench/`. |
| 8 | Acquisition pipeline | 🔄 | `thoraxbench acquire`: `src/thoraxbench/cli/acquire.py`, `src/thoraxbench/acquisition/` (license, per-series license URI, split and budget gates; NBIA download; checksums; manifests). Registry gate: `src/thoraxbench/registry/datasets.py`. Tests: `tests/unit/test_acquisition.py`, `tests/integration/test_acquire.py`. Pilot manifests: `manifests/datasets/lidc_idri.json`, `manifests/datasets/nsclc_radiogenomics.json` | TCIA/NBIA only; Hugging Face and other hosts have no acquirer. The pilot was first downloaded outside the CLI. The de-identification audit is a separate command (`privacy audit`), not an acquisition step. |
| 9 | DICOM / volume preprocessing | 🔄 | Discovery and series selection: `src/thoraxbench/dicom/discovery.py`. Geometry, HU, QC: `src/thoraxbench/dicom/volume.py`. Access guard: `src/thoraxbench/study_access.py`. Views `medgemma_ct_v1`, `generic_multislice_v1`, `ct_clip_v1`, `m3d_lamed_v1`: `src/thoraxbench/views/builders.py`. Windows: `src/thoraxbench/preprocess/windows.py`. Tests: `tests/unit/test_dicom.py`, `tests/unit/test_preprocess.py`, `tests/unit/test_study_sampling_views.py` | Functional and tested on synthetic phantoms. Equivalence with the official MedGemma notebook and CT-CLIP/M3D reference normalization is not verified against reference outputs. Body-region confidence is a lung-voxel fraction only. |
| 10 | Input sampling experiments for MedGemma | ✅ | S1–S6 and MIP slabs: `src/thoraxbench/sampling/strategies.py` (`Uniform`, `LungExtent`, `AnatomyBalanced`, `TwoStage`, `MipSlabs`, `ContactSheet`); `src/thoraxbench/preprocess/masks.py`, `src/thoraxbench/preprocess/reformat.py`; `tests/unit/test_study_sampling_views.py` | Strategies exist and are hashed into provenance. Geometric reference-lesion coverage per strategy × n × slab is measured without a model (`thoraxbench coverage`, `src/thoraxbench/benchmark/coverage.py`, `tests/unit/test_benchmark_coverage.py`; E001-coverage in `docs/results.md`). Model-based comparison is E002/E003 (§26), which is open. |
| 11 | Standardized output schema | ✅ | `src/thoraxbench/schemas/findings.py`, `src/thoraxbench/parsing/findings.py`, `src/thoraxbench/parsing/json_extract.py`; `tests/unit/test_prompts_parsing.py`, `tests/unit/test_schemas_ontology.py` | Abstention and uncertain presence are supported. Keep empty predictions as abstention (`src/thoraxbench/analysis.py`). |
| 12 | Initial abnormality ontology | ✅ | `src/thoraxbench/ontology/labels.yaml` (categories, `native` mappings to CT-RATE/LIDC/NSCLC terms), `src/thoraxbench/ontology/labels.py`; `tests/unit/test_schemas_ontology.py` | Full mapping to all 18 CT-RATE labels cannot be checked against data until CT-RATE access exists. |
| 13 | Benchmark tasks | 🔄 | Tasks A–G: `src/thoraxbench/scoring/classification.py`, `src/thoraxbench/scoring/calibration_metrics.py`, `src/thoraxbench/scoring/lesions.py`, `src/thoraxbench/scoring/segmentation.py`, `src/thoraxbench/scoring/report.py`, `src/thoraxbench/scoring/vqa.py`, `src/thoraxbench/scoring/safety.py`; `tests/unit/test_scoring.py` | `src/thoraxbench/benchmark/runner.py` applies tasks A, B, E and G to development cases (`tests/integration/test_benchmark.py`). Task C is wired for detector millimetre candidates (`tests/integration/test_detector_benchmark.py`). Tasks D and F have no runner caller yet. RadGraph-style scoring is not implemented. |
| 14 | Calibration versus training | 🔄 | No fine-tuning code (weights frozen). Calibrators with sealed-phase refusal: `src/thoraxbench/calibration/calibrators.py` (`fit_thresholds`, `TemperatureScaler`, `PlattCalibrator`, `IsotonicCalibrator`, `AbstentionRule`); `tests/unit/test_calibration_perf_provenance.py` | Opt-in fit/apply integration: `src/thoraxbench/benchmark/calibration.py`, `tests/unit/test_benchmark_calibration.py`. Fit calibration only; apply internal-test only; retain raw metrics. No real-model calibration fit is claimed. |
| 15 | Proposed split policy | 🔄 | `src/thoraxbench/splits/split.py` (patient-level, stratified, salted hashes), `src/thoraxbench/splits/pilot.py` (label-independent pilot split), frozen manifests `manifests/splits/lidc_idri.json`, `manifests/splits/nsclc_radiogenomics.json`; `tests/unit/test_splits.py`, `tests/unit/test_pilot_split.py` | Pilot split is pseudorandom and label-independent by user decision, not stratified. CT-RATE official-split handling is not implemented (no access). No whole dataset is formally reserved as the external test set. |
| 16 | Leakage controls | 🔄 | `src/thoraxbench/scoring/overlap.py` (`possible_training_overlap`, `KNOWN_TRAINING_DATA`); `tests/unit/test_scoring.py` (`test_training_overlap`); parent/derived notes in `configs/datasets/radgenome_chestct.yaml` | Dataset-aware overlap reaches Markdown, HTML/CSV and export manifests (`src/thoraxbench/benchmark/exports.py`, `tests/integration/test_benchmark_exports.py`). Historical missing flags stay unknown. Cross-source patient mapping remains open. |
| 17 | Model adapter API | 🔄 | `ThoraxModel` protocol with `prepare/infer/parse/capabilities`: `src/thoraxbench/adapters/base.py`; `Capabilities`: `src/thoraxbench/schemas/model_io.py`; Ollama: `src/thoraxbench/adapters/ollama.py`; HTTP service: `src/thoraxbench/adapters/http_service.py`; heuristic baseline: `src/thoraxbench/adapters/heuristic.py`; `tests/unit/test_adapters.py`, `tests/unit/test_local_endpoints.py` | Contract done. No 3D service implementation is in the repository. Containers are ✖ (Docker dropped); services are planned as plain local processes. |
| 18 | End-to-end user workflow | 🔄 | `thoraxbench analyze`, `index`, `split`, `models`, `datasets`, `demo-data`, `serve`: `src/thoraxbench/cli/main.py`; `acquire`, `benchmark`, `privacy audit`: `src/thoraxbench/cli/`. Web UI: `src/thoraxbench/api/app.py`, `src/thoraxbench/api/templates/index.html`, `src/thoraxbench/api/static/app.js`; exploratory model comparison `/api/compare`; reports `src/thoraxbench/reports/html_report.py`. Tests: `tests/e2e/test_mvp_cli.py`, `tests/e2e/test_web_ui.py`, `tests/integration/test_api.py`. Concept: `docs/ui.md` | `thoraxbench benchmark` runs the development split (`src/thoraxbench/cli/benchmark.py`); `--unseal` is refused. CLI `compare` is ⏳. `--request` option is not implemented. UI steps 8–9 (reference overlays, reference-label scores) are open. `/api/compare` is exploratory and computes no accuracy. |
| 19 | Prompt strategy | ✅ | `configs/prompts/P0.yaml` … `configs/prompts/P4.yaml` (versioned); `src/thoraxbench/prompts/templates.py`, `src/thoraxbench/prompts/schema.py`; prompt hash in provenance (`src/thoraxbench/analysis.py`); `tests/unit/test_prompts_parsing.py` | Prompts are versioned and hashed. P5 adds a strict fixed-length schema (`strict_findings_json_schema`, probed against Ollama 0.40.4) and one-based `IMAGE k` captions (`caption_style: image_only`). Comparing prompts on calibration data and freezing a winner is E004 (§26), which is open. |
| 20 | Confidence handling | 🔄 | Raw confidence kept and missing confidence shown as uncertain: `src/thoraxbench/parsing/findings.py`, `src/thoraxbench/reports/study_report.py`, `tests/e2e/test_web_ui.py`. Threshold fitting: `src/thoraxbench/calibration/calibrators.py` | Reports use a fixed `PRESENT_THRESHOLD = 0.5` in `src/thoraxbench/reports/study_report.py`. Optional benchmark fitting is implemented with synthetic direction tests; no real-model fitted thresholds are claimed. No model is ranked by calibration yet. |
| 21 | Performance measurements | 🔄 | `src/thoraxbench/perf.py` (`PerfRecord`, `measure`, `throughput_per_hour`, `summarize`); used by `src/thoraxbench/analysis.py`; `tests/unit/test_calibration_perf_provenance.py` | GPU memory is an `nvidia-smi` snapshot, not a true peak. `analyze` does not fill model VRAM or disk size. The benchmark records runtimes only; no aggregate plots (metric vs. VRAM/latency). |
| 22 | Hardware target | n/a | Current host: RTX A2000 Laptop, 8 GB VRAM, 31 GB RAM (`docs/plan.md` → *Environment facts*). 40 GB runner proposal: `docs/lan-runner.md` | Reference target. The current GPU is below the §22 minimum (~12 GB). LAN inference is not implemented; the loopback guard stays. |
| 23 | Storage strategy | 🔄 | `.gitignore` blocks `data/`, DICOM, NIfTI, weights; `scripts/check_no_medical_data.sh`; checksum and license snapshots in `manifests/datasets/`; regenerable HU cache `src/thoraxbench/study.py`; budget setting `src/thoraxbench/config.py` (`DEFAULT_BUDGET_GB`) | `thoraxbench acquire` enforces the 10 GB budget for its own downloads only; other commands do not. `acquire` refuses to overwrite an incomplete existing series; there is no general raw-data immutability check. Suggested separate mounts are not used. |
| 24 | Reproducibility | 🔄 | `src/thoraxbench/provenance.py` (`RunProvenance` with git commit, hashes, seed, GPU, driver, CUDA, `fingerprint`); filled in `src/thoraxbench/analysis.py`; experiment freeze `src/thoraxbench/splits/guard.py` (`freeze_experiment`, `verify_freeze`); `tests/unit/test_calibration_perf_provenance.py`, `tests/unit/test_splits.py` | New analysis records available manifest/reference/scoring/input hashes; Ollama provider settings, rendered text and decoded response diagnostics are retained with image hashes instead of bytes; fingerprints include software version and model ID. `src/thoraxbench/benchmark/checkpoint.py` preserves immutable terminal artifacts, an identity manifest and atomic checksummed progress; strict `--resume` reuses pending work only. No image bytes are stored in case JSON. Historical raw responses remain unavailable. `container_digest` is unused; freeze is not CLI-reachable. |
| 25 | Benchmark report | 🔄 | Cohort Markdown report `src/thoraxbench/benchmark/report.py` (final report.md/result.json); durable case artifacts/checkpoints `src/thoraxbench/benchmark/checkpoint.py`; per-study reports `src/thoraxbench/reports/study_report.py`, `src/thoraxbench/reports/html_report.py`; `tests/integration/test_benchmark.py`, `tests/unit/test_study_report.py`, `tests/unit/test_html_report.py` | The benchmark report covers a subset of the 20 listed sections. HTML/CSV export and read-only run comparison exist (`src/thoraxbench/benchmark/exports.py`, `src/thoraxbench/benchmark/compare.py`). Further report sections and plots remain open. |
| 26 | First experimental matrix | 🔄 | `configs/experiments/` (E000 heuristic baseline, E001–E004 MedGemma, separate E001-smoke); `tests/unit/test_benchmark_config.py`; E000 and E001-smoke recorded in `docs/results.md` | E000 is the pipeline control. Full E001–E004 remain unrun; the separate calibration-only smoke establishes poor usable-output readiness, not comparative accuracy. E005–E008 are blocked planning configurations; their runtime/access prerequisites remain unmet. |
| 27 | Data acquisition phases | 🔄 | Phase A pilot on disk (LIDC-IDRI 60 patients, NSCLC-Radiogenomics 27 patients): `manifests/datasets/lidc_idri.json`, `manifests/datasets/nsclc_radiogenomics.json`; development indexing `src/thoraxbench/index.py`, `tests/integration/test_index.py` | Phase A goal (ingest → … → score → report on real data) is met for the E000 heuristic baseline (`docs/results.md`). One of four VLM case/variant outcomes in the separate E001-smoke was scorable and missed its reference nodule; this does not establish model accuracy. No CT-RATE studies. Phases B and C are open. |
| 28 | Safety and intended use | ✅ | `DISCLAIMER` in `src/thoraxbench/analysis.py`; UI text in `src/thoraxbench/api/templates/index.html`; reports `src/thoraxbench/reports/study_report.py`, `src/thoraxbench/reports/html_report.py`; tests `tests/integration/test_analysis.py`, `tests/unit/test_study_report.py`, `tests/e2e/test_web_ui.py`, `tests/e2e/test_mvp_cli.py` | Keep the disclaimer on every new output (benchmark reports, `compare`). Only de-identified research data is used. |
| 29 | Privacy and security | 🔄 | Loopback-only inference and no proxy/redirect following: `src/thoraxbench/adapters/factory.py`, `tests/unit/test_local_endpoints.py`. No telemetry code. Secrets ignored in `.gitignore`. Results-path and symlink checks: `src/thoraxbench/reports/html_report.py` (`require_results_path`). DICOM header audit (keywords only, PS3.15 Basic Profile subset) and path/identifier redaction of results, reports and CLI errors: `src/thoraxbench/privacy.py`, `thoraxbench privacy audit`, `tests/unit/test_privacy.py` | Selected direct header values are collected in memory on source/cache loads and redacted from analysis free text and metadata. No pixel/OCR check or full anonymity guarantee. Pseudonym keys, series UIDs and local caches/indexes remain unchanged. |
| 30 | GitHub strategy | ✅ | Data gate `scripts/check_no_medical_data.sh` in `localPipeline.sh` and `.github/workflows/local-pipeline.yml`; hash-only split manifests `manifests/splits/`; code, prompts, registry and docs committed | Repository is public by user decision (supersedes "private"). Aggregate results without case-level data are committed in `docs/results.md`. |
| 31 | Milestones | 🔄 | See per-milestone notes. Bootstrap: `pyproject.toml`, `localPipeline.sh`, `.github/workflows/local-pipeline.yml`. MVP record: `docs/mvp-test.md` | M0 ✅ (Docker Compose ✖). M1 ✅ (transport smoke only). M2 ✅. M3 🔄 (LIDC/NSCLC pilot instead of CT-RATE; E000 recorded; E001–E004 configured, not run). M4 🔄 (annotations parsed in `src/thoraxbench/labels/lidc.py`, lesion scoring library; external evaluation ⏳). M5 ⏳. M6 🔄 (UI, study browser, model selector, exploratory side-by-side; benchmark report in CLI only). M7 ⏳. |
| 32 | Definition of success for v1 | 🔄 | See §6, §9, §15, §21, §24 rows | Met: 1 (approved local dataset, guarded), 2 (local inference), 3 (reproducible preprocessing), 5 (patient-level separation), 10 (license/provenance registry). Partial: 6 (tasks A/B/E/G applied to development cases; C/D/F remain unwired), 7 (latency yes, VRAM partial), 8 (single-study review, no cohort review), 9 (available manifests/input/scoring hashes and durable artifacts now recorded; historical artifacts and unknown source identities remain limited). Open: 4 (CT-CLIP and a native-3D generative model not runnable). |
| 33 | Immediate implementation order | n/a | Superseded by `docs/plan.md` (work packages WP0–WP13) | Steps 1–10 and 15 are done in adapted form. Steps 11–14 and 16 are open. |
| 34 | Initial source registry / references | n/a | Source URLs and license snapshots in `configs/datasets/` and `manifests/datasets/`; model sources in `docs/model_cards.md` | Reference list. Re-verify terms before any new acquisition. |
| 35 | Current evidence guiding the project | n/a | Reference only | No action. Do not cite these external results as ThoraxBench measurements. |
| 36 | Final project statement | n/a | Reference only | Traceability from study to score exists per study; cohort-level traceability exists for benchmark runs (manifest hashes, per-case fingerprints). |

## Summary

| Status | Count |
|---|---|
| ✅ implemented | 7 (§6, §10, §11, §12, §19, §28, §30) |
| 🔄 partial | 23 (§1, §2, §4, §5, §7, §8, §9, §13–§18, §20, §21, §23–§27, §29, §31, §32) |
| ⏳ open | 1 (§3) |
| ✖ dropped | 0 whole sections (Docker items inside §7, §17, §24, §31) |
| n/a reference-only | 5 (§22, §33, §34, §35, §36) |

## Gaps ranked

1. **Useful-output reliability and runtime parity** (§1, §3, §27, §32). The supervised
   detector supplies reviewable locations, but LIDC overlaps its training set. MedGemma
   categorical and citation readiness remain unreliable. Some image signal exists;
   constant answers alone do not establish a broken image path. Complete expanded
   calibration controls and approved official-runtime parity before enabling VLM filtering.
2. **Remaining benchmark workflow** (§13, §18, §25, §26). Task C, cohort HTML/CSV export,
   read-only comparison and Evaluation are implemented. CLI `compare`, Tasks D/F,
   additional report plots and a reviewed sealed-evaluation workflow remain open.
3. **Acquisition beyond TCIA** (§8, §23, §27). Approved NBIA collections work under
   license, split, budget and checksum gates. Other hosts have no acquirer.
4. **3D generative comparators and CT-RATE access** (§4, §5, §12, §15, §17, §32).
   CT-CLIP/M3D/CT-CHAT services are not runnable here. Gated weights remain inaccessible;
   E005–E008 planning configs refuse execution before study access.
5. **Remaining provenance and leakage limits** (§2, §7, §16, §24, §32.9). Model manifests,
   available data/reference/input hashes, raw case responses and strict checkpoints exist.
   Missing historical identities cannot be invented. Training-overlap flags are exported;
   cross-source patient linkage and a CLI freeze workflow remain open.
6. **Calibration readiness** (§14, §20). Opt-in fitting is wired and tested on synthetic
   records. Fits see calibration only, application sees internal-test only. No real-model
   fitted accuracy or calibration benefit is claimed while output readiness fails.
7. **Privacy limits** (§29). Header audit and selected direct-value/path redaction exist.
   Pixel-level burned-in text, unmatched free text and ad hoc pseudonym keys remain limits.
   This is not de-identification.
8. **LAN inference / larger GPU** (§22). Documentation only in `docs/lan-runner.md`.
   Preserve the loopback guard. UI reference overlays remain deferred; the read-only
   Evaluation section already shows stored reference-label scores without re-rendering images.

## Historical index-boundary evidence

The E000 record notes five pre-rebuild NSCLC index entries outside development. A
metadata-only review found that all three preserved benchmark results (E000, legacy E001
and E001-smoke) used rebuilt indexes with zero outside-development entries. No historical
index copy was found among current index JSON files. This does not establish whether the
five earlier entries were ever read or processed, or whether they were sealed rather than
unknown. Preserve that uncertainty; do not claim that rebuilding retroactively resolves
leakage. See [the audit scope and limits](benchmarking.md#8-historical-index-boundary-audit).
No raw or sealed patient data was opened for this check.
