# STEP 77 §4 — frame layer and safe areas

Stills (gitignored, on disk): `s4_hdys_writing.png`, `s4_hdys_cta.png`, `s4_choose_level_sheet.png`,
`s4_say_it_level_sheet.png`, `s4_fill_level_write.png`.

- Frame layer: the notebook types finalise with `chrome=False`: no neon progress bar, no white
  Manrope watermark. The brand is `kit.footer` (Bubi mini + «learningroutes.com», Fredoka 36) at
  the page's foot, inside the safe area (addendum B4: it was at y ≈ 1575, in the caption zone).
- Safe areas, tested on every word, line and tick: the title is 60 px lower (frame y ≥ 190); nothing
  readable right of frame x 940 below y 950 (page-local CONTENT_R = 816, the tilt included);
  nothing below y 1450 (the page ends at 1444).
- how_do_you_say: narrower columns (Spanish 296, English 298 px: the longest words in the queue
  at 42 px), rows at pitch 98, emoji 76.
- Level modes, nothing under 42 px: one size per video (46→42); a line that does not fit wraps
  (line 1 at 644 px, line 2 at 580 px, it carries the tick); rows take the height of their lines;
  at most 8 rows a page, split where a tier starts when it fits (7 + 3), and the page turns: the
  old one slides up out, the new one rises and its rows cascade. Tier labels 32 px (pill 46 wide);
  the say_it note is 42 px, its «También: …» may take two lines. `length_spec` measures with the
  renderer's wrap at 42 px (≤ 3 lines a field; choose's options one line) and lays the page out;
  the 100 level_test and 100 say_it_level scripts all fit.
- Pencil: 200 px, soft ink shadow; while the viewer thinks it stands in the right margin (74°),
  tip by the answer line, body down the margin, over no text; it stands there again after the
  last answer. `pencil_rest` is gone (it pushed the pencil off the frame once text reached x 816).
