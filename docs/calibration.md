# Optional development calibration

Research use only. This self-made experimental tool may be wrong, incomplete or misleading.
It is not professional medical advice or a basis for diagnosis or treatment.

Calibration fitting is opt-in. Existing experiment files do not enable it. Add this block
to a separately versioned experiment only after output-readiness checks pass:

```yaml
calibration:
  method: platt  # platt, temperature, isotonic or none
  threshold_method: youden  # youden or sensitivity
  target_sensitivity: 0.9
```

The runner fits thresholds and probability maps on scored `calibration` records only.
It applies them to scored `internal_test` records only. Sealed and unknown phases are
refused. Missing labels stay unavailable. One-class calibration keeps the 0.5 threshold
and skips the probability map. Without both phases, fitting is not applicable. `none`
still fits thresholds but does not fit a probability map.

The result keeps raw 0.5 internal-test metrics beside fitted-threshold metrics, raw and
calibrated Brier/ECE/NLL, fit counts and serialized map parameters. Raw predictions are
unchanged. The Markdown report gives fit counts, thresholds and limitations; the complete
metrics stay in `result.json`. Cohort exports retain those stored metrics verbatim.
Do not tune against the internal-test outputs. No real-data fit is claimed by synthetic
verification, and current broad study-level experiments remain on hold.

Training overlap is recorded per model and dataset. Exports carry the recorded flag in
HTML, CSV and manifests. Historical runs without flags stay `unknown`; do not infer
non-overlap from a missing value. MONAI/LUNA16 on LIDC is always overlap-flagged.

E005–E008 now have planning configurations with explicit `blocked_reason` values. The
runner refuses them before study access. Do not remove those reasons without resolving
model access, service availability, frozen transfer setup and output-readiness gates.

Historical completed runs remain readable using their original stored canonical config
hashes. Validation still checks the complete raw configuration, checksums, cohort phases
and per-case artifacts. Resume remains strict and refuses changed code or identity.

Checkpoint: synthetic tests verify fitting direction, missing classes, overlap export,
legacy read-only export and blocked runs without touching real holdout data. Keep raw and
fitted results separate. Preserve failed or undefined fits instead of inventing scores.
