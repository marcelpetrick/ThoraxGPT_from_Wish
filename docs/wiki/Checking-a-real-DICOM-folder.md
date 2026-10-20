# Checking a real DICOM folder before import

Research use only. Self-made experimental tool; not medical advice or a diagnosis.

## The checker script

`scripts/dcom_evaluator.py` checks a DICOM folder **on your own computer** before (or
instead of) opening it in the app. It prints aggregate JSON only: no paths, names, UIDs,
dates or raw header values. Review the output before sharing anyway; it is not an
anonymization guarantee.

Run from the repository root:

```bash
# Headers only: counts, grouped errors, opaque series summary
uv run --no-sync python scripts/dcom_evaluator.py --scan-headers "/path/to/folder"

# Plus the app's real import and input-QC path (no model, no export)
uv run --no-sync python scripts/dcom_evaluator.py --scan-headers --check-import --progress "/path/to/folder"

# One file only
uv run --no-sync python scripts/dcom_evaluator.py "/path/to/one/file"
```

Read `counts.header_errors`, `error_groups`, `series` and, with `--check-import`,
`import.status`, `import.qc_adequate` and `import.discovery`. Exit 0 = scan complete;
exit 2 = failed or truncated scan. Details: [`docs/local-folders.md`](../local-folders.md).

## Case note: vendor private tag rejected a whole series (2026-10-19)

Redacted. No identifying path, name or acquisition values are reported here.

| | Before (v0.5.0) | After (v0.5.2+) |
|---|---|---|
| Files with unreadable headers | ≈ 18 % (one complete axial series) | 0 |
| `private_values_raw` | — | equals the former error count |
| Import | succeeded, but that series was excluded | succeeded, all files readable, QC adequate, no QC warnings |

**Cause.** Every rejected file failed on one vendor private tag only:
`(01F1,1026)`, implicit VR, 6 bytes, `BytesLengthException`. pydicom's private
dictionary has a tag-specific ELSCINT1 entry typing this *Pitch* value as an 8-byte float
(FD), while the value is a short decimal string. Our strict header reader converted every
element and rejected the file.

**Fix.** Undecodable **private** values are kept as raw `UN` bytes instead of rejecting
the slice; public tags stay strict. The count appears as `private_values_raw`
(informational, not a warning). The checker still lists the tag under `error_groups`,
but those files count as readable. Private values are never used for geometry or pixels.

**How it was found.** The operator ran the checker locally and shared only its JSON; the
single `error_groups` entry identified the tag. No source files left the workstation.

Successful import shows the files are readable and the input QC passes. It does not
establish model accuracy.
