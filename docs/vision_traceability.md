# Vision traceability

Research use only. This self-made tool is not professional medical advice. Its findings
may be incorrect, incomplete or misleading. Do not use them for diagnosis or treatment.

**Date:** 2026-10-16 (WP12; guarded benchmark fixes and calibration readiness evidence).
**Base:** `main` @ `3af797f` (v0.3.8); measured run used a clean tree.

## Purpose

This table maps every numbered section of [`Vision.md`](../Vision.md) (§1–§36) to the
current repository. Each status is based on code and tests, not on claims in other
documents. Use it for the WP12 self-review gate in [`docs/plan.md`](plan.md).

A passing test proves software behavior on synthetic data. It does not prove model
accuracy or clinical usefulness. Real-data evidence comprises E000's HU-heuristic development baseline and a two-study
calibration-only Q4/Q8 readiness smoke ([`docs/results.md`](results.md)). Q4 abstained twice;
Q8 missed the reference nodule in its only scorable response and truncated the other.
Neither establishes clinical accuracy or generalization.

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
| 1 | Vision | 🔄 | End-to-end single-study chain: `src/thoraxbench/analysis.py`, `src/thoraxbench/cli/main.py` (`analyze`), `src/thoraxbench/api/app.py`; `tests/e2e/test_mvp_cli.py`, `tests/integration/test_analysis.py` | Cohort scoring exists for the development split (`thoraxbench benchmark`, `src/thoraxbench/benchmark/`); E000 and the separately configured calibration-only E001-smoke are recorded. Questions 1–7 have no measured answer yet. |
| 2 | Core principles | 🔄 | Local-first: `src/thoraxbench/adapters/factory.py` (`require_local_endpoint`), `tests/unit/test_local_endpoints.py`. Study-level HU volumes: `src/thoraxbench/dicom/volume.py`. Provenance: `src/thoraxbench/provenance.py`. Patient-level split and sealed guard: `src/thoraxbench/splits/split.py`, `src/thoraxbench/splits/guard.py`, `tests/unit/test_splits.py`, `tests/integration/test_index.py`. License registry: `configs/datasets/`, `src/thoraxbench/registry/datasets.py`. Data gate: `scripts/check_no_medical_data.sh` | `analyze` leaves `dataset_manifest_hash` and `split_manifest_hash` empty. Ground-truth and scoring versions are not recorded, also not in benchmark runs. Validation and external-test sets are defined only as phases, not used. |
| 3 | Initial research questions | ⏳ | Building blocks only: MedGemma configs `configs/models/medgemma1.5-q4.yaml`, `configs/models/medgemma1.5-q8.yaml`; sampling `src/thoraxbench/sampling/strategies.py`; calibrators `src/thoraxbench/calibration/calibrators.py` | RQ1–RQ6 are unanswered. The benchmark runner exists; MedGemma experiments E001–E004 (`configs/experiments/`) have no recorded run (WP11). A two-study calibration-only MedGemma readiness run is recorded in `docs/results.md`; full E001–E004 and accuracy evaluation remain open. |
| 4 | Model portfolio | 🔄 | Tier A: `src/thoraxbench/adapters/ollama.py`, `configs/models/medgemma1.5-q4.yaml`, `configs/models/medgemma1.5-q8.yaml`, `configs/models/medgemma1.5-bf16.yaml`. Tier B/C contract: `src/thoraxbench/adapters/http_service.py`, `configs/models/ct-clip.yaml`, `configs/models/ct-chat.yaml`, `configs/models/m3d-lamed-4b.yaml`, `configs/models/radfm.yaml`, `configs/models/huatuo-vision-7b.yaml`. Tier D controls: `configs/models/gemma3-4b.yaml`, `configs/models/qwen3-vl-4b.yaml`. Tests: `tests/unit/test_adapters.py`. Research: `docs/model_cards.md`, `docs/model_selection.md` | No Tier B/C service process exists in the repository; those models report "unavailable". BF16 does not fit the 8 GB GPU. CT-CLIP weights are gated (`pending_access`). |
| 5 | Dataset strategy | 🔄 | 16 registry entries in `configs/datasets/` (e.g. `configs/datasets/ct_rate.yaml`, `configs/datasets/lidc_idri.yaml`, `configs/datasets/nsclc_radiogenomics.yaml`, `configs/datasets/mosmeddata_covid19_1110.yaml`, `configs/datasets/deeplesion.yaml`); pilot manifests `manifests/datasets/lidc_idri.json`, `manifests/datasets/nsclc_radiogenomics.json`; `docs/datasets.md` | CT-RATE (the primary dataset) is `pending_access`. Only LIDC-IDRI (60 patients) and NSCLC-Radiogenomics (27 patients) are on disk. RadGenome and MosMed are not acquired. |
| 6 | Data registry | ✅ | `src/thoraxbench/registry/datasets.py` (`DatasetStatus`, `require_acquirable`); `configs/datasets/`; `tests/unit/test_registry.py`, `tests/unit/test_registry_repo.py`, `tests/unit/test_pilot_split.py` (license check before scan) | Adds status `pending_access` beyond the Vision list. The gate guards `acquire`, `split` and `index` (see §8). |
| 7 | Repository and data layout | 🔄 | `src/thoraxbench/` package (cli, dicom, preprocess, sampling, adapters, schemas, calibration, scoring, reports, api); `configs/datasets/`, `configs/models/`, `configs/prompts/`; `manifests/datasets/`, `manifests/splits/`; `docs/architecture.md`, `docs/datasets.md`, `docs/model_cards.md`; `.gitignore`; `uv.lock`; `LICENSE` | Present since this refresh: `SECURITY.md`, `DATA_POLICY.md`, `docs/reproducibility.md`, `docs/results.md`, `configs/experiments/`, `src/thoraxbench/acquisition/` (the Vision ingest role), `src/thoraxbench/benchmark/`. Missing: `configs/preprocessing/`, `scripts/acquire/`, `scripts/verify/`, `scripts/benchmark/` (the CLI commands cover these roles), `experiments/`, `manifests/models/`, `docs/benchmarking.md`. `docker-compose.yml` and `.env.example` are ✖ (Docker dropped). Data lives in `./data/`, not `/data/thoraxbench/`. |
| 8 | Acquisition pipeline | 🔄 | `thoraxbench acquire`: `src/thoraxbench/cli/acquire.py`, `src/thoraxbench/acquisition/` (license, per-series license URI, split and budget gates; NBIA download; checksums; manifests). Registry gate: `src/thoraxbench/registry/datasets.py`. Tests: `tests/unit/test_acquisition.py`, `tests/integration/test_acquire.py`. Pilot manifests: `manifests/datasets/lidc_idri.json`, `manifests/datasets/nsclc_radiogenomics.json` | TCIA/NBIA only; Hugging Face and other hosts have no acquirer. The pilot was first downloaded outside the CLI. The de-identification audit is a separate command (`privacy audit`), not an acquisition step. |
| 9 | DICOM / volume preprocessing | 🔄 | Discovery and series selection: `src/thoraxbench/dicom/discovery.py`. Geometry, HU, QC: `src/thoraxbench/dicom/volume.py`. Access guard: `src/thoraxbench/study_access.py`. Views `medgemma_ct_v1`, `generic_multislice_v1`, `ct_clip_v1`, `m3d_lamed_v1`: `src/thoraxbench/views/builders.py`. Windows: `src/thoraxbench/preprocess/windows.py`. Tests: `tests/unit/test_dicom.py`, `tests/unit/test_preprocess.py`, `tests/unit/test_study_sampling_views.py` | Functional and tested on synthetic phantoms. Equivalence with the official MedGemma notebook and CT-CLIP/M3D reference normalization is not verified against reference outputs. Body-region confidence is a lung-voxel fraction only. |
| 10 | Input sampling experiments for MedGemma | ✅ | S1–S6 and MIP slabs: `src/thoraxbench/sampling/strategies.py` (`Uniform`, `LungExtent`, `AnatomyBalanced`, `TwoStage`, `MipSlabs`, `ContactSheet`); `src/thoraxbench/preprocess/masks.py`, `src/thoraxbench/preprocess/reformat.py`; `tests/unit/test_study_sampling_views.py` | Strategies exist and are hashed into provenance. Comparing them is experiment E002/E003 (§26), which is open. |
| 11 | Standardized output schema | ✅ | `src/thoraxbench/schemas/findings.py`, `src/thoraxbench/parsing/findings.py`, `src/thoraxbench/parsing/json_extract.py`; `tests/unit/test_prompts_parsing.py`, `tests/unit/test_schemas_ontology.py` | Abstention and uncertain presence are supported. Keep empty predictions as abstention (`src/thoraxbench/analysis.py`). |
| 12 | Initial abnormality ontology | ✅ | `src/thoraxbench/ontology/labels.yaml` (categories, `native` mappings to CT-RATE/LIDC/NSCLC terms), `src/thoraxbench/ontology/labels.py`; `tests/unit/test_schemas_ontology.py` | Full mapping to all 18 CT-RATE labels cannot be checked against data until CT-RATE access exists. |
| 13 | Benchmark tasks | 🔄 | Tasks A–G: `src/thoraxbench/scoring/classification.py`, `src/thoraxbench/scoring/calibration_metrics.py`, `src/thoraxbench/scoring/lesions.py`, `src/thoraxbench/scoring/segmentation.py`, `src/thoraxbench/scoring/report.py`, `src/thoraxbench/scoring/vqa.py`, `src/thoraxbench/scoring/safety.py`; `tests/unit/test_scoring.py` | `src/thoraxbench/benchmark/runner.py` applies tasks A, B, E and G to development cases (`tests/integration/test_benchmark.py`). Tasks C, D and F have no caller yet. RadGraph-style scoring is not implemented. |
| 14 | Calibration versus training | 🔄 | No fine-tuning code (weights frozen). Calibrators with sealed-phase refusal: `src/thoraxbench/calibration/calibrators.py` (`fit_thresholds`, `TemperatureScaler`, `PlattCalibrator`, `IsotonicCalibrator`, `AbstentionRule`); `tests/unit/test_calibration_perf_provenance.py` | Library + tests. No calibration has been fitted on development data for any real model. |
| 15 | Proposed split policy | 🔄 | `src/thoraxbench/splits/split.py` (patient-level, stratified, salted hashes), `src/thoraxbench/splits/pilot.py` (label-independent pilot split), frozen manifests `manifests/splits/lidc_idri.json`, `manifests/splits/nsclc_radiogenomics.json`; `tests/unit/test_splits.py`, `tests/unit/test_pilot_split.py` | Pilot split is pseudorandom and label-independent by user decision, not stratified. CT-RATE official-split handling is not implemented (no access). No whole dataset is formally reserved as the external test set. |
| 16 | Leakage controls | 🔄 | `src/thoraxbench/scoring/overlap.py` (`possible_training_overlap`, `KNOWN_TRAINING_DATA`); `tests/unit/test_scoring.py` (`test_training_overlap`); parent/derived notes in `configs/datasets/radgenome_chestct.yaml` | Library + tests only. No report or table carries the `possible_training_overlap` column. No cross-source patient-ID mapping. Leakage tracking is ⏳ in WP6. |
| 17 | Model adapter API | 🔄 | `ThoraxModel` protocol with `prepare/infer/parse/capabilities`: `src/thoraxbench/adapters/base.py`; `Capabilities`: `src/thoraxbench/schemas/model_io.py`; Ollama: `src/thoraxbench/adapters/ollama.py`; HTTP service: `src/thoraxbench/adapters/http_service.py`; heuristic baseline: `src/thoraxbench/adapters/heuristic.py`; `tests/unit/test_adapters.py`, `tests/unit/test_local_endpoints.py` | Contract done. No 3D service implementation is in the repository. Containers are ✖ (Docker dropped); services are planned as plain local processes. |
| 18 | End-to-end user workflow | 🔄 | `thoraxbench analyze`, `index`, `split`, `models`, `datasets`, `demo-data`, `serve`: `src/thoraxbench/cli/main.py`; `acquire`, `benchmark`, `privacy audit`: `src/thoraxbench/cli/`. Web UI: `src/thoraxbench/api/app.py`, `src/thoraxbench/api/templates/index.html`, `src/thoraxbench/api/static/app.js`; exploratory model comparison `/api/compare`; reports `src/thoraxbench/reports/html_report.py`. Tests: `tests/e2e/test_mvp_cli.py`, `tests/e2e/test_web_ui.py`, `tests/integration/test_api.py`. Concept: `docs/ui.md` | `thoraxbench benchmark` runs the development split (`src/thoraxbench/cli/benchmark.py`); `--unseal` is refused. CLI `compare` is ⏳. `--request` option is not implemented. UI steps 8–9 (reference overlays, reference-label scores) are open. `/api/compare` is exploratory and computes no accuracy. |
| 19 | Prompt strategy | ✅ | `configs/prompts/P0.yaml` … `configs/prompts/P4.yaml` (versioned); `src/thoraxbench/prompts/templates.py`, `src/thoraxbench/prompts/schema.py`; prompt hash in provenance (`src/thoraxbench/analysis.py`); `tests/unit/test_prompts_parsing.py` | Prompts are versioned and hashed. Comparing them on calibration data and freezing a winner is E004 (§26), which is open. |
| 20 | Confidence handling | 🔄 | Raw confidence kept and missing confidence shown as uncertain: `src/thoraxbench/parsing/findings.py`, `src/thoraxbench/reports/study_report.py`, `tests/e2e/test_web_ui.py`. Threshold fitting: `src/thoraxbench/calibration/calibrators.py` | Reports use a fixed `PRESENT_THRESHOLD = 0.5` in `src/thoraxbench/reports/study_report.py`. No thresholds are fitted on calibration data. No model is ranked by calibration yet. |
| 21 | Performance measurements | 🔄 | `src/thoraxbench/perf.py` (`PerfRecord`, `measure`, `throughput_per_hour`, `summarize`); used by `src/thoraxbench/analysis.py`; `tests/unit/test_calibration_perf_provenance.py` | GPU memory is an `nvidia-smi` snapshot, not a true peak. `analyze` does not fill model VRAM or disk size. The benchmark records runtimes only; no aggregate plots (metric vs. VRAM/latency). |
| 22 | Hardware target | n/a | Current host: RTX A2000 Laptop, 8 GB VRAM, 31 GB RAM (`docs/plan.md` → *Environment facts*). 40 GB runner proposal: `docs/lan-runner.md` | Reference target. The current GPU is below the §22 minimum (~12 GB). LAN inference is not implemented; the loopback guard stays. |
| 23 | Storage strategy | 🔄 | `.gitignore` blocks `data/`, DICOM, NIfTI, weights; `scripts/check_no_medical_data.sh`; checksum and license snapshots in `manifests/datasets/`; regenerable HU cache `src/thoraxbench/study.py`; budget setting `src/thoraxbench/config.py` (`DEFAULT_BUDGET_GB`) | `thoraxbench acquire` enforces the 10 GB budget for its own downloads only; other commands do not. `acquire` refuses to overwrite an incomplete existing series; there is no general raw-data immutability check. Suggested separate mounts are not used. |
| 24 | Reproducibility | 🔄 | `src/thoraxbench/provenance.py` (`RunProvenance` with git commit, hashes, seed, GPU, driver, CUDA, `fingerprint`); filled in `src/thoraxbench/analysis.py`; experiment freeze `src/thoraxbench/splits/guard.py` (`freeze_experiment`, `verify_freeze`); `tests/unit/test_calibration_perf_provenance.py`, `tests/unit/test_splits.py` | `dataset_manifest_hash` and `split_manifest_hash` stay empty in `analyze`; `benchmark` fills them (`src/thoraxbench/benchmark/runner.py`). `container_digest` is unused (Docker dropped). Freeze is not reachable from the CLI. |
| 25 | Benchmark report | 🔄 | Cohort Markdown report `src/thoraxbench/benchmark/report.py` (writes report.md and result.json); per-study reports `src/thoraxbench/reports/study_report.py`, `src/thoraxbench/reports/html_report.py`; `tests/integration/test_benchmark.py`, `tests/unit/test_study_report.py`, `tests/unit/test_html_report.py` | The benchmark report covers a subset of the 20 listed sections. No HTML/CSV export, plots or run comparison. |
| 26 | First experimental matrix | 🔄 | `configs/experiments/` (E001 heuristic baseline, E002–E004 MedGemma); `tests/unit/test_benchmark_config.py`; E001 run recorded in `docs/results.md` | Project E001 is a heuristic baseline, not the Vision §26 quantization comparison. E002–E004 have no recorded run. E005–E008 are not configured; E005–E007 also need 3D services. |
| 27 | Data acquisition phases | 🔄 | Phase A pilot on disk (LIDC-IDRI 60 patients, NSCLC-Radiogenomics 27 patients): `manifests/datasets/lidc_idri.json`, `manifests/datasets/nsclc_radiogenomics.json`; development indexing `src/thoraxbench/index.py`, `tests/integration/test_index.py` | Phase A goal (ingest → … → score → report on real data) is met for the heuristic baseline only (E001, `docs/results.md`); no VLM run is scored. No CT-RATE studies. Phases B and C are open. |
| 28 | Safety and intended use | ✅ | `DISCLAIMER` in `src/thoraxbench/analysis.py`; UI text in `src/thoraxbench/api/templates/index.html`; reports `src/thoraxbench/reports/study_report.py`, `src/thoraxbench/reports/html_report.py`; tests `tests/integration/test_analysis.py`, `tests/unit/test_study_report.py`, `tests/e2e/test_web_ui.py`, `tests/e2e/test_mvp_cli.py` | Keep the disclaimer on every new output (benchmark reports, `compare`). Only de-identified research data is used. |
| 29 | Privacy and security | 🔄 | Loopback-only inference and no proxy/redirect following: `src/thoraxbench/adapters/factory.py`, `tests/unit/test_local_endpoints.py`. No telemetry code. Secrets ignored in `.gitignore`. Results-path and symlink checks: `src/thoraxbench/reports/html_report.py` (`require_results_path`). DICOM header audit (keywords only, PS3.15 Basic Profile subset) and path/identifier redaction of results, reports and CLI errors: `src/thoraxbench/privacy.py`, `thoraxbench privacy audit`, `tests/unit/test_privacy.py` | No pixel-level burned-in text check. Ad hoc `PatientID` and folder names pass through to results. |
| 30 | GitHub strategy | ✅ | Data gate `scripts/check_no_medical_data.sh` in `localPipeline.sh` and `.github/workflows/local-pipeline.yml`; hash-only split manifests `manifests/splits/`; code, prompts, registry and docs committed | Repository is public by user decision (supersedes "private"). Aggregate results without case-level data are committed in `docs/results.md`. |
| 31 | Milestones | 🔄 | See per-milestone notes. Bootstrap: `pyproject.toml`, `localPipeline.sh`, `.github/workflows/local-pipeline.yml`. MVP record: `docs/mvp-test.md` | M0 ✅ (Docker Compose ✖). M1 ✅ (transport smoke only). M2 ✅. M3 🔄 (LIDC/NSCLC pilot instead of CT-RATE; E000 recorded; E001–E004 configured, not run). M4 🔄 (annotations parsed in `src/thoraxbench/labels/lidc.py`, lesion scoring library; external evaluation ⏳). M5 ⏳. M6 🔄 (UI, study browser, model selector, exploratory side-by-side; benchmark report in CLI only). M7 ⏳. |
| 32 | Definition of success for v1 | 🔄 | See §6, §9, §15, §21, §24 rows | Met: 1 (approved local dataset, guarded), 2 (local inference), 3 (reproducible preprocessing), 5 (patient-level separation), 10 (license/provenance registry). Partial: 6 (metrics library, not applied), 7 (latency yes, VRAM partial), 8 (single-study review, no cohort review), 9 (manifest hashes missing). Open: 4 (CT-CLIP and a native-3D generative model not runnable). |
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

1. **Benchmark runner follow-up** (§13, §18, §25, §26). `thoraxbench benchmark` and
   `configs/experiments/` exist for the development split. Open: CLI `compare`, HTML/CSV
   report, tasks C/D/F in the runner, and a reviewed sealed-evaluation workflow.
2. **No reliable real-data model output** (§1, §3, §27, §32). The two-study
   calibration smoke yielded 3 abstentions and 1 scorable response that missed its reference
   nodule. Resolve output reliability on calibration before full development sweeps.
3. **Acquisition beyond TCIA** (§8, §23, §27). `thoraxbench acquire` covers approved NBIA
   collections with license, split, budget and checksum gates. Other hosts (Hugging Face,
   MosMed) have no acquirer.
4. **3D comparators not runnable** (§4, §17, §32.4). No CT-CLIP, M3D-LaMed or CT-CHAT
   service; weights are gated or exceed the 8 GB GPU. E005–E007 are blocked.
5. **CT-RATE access** (§5, §12, §15, §27). Status `pending_access`. Primary dataset and
   official split handling are missing.
6. **Run provenance gaps** (§2, §24, §32.9). `analyze` leaves dataset and split manifest
   hashes empty. Ground-truth and scoring versions are not recorded. Benchmark per-case raw responses,
   full request/provenance and incremental checkpoints are absent. Freeze is CLI-unreachable.
7. **Calibration not applied** (§14, §20). Reports use a fixed 0.5 threshold. Fit
   thresholds and calibrators on calibration data only, then report Task B metrics.
8. **Leakage column absent** (§16). Add `possible_training_overlap` to every benchmark
   table and complete WP6 leakage tracking.
9. **Privacy audit** (§29). Header audit and path redaction exist. Remaining: pixel-level
   burned-in text check, ad hoc `PatientID` pass-through, header-value redaction in `analyze`.
10. **LAN inference / larger GPU** (§22). Documented in `docs/lan-runner.md` only. Keep
    the loopback guard until an explicit allowlist design is implemented and tested.
11. **Missing layout documents** (§7). `docs/benchmarking.md`, `manifests/models/`.
12. **UI reference overlays and reference-label scores** (§18 steps 8–9). Deferred; CLI
    benchmark outputs exist, the GUI does not show them yet.
