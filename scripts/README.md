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
| `capture_screenshots.py` | Regenerate the documentation screenshots in `docs/assets/` | `uv run python scripts/capture_screenshots.py`. Uses synthetic data and mocked models only. See *Capture documentation screenshots*. |
| `move_ollama_models_to_home.sh` | Move the system Ollama model store from `/` to `/home` | `sudo scripts/move_ollama_models_to_home.sh [TARGET]`. Administrator operation; read the script's preconditions first. It stops/restarts the service and changes system configuration. |

## Capture documentation screenshots

`capture_screenshots.py` starts the local workbench on a free loopback port with a
temporary data root. It creates the synthetic demo phantom and drives Chromium through
Playwright. Ollama and the 3D services point at an unused loopback port, so no real model
runs and no network access happens. The comparison outputs and the download progress are
mocked in the browser and labeled as mocked. Never capture patient studies.

The table lists what the script writes. Only `ui-about.png` is committed today; the other
PNGs exist after the first successful capture.

| PNG in `docs/assets/` | Content |
|---|---|
| `ui-study-viewer.png` | Synthetic phantom, slice 22, setup panel and viewer (1440 × 900) |
| `ui-results.png` | Real `heuristic-hu` findings below the research banner (full page) |
| `ui-comparison.png` | Sequential comparison: completed, abstained, failed and skipped models (panel) |
| `ui-model-setup.png` | Model availability, terms acknowledgement, mocked download progress (panel) |
| `ui-about.png` | About page with author, purpose and dependency licenses (full page) |
| `ui-dark-de.png` | German interface in dark mode after a heuristic run (1440 × 900) |
| `ui-mobile.png` | Synthetic study at 390 × 844 phone width |

Prerequisites:

* `uv sync --all-groups` completed.
* Chromium for Playwright is installed: `uv run playwright install chromium`. The script
  honours `PLAYWRIGHT_BROWSERS_PATH`, then searches `~/.cache/ms-playwright`.
* The host allows Chromium to start. Restricted sandboxes can block it.

Procedure, from the repository root:

1. Verify the server and routes without a browser.

   ```bash
   uv run python scripts/capture_screenshots.py --check
   ```

2. Capture all screenshots.

   ```bash
   uv run python scripts/capture_screenshots.py
   ```

3. Inspect each PNG in `docs/assets/` for patient data, absolute paths and host names.
4. Run the data gate.

   ```bash
   scripts/check_no_medical_data.sh
   ```

**Checkpoint:** step 1 ends with `Check passed: routes ready; no browser launched.` Step 2
prints one `wrote … (<bytes> bytes)` line per PNG and ends with `Done: 7 screenshot(s)`.
Content is deterministic: English and light mode except `ui-dark-de.png`, a fixed browser
clock, fixed engine timings and a seeded phantom. Pixels can still differ between hosts
because system fonts differ. Version numbers on the About page follow the installed release.
Page screenshots start at the top so the header and research banner remain visible.

**Recovery:**

* `Chromium not found`: install it with `uv run playwright install chromium`, or pass
  `--chromium /path/to/chrome`.
* Chromium fails to launch (for example `socket() failed: Operation not permitted`): run the
  script outside the sandbox or container.
* One shot fails: rerun only that shot, for example
  `uv run python scripts/capture_screenshots.py --only ui-comparison`.
* `… the data gate allows < 2 MB`: the PNG is too large to commit. Reduce the page content
  or capture a panel instead of the full page.
* To preview without touching tracked files, add `--out-dir data/results/screenshots`.

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
