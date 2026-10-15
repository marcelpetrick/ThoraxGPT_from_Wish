# A reproducible MVP test

> Research use only. This self-made experimental tool is not medical advice from a
> qualified healthcare professional, a diagnosis, or a medical device. Available models
> and reference knowledge may produce incorrect, incomplete or misleading findings.
> Do not use outputs for diagnosis or treatment decisions.

![Synthetic input to saved findings and report](assets/mvp-walkthrough.svg)

## Input and command

Prerequisites: `uv`, Python 3.14 and the source checkout. Start in the repository root.
Keep that working directory throughout this procedure. Use only synthetic data.

1. Install the locked dependencies.

   ```bash
   uv sync --frozen --all-groups
   ```

2. Generate the study.

   ```bash
   uv run thoraxbench demo-data data/demo/user-test
   ```

3. Run the baseline.

   ```bash
   uv run thoraxbench analyze data/demo/user-test --model heuristic-hu \
     --output data/results/user-test/result.json \
     --report data/results/user-test/report.md \
     --html data/results/user-test/report.html
   ```

4. Open `data/results/user-test/report.html` in a browser.
5. Inspect the matching JSON and Markdown files.

**Checkpoint:** exit status 0, adequate QC, no abstention, and the synthetic findings listed
below. The HTML opens offline with embedded illustrations. Timing can differ.

**Recovery:** if the command fails, read the terminal reason and any saved result. Confirm
the study directory and output paths. Do not treat failure or abstention as a negative
finding. Keep image-bearing exports in ignored `data/results/`.

The default generated phantom is 64 synthetic axial CT slices with spacing
5.0 × 2.5 × 2.5 mm. It includes a right 12 mm nodule and a right fluid-density region.
It contains no real patient images. The walkthrough illustration is a vector schematic,
not a rendered DICOM slice. The test reads no sealed patients.

The `--html` option additionally creates a self-contained, offline report with embedded
PNG previews and finding-to-image links where evidence was supplied. Vision-model runs
show the actual prepared model inputs; heuristic runs show labeled source-slice previews,
since that baseline operates on the HU volume. Missing or invalid evidence is never
presented as a confirmed image association. This HTML export was added after the original
v0.0.29 run below; use the current version to reproduce it.

## Browser acceptance procedure

1. Start `uv run thoraxbench serve` from the repository root.
2. Open `http://127.0.0.1:8000`.
3. Follow the demo, viewer, analysis and download checklist in
   [the operator manual](../manual.html#workbench).
4. Check the research disclaimer in the UI and downloaded HTML.
5. Stop the server with Ctrl+C.
6. Open the downloaded HTML again.

**Checkpoint:** offline images still render. The explicit status and educational severity
remain visible. Use mocked models for automated comparison and failure tests; never use
patient or sealed data for browser screenshots.

## Actual recorded outcome

Recorded on 2026-10-15 using v0.0.29, commit `fb7d7b7`, with a clean source tree.

| Check | Observed result |
|---|---|
| Process | Successful, exit status 0 |
| Model | `heuristic-hu`: deterministic rules, not an AI model |
| QC | Adequate |
| Abstention | False |
| Nodule | Right, estimated 12 mm, uncalibrated heuristic score 0.79 |
| Fluid region | Right pleural-effusion label, uncalibrated heuristic score 1.00 |
| Analysis-stage runtime | 0.464544683 s, displayed as 0.465 s |
| Saved outputs | Findings JSON and English research Markdown |

The runtime covers preprocessing, inference and parsing inside `analyze_study`; it
excludes DICOM loading, provenance collection, report rendering and file writes. It is
one measurement on this workstation, not a latency benchmark. A score of 1.00 is a
rounded heuristic output, not 100% accuracy or calibrated certainty.

Selected fields from the actual result:

```json
{
  "model_id": "heuristic-hu",
  "study_quality": {"adequate": true, "limitations": []},
  "abstain": false,
  "positive_findings": [
    {"label": "pleural_effusion", "laterality": "right", "score": 1.00},
    {"label": "pulmonary_nodule", "laterality": "right", "size_mm": 12.0, "score": 0.79}
  ]
}
```

This excerpt is a readable summary: the full file stores the report under `report`,
with findings under `report.findings` and their scores in `confidence`.

## What this verifies

Synthetic DICOM generation → guarded input loading → geometry/HU/QC → deterministic
measurements → heuristic inference → parsed findings → JSON and Markdown exports works.
The designed nodule and fluid structures appear in the output. This is a functional
smoke test; it does not establish real-patient detection accuracy or generalization.

The separate live MedGemma Q4 smoke test completed in about 49.5 s but returned empty
findings. Empty predictions now abstain. A full-label request produced excessive output;
generation is bounded at 4,096 tokens and truncation also abstains. The current AI model
therefore has working local transport but unproven useful CT predictions.

See [model selection and benchmark status](model_selection.md) for comparisons, and
[the plan](plan.md) for remaining work. Real or derived image data and full local run
artifacts remain outside Git under `data/`.

## UI and illustrated-export completion check (2026-10-15)

Repeated the synthetic CLI workflow from the working tree based on v0.0.29 using
`data/demo/ui-completion` and `data/results/ui-completion/{result.json,report.md,report.html}`.
It completed with adequate QC, no abstention, the right 12 mm nodule (score 0.79) and
right fluid region (score 1.00). Recorded analysis-stage time was 0.387528765 s.
The HTML includes embedded source-slice illustrations and the research disclaimer;
no prepared vision images are claimed for the HU baseline. Full artifacts stay ignored.

Browser acceptance uses a separate temporary synthetic-only directory and a loopback
server with an unavailable Ollama endpoint. This exercises the built-in baseline without
contacting a model server or opening any real or sealed study. The accepted workflow covers
preferences, viewer controls, findings, JSON/Markdown/HTML downloads, offline images, help,
About licenses and narrow screens. Failure/abstention checks preserve explicit limitations.

The completed HTML review adds visible educational severity and typical attention, positive
findings first, terminology and follow-up context, plus expandable English report/raw output/
provenance. Negative or uncertain findings are not assigned a severity and do not establish
that no review is needed. The stronger self-made-tool and fallibility disclaimer appears in
both UI languages and the offline HTML. Five browser tests cover these workflows.

Integrated non-live verification after these changes: **272 tests passed, 98.98% coverage**;
formatting, lint and strict typing passed. The final release uses the full commit-script gate,
including package build, clean-wheel installation and locked-dependency audit.

See the [HTML operator manual](../manual.html) or [matching PDF](../manual.pdf) for the complete
setup and run procedure. The manual was checked at desktop/mobile widths, all navigation
anchors resolved, and the eight-page A4 PDF was checked by text extraction and rendered-page
inspection. Neither manual contains patient images.

A further Playwright smoke check exercised the user's running loopback UI at v0.1.1:
create synthetic demo → heuristic findings → HTML download → offline images and visible
educational severity. It passed. The local review file and screenshot are ignored under
`data/results/user-ui-test/`; no real study was analyzed.
