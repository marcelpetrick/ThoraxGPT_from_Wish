# Model test runs — 2026-10-20

Every locally installed model ran once through the app's job API on three studies:
the synthetic phantom (12 mm right nodule and an effusion), calibration case
LIDC-IDRI-0027 (reference nodules, no mass) and calibration case LIDC-IDRI-0306 (no
nodule, no mass). Vision-language models got 16 images (P6: 1). The sealed holdout was not
used. These are execution checks on three studies, not accuracy estimates.

## First round (v0.5.6 parser)

| Model | Fit | Phantom | LIDC-0027 (nodules) | LIDC-0306 (none) |
|---|---|---|---|---|
| monai-lung-nodule | 1️⃣ | nodule 0.998 ✅ | nodule 0.998, 19 candidates ✅ | top candidate 0.77 ⚠️ false alarm |
| heuristic-hu | 2️⃣ | nodule + effusion ✅ | 5 labels incl. pneumothorax ❌ | 4 labels incl. emphysema ❌ |
| medgemma1.5-q4 | 3️⃣ | abstained* | abstained* | abstained* |
| medgemma1.5-q8 | 3️⃣ | abstained* | abstained* | abstained* |
| medgemma1.5-q4-p6 | 3️⃣ | all 16 positive | all 16 positive | all 16 positive |
| minicpm-v | 3️⃣ | 0 positive | abstained (timeout) | abstained (timeout) |
| qwen3.5-4b | 3️⃣ | timeout 600 s | timeout 600 s | effusion only |
| qwen3-vl-4b(-nothink) | 3️⃣ | context too small for 16 images | same | same |
| moondream | 3️⃣ | context too small (2K) | same | same |
| llama3.2-vision-11b | 3️⃣ | runtime failed to load | same | same |

\* **Parser bug, fixed the same day.** MedGemma answered `present: false, confidence: 0.0`
for every label (and listed them as negative findings). The parser read confidence as "the
answer is correct", so it turned each negative into P(present) = 1.0; the evidence guard then
discarded these unsupported "positives" and the run abstained. The explicit yes/no answer now
sets the direction and confidence only the strength (exact 0.5 = unknown); a warning records
every such contradiction. P6 keeps its logprob P(yes) as the direction. Earlier repository
conclusions of "constant positive answers" for P5-style MedGemma runs may partly reflect this
bug and need re-running before they are cited.

## Second round (fixed parser)

| Model | Phantom (nodule + effusion) | LIDC-0027 (nodules) | LIDC-0306 (none) |
|---|---|---|---|
| medgemma1.5-q4 | nothing flagged ❌ (228 s) | nothing flagged ❌ | nothing flagged |
| medgemma1.5-q8 | nothing flagged ❌ (319 s) | abstained | nothing flagged |

With the parser fixed MedGemma no longer abstains, but it answers "absent" for every label,
including the planted 12 mm nodule and the reference LIDC nodules: a constant negative
answer, not a yes-bias. Its "nothing flagged" therefore carries no information, and the
fit stays 3️⃣. Only the MONAI detector found the known nodules (with one false alarm on the
nodule-free case).
