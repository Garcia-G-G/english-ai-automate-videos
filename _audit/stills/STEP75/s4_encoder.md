# STEP 75 §4 — Shorts encoder and colour

Re-render of `cómo_se_dice_20261019_163101` from its cached audio and its six recorded Pexels
queries (`rerender_short.py`, $0, no TTS), then gate + outro (redrawn with the same encoder).

| | §0 baseline (VideoToolbox) | §4 (libx264 crf 17 slow, BT.709) |
|---|---|---|
| codec | h264 High yuv420p | h264 High yuv420p |
| video bitrate | 2686 kb/s | 3229 kb/s |
| keyframes / median gap | 207 / 0.40 s | 42 / 2.00 s |
| has_b_frames | 0 | 2 |
| colour tags | none | bt709 / bt709 / bt709 / tv |
| integrated loudness | −15.5 LUFS | −15.5 LUFS (unchanged until §5) |
| true peak | −0.4 dBTP | −0.4 dBTP |
| LRA | 4.7 LU | 4.7 LU |
| duration | 82.76 s | 82.76 s |
| faststart | no | yes (render and concat) |

Encoder cost, same 20 s of decoded frames, load average ≈ 20 (another project's suite was
running): VideoToolbox 4.6 s, libx264 slow 31.2 s (≈ +2 min of encoding on an 80 s Short,
partly overlapped by frame generation). The full proof render ran at load ≈ 33 and its wall
time is not comparable with the baseline; §6 re-times on a quiet machine.

Colour, median CIE76 ΔE of the pixels within ΔE 12 of each target (`colour_check.py`).
The old file is untagged, decoded as BT.601 (what players assume for untagged video); the new
one with the BT.709 it declares.

| frame | title blue #1B6FA8 old → new | sticky yellow #F2D66B old → new |
|---|---|---|
| t = 4 s | 2.13 → 0.72 | 2.13 → 1.44 |
| t = 30 s | 2.42 → 0.85 | 2.33 → 1.52 |

Stills: `s4_old_t4.png`, `s4_new_t4.png`, `s4_old_t30.png`, `s4_new_t30.png`.

Final-duration gate: this Short is 82.7 s with its outro, over the global 80 s ceiling.
how_do_you_say has no window of its own, so the check warns and does not block; types that
are calibrated or declare a window are rejected before the outro.
