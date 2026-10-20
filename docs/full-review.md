# Full thorax review

The full thorax review is one research job for one study and one local image model. It
checks every slab of the chest for every core finding type, runs the deterministic HU
measurements and (when installed) the MONAI nodule detector once on the whole volume, and
ends with a plain-language outcome. It is an experimental research output, not a diagnosis.

## Prerequisites

* A study that passes input QC and whose source image loaded in the viewer (the same rules
  as *Run analysis locally*).
* An available local Ollama image model, for example `medgemma1.5-q4`.
* Optional: the detector extras and verified weights (`docs/detector-baseline.md`). Without
  them the job still runs and states that the detector did not run.

## Start a review

1. Select the study and the image model in the Analysis page.
2. Switch off *Compare configured research models*.
3. Click **Full thorax review**.

**Checkpoint:** below the button the job shows `Full review: image k of n checked · X s per
image · m images left, about M min` after the first image. The Jobs page shows the same
line. If the button stays disabled, read the line under it: it names the missing model or
the comparison switch.

**Stop:** *Stop this job* stops between slabs. The slabs already checked are kept and shown
as a partial result with their coverage. A running provider request is aborted.

API: `POST /api/jobs` with `{"kind": "full-review", "dataset": …, "case_id": …,
"model_id": …}`. Progress uses the shared job progress (`operation: review_images`,
`completed`, `total`, measured `seconds_per_item`, `remaining_s`). The result holds the
summary and links to `full-review.json` and `full-review.html` under ignored
`data/results/ui/<uuid>/`.

## How it works

| Step | Code | What happens |
|---|---|---|
| B1 coverage | `sampling.ThoraxSweep` (`thorax_sweep` v1) | Lung z-range from the HU cues, widened by 10 mm above (thoracic inlet) and 30 mm below (upper abdomen), clipped to the volume, tiled without gaps by 5 mm slabs (whole slices). More than `n` = 96 slabs widen the slabs instead. |
| Visit order | `sampling.coarse_to_fine` | Both ends, the middle, quarters, eighths … until every slab is visited, so an early stop still spreads over the chest. Results stay cranial-first. |
| B2 query | `fullreview.runner`, prompt `P7` | One image per call: the slab MIP rendered in the model's own mode (MedGemma RGB or lung window, configured size). All 16 core labels, yes/no/null plus a short description, strict schema v2, same parser. A positive must cite IMAGE 1. |
| Baselines | `analyze_study` | HU heuristic once (nodule candidates with slice and side; whole-scan cues such as effusion volume). MONAI detector once when available; scores ≥ 0.5 enter the list. |
| B3 aggregation | `fullreview.aggregate.aggregate_labels` | Per label: positive rate over slabs that answered it (null is not negative). Neighbouring positive slabs form clusters; one non-positive slab inside is bridged. A label positive on more than 60 % of its answered slabs is *not informative (constant answer)* and yields no cluster. A model positive on more than 85 % of all answered questions is constant as a whole. |
| B4 ranking | `fullreview.aggregate.rank_look_here` | Detector candidates, HU candidates (matched within 10 mm and a compatible side) and VLM clusters (nodule/mass clusters absorb a detector/HU point within one slab) become one list. More independent sources rank first, then agreement, detector score, VLM support, cranial position. At most 25 entries. |
| B6 outcome | `verdict_of`, `next_steps`, `reports.full_review` | Verdict `findings_to_review`, `nothing_flagged_in_checked_area` or `not_assessable`; coverage; places to look; labels checked by the whole-volume tools (`labels_tool_checked`: detector → nodule, density rules → their labels), labels not informative or not flagged by the image model, and `labels_not_checked` (answered by no tool; without a slab sweep the app says they need an image model); next steps only from the existing Fleischner code and knowledge-base follow-up text. |

All thresholds are named constants in `fullreview/aggregate.py` and are stored in
`provenance.thresholds`; the strategy id, version, parameters and hash, the prompt hash
and the model digest are stored in the summary provenance.

## Output

* `full-review.json`: verdict, coverage (`slabs_total`, `slabs_visited`, `slabs_answered`,
  `partial`, `stopped`, `runtime_failed`, covered slice range), timing, per-label rates and
  clusters, look-here list, detector/HU status, every slab's status and positives, and
  provenance.
* `full-review.html`: self-contained, no scripts or network. Outcome box first, one short
  disclaimer line, then where to look with downscaled copies of the images sent to the
  model for those slabs. Slice numbers are one-based.
* Neither output prints SeriesInstanceUID, patient identifiers or local paths. Model text
  is escaped and redacted like every analysis output.

## Timing

Time per image is measured during the run and shown after the first image. The plan
estimate is about 60–70 slabs for a 317 mm scan and roughly 10–15 min with MedGemma Q4 on
the 8 GB workstation. The first slab includes model loading and is slower.

Measured smoke (2026-10-20, synthetic phantom, `ThoraxSweep(n=8)`, real local Ollama
`medgemma1.5:4b-it-q4_K_M`, detector not installed): 26–49 s per image (first image 49 s
including load), about 35 s mean, so a 60-slab review would take about 35 min, not
10–15 min. Five of eight slabs abstained and the three answered slabs gave no usable
label answers, so all 16 labels were unanswered; the outcome came from HU cues only.
This is an execution check, not benchmark latency or accuracy. Reducing the per-call
output (fewer labels per call or a smaller generation budget) is open.

## Limits

* Full coverage does not make a small image model accurate. When its answers are constant
  the outcome says so and only the detector and HU measurements count.
* The detector is the only component with demonstrated signal (nodules only). LUNA16
  training overlaps LIDC-IDRI; scores are uncalibrated.
* One 5 mm MIP slab per call loses fine detail and cross-slab context; mediastinal labels
  are judged in the model's render mode only.
* "Nothing flagged" never means the scan is normal. Only a radiologist's report counts.
* Validate on synthetic studies and calibration cases only; never on the sealed holdout.

## Update 2026-10-20 (review fixes)

- Density-rule (HU) entries alone are listed as **weak cues** and never make the verdict
  "findings to review"; they still raise agreement when another tool points to the same place.
- The review can start with the detector (1️⃣ `monai-lung-nodule`) or the HU baseline: then
  no image-model slab sweep runs and the detector plus density rules check the whole volume.
  With MedGemma the sweep adds about 2 minutes per slab and, in test runs, answered "absent"
  for every label (see `docs/model-test-runs-2026-10-20.md`).
- MedGemma's per-slab "abstain" (it sees one slice) no longer discards its per-label answers.
- Live check after the fixes (synthetic phantom, MedGemma Q4, stopped after 8 of 59 slabs
  to free the GPU): all 8 slabs answered (previously none), every label "absent" on every
  slab including the nodule level; ~110 s per slab while the detector shared the GPU. The
  detector found the planted nodule and the HU rules agreed, so the outcome was "findings to
  review" with that nodule first. Use the detector-only review for practical runs.
