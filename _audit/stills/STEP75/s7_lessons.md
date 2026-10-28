# STEP 75 §7 — lessons: final encode and loudness

`renders.register` now runs `renders.final_encode` on the copied render: libx264 crf 14
slow `-tune animation`, BT.601 → BT.709 with tags, `+faststart`, audio two-pass loudnorm
to −14 LUFS / −1.5 dBTP (AAC 48 kHz stereo 192k). The copy is replaced only when the pass
succeeds and the length matches; a failure is logged in the ledger row and Manim's file stays.

Proof: the latest make-vs-do render, re-encoded in place, no re-render
(`renders/make-vs-do/20261019-143930_english-teacher_1080p30_sand.mp4`; the original is kept
at `output/rendering/step75_s7/original.mp4`).

| | Manim's file | after the final pass |
|---|---|---|
| video bitrate | 363 kb/s | 508 kb/s |
| colour tags | none | bt709 / bt709 / bt709 / tv |
| brand blue as an HD player decodes it (BT.709), median ΔE | 7.12 | 0.84 |
| integrated loudness | −18.5 LUFS | −14.0 LUFS (linear) |
| true peak | −3.9 dBTP | −2.3 dBTP |
| LRA | 3.5 LU | 3.4 LU |
| duration | 461.45 s | 461.47 s |
| keyframes / median gap | 275 / 0.5 s | 56 / 8.3 s |
| pass time | — | 215 s |

Manim encodes with the BT.601 matrix and no tags; decoded with BT.601 the blue is ΔE 0.80,
so the colours were right in the file and wrong on HD players, which assume BT.709.

True peak: the first run with a −2 dBFS guard measured −1.1 dBTP after the 48 kHz stereo
AAC encode. The guard now oversamples at 4× the actual rate and sits at −2.5 dBFS. The
Shorts' narration under the same guard: −14.4 LUFS, −2.3 dBTP after AAC (§5 measured
−14.1 / −1.9 with the old guard).

Banding: `s7_vignette_pair.png` (top-left corner at t = 60 s, 2× nearest; Manim's file
above, the final pass below). No visible banding in either; distinct grey levels 239 → 236,
flat neighbours 92.8 % → 93.0 %.

The ledger row of this render still carries Manim's byte count (27.6 MB); the file is now
39.5 MB. New renders record the size after the pass.
