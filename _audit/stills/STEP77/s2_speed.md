# STEP 77 §2 — speed (target NOT met; STEP stopped here)

What changed:
- The page is described, not drawn: every composite onto it is recorded; the record (each
  image's content + position) is the page state. A state seen in the last 12 frames reuses its
  tilted page; a new one is drawn and tilted once, with cv2 (16 ms, against PIL's 160).
  Countdown dots (1/8 steps), pulse scales (0.5 %) and the say_it note's pop (1 %) are
  quantised so states repeat. On one Short: 670 pages drawn, 1,524 reused.
- The pencil leaves the page: drawn after the tilt, unrotated, at its tip's rotated point, with
  a sub-pixel affine shift.
- Frames render in a fork process pool (6 on 8 cores; VIDEO_RENDER_WORKERS overrides), in
  contiguous chunks written in order; the background, static pages and caches are built once
  in the parent and inherited; open captures are released before the fork.
- The watermark scrim is applied to its rectangle only (it converted the whole frame to
  float: 14 of 52 ms). x264's 4-thread cap removed (54 → 60 fps encode-only).
- Notes and line wraps cached.

Single-process frame cost (flat base, one Short): ~240 ms → 34 ms.

Whole renders (frames + encode). Wall time is NOT usable on this machine today: other
projects held the load at 10–105 (and one run spanned a sleep). CPU seconds are:

| mode | video | CPU s | ≈ idle 8-core wall | before (STEP 75 A/B) |
|---|---|---|---|---|
| how_do_you_say | 69.1 s | 505 | ~65–70 s | ~280 s for 82 s |
| level_test | 88.1 s | 620 | ~80–85 s | — |

Encoder share, 900 frames encode-only: x264 slow 112 CPU s (0.124/frame), medium 89 (0.099).
For a 2,073-frame Short that is ~257 of its 505 CPU s: half the render is the STEP 75 encoder.

The ≤ 60 s target for an 80 s Short is not met (estimate ~80 s idle). What would close it is
a decision, not a fix: x264 `medium` instead of `slow` (−20 % encoder CPU, files 3 % larger),
and/or cutting frame work further (pickling 6 MB frames between processes, memo misses at chunk
edges). Not changed here, because `slow` was chosen in STEP 75.

## §2b — x264 `medium` (addendum A, 22 Oct)

Full suite before the change: 2369 passed, 9 skipped, 1 xfailed, 0 failed.

`render_video_ffmpeg`'s default preset is now `medium`; CRF 17, `X264_PARAMS` and the BT.709
tags are unchanged; `--fast` still asks `ultrafast`.

Encode-only A/B, the same 900 frames (load 10–12):

| preset | CPU s (user+sys) | wall s | bytes |
|---|---|---|---|
| slow | 69.7 | 12.8 | 10,332,420 |
| medium | 61.0 | 10.8 | 10,611,120 (+2.7 %) |

Whole render, `cómo_se_dice_20261021_172946` (69.1 s of video, 6 workers, load 16 → 28):
422 CPU s (was 505 with slow) → **≈ 70 s idle wall estimate, ≈ 81.5 s for an 80 s Short**.
That is between 75 and 90 s: noted, and the STEP continues (the addendum's rule). The measured
wall time under load was 113.7 s.

Colour on that render at t = 20 s (`_audit/stills/STEP75/colour_check.py`, BT.709):
title blue median ΔE **0.85** (≤ 1.0 ✓), sticky yellow 1.52, the same as STEP 75's slow encode.
