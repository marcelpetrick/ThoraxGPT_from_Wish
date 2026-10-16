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

## Current operator status (2026-10-16)

The publication handover is resolved. At resumption, GitHub main was v0.3.6 at 03754d1.
The unrestricted session subsequently pushed through v0.3.9; see docs/plan.md for current
work. This paragraph is an environment handover record, not a fixed latest-version claim.
The public v0.2.0 release points to 083971a and includes both operator manuals.
Do not repeat the historical tag/release commands.

This unrestricted session can reach Ollama and launch Chromium. Code-generated synthetic
phantom screenshots are approved; real study renders remain forbidden. See AGENTS.md and
DATA_POLICY.md. Screenshot timings and mocked model states are illustrative.

The remaining environment obstacle is a full shared /tmp tmpfs. Start in the repository
root and use disk-backed task storage without deleting unrelated temporary files:

```bash
mkdir -p /var/tmp/thoraxbench-pipeline-mpetrick
TMPDIR=/var/tmp/thoraxbench-pipeline-mpetrick ./localPipeline.sh
```

**Checkpoint:** every stage passes, including Playwright. Review synthetic-only screenshots
and commit through scripts/commit.sh, with the same TMPDIR if required. Then follow the current engine priority in docs/plan.md. Preserve durable artifacts before
bounded calibration-only experiments. Full sweeps require useful-output readiness.
Never pass --unseal.

The sandbox settings above describe the previous restricted environment. They are not
instructions to change settings in this unrestricted session.

## Sources

- <https://code.claude.com/docs/en/sandboxing>
- <https://code.claude.com/docs/en/settings-reference>
