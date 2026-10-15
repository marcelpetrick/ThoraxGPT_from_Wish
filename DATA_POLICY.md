# Data policy

Research use only. This self-made tool is not professional medical advice. Its findings
may be incorrect, incomplete or misleading. Do not use them for diagnosis or treatment.

This policy states how ThoraxBench Local handles medical image data. It applies to every
human and AI agent that changes this repository. The rationale is in
[`Vision.md`](Vision.md) §2.4, §6, §7, §15–§16, §23, §29 and §30. The working rules are
in [`AGENTS.md`](AGENTS.md) §1.

## 1. No medical data in Git

Never commit DICOM studies, NIfTI or other volumes, rendered CT slices, dataset archives,
model weights, credentials or tokens.

Two controls enforce this:

1. `.gitignore` excludes `/data/`, `*.dcm`, `*.nii`, `*.nii.gz`, `*.nrrd`, `*.mha`,
   `*.mhd`, `*.npz`, `*.npy`, any `rendered/` or `raw/` directory, model weights
   (`*.gguf`, `*.safetensors`, `*.pt`, `*.pth`, `*.ckpt`), `.env` and `*.token`.
   `manifests/` is re-included explicitly.
2. `scripts/check_no_medical_data.sh` runs as the `datagate` stage of
   `./localPipeline.sh`. It checks every tracked or about-to-be-tracked file and fails on:
   * image-volume, weight or archive extensions (`dcm`, `nii`, `nii.gz`, `nrrd`, `mha`,
     `mhd`, `npz`, `npy`, `gguf`, `safetensors`, `pt`, `pth`, `ckpt`, `zip`, `tar`, `tgz`);
   * any `.env` file or any path containing `data/`;
   * files larger than 2 MB (except `uv.lock`);
   * files under `tests/fixtures/` larger than 200 KB;
   * strings that look like Hugging Face (`hf_…`) or GitHub (`ghp_…`, `gho_…`) tokens.

### Run the data gate

Prerequisite: a source checkout. Start in the repository root.

1. Run the gate.

   ```bash
   scripts/check_no_medical_data.sh
   ```

**Checkpoint:** the script prints
`data-policy gate passed: no medical data, weights or secrets tracked` and exits 0.

**Recovery:** the script names each offending file. Remove it from the Git inputs, for
example with `git rm --cached <file>`, and move it under `data/`. Run the gate again.
If a secret was ever committed, revoke it at the provider first.

**Limitation:** the gate does not inspect image content. A small PNG or JPEG of a real CT
slice outside `data/` would pass it. Review every added image by hand.

## 2. The local data directory

All real and derived data lives in `data/` in the repository root. Git ignores it. Set
`THORAXBENCH_DATA_DIR` to use another location.

| Path | Content | Created by |
|---|---|---|
| `data/raw/<dataset>/` | downloaded source DICOM per patient; `_sha256.txt`, `_acquisition.json`, license snapshot | `thoraxbench acquire` (pilot cohorts: earlier manual download) |
| `data/splits/<dataset>.json` | development case IDs and phases | `thoraxbench split` |
| `data/sealed/<dataset>.json` | sealed holdout IDs, read-only | `thoraxbench split` |
| `data/index/<dataset>.json` | development study and label index | `thoraxbench index` |
| `data/cache/` | derived volume (`.npz`) and tensor (`.npy`) caches | study loading and 3D-service views, when a cache directory is used |
| `data/demo/` | synthetic phantom studies | `thoraxbench demo-data`, web UI |
| `data/results/` | result JSON, Markdown and HTML reports | `thoraxbench analyze`, web UI |
| `data/results/benchmark/<experiment>/` | benchmark `result.json` and `report.md` | `thoraxbench benchmark` |

Vision §7 also proposes `normalized/`, `rendered/`, `labels/` and `reports/`
subdirectories. They are **planned** and not created by the current code.

### Disk budget

The configured budget is 10 GB (`DEFAULT_BUDGET_GB` in `src/thoraxbench/config.py`,
override with `THORAXBENCH_DATA_BUDGET_GB`). `thoraxbench acquire` enforces it for its own
downloads: it refuses a plan that does not fit and re-checks `data/` usage while a transfer
streams. Other commands (`demo-data`, `analyze`, `benchmark`, the web UI) do not enforce it.

1. Check free space.

   ```bash
   df -h .
   ```

2. Check the data directory size.

   ```bash
   du -sh data
   ```

**Checkpoint:** `data` stays below 10 GB.

**Recovery:** stop downloads. Delete regenerable content first (`data/cache/`,
`data/demo/`, old `data/results/`). Never delete or rewrite `data/splits/` or
`data/sealed/`; a split is frozen once created.

## 3. License gate

Each data source has a registry entry in `configs/datasets/<id>.yaml`. Its `status`
field is the license decision (`DatasetStatus` in
`src/thoraxbench/registry/datasets.py`).

| Status | Acquisition, split and index allowed |
|---|---|
| `approved` | yes |
| `approved_noncommercial` | yes |
| `approved_eval_only` | yes |
| `pending_terms_review` | no |
| `pending_access` | no |
| `rejected` | no |

`require_acquirable` raises `PolicyError` for every other status. `thoraxbench acquire`,
`thoraxbench split` and `thoraxbench index` call it before they touch a dataset.

Rules:

* Verify each source's own current terms. Never inherit a license from another
  collection on the same host.
* Record the decision in the registry entry before any download.
* Details per source are in [`docs/datasets.md`](docs/datasets.md).

Check the registry from the repository root:

```bash
uv run thoraxbench datasets
```

**Checkpoint:** each line shows the status, dataset id and license.

`thoraxbench acquire` downloads an approved TCIA collection. It also refuses any series
whose license URI or collection differs from the registry entry. The pilot cohorts were
first downloaded manually; their frozen selections and acquisition manifests are in
`data/raw/<id>/` and `manifests/datasets/`. Procedure: [`docs/datasets.md`](docs/datasets.md#acquire-an-approved-dataset).

## 4. Sealed holdout

Every approved dataset gets a patient-level split before any real-study indexing or
analysis (`src/thoraxbench/splits/`).

* 20 % of patients per stratum form the **sealed** validation set. Each stratum with two
  or more patients contributes at least one sealed patient.
* The remaining 80 % is **development**: 80 % `calibration`, 20 % `internal_test`.
* Splitting is by patient, never by study or slice.
* Order is `sha256(salt:patient_id)` with the versioned salt `thoraxbench-split-v1`.
  The split is reproducible from the patient list and the salt.
* `thoraxbench split` uses directory names only. It reads no DICOM, labels or sealed file.
* A split is frozen once created. `thoraxbench split` refuses to replace it.

Storage:

| File | In Git | Content |
|---|---|---|
| `data/splits/<dataset>.json` | no | development case IDs and phases |
| `data/sealed/<dataset>.json` | no | sealed case IDs; file mode set to read-only (0400) |
| `manifests/splits/<dataset>.json` | yes | counts, salted patient hashes, set hashes |

Guards:

* `CaseGuard` (`src/thoraxbench/splits/guard.py`) hands out case IDs per phase. A request
  for sealed cases raises `SealedAccessError` unless a matching freeze record exists.
* `load_split` reads the sealed file only for a frozen experiment. It checks the stored
  files against the committed manifest hashes.
* `guard_study_input` (`src/thoraxbench/study_access.py`) runs before pixel data loads in
  the CLI and the web UI. It blocks paths under `data/sealed/`, raw folders outside the
  development split, mismatched DICOM `PatientID` values, and any DICOM whose `PatientID`
  hash appears in a committed sealed manifest.

Rules:

* Development, prompt tuning, calibration fitting, threshold fitting and tests never read
  sealed cases.
* Never open `data/sealed/` by hand or with an agent.
* Never weaken `thoraxbench.splits.guard`.
* Only a frozen experiment config may unlock sealed cases. The library function
  `freeze_experiment` records the config hash in `data/sealed/freeze/<experiment>.json`;
  a changed config invalidates the freeze.
* Freezing is not yet exposed in the CLI. `thoraxbench benchmark` reads development cases
  only; `--unseal` is not implemented and is refused (exit status 2). No current CLI
  command or web route reads sealed cases.
* After a split exists, `thoraxbench acquire` refuses new patients, and `--verify` opens
  development patients' files only.

### Freeze a split for a new approved dataset

Prerequisites: the dataset status is `approved*`, its patient folders are in
`data/raw/<dataset>/`, and no split exists yet. Start in the repository root.

1. Create the split.

   ```bash
   uv run thoraxbench split <dataset>
   ```

2. Read the printed development and sealed patient counts.
3. Commit `manifests/splits/<dataset>.json` with the next change.

**Checkpoint:** the command prints
`Frozen <dataset>: <n> development patients, <m> sealed holdout patients.`

**Recovery:** `split for <dataset> already exists and is frozen` means a split exists.
Keep it. A `PolicyError` means the license gate refused the dataset; resolve the license
status first.

## 5. Synthetic data for tests and screenshots

* Tests use synthetic DICOM phantoms generated in code by `src/thoraxbench/synthetic.py`.
  They never use real patient data. Tests that need real data or a running model are
  marked `live` and excluded from the pipeline.
* Browser tests, screenshots and demos use synthetic studies only.
* Create a synthetic study from the repository root:

  ```bash
  uv run thoraxbench demo-data data/demo/example
  ```

  **Checkpoint:** the command prints `synthetic phantom written to data/demo/example`.

## 6. What may be committed

| Allowed | Example |
|---|---|
| source code, prompts, configs, the dataset registry | `src/`, `configs/` |
| acquisition manifests with counts, checksums and license snapshots | `manifests/datasets/*.json` |
| split manifests with counts and salted hashes only | `manifests/splits/*.json` |
| synthetic or schematic documentation images | `docs/assets/mvp-walkthrough.svg`, `docs/assets/ui-about.png` |
| aggregate results without images or case-level data | [`docs/results.md`](docs/results.md) |
| documentation | `docs/`, `README.md`, manuals |

Never commit:

* DICOM, NIfTI or other image volumes;
* rendered CT slices or screenshots of real studies;
* dataset archives or full result exports with embedded images;
* model weights that prohibit redistribution;
* credentials, tokens or `.env` files;
* plaintext patient or case IDs of the sealed set;
* sensitive source metadata.

Before the repository becomes public, run a license and data audit and remove anything
that cannot be redistributed (Vision §30).
