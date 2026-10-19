# Local video delivery — 2026-10-19

Research use only. ThoraxBench Local is a self-made experimental tool. Findings may be
incorrect, incomplete or misleading. Outputs are not professional medical advice and
must not inform diagnosis or treatment decisions.

## Delivered files

Run commands from the repository root. These paths are local, ignored and intentionally
absent from Git. No LinkedIn upload occurred.

Take folder:
`data/results/linkedin/20261019T102836Z-9da74f42c5c74ca1b3a71e0e8164076e/`

Final render subfolder:
`render-7bba9de9237644679dbe91bbd8e48970/`

| File | Purpose |
|---|---|
| `master.mp4` in take folder | Complete original, 3840×2160, 168.7 seconds |
| `take.json` | Clean source identity, timing, model digest and original SHA-256 |
| `offline-report.html` | Actual downloaded detector report |
| `pilot-A.mp4` in final render | Square, 1080×1080, 30 seconds |
| `pilot-B.mp4` in final render | Portrait, 1080×1350, 30 seconds |
| `pilot-A.srt`, `pilot-B.srt` | Captions |
| `credits.txt` | Full TCIA attribution, license, changes and disclosures |
| `pilot-*-verification.json` | FFprobe codec, frame and duration records |
| `delivery-qa.json` | Final hashes, dimensions and complete decode checks |
| `pilot-*-contact-sheet.png` | Six-shot visual review sheets |

## Recorded execution

Clean source: `d1718031e557c8d30d2203b496712c90fe2c3d4f`, v0.4.17.
Chromium ran headful on an isolated X11 display. The take includes source navigation,
model setup, a genuine queued inference, candidate review, the actual new-tab report,
HTML download, Evaluation landing, About, language/theme changes and the manual.
The visible library was narrowed to the authorized study; other-case slice requests
were blocked. Results were not mocked. The cuts contain selected excerpts; captions
state that the wait was shortened.

The authorized, previously reviewed public calibration example was LIDC-IDRI-0027.
MONAI bundle `lung_nodule_ct_detection` version 0.6.10 ran on the local RTX A2000.
Weights SHA-256: `b5e79231466adae93a6fe8e8594029e9add142914e223b879aa0343bb2402d01`.
Server elapsed: 80.108 seconds. Engine stages: 76.376 seconds. Output: 19 proposals,
8 at the existing 0.5 cutoff; 12 candidates have illustrative previews.
The detector processes the volume; prepared VLM image count is zero. Slice targets
are not a VLM input count. No heuristic model or VLM filtering was used.

## Review and limitations

Both final cuts contain exactly 900 frames at 30 fps, H.264/yuv420p, and decode fully
without FFmpeg errors. Visual review checked each scene, model/result pairing, crop
captions, source images, author, credits and the final disclosure card. The square
renderer initially placed captions over footage; reserved header/footage/caption
bands fix that defect in both formats. Earlier render attempts remain preserved.
No direct identifying text was observed in reviewed frames. Header audit alone is
not an anonymity guarantee. The public pseudonym remains visible.

The first capture failed before inference because Chromium inherited Wayland routing.
Its original remains under
`data/results/linkedin/20261019T102126Z-d222a95dc3334830a2fcd5d61e4ea1c6/`.
The X11 correction passed a synthetic capture before the successful real take.

This is a deliberately selected calibration demonstration. LUNA16-trained detector
weights overlap LIDC: training overlap is **yes**. Scores remain uncalibrated, and
adapted preprocessing/ROI do not establish upstream benchmark parity. The demonstration
is neither unbiased detection accuracy nor clinical validation. No sealed or internal-test
case was used. MedGemma useful-reading readiness and official-runtime parity remain open.

TCIA records license the DICOM/XML data under CC BY 3.0. Full attribution and presentation
changes are retained in `credits.txt` and `take.json`. See the
[official collection record](https://wiki.cancerimagingarchive.net/pages/viewpage.action?pageId=1966254)
and [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/).

**Checkpoint:** play both final MP4s and retain their SRT/credits with the original.
**Recovery:** if a crop or caption needs editing, create another unique render from the
preserved master. Never overwrite the source or fabricate a successful result.
