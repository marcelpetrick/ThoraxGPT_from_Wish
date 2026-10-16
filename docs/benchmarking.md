# Run a development benchmark

> Research use only. This self-made experimental tool may return incorrect, incomplete or
> misleading findings. It is not professional medical advice or a basis for diagnosis or
> treatment decisions.

Prerequisites: install the locked dependencies. Create the frozen patient split before
indexing real studies. Index the development cases named in the experiment. Vision-model
experiments also require their configured model in local Ollama. Run every command from
the repository root. Keep the sealed holdout closed.

1. Run a limited pipeline check.

   ```bash
   uv run thoraxbench benchmark configs/experiments/E000_heuristic_hu_baseline.yaml --limit 2
   ```

2. Open the file named by the printed `Report:` path.
3. Inspect `result.json` in the same directory.
4. Run the full development experiment when the limited check is understood.

   ```bash
   uv run thoraxbench benchmark configs/experiments/E000_heuristic_hu_baseline.yaml
   ```

**Checkpoint:** the command prints per-variant status counts, two output paths, and the
experiment config SHA-256. Failed and abstained cases remain explicit. A limited run is
partial. The E000 heuristic control does not establish learned-model accuracy or clinical
validity. Read [recorded results and limitations](results.md) before interpreting metrics.

**Recovery:** if the split or index is missing, create it through the guarded CLI first.
If a vision model is unavailable, check `uv run thoraxbench models` and local Ollama.
Do not substitute a cloud endpoint. `--unseal` is unsupported and exits with status 2.

## Configuration and saved runs

The experiment's `labels` select both requested findings and scored labels. Prompt
precedence is variant override, experiment setting, selected model configuration, then
`P3`. A variant inherits unset settings from the experiment. Inference receives the
resolved prompt and label set.

Each invocation writes a new directory under the configured data directory:

```text
results/benchmark/<experiment-id>/<timestamp>-<hashprefix>-<uuid>/
  result.json
  report.md
```

The timestamp is UTC. The hash prefix contains the first 12 characters of the experiment
file SHA-256. Follow the printed paths; do not assume a fixed latest-run filename.
Repeated, partial and full runs preserve previous outputs. Historical flat paths in
[the results record](results.md) identify earlier runs and remain valid historical examples.
