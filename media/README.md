# ThoraxBench Local — demo videos

- [**Promo, 40 seconds**](promo-16x9.mp4): 1920×1080 with voice-over and music, captions in
  [promo-16x9.srt](promo-16x9.srt), [thumbnail](promo-16x9-thumbnail.png) and
  [credits](promo-credits.txt). A real MONAI full thorax review on the public LIDC-IDRI-0027
  calibration example (real run 2:03, shown sped up and labelled). The voice is Kokoro-82M
  (Apache-2.0); the music is generated. Story and procedure:
  [the promo record](../docs/linkedin-promo-2026-10-20.md).
- [Square video](pilot-A.mp4): 1080×1080, 30 seconds.
- [Portrait video](pilot-B.mp4): 1080×1350, 30 seconds.

Both videos show genuine local MONAI inference on the deliberately selected public
LIDC-IDRI-0027 calibration example. Processing took 80.1 seconds; edited waits are
labelled. The detector returned 19 candidate proposals, including 8 at the existing
0.5 cutoff. Scores are uncalibrated. LUNA16 training overlaps LIDC; this demonstration
is not independent accuracy evidence. No VLM verification or heuristic model was used.

Research use only. This self-made experimental tool may produce incorrect, incomplete
or misleading results. It is not medical advice, a diagnosis or a basis for treatment
decisions. No clinical validity is claimed.

The user explicitly authorized committing these two reviewed cuts on 2026-10-19.
The full original, failed takes and image-bearing reports remain ignored locally.
No upload to LinkedIn is authorized or performed.

## Attribution and reuse

The CT source is LIDC-IDRI / The Cancer Imaging Archive, CC BY 3.0:
Armato III et al. (2015), Data From LIDC-IDRI,
[doi:10.7937/K9/TCIA.2015.LO9QL9SX](https://doi.org/10.7937/K9/TCIA.2015.LO9QL9SX).
See [full credits](credits.txt) for the publication, required acknowledgement,
presentation changes and license links. Retain those credits when sharing the videos.
Medical-image content retains its CC BY 3.0 terms; this is not a transfer of its copyright
under the software license. Project-authored presentation is GPL-3.0-or-later.

Each scene starts with context, then smoothly zooms/pans to the entire relevant panel.
The viewer controls, full MONAI card, jobs columns, finding source, image-pair captions
and About details were checked. These replace the original fixed-crop drafts.

The SRT files match the burned captions. `SHA256SUMS` records the reviewed MP4 bytes.
Verify them from this directory with `sha256sum -c SHA256SUMS`.
Both files contain exactly 900 H.264/yuv420p frames at 30 fps and passed full decode.
[Verification records](verification.json) contain final hashes, sizes and frame checks.
See [the delivery record](../docs/video-delivery-2026-10-19.md) for provenance.
