# Development benchmark procedure

Research use only. This self-made experimental tool is not medical advice from a qualified
healthcare professional. Findings may be incorrect, incomplete or misleading. Do not use
outputs for diagnosis or treatment decisions.

The runner scores parsed outputs against indexed reference labels from the frozen
**development split**. It does not evaluate the sealed holdout. `--unseal` is refused
with exit status 2. Keep UI feature work frozen; this procedure extends the CLI engine.

## 1. Check the prerequisites

Run commands from the repository root. Use the source checkout and locked environment.

1. Run `uv sync --frozen --all-groups`.
2. Check `git status` and `uv run thoraxbench --version`.
3. Confirm the experiment's datasets have frozen splits and development indexes.
4. Read the experiment YAML before starting inference.
5. For a vision model, run `uv run thoraxbench models` to check local availability.
6. Check actual space with `df -h .` and `du -sh data`.

**Checkpoint:** the configuration identifies the intended model, phases, labels and
input budget. The benchmark does not enforce an analysis-output disk quota. Results stay
inside ignored `data/results/`. Split and endpoint guards remain active.

**Recovery:** fix a missing prerequisite before the run. Never regenerate a frozen split,
copy holdout data into development, or substitute a cloud endpoint.

## 2. Choose the experiment

| Config under `configs/experiments/` | Purpose | Current scope |
|---|---|---|
| `E000_heuristic_hu_baseline.yaml` | Deterministic HU pipeline control | Recorded on 70 development cases; constant-like predictions are not model accuracy |
| `E001_calibration_smoke.yaml` | Bounded Q4/Q8 readiness check | Calibration only; four 256-pixel axial inputs and two labels; distinct from full E001 |
| `E001_calibration_diagnostic.yaml` | Bounded Q4 structured-output diagnostic | Existing P2, two 256-pixel axial inputs, calibration only; explicit `--limit 1` required |
| `E001_medgemma_quantization.yaml` | MedGemma quantization comparison | Full sweep deferred until reliable usable output is demonstrated |
| `E002_medgemma_slice_count.yaml` | Slice-count comparison | Configured; full sweep deferred |
| `E003_medgemma_sampling.yaml` | Sampling comparison | Configured; full sweep deferred |
| `E004_medgemma_prompt.yaml` | Prompt comparison | Configured; full sweep deferred |

The YAML `labels` select both requested and scored findings. Prompt precedence is variant
override, experiment setting, model configuration, then `P3`. `phases` selects calibration,
internal test, or both within development. Use calibration cases for prompt/parser/output
reliability work. Internal-test results must not drive tuning.

The `--limit N` option selects at most N cases **per dataset**, after the phase filter,
in frozen split order. It does not select N cases per experiment or a new random sample.
Variants use those same selected cases. Missing index entries remain `not_indexed`.

## 3. Run a bounded check

1. Start a small heuristic check.

   ```bash
   uv run thoraxbench benchmark configs/experiments/E000_heuristic_hu_baseline.yaml --limit 2
   ```

2. Read the printed per-variant status counts.
3. Follow the printed result and report paths.
4. Inspect errors, abstentions and missing-index counts before metrics.
5. Compare the recorded configuration and manifest hashes with the intended setup.

**Checkpoint:** only development cases are read. Each invocation has a new
`data/results/benchmark/<experiment-id>/<timestamp>-<hashprefix>-<uuid>/` directory.
Previous complete/partial runs and historical flat files stay intact.

For calibration-only vision readiness, use the separately named smoke config:

```bash
uv run thoraxbench benchmark configs/experiments/E001_calibration_smoke.yaml --limit 1
```

The recorded two-study smoke at `3af797f` (v0.3.8, 2026-10-16) took 290.8 seconds wall
time. It used `n_boot: 0`, no coronal view, and the `pulmonary_nodule`/`pulmonary_mass` labels.
Q4 abstained on both studies; Q8 missed the reference nodule in its one scorable response
and reached the generation limit on the other. See [measured results](results.md). Do not expand to full
E001–E004 solely because inference finished. Diagnose usable-output reliability first.

### Separate bounded provider diagnostic

Once durable artifacts and local prerequisites are verified, the diagnostic configuration
can inspect Q4 provider output on at most one calibration case per dataset:

```bash
uv run thoraxbench benchmark configs/experiments/E001_calibration_diagnostic.yaml --limit 1
```

The YAML does not enforce this case bound; `--limit 1` is required. The run uses existing P2,
Q4 only, uniform sampling, two 256-pixel axial images, two labels, no coronal view and no
bootstrap. Prompt, sampling strategy and image count differ from E001-smoke; this cannot
isolate their effects or establish detection accuracy. The earlier anatomy diagnostic
actually prepared nine images per case. The corrected uniform run prepared two but still
copied heuristic candidates and cited invalid image numbers. See [results](results.md). Inspect durable provider diagnostics before another
run. This is not a full E001 sweep or a quantization comparison.

## 4. Interpret the accounting

| Status or metric | Meaning | Required review |
|---|---|---|
| `scored` | Parsed output was eligible for scoring | Check unknown labels and false negatives; scorable does not mean correct |
| `abstained` | Engine abstained or returned a raw inference error | Inspect the reason; generation-limit errors can appear here |
| `failed` | Loading or analysis raised a recoverable error | Inspect the error; it is not a negative prediction |
| `not_indexed` | Selected development case is absent from the index | Preserve the count; do not silently replace the case |
| Task A | Study-level label metrics on scored cases | Check denominators, class balance and undefined values |
| Task B | Calibration metrics of raw scores | No calibrator is fitted by the runner |
| Task E | Reference-label factuality | Missing reference labels stay unknown |
| Task G | Abstention and safety accounting | Read alongside failures; a low failure count can hide many abstentions |

Tasks C, D and F are not wired into the runner. No CLI run comparison, cohort HTML/CSV,
reference overlays or sealed-evaluation workflow is implemented. The GUI's offline
comparison is exploratory and computes no reference-label accuracy.

### Current missing-prediction and safety semantics

Unknown presence, missing finding confidence and abstention produce unavailable scores
(`null`), not a guessed 0.5 or zero. An explicit negative-list entry implies zero only
when no finding overrides it. Decisions use full-precision implied presence scores;
rounding for display does not change a threshold decision. A response with zero available
predictions for the requested labels abstains, even if it contains uncertain findings or
only unrequested labels. Partial requested-label coverage can remain scorable; missing
predictions remain unavailable and count as omissions, never invented negatives.

Task E counts an omission for **every known reference label without an available
prediction**, including negative references. It does not award agreement for an omitted
negative. `label_agreement` uses all known reference labels as its denominator.
`available_predictions` and `prediction_coverage` expose how many received predictions.

Task G skips abstained and unavailable decisions. Fabricated-measurement accounting uses
present, available findings with known references. False reassurance is eligible only if
all reference-positive labels have available predictions; read
`false_reassurance_eligible_studies` beside its rate. A low rate with few eligible studies
is not evidence of safety.

These definitions apply to new runs using the current code. Historical E000/E001-smoke
outputs were not recomputed; compare methods and code state before comparing their metrics.
Prompt versions P0–P4 also changed to one-based model-image captions. Do not overwrite a
historical report or mix outputs across these result-affecting changes.

## 5. Inspect durable artifacts

The CLI prints `Invocation:` after preflight and before model inference. Copy that directory
path. Fresh runs create it under ignored `data/results/benchmark/<experiment-id>/`.

```text
<timestamp>-<hashprefix>-<uuid>/
  manifest.json
  checkpoint.json
  cases/<unit-hash>-<uuid>.json
  result.json
  report.md
```

| File | Content and lifetime |
|---|---|
| `manifest.json` | Immutable invocation identity: experiment, selection/limit, index/split/input hashes, model/prompt settings, source/commit/dependency-lockfile and runtime model digests |
| `checkpoint.json` | Atomically replaced progress record with integrity checksums and links to terminal case/variant artifacts |
| `cases/*.json` | Immutable terminal case/variant artifact: resolved spec, structured request, outcome, report and serialized analysis when available |
| `result.json`, `report.md` | Final aggregate outputs; a validated complete invocation reuses them without rewriting |

When analysis returns, the case artifact retains `raw_text`, `raw_meta`, `raw_error`,
`request`, QC, view metadata, captions, timings and provenance. Prepared image bytes are
excluded. These records are not an independently verified image localization.

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

Loading/analysis exceptions and missing-index cases retain their terminal outcome and
error; no raw response is invented when none exists.

Each terminal unit is saved before proceeding to the next. Persistence errors stop the
run. After interruption, the last durable checkpoint is authoritative. An in-flight unit
or an artifact written before its checkpoint commit may remain pending and run again.
An orphan file alone is not proof that a unit completed.

Keep complete local artifacts under ignored `data/results/`. Publish only reviewed
aggregates with their limitations. Case identifiers, raw responses and reports can contain
sensitive source information even when they contain no images. Never commit those files.

## 6. Resume an interrupted invocation

Prerequisites: a new-format run with `manifest.json` and `checkpoint.json`. Keep the original
experiment bytes, `--limit`, code/commit, dependency lockfile, data/index/split state, model settings,
prompts and runtime weights. Local model services must expose a known matching digest.
Resume validates the current guarded input hashes before reusing progress; this can take time.

1. Locate the original printed `Invocation:` directory.
2. Replace `PASTE_PRINTED_RUN_ID` below with its final directory name.
3. Re-run with the same experiment and limit.

   ```bash
   uv run thoraxbench benchmark configs/experiments/E000_heuristic_hu_baseline.yaml \
     --limit 2 --resume data/results/benchmark/E000/PASTE_PRINTED_RUN_ID
   ```

4. Inspect the preserved statuses and new pending-unit outcomes.
5. Read the final report when all selected units are terminal.

**Checkpoint:** resume reuses checkpointed `scored`, `abstained`, `failed` and `not_indexed`
units. Only pending units receive new analysis. A complete invocation validates integrity
and returns its existing aggregates without inference or output rewriting.

**Recovery:** identity/checksum mismatches, unknown model digests, symlink escapes, or an
active writer refuse resume. Resolve the cause without editing checksums or weakening the
guards. If settings, data or code changed, start a new invocation. To retry a failure or
abstention, start a new invocation; resume deliberately preserves those terminal outcomes.
Legacy runs without a checkpoint cannot be resumed. Keep their files as historical evidence.
Only one process may write the same invocation at a time.

## 7. Historical evidence limits

Historical E000 and E001-smoke runs saved scores, warnings and fingerprints but did not
preserve complete per-case raw responses. Their summaries cannot reconstruct discarded
responses or prove what an interrupted historical invocation processed.

## 8. Historical index-boundary audit

The committed E000 record notes five NSCLC index entries outside the frozen development
split before its index rebuild. The runner counts such entries and does not select them.
A metadata-only review on 2026-10-16 found all three preserved benchmark result files
(E000, legacy E001 and E001-smoke) recorded zero outside-development entries for both
collections and the same rebuilt NSCLC index hash. No pre-rebuild index copy was found
among the current index JSON files.

This supports the development-only selection of those recorded runs. It does **not** prove
that the five earlier entries were never read, indexed or used before the rebuild. The
aggregate count alone cannot distinguish sealed from unknown entries. Historical leakage
remains unresolved until auditable evidence establishes the earlier processing history.
No raw or sealed patient data was opened for this review; no identifiers are published.

## 9. Recover from a refusal

* Exit status 1: read the named error and check the experiment, split, index, output path
  and local model prerequisites.
* Exit status 2 with `--unseal`: expected. Remove that option; sealed evaluation is unavailable.
* Empty or truncated predictions: preserve them as abstentions and investigate only on
  synthetic or calibration data.
* Changed configuration or data state: record a new run. Do not relabel an old result.

For provenance fields and remaining gaps, read [reproducibility](reproducibility.md).

### Read total runtime after interruption

Experiment `runtime_s` accumulates active invocation time through selection, input hashing,
study loading and scoring. Resume adds active time to the last saved checkpoint and
excludes downtime. An interrupted tail after the last checkpoint is not recovered.
Per-variant runtime covers evaluated units and excludes shared input hashing/loading.
Completed resume verifies the existing output and retains its original timing.

## Constrained visual evidence and context ablation

P2–P4 Ollama requests bind evidence indices to actual attached images. Analysis removes
invalid/duplicate references and makes unsupported positive predictions unavailable. A run
abstains if no requested-label predictions remain available. Raw responses are preserved.
P0/P1 free-form controls and the HU baseline keep their separate semantics. A valid index
is a bounds check, not proof of a visual observation.

For the next bounded diagnostic, run from the repository root after checking local prerequisites:

```bash
uv run thoraxbench benchmark configs/experiments/E001_cue_ablation.yaml --limit 1
```

Both variants use the same anatomy sampling, target nine axial images, size and P2 prompt.
Only `include_cues` changes. The false variant sends no deterministic context and records
empty context. Cues are still computed for preprocessing. Compare prepared image hashes,
actual counts, coverage and abstentions before interpreting responses. The case limit is
a CLI prerequisite. Keep internal-test and sealed data out of this check.

**Checkpoint:** immutable artifacts retain both variants, including failures or abstentions.
**Recovery:** inspect raw responses and valid evidence. Do not choose a model or claim
accuracy from this small diagnostic. Preserve the run and create a new invocation for changes.

Evidence eligibility uses the shared implied presence probability at the default 0.5
cutoff, including low-confidence absent verdicts that imply a positive probability.
`include_cues` accepts only YAML booleans; null, numbers and strings are refused.
