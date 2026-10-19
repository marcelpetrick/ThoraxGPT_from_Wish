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
| `fetch_monai_bundle.py` | Explicit pinned MONAI detector setup | `uv run python scripts/fetch_monai_bundle.py` prints terms without download (exit 2); `--accept-terms` downloads and verifies; `--verify` checks local files only. See `docs/detector-baseline.md`. |
| `capture_screenshots.py` | Regenerate the documentation screenshots in `docs/assets/` | `uv run python scripts/capture_screenshots.py`. Uses synthetic data and mocked models only. See *Capture documentation screenshots*. |
| `move_ollama_models_to_home.sh` | Move the system Ollama model store from `/` to `/home` | `sudo scripts/move_ollama_models_to_home.sh [TARGET]`. Administrator operation; read the script's preconditions first. It stops/restarts the service and changes system configuration. |

## Capture documentation screenshots

`capture_screenshots.py` starts the local workbench on a free loopback port with a
temporary data root. It creates the synthetic demo phantom and drives Chromium through
Playwright. Ollama and the 3D services point at an unused loopback port, so no real model
runs and no network access happens. The comparison outputs and the download progress are
mocked in the browser and labeled as mocked. Evaluation shots read synthetic benchmark runs
with scripted model outputs. Never capture patient studies.

The table lists the twelve committed synthetic screenshots. The capture script can
regenerate them; compare the output before replacing tracked images.

| PNG in `docs/assets/` | Content |
|---|---|
| `ui-study-viewer.png` | Synthetic phantom, slice 22, setup panel and viewer (1440 × 900) |
| `ui-results.png` | Real `heuristic-hu` findings below the research banner (full page) |
| `ui-comparison.png` | Sequential comparison: completed, abstained, failed and skipped models (panel) |
| `ui-model-setup.png` | Model availability, terms acknowledgement, mocked download progress (panel) |
| `ui-jobs.png` | Shared processing queue with mocked job states |
| `ui-about.png` | About page with author, purpose and dependency licenses (full page) |
| `ui-dark-de.png` | German interface in dark mode after a heuristic run (1440 × 900) |
| `ui-mobile.png` | Synthetic study at 390 × 844 phone width |
| `ui-evaluation-runs.png` | Evaluation: synthetic benchmark runs and the per-case reference/prediction table (full page) |
| `ui-evaluation-case.png` | Evaluation case detail: image information, evidence check, raw response (panel) |
| `ui-evaluation-compare.png` | Evaluation: descriptive comparison of three synthetic setups (panel) |
| `ui-evaluation-mobile.png` | Evaluation in German and dark mode at 390 × 844 |

The Evaluation captures use a second temporary tree from `thoraxbench.synthetic_runs`: the
real benchmark runner over code-generated phantoms. The HU baseline runs for real; the two
"vision" variants are scripted outputs whose raw text states that no model ran.

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

The `ui-jobs` capture uses scripted server job state and elapsed time over the synthetic phantom.
It does not run a vision model or measure inference latency.

## Bounded P6 synthetic probe

From the repository root, after the configured local P6 model is installed:

```bash
uv run python scripts/probe_p6.py --window both
```

This sends four synthetic inputs (sphere/control × two windows), one condition each, with
up to eight local calls. It writes unique raw/provenance artifacts under ignored
`data/results/p6-probe/`. It reads no real or sealed patients. Both latest readiness gates
failed; see `docs/model-usage-review-2026-10-17.md`. Do not present it as accuracy.

Use `--view full --slab-mm 5 --window both` for the separate selected-plane synthetic
context check. This is a known target plane, not detection. Its latest categorical gate
also failed. Raw responses and source/script hashes remain preserved per invocation.

## `linkedin_video.py` — local recording and separate editing

Follow [the current video procedure](../docs/linkedin-video-plan.md). The user authorized
two 30-second local draft cuts using a deliberately selected approved LIDC calibration
example and the actual MONAI detector. This is not an accuracy benchmark or an upload tool.

`capture` requires a clean checkout, explicit `--allow-real-calibration`, a loopback `--url`,
an approved registry and a calibration guard. It owns an isolated Xvfb/Chromium display and
preserves an uncut high-quality master plus failed attempts under ignored results. It never
records the personal desktop, downloads weights or starts a server. `render` reads the
reviewed original and editable cut plan, writes unique square/portrait 30-second H.264 cuts
with persistent disclosures, captions, five-second URL/credit end cards, SRT and FFprobe
checks. Inspect every final frame/crop; local recording does not authorize publication.

Synthetic metadata/guard tests: `uv run --extra detector pytest tests/unit/test_linkedin_video.py -q --no-cov`.

## Inspect one DICOM header locally

Run from the repository root. Choose one file, including a file without a suffix:

```bash
uv run --no-sync python scripts/dcom_evaluator.py "/absolute/path/to/one/file"
```

The helper in `scripts/` prints JSON to stdout. It reads that file's header without decoding
pixels or traversing its folder. It reports technical metadata, decoder-package versions,
and malformed tag numbers, VRs and byte lengths. It omits input paths, identifying values,
raw bytes and exception/warning messages. Review output before sharing; this is not an
anonymization guarantee. Exit 0 means the inspected header converted without errors;
exit 2 means the JSON describes a read/conversion failure. Neither establishes clinical
usability. Research use only; this self-made helper is not medical advice.

For an explicit local pixel-decoder check, append `--check-pixels`. It reads pixels only
on your computer and prints shape/type or an exception class, never pixel values or an
image. The helper never uploads data or writes an output file unless you redirect stdout.

## Scan a folder before a full import

Run from the repository root. Choose the folder on your own workstation:

```bash
uv run --no-sync python scripts/dcom_evaluator.py --scan-headers "/absolute/path/to/folder"
```

This scans headers only. It reports aggregate error groups, counts and opaque series
summaries. It does not decode pixels, start a model or export images. The default bounds
are 10,000 files and 300 seconds; use `--help` for explicit limits and `--progress` for
aggregate counters on stderr. Paths and identifying values are omitted from JSON.

**Checkpoint:** inspect `status`, file counts, error groups and series eligibility. Exit 0
means the scan completed, even when some headers were unreadable; it does not mean every
file was usable. Exit 2 includes failure or a truncated scan. Correct the source or choose
explicit bounds before retrying. Never treat a partial scan as a full import check.

For an explicit local pixel-loading and input-QC check:

```bash
uv run --no-sync python scripts/dcom_evaluator.py --scan-headers --check-import "/absolute/path/to/folder"
```

This runs the application's import/QC path only after a complete header scan. It does not
run a model or create an image/report export. Inspect the `import` result and QC; readable
headers alone do not prove that pixels decode or that the selected CT series is adequate.
Keep the split guard enabled. Review JSON before sharing; this is not anonymization.
