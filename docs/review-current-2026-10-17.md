Base: main @ aba1b31   Head: 5aec0e3
Files changed: 21   +281 / -46 lines

## Findings

#1  MEDIUM  Code  src/thoraxbench/api/static/app.js:631
    Adding the detector to every comparison roster makes membership-based cancellation messages describe detector behavior even when the detector was skipped and Ollama is running. Resolve the active or started-cancelled step before choosing provider wording at all three call sites.

## Verdict

The reviewed UI branch needs finding #1 fixed before release. The integrated correction selects the actual step and adds a real synthetic comparison cancellation regression in English/light and German/dark mobile layouts.

## Review scope and repairs

The base above is the resolved merge-base of the UI implementation branch against main
before integration. `main...HEAD` on main itself was empty; that is not evidence of a
whole-program audit. This review additionally follows the user's explicit current-code
scope through the runtime changes `aba1b31..941c536` and the integration corrections.

Runtime cross-review found one LOW Code issue at `adapters/ollama.py:325` in `941c536`:
truthiness removed an empty first-pass provider object, shifting second-pass generation
limit diagnostics to call 1. Preserve every non-None response, including `{}`. The
integration correction includes a mocked empty-first-pass/truncated-second-pass regression.
It preserves abstention and original raw responses. Schema documentation now states that
bounded fields can still exhaust a fixed token budget.

Both workers reviewed the other's changes. The lead traced CLI label validation and
prompt precedence, generation failures, exact prepared PNG/count/order tests, manifests,
registered output paths, inline/download dispositions, response CSP, escaped model text,
comparison scheduling, cancellation, browser focus and translated controls. The synthetic
combined HTML was independently opened under its actual response CSP, including its
sandboxed embedded report and image.

No additional confirmed Code or Architecture findings remain in the reviewed scope.
Final release requires the complete combined gate and recorded live checks. A clean
review and passing software tests do not establish medical prediction accuracy, official
Hugging Face/BF16 runtime parity or whole-study exclusion from sampled images.

## Verified repair checkpoint

Integration `a12b867` passed 846 tests at 97.87% coverage and all full-gate stages. Both
new regression cases were also run against their original clean branches: cancellation
failed because the UI showed detector wording during Ollama inference; diagnostic indexing
failed because an empty first call was dropped. The same repaired cases pass. The complete
dependency integration will run the full gate again; no unresolved review finding remains.

## Recorder review — 2026-10-19

Reviewed the new recorder branch at `ba66639` against its integration base `5aec0e3`.
The independent reviewer confirmed fixes for initial study selection, POST submission
matching, child-process cleanup, contained downloads/master integrity, genuine detector
source identity, report image selection, finite crop/time bounds and credit disclosures.
Twenty-five synthetic guard regressions and a genuine synthetic FFmpeg encode smoke pass;
both test cuts have 900 frames and 30-second duration. No confirmed blocker remains.
The worker full gate passed 858 tests at 97.84% coverage. The lead's combined gate and
real take/frame review remain release acceptance; no real images are committed.

## Final recording review — 2026-10-19

A clean v0.4.17 recording completed genuine MONAI inference in 80.108 seconds. Review
found captions overlapping the square footage. The renderer now reserves separate
header, footage and caption areas. Both repaired cuts were actually encoded, visually
reviewed across all six scenes and decoded in full without errors. FFprobe confirms
900 frames /30 seconds for both formats. See [delivery evidence](video-delivery-2026-10-19.md).
The failed first take and initial renders remain preserved; no patient pixels enter Git.
No unresolved finding remains in this delivery scope. Model recognition and unbiased
accuracy remain open scientific work, unaffected by presentation or software gate success.

## User framing correction and leftover review — 2026-10-19

The user correctly identified truncated interface content in the fixed-crop edits. The
pending media commit was stopped before publication. Replacements begin with context,
then smoothly pan/zoom to a complete panel. Independent source-rectangle review checked
viewer controls, full MONAI card, all Jobs columns, finding source, paired candidate
captions, report images and About details. Root review caught a further intermediate-frame
clipping risk: linear zoom plus linear camera-center motion does not preserve containment.
Reciprocal zoom now interpolates viewport dimensions linearly with the center.
Forty-nine focused tests pass. Actual synthetic encodes in both formats preserve all
four colored focus corners in every decoded frame, including optional return motion.

Historical Git changes were classified and preserved before cleanup. Calibration/P6
work is integrated or superseded. One ad hoc HMAC identifier proposal remains preserved
for a separate reviewed port; see [the inventory](worktree-cleanup-2026-10-19.md).

Revised real cuts passed complete decoding and exact 900-frame/30-second checks. Root
reviewed 15 overview/movement/focus frames per format. Gate exceptions name only the
two approved MP4 paths and pin their SHA-256; changed approved bytes and an unrelated
oversized synthetic file were both refused. No general media or size exemption was added.

Final independent acceptance found no blocker. The reviewer inspected both 15-frame
motion sheets, native-resolution Jobs/findings/candidate-pair/report frames and both
endcards, then independently checked both MP4s with FFprobe. Required content and labels
remain visible. Dense Jobs text is readable at native resolution. Exact-path/hash gate
exceptions match the final MP4s; all other guards remain intact.
