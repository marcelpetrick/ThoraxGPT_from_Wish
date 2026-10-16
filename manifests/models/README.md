# Versioned model configuration snapshots

Research use only. This self-made experimental tool is not medical advice from a qualified
healthcare professional. Findings may be incorrect, incomplete or misleading. Do not use
outputs for diagnosis or treatment decisions.

These schema-version-1 JSON files snapshot every configured model. They contain metadata,
not model weights or runtime credentials. No provider was contacted to create this snapshot.

## What is recorded

* The model ID, exact source YAML path and SHA-256 of its bytes.
* The declared adapter, family, tag, service, quantization and license label.
* Source/provider references already present in repository configurations and documentation.
* Historical full Q4/Q8 MedGemma digests quoted from the named rows of
  [`docs/results.md`](../../docs/results.md). The record is dated; it does not assert what
  is installed now. All other digests remain `null`, including the weight-free heuristic.
* Explicit `unknown` current availability, terms acceptance and model-level training overlap.

A matching hash detects a changed configuration. A historical runtime digest does not
prove publisher identity, weight authenticity, a model's complete training data, applicable
license terms, or the user's acceptance of those terms. Provider links are references,
not a new terms review. The license field preserves the YAML declaration verbatim.

Training overlap is dataset-specific. This model-level snapshot has no evaluation dataset
and cannot certify non-overlap. Its `unknown` flag does not replace the benchmark's
pairwise exposure assessment. Do not convert missing evidence into `no`.

## Validate from the repository root

Prerequisite: the locked source-checkout environment is installed.

1. Run the offline validator.

   ```bash
   uv run python -c 'from pathlib import Path; from thoraxbench.model_manifests import load_model_manifests; print(len(load_model_manifests(Path.cwd())), "model snapshots validated")'
   ```

2. Check the validation result before using a snapshot as a configuration reference.

**Checkpoint:** every configured model has exactly one named snapshot, its byte hash and
copied fields match the current YAML, and each historical digest matches its cited result
row. The validator reads configs, these JSON files and cited aggregate documentation only.
It performs no inference, availability probe, download, study read or sealed access.

**Recovery:** on a missing/stale/extra snapshot, review the source configuration first.
Update the affected JSON only from verified repository evidence. Increment its
`snapshot_version` and set the new `snapshot_date`. Preserve historical evidence or leave
the digest unknown; never invent a value merely to pass validation.

## Schema maintenance

`schema.json` is generated from `ModelManifest.model_json_schema()` in
[`src/thoraxbench/model_manifests.py`](../../src/thoraxbench/model_manifests.py).
Tests validate the schema and the complete repository snapshot set. A future schema change
must deliberately bump `schema_version`; a changed source snapshot increments
`snapshot_version` within that schema.

To inspect the current source hash, run `sha256sum configs/models/MODEL_ID.yaml` after
replacing `MODEL_ID`. Do not change a model configuration or its terms merely to match an
old snapshot. Manifests describe configuration provenance; they do not grant access.
