# Model recovery and result review plan — 2026-10-17

Research use only. This self-made experimental tool may produce incorrect, incomplete or
misleading findings. It is not medical advice or a basis for diagnosis/treatment decisions.

## Objective and acceptance

Make local requests finish reliably, distinguish visual signal from plausible text, and
make each saved result easy to inspect with its actual inputs, source and failure reason.
A passing transport/schema test is not model accuracy. Keep the working MONAI detector
available while MedGemma readiness remains experimental. Never suppress abstentions.

## Confirmed failure in the user's current run

The Q4/P3 request stopped after exactly **4096 generated tokens**. Its prompt used 4544
tokens with a 16384-token context, so the recorded failure is output-budget exhaustion,
not the 600-second HTTP timeout. Its 13530-character response repeated the sixteen-label
roster seven to eight times instead of closing the JSON object. Increasing or removing the
cap would prolong a schema loop; that is not the selected fix. The original run is preserved.

The default Q4/Q8 profiles still select P3's unbounded schema even though bounded
P5/schema-v2 exists. Earlier P5 runs improved completion, but did not establish useful
recognition. RGB/HU windows already match Google's executable CT example. Runtime,
message layout and task differences still need a controlled comparison.

## Work packages and ownership

| Work | Owner | Scope and acceptance |
|---|---|---|
| R1 termination and focused requests | model-runtime agent, isolated worktree | Use bounded P5 defaults for Q4/Q8, no heuristic cues, image-only captions; preserve historical prompt definitions. Expose actual token/budget/repetition diagnostics. Add canonical CLI label selection. Synthetic/mocked regressions; full commit gate. |
| U1 About contribution entry | UI agent, isolated worktree | Canonical GitHub link for forks/issues/contributions, EN/DE text and accessible help, corrected purpose text. Updated synthetic screenshot and synchronized HTML/PDF manual. Atomic gated commit. |
| U2 result review | UI agent, isolated worktree | Open HTML in a new tab beside downloads, including partial and abstained results; inline response and restrictive report CSP, images/styles render; simple context and result inspection. Synthetic API/browser tests in both languages/themes and mobile. Atomic gated commit. |
| R2 bounded live comparison | lead, one GPU owner | After the user's current queue becomes idle: one focused condition, fixed inputs, existing calibration positive/control pair, unique provenance/raw-response artifacts. Compare completion, requested-label uniqueness, explicit abstentions and categorical behavior. No threshold tuning, broad sweep or hidden retries. |
| R3 complete E2E and self-review | lead | Synthetic demo → viewer → queued inference → visible result/failure → new-tab HTML → offline download. Inspect complete combined diff, strict guards, manual, optional detector setup and full gate. Merge atomic commits and push. |

Maximum two subagents. The lead owns GPU scheduling and integration. No worker changes the
main environment or interrupts the user's active comparison. Preserve existing session
results and download links; plan any necessary provider/server transition explicitly.

## Sequence

1. Preserve the failed request, raw output, counts and input identities. Do not rerun it.
2. Fix structural termination and add focused-condition controls with mocked tests first.
3. Keep the About change separate from the result-review change and runtime fix.
4. Wait for the current queue and provider to be idle before the next GPU request.
5. Run the focused bounded profile on a predeclared positive/control calibration pair.
6. Record complete output, duplicates, abstentions, references, wall time and raw text.
7. Stop token-budget experiments if categorical outputs stay constant or unsupported.
8. Perform official Hugging Face/BF16 parity only with approved weights/access. Do not
   bypass gating or present another Ollama prompt as official-runtime parity.
9. Complete synthetic E2E, self-review and full local/CI gates. Preserve all failures.

## Readiness gates

- **Termination:** every bounded request finishes, has exactly the requested canonical
  labels once, and has no token-limit failure. A provider error remains a failure.
- **Evidence:** positive constrained findings retain valid one-based input references;
  this is necessary but does not establish visual correctness. No reference is invented.
- **Signal:** both positive/control classes are represented. Report misses, positives on
  controls and abstentions. Constant answers fail readiness even when output parses.
- **Usability:** failed and completed outputs are distinguishable; model, study, image
  count and source remain visible. Opening a report starts no inference and needs no
  download/open-file dance. Offline download remains available.
- **Safety:** sealed 20% and internal-test cases stay out of tuning. No patient images,
  weights or identifiers in commits/screenshots. No cloud inference or remote LAN changes.

## Sources and limits

[Ollama chat fields](https://docs.ollama.com/api/chat),
[Ollama generation parameters](https://docs.ollama.com/modelfile), and
[structured outputs](https://docs.ollama.com/capabilities/structured-outputs) distinguish
context, output budget and schema enforcement. Google's
[CT example](https://github.com/Google-Health/medgemma/blob/main/notebooks/high_dimensional_ct_hugging_face.ipynb)
uses a focused condition and a different runtime/message processor. The
[model card](https://huggingface.co/google/medgemma-1.5-4b-it) requires application validation.
The earlier [usage review](model-usage-review-2026-10-17.md) records failed P6/T2 readiness
and useful, overlap-affected detector review. This plan does not promise clinical validity
or that prompt changes alone can make this model accurate.

## Execution record

- User's Q4 failure inspected without new inference: repeated-label loop confirmed.
- Two isolated workers assigned; main comparison remains running and untouched.
- R1 implementation complete: `924a147` (bounded P5/CLI labels/diagnostics), `941c536`
  (uniform raw axial896 protocol). Full worker gate: 839 tests, 97.85% coverage.
- U1 `6b919ee` and U2 `5aec0e3` complete. Worker gates: 830/833 tests,
  97.84% coverage; direct new-tab synthetic image/style checks passed.
- Independent cross-review identified and fixed comparison cancellation provider wording
  and empty-first-pass diagnostic indexing; see [the review](review-current-2026-10-17.md).
- R2 is running from clean `941c536`: first sorted annotated-positive calibration case
  and the user's annotation-negative calibration case; Q4/Q8, P5, one canonical nodule
  label,16 uniform raw axial896 images each. No retries or changed thresholds.
- Dependency refresh and the final combined R3 gate are in progress.
