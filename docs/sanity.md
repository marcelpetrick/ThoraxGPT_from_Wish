# Image-path readiness diagnostics

Research use only. This self-made experimental tool can produce incorrect, incomplete or
misleading findings. Its output is not professional medical advice or a basis for diagnosis
or treatment decisions.

Run commands from the repository root. Start Ollama and install each configured model
through its approved setup path first. No command downloads weights automatically.

```bash
uv sync --all-groups
uv run thoraxbench sanity configs/experiments/sanity/E001-sanity-s2-single.yaml --dry-run --limit 1
uv run thoraxbench sanity configs/experiments/sanity/E001-sanity-s2-single.yaml --limit 1
```

The first command prepares synthetic inputs without inference. The second sends a bounded
smoke run. `--limit` counts source/pair groups, not individual requests; a group can contain
several sizes, windows, conditions and layouts. Dry-run prints input and image counts but
not layout-expanded request counts. Inspect the YAML before running the full battery.
Use one GPU job at a time.

| Configuration suffix | Question | Input |
|---|---|---|
| `s1-synthetic` / `s1-lidc` | Do real, gray, noise, shuffled and absent images change the answer? | Synthetic or calibration only |
| `s2-single` / `s2-multi` | Does a large synthetic sphere change the answer? | Synthetic matched phantoms |
| `s3-describe` | What does one image show? | Synthetic and calibration; manual review required |
| `s4-pairs` | Do reference-centred and same-patient control slabs differ? | LIDC calibration only |
| `t2-binding` | Which attachment contains the bright disk? | Synthetic; two message layouts |

Checkpoint: each invocation creates a unique folder under ignored
`data/results/benchmark/<id>/` with `manifest.json`, per-request artifacts, checkpoints and
final `result.json` / `report.md`. Image bytes are omitted; request image hashes, raw provider
responses, prompts, runtime identity and logprobs are retained. These artifacts can contain
development identifiers. Do not commit them. This diagnostic command has no resume option;
checkpoints preserve completed requests after interruption but do not resume a run.

Recovery: inspect recorded errors and parse states. Missing models, unavailable endpoint,
unsafe output paths and non-calibration input guards must be fixed at their source. Never
bypass a guard or substitute internal-test/sealed data. All real inputs pass calibration
selection and the standard study-opening guard. Synthetic tests need no patient data.

Interpretation: repeated categorical answers alone do not prove ignored pixels. Compare
probabilities, image conditions and binding results. `P(yes)` is renormalised over visible
yes/no alternatives in the provider's top-logprob list; it is not calibrated probability.
The grammar and logprob request can change model behavior. A missing alternative in the
truncated top list has zero observed mass, not proven zero model probability. The stated
confidence is a separate score. Neither score establishes clinical validity.

S4 uses known lesion positions and controls selected away from recorded lesions. It tests
recognition on selected slabs, not detection, study accuracy or unbiased generalization.
Unmarked findings may remain in controls. Future controls enforce the distance from actual
rendered voxel edges after slab rounding. Historical runs used nominal slab half-width;
keep that difference visible when comparing runs. Single-message and one-message-per-image
requests are candidate layouts; their existence does not prove correct image-number binding.
T0 provider-token audit and a full T2 binding gate remain required before trusting citations.
