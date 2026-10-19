# Reproducibility

Research use only. This self-made tool is not professional medical advice. Its findings
may be incorrect, incomplete or misleading. Do not use them for diagnosis or treatment.

This document states what ThoraxBench Local records today so that a result can be traced
and repeated (Vision §24). It also lists the reproducibility gaps that remain open.
A reproduced run shows that the software behaves the same. It does not show that the
findings are correct.

## 1. What each analysis records

`thoraxbench analyze` and the web UI return one result object. With `--output <file>`,
the CLI writes it as JSON. The result contains:

* `provenance`: the run provenance record (`RunProvenance` in
  `src/thoraxbench/provenance.py`);
* `perf`: measured engine-stage timings (`preprocess`, `inference`, `parse`), input bytes,
  image count, generated tokens and the failure flag;
* `request`, `view_meta`, `slice_indices`, `image_captions`, `qc`, `raw_text`,
  `raw_error` and `raw_meta` (including the Ollama model identity when available).

The provenance record is embedded under the `provenance` key. No separate `run.json` file
is written.

### Provenance fields

| Field | Content | Current state |
|---|---|---|
| `git_commit` | `git rev-parse HEAD` of the checkout | set inside a Git checkout |
| `git_dirty` | `true` when tracked files have uncommitted changes | set inside a Git checkout |
| `thoraxbench_version` | `__version__` from `src/thoraxbench/__init__.py` | always set |
| `dataset_manifest_hash` | acquisition manifest hash; benchmark summary combines manifests/indexes | set when a matching manifest exists; otherwise `null` |
| `split_manifest_hash` | split manifest hash; combined across benchmark datasets | set when a matching manifest exists; otherwise `null` |
| `ground_truth_hash` | bytes of the dataset reference index | set when the index exists; identifies reference state, not its correctness |
| `scoring_hash` | bytes of scoring and shared prediction-schema source files | set from the current implementation |
| `input_hash` | canonical HU bytes/shape/spacing plus prepared image/tensor hashes and context | set outside measured engine stages; no image bytes are persisted in this field |
| `model_id` | configured model id, e.g. `heuristic-hu` | always set |
| `model_hash` | Ollama model digest | Ollama models only |
| `container_digest` | service container digest | **planned**; currently `null` |
| `prompt_hash` | SHA-256 of the canonical prompt template | prompt-based models only |
| `preprocess_hash` | SHA-256 of view id/version, view and strategy hashes, cue version and view parameters | always set |
| `config_hash` | SHA-256 of the model config, request and view overrides | always set |
| `seed` | random seed | always `0`; current sampling is deterministic |
| `hardware` | CPU processor or machine name | always set |
| `gpu`, `driver`, `cuda` | from `nvidia-smi` | `null` without an NVIDIA GPU |
| `python` | Python version | always set |
| `platform` | operating system string | always set |
| `created_at` | UTC timestamp | always set |

Hashes use SHA-256 over canonical JSON (sorted keys, no whitespace), see
`canonical_json` and `sha256_of_obj`.

`RunProvenance.fingerprint()` hashes the result-determining fields (`git_commit`, the
manifest, model, prompt, preprocessing and config hashes, `ground_truth_hash`,
`scoring_hash`, `input_hash`, software version, model ID and `seed`). It excludes time
and hardware. `thoraxbench benchmark` writes it per case (`fingerprint`); `analyze` does
not write it.

Unavailable manifests or indexes remain `null`; no version is invented. Source/index byte
hashes now identify scoring rules and reference state. This does not establish that labels
are complete or independent of model pretraining. The standalone `analyze` JSON still does
not include a separate fingerprint field. See [remaining gaps](vision_traceability.md).

Study loading collects selected direct identifying header values in memory, including
when cached pixels are used. The shared analysis redactor applies them and absolute-path
redaction to the request, report, raw output/errors, metadata, context, timings, QC and
image captions. Dataset/case/patient pseudonym keys, series UIDs and hashes stay unchanged.
This is not OCR or proof of anonymity; caches/indexes and unmatched free text still need
controlled handling. A cache alone cannot recover identifier values if source headers are
unavailable. The identifier collection is not serialized. Printed local output paths remain
actionable and are not blanket-redacted. See [the security policy](../SECURITY.md).

## 2. Pinned software

* Python 3.14 (`requires-python = ">=3.14"`). CI installs Python 3.14 with `uv`.
* Every runtime and development dependency is pinned to an exact version in
  `pyproject.toml`. The build backend is pinned as well (`hatchling==1.32.4`).
* `uv.lock` pins the complete transitive set. It is committed.
* The pipeline installs with `uv sync --frozen --all-groups`. `--frozen` installs exactly
  the locked versions and never rewrites `uv.lock`. It does not check that the lock still
  matches `pyproject.toml`; update both files in the same change.
* The `audit` stage runs `pip-audit` against the exported locked set.
* The `wheel` stage installs the built wheel into a clean environment and runs
  `thoraxbench --version`.

Install the locked environment from the repository root:

```bash
uv sync --frozen --all-groups
```

**Checkpoint:** the command finishes without resolving new versions.

**Recovery:** if the sync fails, do not edit `uv.lock` by hand. Make sure
`pyproject.toml` and `uv.lock` come from the same commit, then retry. To check that the
lock matches `pyproject.toml`, run `uv lock --check`.

## 3. Versions and commits

* The version lives in `src/thoraxbench/__init__.py` (`__version__`).
* Commits go only through `scripts/commit.sh "<type>(<scope>): <message>"`.
* The script bumps the version with `scripts/bump_version.sh` (patch by default,
  `--minor` for a major feature).
* It runs the full `./localPipeline.sh`. It commits only after a green gate.
* The commit message carries a `Version: <x.y.z>` trailer.
* A failed gate reverts the version bump and makes no commit.

A clean result therefore names a commit whose full gate passed. Check `git_dirty` before
you rely on `git_commit`: `true` means the run used uncommitted code.

Read the installed version from the repository root:

```bash
uv run thoraxbench --version
```

## 4. Reproduce the synthetic demo

Prerequisites: `uv`, Python 3.14 and the source checkout. Start in the repository root.
Keep that working directory. This procedure uses only synthetic data and no model server.

1. Install the locked dependencies.

   ```bash
   uv sync --frozen --all-groups
   ```

2. Generate the synthetic phantom.

   ```bash
   uv run thoraxbench demo-data data/demo/repro
   ```

3. Analyse it with the deterministic baseline.

   ```bash
   uv run thoraxbench analyze data/demo/repro --model heuristic-hu \
     --output data/results/repro/result.json \
     --html data/results/repro/report.html
   ```

4. Open `data/results/repro/result.json`.
5. Compare `provenance.git_commit`, `provenance.thoraxbench_version`,
   `provenance.config_hash` and `provenance.preprocess_hash` with a previous run.

**Checkpoint:** exit status 0. The result reports adequate QC, no abstention, a right
12 mm nodule and a right fluid region. On the same commit and model config,
`config_hash` and `preprocess_hash` match between runs. Timings and `created_at` differ.

**Recovery:** a non-zero exit status means failure or abstention. Read the terminal
reason. Confirm the study directory exists. The `--html` path must be inside
`data/results/`. Do not treat failure or abstention as a negative finding.

The full MVP test with the recorded reference outcome is in
[`mvp-test.md`](mvp-test.md).

## 5. Frozen splits

Patient-level splits are deterministic. The same patient list and salt
(`thoraxbench-split-v1`) produce the same assignment. Once written, a split is frozen:
`thoraxbench split` refuses to replace it. The committed manifest
`manifests/splits/<dataset>.json` stores counts, salted patient hashes and the SHA-256 of
the development and sealed patient sets. Loading a split verifies the local files against
these hashes. A tampered or regenerated split fails to load.

Procedure and sealed-holdout rules: [`DATA_POLICY.md`](DATA_POLICY.md#4-sealed-holdout).

Freezing an *experiment config* for sealed evaluation exists only as the library function
`freeze_experiment` in `src/thoraxbench/splits/guard.py`. It is not yet exposed in the CLI.

## 6. Benchmarks

`thoraxbench benchmark <experiment.yaml>` runs an experiment from `configs/experiments/` on
the development split. It writes `result.json` and `report.md` in a unique
`data/results/benchmark/<id>/<timestamp>-<hashprefix>-<uuid>/` directory. Follow the printed
paths. Earlier runs and historical flat files remain intact.
The result records the config file SHA-256, a canonical config hash, the dataset, index
and split manifest hashes, per-run provenance and per-case fingerprints.

New runs create `manifest.json` and an atomic `checkpoint.json` before inference. Each
terminal case/variant receives an immutable `cases/<unit-hash>-<uuid>.json` artifact. It
contains the resolved spec, structured request, outcome, report and serialized analysis
when one exists. Raw text, metadata, errors, timings and provenance remain available;
prepared image bytes are excluded. No response is fabricated for a pre-analysis failure.
For Ollama, `raw_meta.requests` records rendered system/user messages and actual
model/options/format/schema/keep-alive/thinking settings. Image bytes are omitted and
replaced by image SHA-256 values with `image_bytes_omitted: true`.
`raw_meta.responses` retains HTTP status, latency and complete decoded JSON provider
bodies when available, including content, thinking, stop reason and token counts.
Malformed/non-JSON HTTP bodies retain bounded diagnostic text (up to 300 characters),
not a promise of complete response bytes. Transport failures retain error type, reason
and latency. Two-pass requests/responses remain available if the second pass fails.
The shared analysis redactor processes this metadata before persistence.

These are provider diagnostics, not packet capture: no network headers or base64 pixels
are archived. Optional HTTP model services do not yet retain equivalent full provider
request/response diagnostics. Their ordinary parsed/raw analysis fields remain available.

The manifest also binds guarded input bytes, selected phases/cases, code/commit,
the dependency lockfile, model and prompt settings, and known runtime model digests.

Use `--resume <original-invocation-directory>` with the same experiment and `--limit` to
continue pending units. Identity and integrity checks run before reuse. Completed failures,
abstentions and missing-index units remain terminal; use a fresh invocation to retry them.
A validated complete run returns existing aggregates without inference or rewriting.
Legacy runs without checkpoints cannot resume. See [the exact procedure and refusal
conditions](benchmarking.md#6-resume-an-interrupted-invocation).

Checkpoints use integrity checksums, not authentication against a malicious editor. Preserve
the entire invocation directory. A case file absent from the authoritative checkpoint
can be an orphan from interruption and is not reused merely because it exists.

Prerequisites: the experiment's datasets are split and indexed. Start in the repository
root.

1. Run the experiment.

   ```bash
   uv run thoraxbench benchmark configs/experiments/E000_heuristic_hu_baseline.yaml
   ```

2. Compare the printed `Config SHA-256` with the value in [`results.md`](results.md).
3. Compare the manifest hashes in `result.json` with the recorded run.

**Checkpoint:** with the same config, data state and commit, the hashes and case counts
match the recorded run. Timings differ.

**Recovery:** a different config hash means the YAML changed; record a new run instead of
overwriting the old entry. Resume also refuses changed code/commit, data, index/split,
model/prompt settings or runtime identity. Do not edit the checkpoint to force reuse. `--limit N` produces a partial run; do not compare it with a
full run. `--unseal` is refused (exit status 2).

Recorded runs are in [`results.md`](results.md). E000 is a pipeline baseline of a
deterministic HU heuristic. No result in this repository measures model accuracy on the
sealed holdout.

### Metric and prompt version changes

Current scoring leaves unknown presence and missing confidence unavailable. Zero available
requested-label predictions cause abstention; partial coverage scores available labels
without inventing negative predictions. Task E counts
unavailable predictions as omissions for all known reference labels, exposes prediction
coverage, and does not credit an omitted negative. Task G excludes abstained/unknown
measurements and reports the eligible false-reassurance denominator. P0–P4 captions use
one-based model image numbers. Historical results were not recomputed under these changes.
Record a new invocation for the changed code/prompt hashes; do not reinterpret old metrics
as if they came from the current implementation.

## 7. Open gaps

These items are **planned**:

* exact source/label validity checks beyond the recorded index and scoring hashes;
* the result fingerprint in `analyze` results;
* container digests for local PyTorch model services;
* `manifests/models/` with model manifests;
* a CLI command to freeze an experiment config.

## Visual-evidence method update

P0–P3 are version 1.0.2 and P4 is 1.0.3. Schemas now restrict attached-image numbers and
constrained negative-label IDs. P2/P3 explicitly separate heuristic candidates from visual
support. P2–P4 analysis makes positives without valid image evidence unavailable. These
changes affect eligibility and metrics; keep old measurements under their original method.
MultiSliceView version 2 hashes `include_cues` and preserves empty model context when false.
The calibration-only E001-cue-ablation configuration compares identical images with and
without that text; valid-number citations still cannot establish visual correctness.

Evidence eligibility uses the shared implied presence probability at the default 0.5
cutoff, including low-confidence absent verdicts that imply a positive probability.
`include_cues` accepts only YAML booleans; null, numbers and strings are refused.
