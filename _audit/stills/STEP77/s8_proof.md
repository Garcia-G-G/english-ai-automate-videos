# STEP 77 §8 — proof (Claude reviews it, not Garcia)

Re-rendered from cached audio, $0, through pipeline.render_video and finalize_video
(`_audit/stills/STEP75/rerender_short.py`, the clips each sidecar recorded):

- how_do_you_say: `cómo_se_dice_20261021_172946` (the newest uploaded one).
- A level mode: `dilo_en_inglés_20261021_161624` (say_it_level). There is no cached choose_level
  or fill_level audio — neither type has ever been rendered — so the level proof is the one that
  exercises the most of §4 (wrapped lines, two pages, the note, the verdict). choose_level and
  fill_level get real renders in §9.

Finals: `output/rendering/step77_s8/<name>/<name>.mp4`. Stills (gitignored):
`s8/hdys_*.png`, `s8/sayit_*.png` at 0.0, 0.3, 0.7, 1.0, 3.0 s, a writing moment, recap/verdict
start, CTA, and two frames across the hand-off (0.15 s before the end, 0.25 s into the outro);
`s8/*_sheet.png` puts each set on one page.

## Render time (frames + encode, 6 workers, x264 medium)

| Short | video | wall s | load | ≈ per 80 s Short |
|---|---|---|---|---|
| how_do_you_say | 69.1 s | 94.3 | ~4 | ~109 s |
| say_it_level | 88.8 s | 126.0 | ~4 | ~114 s |
| say_it_level, after the pill fix | 88.8 s | 167.9 | 43 (other projects) | not comparable |

Above §2b's 75–90 s band: §3's motion (rise, cascades, swipes, push, feathered writing) makes
many more distinct page states than §2 measured, and each new state is drawn and tilted once.
The addendum asked not to spend more sections on speed; noted here. Before STEP 77: ~280 s.

## STEP 75 measurement table

| Short | codec | video kbps | keyframes (median gap) | B-frames | colour | LUFS I | TP dBTP | LRA | duration |
|---|---|---|---|---|---|---|---|---|---|
| how_do_you_say + outro | h264 High yuv420p | 2674 | 37 (2.0 s) | 2 | bt709/bt709/bt709/tv | −14.2 | −2.4 | 5.7 | 73.06 s |
| say_it_level + outro | h264 High yuv420p | 2470 | 47 (2.0 s) | 2 | bt709/bt709/bt709/tv | −14.2 | −2.3 | 9.1 | 92.79 s |

Both pass the gate (loudness, true peak, spread 2.28 / 1.19 dB) and got their outro.

## Review

- Opening: the page rises, rows cascade, the hook note lands by 0.7 s and leaves with the intro.
- Writing: the swipe, the feathered word at the pencil tip, stroke ticks with a clear gap.
- Level page: wrapped lines at ≥ 42 px, two pages (rows 1–5, 6–10), the pencil standing in the
  margin while the viewer thinks, the verdict note, then the CTA over the title.
- Hand-off: the page slides up out; the outro card comes up with Bubi.
- Fixed while reviewing: tier pills now come in with their first row (they sat on an empty page
  at t = 0), and a page with few rows spreads them over more of its height (ROW_EXTRA_MAX 36 → 60).
- say_it_level's outro seam has no silence span at the cut (gap 0 ms): its narration's last word
  runs to the end of the file. That was so before STEP 77 (STEP 75 measures it the same way).
