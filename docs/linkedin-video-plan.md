# LinkedIn video pilots — planned, not recorded

Research use only. ThoraxBench Local is a self-made experimental tool. Findings may be
incorrect, incomplete or misleading. It does not provide professional medical advice
or a basis for diagnosis or treatment decisions.

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

## Future recording automation — implement after the trigger

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
