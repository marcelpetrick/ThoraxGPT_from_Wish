# LinkedIn video pilots — authorized local drafts, two 30-second cuts

Research use only. ThoraxBench Local is a self-made experimental tool. Findings may be
incorrect, incomplete or misleading. It does not provide professional medical advice
or a basis for diagnosis or treatment decisions.

**Current authorization (2026-10-18):** the user explicitly requested recording and editing
two **30-second** videos of a real successful detector workflow. This overrides the earlier
synthetic-only recording proposal for these local drafts only. Use the deliberately selected
positive **calibration** example `lidc_idri / LIDC-IDRI-0027` and `monai-lung-nodule`.
LUNA16-trained weights overlap LIDC: this is an illustration, never independent accuracy.
No sealed/internal-test case, acquisition, upload or publication is authorized by the recorder.
Keep all real frames, full takes, failed attempts and edits under ignored
`data/results/linkedin/`. Never commit patient pixels or video.

The completed delivery is recorded in [the delivery record](video-delivery-2026-10-19.md).
**Later user instruction (2026-10-19):** commit/push only the two reviewed final cuts
and accompanying captions/credits/checksums under [`media/`](../media/README.md).
This supersedes the local-only Git restriction for those cuts. Full takes, reports and
other frames stay ignored; no LinkedIn upload is authorized.

## Current recorder procedure

Prerequisites: a clean committed checkout, a green full gate, an already running loopback
UI with an idle processing queue, verified detector weights, Chromium, Xvfb, FFmpeg/FFprobe
and DejaVu Sans. Run commands from the repository root. Complete a real UI rehearsal and
inspect the source images for identifiers before capture. Header audit alone does not
establish absence of burned-in identifiers.

1. Start continuous capture on an isolated Xvfb display. It never records the personal desktop. Chromium is forced to X11 and does not inherit
   the personal Wayland display.

   ```bash
   uv run --extra detector python scripts/linkedin_video.py --repo "$PWD" capture \
     --url http://127.0.0.1:8001 --dataset lidc_idri --case LIDC-IDRI-0027 \
     --model monai-lung-nodule --allow-real-calibration --chromium /usr/bin/chromium
   ```

2. Save the printed take folder. Inspect its **uncut** `master.mp4`, `take.json` and
   `capture.log`. The master is 2560×1440, H.264 CRF16, 30 fps, limited to two encoder
   threads. Optional `--width 3840 --height 2160` captures 4K with greater CPU/disk cost.
   The visible library is narrowed to the selected calibration case before initial page load;
   requests for other studies/slices are blocked. Download staging also stays inside the
   take folder. The script drives source slices/windows/help, an actual queued detector job, candidate
   review/source navigation, the actual new-tab report, About, manual and EN/DE/light/dark.
   It also opens the read-only Evaluation landing and saves the actual offline HTML download.
   No results are mocked. It records source identity, real elapsed time, job/result IDs and
   detector metadata. Failed takes remain preserved and cannot be rendered as successes.

3. Inspect `cut-plan.json`. Adjust its per-shot pixel crops/start times to keep the UI
   readable and inside the recorded frame. Crops are presentation changes. Keep the genuine
   model/result pairing, explicit shortened-wait captions and actual processing duration.
   For animated framing, use `crop: [x, y, width, height]` for the complete context
   rectangle (omit it for the whole frame) and `focus_crop` for the full detail panel.
   Focus must lie inside context. The camera holds context for 0.6 seconds, moves
   smoothly for 1.8 seconds, then holds focus. Optional `return_to_overview: true`
   returns to context. Endpoints preserve aspect ratio; the entire focus stays visible
   throughout motion. Check the actual output, including all columns and image captions.
   The original take is never overwritten. Its finalized SHA-256 is checked before rendering.

4. Render separately after reviewing the original. Substitute the printed folder.

   ```bash
   uv run --extra detector python scripts/linkedin_video.py --repo "$PWD" render \
     --take data/results/linkedin/REPLACE_WITH_PRINTED_TAKE_FOLDER
   ```

5. Inspect both `pilot-A.mp4` (1080×1080) and `pilot-B.mp4` (1080×1350) in the new unique
   render folder. Each has exactly 900 frames / 30 seconds, H.264/yuv420p/30 fps, burned
   captions in a reserved band, SRT, thumbnail and FFprobe verification. Both disclose shortened waits. The
   project URL remains on screen for the final five seconds. No audio or upload occurs.

**Checkpoint:** the original includes the full real wait and outcome. Both edits disclose
selected calibration example, research-only/not-diagnosis status and LIDC training overlap.
Verify text/crops on a phone. A successful encoding does not establish model accuracy.
**Recovery:** keep any failure and its logs. Resolve the cause and record a new unique take;
do not replace failures with fabricated or synthetic findings. Check disk space before retrying.

## Dataset credit and local reuse check

The official [TCIA LIDC-IDRI wiki](https://wiki.cancerimagingarchive.net/pages/viewpage.action?pageId=1966254)
identifies images/XML as CC BY 3.0. The registry agrees. End cards credit LIDC-IDRI / TCIA,
Armato et al. (2015), CC BY 3.0 and dataset DOI `10.7937/K9/TCIA.2015.LO9QL9SX`. Each render
includes `credits.txt` with the full registry dataset citation, recommended 2011 publication
DOI `10.1118/1.3528204`, NCI/FNIH acknowledgement and
[license link](https://creativecommons.org/licenses/by/3.0/). Windowing, crops and captions
modify the presentation. No endorsement by TCIA or contributors is implied. Review the final
local draft before any separate publication decision.

## Historical pilot proposal — superseded

The following 60/90-second synthetic-only proposal is preserved as design history. Its
durations, synthetic-only restriction and pending-trigger status do not govern the explicitly
authorized two 30-second real-calibration local drafts above.

**Status:** two editorial pilots are ready for review. Recording, recorder automation,
encoding and publication remain pending. Start recording only after the user triggers it
and the readiness checkpoint below passes. These are scripts for a future recording,
not evidence that a successful model demonstration has already happened.

## Purpose and project

Introduce Marcel Petrick's ThoraxBench Local: a local research workbench for inspecting
prepared CT inputs, comparing experimental model outputs and retaining evidence of what
ran. It can help developers spot missing predictions, inspect disagreements and reproduce
a setup. Agreement, severity labels and confidence scores do not establish correctness.

Project: <https://github.com/marcelpetrick/ThoraxGPT_from_Wish>.
Start with [README](../README.md) and the [flight manual](../manual.html).

## Delivery format

| Pilot | Purpose | Duration | Frame | File |
|---|---|---|---|---|
| A: Meet the workbench | Short introduction and one workflow | 60 seconds | 1080 × 1080, square | MP4, H.264, yuv420p, 30 fps; AAC if narrated |
| B: Inspect the evidence | Slower technical walkthrough | 90 seconds | 1080 × 1350, 4:5 | MP4, H.264, yuv420p, 30 fps; AAC if narrated |

These are production choices for readable feed videos. Target 6–8 Mbps video and 128 kbps
AAC at 48 kHz, with a file below 100 MB. This file target is our preference, not a LinkedIn
limit. Keep key text inside the central 80% of the frame as an editorial margin. Preview
on a phone. Use close views of one UI area instead of shrinking the entire desktop.
Provide an SRT transcript and an optional version with burned-in captions. Keep the project
link on screen for at least five seconds. Use a matching PNG thumbnail.

LinkedIn's [organic upload requirements](https://www.linkedin.com/help/linkedin/answer/a548372?iframe=yes)
accept MP4, 10–60 fps, resolution from 256 × 144 to 4096 × 2304, and aspect ratios from
1:2.4 to 2.4:1. They list a 5 GB maximum and 15-minute maximum, with a three-second minimum
on desktop. Both pilots fit those requirements. LinkedIn's separate
[advertising specifications](https://business.linkedin.com/advertise/ads/sponsored-content/video-ads/specs)
recommend MP4 and 30 fps and list square and 4:5 formats. Advertising limits differ from
organic limits. Specs were checked on 2026-10-16; check again before uploading.

## Readiness checkpoint before recording

Prerequisites: clean committed checkout, green full gate, local browser and working local
UI. Use the English light theme. Do not expose terminal history, personal paths or secrets.

1. Follow the [current UI startup instructions](ui.md).
2. Create the code-generated synthetic demo.
3. Verify the demo's known synthetic structures against its generating code.
4. Confirm the selected model is installed and available.
5. Rehearse a real request with four prepared images if the model's supported configuration allows it.
6. Inspect the actual prepared inputs and response before calling it a four-image run.
7. Confirm that analysis, elapsed time, results and offline HTML export work.
8. Confirm that the disclaimer and model identity stay visible in the planned views.
9. Record the commit, model tag/digest, configuration and actual run duration in the take notes.

**Checkpoint:** a complete rehearsal has inspectable output and a working export. Synthetic
structures are reference features of the phantom; do not promise that a model will detect
them. Four model input images are four views of a synthetic study, not four independent
patients. For a strict four-image target, use a supported uniform selection with `n: 4`
and no added coronal view. Anatomy sampling preserves landmarks and can exceed `n`;
changing the image target alone does not guarantee four prepared images. If the UI
configuration cannot produce four, show its actual count or defer that shot. Heuristic slice illustrations are not VLM inputs. Do not invent image associations.

**Recovery:** if a model abstains or fails, retain that outcome. Either demonstrate the
failure honestly or use the clearly labelled deterministic HU baseline for the workflow.
Do not substitute a mocked result or imply that the baseline is a successful VLM run.
The poor calibration-readiness results in [results.md](results.md) remain a limitation.
If the four-input model path cannot finish reliably, postpone that part of the recording.

Use only the code-generated synthetic phantom and its images. The repository's ban on
committing or publishing rendered real CT studies applies. Do not use the provided real
study images for LinkedIn. A supplied image requires verified synthetic provenance before
use in this demo.

## Pilot A — “A local workbench you can inspect”

| Time | Picture and action | Narration / captions |
|---|---|---|
| 00–07 | Title: ThoraxBench Local. Marcel Petrick. Synthetic demo. Show the project URL. | “I'm Marcel Petrick. I built ThoraxBench Local, a small local research workbench for exploring experimental CT model outputs.” |
| 07–15 | Open the synthetic demo and move through the viewer. | “This example uses generated synthetic data. The viewer lets me inspect the study and understand what goes into a run.” |
| 15–24 | Show the model identity and the actual prepared four-image preview, if supported. Focus one tooltip. | “Here I choose a local model and inspect its prepared inputs. The help explains the settings.” |
| 24–33 | Start the real request. Keep elapsed time and rough estimate readable. | “The timer shows actual elapsed time. The wait estimate is a workstation guess, not measured inference progress.” |
| 33–44 | Show the real response, coverage or abstention, and research review/severity context. | “I inspect what it returned, including omissions and failures. Review flags are experimental cues, not clinical recommendations.” |
| 44–52 | Download and open the offline HTML report. | “An offline report keeps the inputs and findings together so another developer can review them.” |
| 52–60 | End card with URL, README and manual; research-only disclaimer. | “Find the code and flight manual on GitHub. This is a self-made research tool. It can be wrong and is not professional medical advice.” |

If the run takes longer than the slot, keep the full original recording and label the
edited jump “Wait shortened — actual elapsed: …”. Never accelerate only the timer without
an explicit edit label. Do not insert a result from another request.

Suggested post: “I built a local research workbench to inspect experimental CT model
outputs, compare findings and preserve reproducible evidence. This walkthrough uses only
synthetic data. Failures and missing predictions stay visible. Self-made research tool;
not medical advice. Code and manual: https://github.com/marcelpetrick/ThoraxGPT_from_Wish”

## Pilot B — “From inputs to a reviewable result”

| Time | Picture and action | Narration / captions |
|---|---|---|
| 00–09 | Presenter/title card. Project URL and synthetic-data label. | “I'm Marcel Petrick. ThoraxBench Local helps me ask a practical research question: what did this local model actually see and return?” |
| 09–20 | Load the synthetic demo. Inspect its known generated structures in the viewer. | “This generated phantom has known structures. They let me demonstrate the workflow without showing patient data. A known feature is not a guaranteed model detection.” |
| 20–33 | Choose an available model. Inspect its identity and four actual prepared inputs where supported. | “The configuration determines the prepared images, prompt and model. I inspect those inputs before interpreting a response.” |
| 33–43 | Start analysis. Show elapsed time and estimate tooltip. | “Actual elapsed time and rough wait estimates are separate. Neither is an accuracy measure.” |
| 43–57 | Show the genuine result and finding help, or an explicit abstention/error. | “Missing confidence and uncertain predictions remain unavailable. A failure stays a failure. These review and severity cues are experimental, not medical judgments.” |
| 57–70 | Opt into sequential comparison after the first run. Show model names, status and timing. | “Optional comparison runs available recommended models one after another. Skips, failures and disagreements remain visible. Agreement does not prove correctness.” |
| 70–80 | Open the offline HTML export. Inspect input preview and provenance. | “The report supports review of the setup and output. It helps developers trace a result rather than trust a polished summary.” |
| 80–90 | End card: GitHub URL, manual, research-only disclaimer. | “The source, setup instructions and manual are on GitHub. This self-made experimental tool may be incorrect or incomplete. It is not professional medical advice or a basis for diagnosis or treatment.” |

Only show comparison if the real sequential rehearsal succeeds or explicitly demonstrates
partial failures. Label every shortened wait. Keep a legible, static disclaimer during
results and the final card. Do not describe output as finding a disease or validating a model.

## Historical automation proposal — replaced by `scripts/linkedin_video.py`

The repository does not yet contain a dedicated LinkedIn recording script. The future
script should reuse synthetic demo setup and browser flow from the existing screenshot
and Playwright helpers. It should record a full, uncut browser run to ignored
`data/results/linkedin/<timestamp>/`, then retain the raw WebM, take notes and manifest.
Export the two edited pilots, subtitles and matching thumbnails from that take.

1. Check readiness before starting capture.
2. Launch the local UI on loopback.
3. Record the viewer, real analysis, results and HTML download using Playwright video.
4. Preserve the original recording without cuts.
5. Make a shot list with actual timecodes and explicit shortened-wait labels.
6. Encode MP4 variants with FFmpeg using the delivery settings above.
7. Verify codecs, dimensions, frame rate and duration with FFprobe.
8. Watch each exported video with captions on a phone-sized preview.
9. Review every frame for identifiers, secrets, readability and unsupported claims.

**Checkpoint:** retain a complete original run and two independently playable MP4 pilots,
with readable UI, correct project link and truthful model outcomes. Record the user's
choice before publishing; preparation of this plan does not publish anything.

**Recovery:** if capture, inference or encoding fails, keep diagnostics in the ignored
recording directory. Repair the failed step and repeat the rehearsal. Do not replace a
failed run with staged findings. Recheck current LinkedIn requirements before uploading.
