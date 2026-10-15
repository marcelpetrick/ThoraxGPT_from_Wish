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

1. Verify, push and release the local commits (see the next section).
2. Capture documentation screenshots with `scripts/capture_screenshots.py` (see `scripts/README.md`).
3. Run MedGemma experiments through `thoraxbench benchmark` on the development split.
   Never use `--unseal`.

**Checkpoint:** version 0.2.0 on `main`, GitHub CI green, the release lists both manuals.

## Local commits awaiting the full gate and push

At the user's request the sandboxed session committed the work locally as atomic
conventional commits with plain `git commit`. Versions were bumped as `commit.sh` does.
Every gate stage except Playwright passed on each commit's tree. Nothing is pushed.

| Commit | Version | Message |
|---|---|---|
| `083971a` | 0.2.0 | `feat(ui): add live runtime, model comparison and guided model setup` |
| `a80a714` | 0.2.1 | `feat(privacy): audit DICOM headers and redact output paths` |
| `6e5ce9f` | 0.2.2 | `feat(acquire): add license, budget, split and checksum gated acquisition` |
| `1578b0b` | 0.3.0 | `feat(benchmark): add development benchmark runner and E000 baseline` |
| `bd0a770` | 0.3.1 | `docs(scripts): add reproducible synthetic screenshot capture script` |
| `9de41d8` | 0.3.2 | `fix(splits): stop pointing to a nonexistent freeze command` |
| last | 0.3.3 | `docs(repo): document benchmark, acquisition, privacy and data policies` |

Prerequisites: the settings above are active. Work from the repository root.

1. Run `./localPipeline.sh`. Expect `RESULT: GREEN`, including `tests/e2e/test_web_ui.py`.
2. If a stage fails, fix it in a new commit through `scripts/commit.sh --no-push "fix(<scope>): …"`.
3. Regenerate `manual.pdf` (command at the end of `manual.html`; the PDF is two sheets behind).
   Commit it: `scripts/commit.sh "docs(manual): regenerate PDF manual"`. This also pushes.
4. Tag and publish v0.2.0 on its commit:
   `git tag v0.2.0 083971a && git push origin v0.2.0`, then
   `gh release create v0.2.0 --verify-tag --title "ThoraxBench Local 0.2.0" --notes-file docs/releases/v0.2.0.md manual.html manual.pdf`.
5. Capture screenshots after the decision below; embed them in `README.md` and `docs/ui.md`.
6. Set the README coverage badge from `.pipeline/tests.log`.

**Decision needed:** four shots show a rendered slice of the synthetic phantom. AGENTS.md
forbids committing rendered CT slices; confirm that synthetic phantoms are exempt first.

Never stage the root dotfiles (`.bashrc`, `.gitconfig`, `.idea`, …). They are sandbox mount
points, not project files.

**Checkpoint:** `git status` is clean, `origin/main` matches `main`, GitHub CI is green.

## Sources

- <https://code.claude.com/docs/en/sandboxing>
- <https://code.claude.com/docs/en/settings-reference>
