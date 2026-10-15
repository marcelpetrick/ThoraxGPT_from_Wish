# Repository helper scripts

Run the examples from the repository root. Each script resolves repository paths from its
own location. Read its header before use; not every helper implements `--help`.

## Normal development procedure

1. Inspect the working tree with `git status`.
2. Run `./localPipeline.sh --fast` while iterating.
3. Review the complete diff and update affected living documentation.
4. Commit through the full gate.

   ```bash
   scripts/commit.sh "docs(manual): clarify operator steps"
   ```

**Checkpoint:** the script bumps the version, passes the full pipeline, commits, then
pushes. A failed gate makes no commit and reverts the version bump.

**Recovery:** inspect `.pipeline/<stage>.log`, correct the cause and retry. Do not use the
script's `--fast` option to bypass the required full commit gate. Use `--staged` only when
you intend to commit the staged changes; other work is stashed during verification.

| Script | Purpose | Usage / checkpoint |
|---|---|---|
| `bump_version.sh` | Update semver in `src/thoraxbench/__init__.py` | `scripts/bump_version.sh patch` (also `minor` or `major`). Normally let `commit.sh` call it. |
| `commit.sh` | Bump, gate, commit and push | `scripts/commit.sh [--minor] [--staged] [--no-push] "feat(x): message"`. Repository policy requires the full gate even though the helper also accepts `--fast`. |
| `land_branch.sh` | Integrate an existing worker branch onto `main` | `scripts/land_branch.sh --full <branch>`. Requires a clean tree. Do new work directly on `main`; this helper exists for previously created branches. |
| `check_headers.sh` | Verify GPL-3.0-or-later SPDX headers | `scripts/check_headers.sh`. Expect a success message or a list of missing headers. |
| `check_no_medical_data.sh` | Reject medical data, weights and secrets in Git inputs | `scripts/check_no_medical_data.sh`. Expect a passed gate. Remove forbidden files from Git inputs before retrying. |
| `move_ollama_models_to_home.sh` | Move the system Ollama model store from `/` to `/home` | `sudo scripts/move_ollama_models_to_home.sh [TARGET]`. Administrator operation; read the script's preconditions first. It stops/restarts the service and changes system configuration. |

## Read a helper before using it

1. Read the header, for example `sed -n '1,40p' scripts/commit.sh`.
2. Check the required inputs and effects.
3. Run the helper only when its prerequisites are satisfied.
4. Inspect its exit status and output.

If branch integration conflicts, preserve the changes and inspect the conflict before
continuing. Do not force-push. If a system model-store move fails, inspect its service and
filesystem state before retrying; do not delete either copy without verification.

Research use only. ThoraxBench Local is a self-made experimental tool, not professional
medical advice. Its findings may be incorrect, incomplete or misleading. Do not use them
for diagnosis or treatment decisions. Never commit medical data or model weights.
