# Enable the restricted operations for an agent session

This page lists the Claude Code sandbox settings that an agent session needs for work the
default sandbox blocks. It also lists the operator tasks that wait for such a session.
Verified against the Claude Code sandboxing documentation on 2026-10-15.

> Research use only. This self-made tool is not professional medical advice. Its findings
> may be incorrect, incomplete or misleading. Do not use them for diagnosis or treatment.

## What the default sandbox blocks

| Operation | Symptom in the sandbox | Cause |
|---|---|---|
| Local Ollama inference | `Failed to connect to 127.0.0.1:11434 after 0 ms` | Each sandboxed command gets a private loopback interface on Linux |
| Playwright browser tests, screenshots | `process_singleton_posix.cc … socket() failed: Operation not permitted` | The seccomp filter blocks `AF_UNIX` sockets |
| Commit and push, GitHub release | Auto-mode classifier denial; `gh` reports no login | Publishing to the public repository needs operator approval and `gh` credentials |

`allowLocalBinding` and `allowedDomains` do not fix the loopback problem on Linux.

## Enable local Ollama access

Prerequisites: Ollama runs on the host. Check it outside the sandbox:
`! curl -s http://127.0.0.1:11434/api/tags | head -c 300`. Expect JSON.

1. Open `~/.claude/settings.json`.
2. Add the commands that must reach Ollama to `sandbox.excludedCommands`:

   ```json
   {
     "sandbox": {
       "excludedCommands": [
         "uv run thoraxbench *",
         ".venv/bin/thoraxbench *",
         "curl http://127.0.0.1:11434/*"
       ]
     }
   }
   ```

3. Restart the Claude Code session.

**Checkpoint:** `uv run thoraxbench models` lists the pulled Ollama models as available.
**Recovery:** if the connection still fails, check the `/sandbox` Overrides tab. An
admin-required sandbox ignores repository settings; use the user file or managed settings.

Excluded commands run without filesystem or network limits and with your credentials.
Keep the patterns narrow. They still pass through the normal permission prompts.

## Enable browser tests and screenshots

1. Choose one option.
   - Narrow: add `"./localPipeline.sh *"`, `"./localPipeline.sh"`, `"scripts/commit.sh *"` and
     `"uv run python scripts/capture_screenshots.py*"` to `sandbox.excludedCommands`.
   - Broad: allow every Unix socket:

     ```json
     { "sandbox": { "network": { "allowAllUnixSockets": true } } }
     ```

2. Restart the Claude Code session.

**Checkpoint:** `./localPipeline.sh` reports `PASS tests` including `tests/e2e/test_web_ui.py`.
**Recovery:** if Chromium is missing, run `uv run playwright install chromium` outside the sandbox.

`allowAllUnixSockets` cannot be narrowed on Linux. It also exposes sockets such as
`/var/run/docker.sock`, which grant host-level control. Prefer the narrow option.
`allowUnixSockets` is ignored on Linux.

## Enable commit, push and release

1. Log in to GitHub outside the sandbox: `! gh auth login`.
2. Approve the push when the commit script asks.

## Operator tasks waiting for these settings

Run each from the repository root. Read `docs/plan.md` → *Next steps* for the current list.

1. Commit the staged v0.2.0 file set:
   `scripts/commit.sh --minor --staged "feat(ui): add live runtime, model comparison and guided model setup"`
2. Publish the release:
   `gh release create v0.2.0 --title "ThoraxBench Local 0.2.0" --notes-file docs/releases/v0.2.0.md manual.html manual.pdf`
3. Capture documentation screenshots with `scripts/capture_screenshots.py` (see `scripts/README.md`).
4. Run MedGemma experiments through `thoraxbench benchmark` on the development split.
   Never use `--unseal`.

**Checkpoint:** version 0.2.0 on `main`, GitHub CI green, the release lists both manuals.

## Atomic commit queue

The sandboxed session could not commit: `commit.sh` runs the full gate, and the gate's
Playwright stage cannot start Chromium in the sandbox. Commit the work in this order. Each
step is one logical change. Stage exactly the listed paths, then run
`scripts/commit.sh --staged "<message>"`. The script stashes everything else during the gate.

Never stage the root dotfiles (`.bashrc`, `.gitconfig`, `.idea`, …) if they appear. They are
sandbox mount points, not project files.

`src/thoraxbench/cli/main.py` and `docs/architecture.md` carry changes for several steps.
Prepared versions of `main.py` live in the git-ignored `.pipeline/queue/` (lint- and
type-checked). Before steps 2, 3 and 4, run
`cp .pipeline/queue/main.stepN.py src/thoraxbench/cli/main.py && git add src/thoraxbench/cli/main.py`
with N = 2, 3, 4. `main.step4.py` equals the final file. Commit `docs/architecture.md`
(including its privacy section) whole in step 6.

1. **Release v0.2.0** (already staged): `--minor`,
   `feat(ui): add live runtime, model comparison and guided model setup`.
2. **Privacy:** `src/thoraxbench/privacy.py`, `src/thoraxbench/cli/privacy.py`,
   `tests/unit/test_privacy.py`, `src/thoraxbench/analysis.py`, `tests/e2e/test_mvp_cli.py`,
   and `main.step2.py`. Message: `feat(privacy): audit DICOM headers and redact output paths`.
3. **Acquisition:** `src/thoraxbench/acquisition/`, `src/thoraxbench/cli/acquire.py`,
   `tests/unit/test_acquisition.py`, `tests/integration/test_acquire.py`,
   `configs/datasets/lidc_idri.yaml`, `configs/datasets/nsclc_radiogenomics.yaml`,
   `docs/datasets.md`, and `main.step3.py`.
   Message: `feat(acquire): add license, budget, split and checksum gated acquisition`.
4. **Benchmark:** `src/thoraxbench/benchmark/`, `src/thoraxbench/cli/benchmark.py`,
   `configs/experiments/`, `tests/unit/test_benchmark_config.py`,
   `tests/integration/test_benchmark.py`, `docs/results.md`, and `main.step4.py`. Use `--minor`. Message: `feat(benchmark): add development benchmark runner and E000 baseline`.
5. **Screenshots:** run `uv run python scripts/capture_screenshots.py`, review every PNG, then
   stage `scripts/capture_screenshots.py`, `scripts/README.md` and `docs/assets/*.png`, and
   add the image embeds to `README.md` and `docs/ui.md`.
   Message: `docs(ui): add reproducible synthetic screenshots`.
   **Decision needed:** four shots show a rendered slice of the synthetic phantom. AGENTS.md
   forbids committing rendered CT slices; confirm that synthetic phantoms are exempt first.
6. **Documentation:** first regenerate `manual.pdf` (command at the end of `manual.html`;
   the PDF is two sheets behind). In `docs/plan.md`, flip the "Course correction work
   (uncommitted …)" entry to ✅ and drop "uncommitted". Set the README coverage badge from
   the full gate in `.pipeline/tests.log`. Then stage all remaining changes (`README.md`, `AGENTS.md`, `docs/plan.md`,
   `SECURITY.md`, `DATA_POLICY.md`, `docs/reproducibility.md`, `docs/vision_traceability.md`,
   other `docs/*.md`, `manual.html`, `manual.pdf`, `src/thoraxbench/splits/guard.py` message).
   Message: `docs(repo): document benchmark, acquisition, privacy and data policies`.

**Checkpoint:** `git status` shows only the sandbox dotfiles; every commit has a green gate.
**Recovery:** if a step's gate fails because it needs a file from a later step, move that
file forward to the current step and retry.

## Sources

- <https://code.claude.com/docs/en/sandboxing>
- <https://code.claude.com/docs/en/settings-reference>
