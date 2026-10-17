# GitHub About — 2026-10-17

The user authorized updating the public About metadata and keeping the lung emoji.
The previous description emphasized MedGemma/Ollama and offline HTML;16 topics included
near-duplicates (`research-tool`/`research-tools`, `chest-ct`/`thoracic-ct`).

Applied description (under350 characters):

> 🫁 Local chest-CT research workbench: inspect DICOM studies, review MONAI detector candidates and experimental MedGemma outputs, and export image-linked HTML reports. Patient holdout stays sealed. Research use only; not for diagnosis.

Applied ten topics: `dicom`, `local-ai`, `medgemma`, `medical-imaging`, `monai`, `ollama`,
`reproducible-research`, `research-software`, `thoracic-ct`, `vision-language-model`.

## Evidence

| Claim | Repository evidence |
|---|---|
| Local chest-CT/DICOM workbench | `src/thoraxbench/study.py`, `api/app.py`, loopback endpoint validation |
| MONAI detector candidate review | `adapters/monai_detector.py`, `docs/detector-baseline.md`, synthetic detector review tests |
| Experimental MedGemma outputs | Q4/Q8 model profiles, preserved abstentions, `docs/model-usage-review-2026-10-17.md` |
| Image-linked offline HTML | `reports/html_report.py`, API/export and genuine new-tab browser tests |
| Sealed patient holdout | `splits/guard.py`, split manifests and refusal/guard tests |
| Research-only limits | `Vision.md`, disclaimers in CLI/API/reports/UI |

No description or topic claims clinical quality, unbiased detector accuracy or passing
VLM recognition gates. GitHub metadata is separate from the application's About page.

## Alternative wording for a later audience change

- Short: “🫁 A local chest-CT research workbench with DICOM viewing, detector candidate review and offline image-linked reports. Experimental outputs; not for diagnosis.”
- Technical: “🫁 Reproducible local CT model research with guarded patient splits, sourced detector/VLM outputs, request provenance and offline HTML evidence. Research use only.”

Possible topic swaps: `python`, `fastapi`, `nodule-detection`. Prefer domain discovery over
redundant research/local topics. Read the actual feature and accuracy limits before edits.
