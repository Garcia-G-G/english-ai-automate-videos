# STEP 77 §3 — motion (with addendum B fixes 1–3)

Stills (flat test background, the test fixtures' timelines): `s3_hdys_sheet.png` (0.0, 0.3, 0.7,
1.0, 3.0 s, writing, recap, CTA, hand-off), `s3_*_level_sheet.png` (hook, writing, tick, CTA),
`s3_cta.png`, `s3_writing_crop.png` (feathered edge, tick gap), `s3_choose_ticks.png`,
`s3_outro_sheet.png` (card entry 0–0.8 s, rest at 3 s).

- Opening: page rises 120 px with ease_out_back over 0.5 s; rows cascade 50 ms apart (fade +
  24 px rise); the hook sticky note slaps on at 0.45 s, −4°, Fredoka 68 (64 if it needs two
  lines), and leaves when the intro ends. Text: the script's `hook`, else
  «¿Sabes decir estas 10 palabras del/de …?» (how_do_you_say) or «¿Cuántas aciertas de 10?».
- Writing: the marker swipes left→right (ease_out_expo, 0.25 s); emoji pop with ease_out_back
  from 0.6, peak 1.15; ticks are drawn along their stroke; the pencil wobbles ±2 px while it
  writes and lifts 22 px between rows; the written word has a 12 px feathered edge at the tip.
- Recap: the marker re-sweeps each row at its word's recap time; the page pushes 1.00→1.04 over
  the recap (level modes: from the last answer to the outro); the CTA «¿Cuántas sabías? __/10»
  pops with an overshoot on the spoken outro, Bubi sticker on its corner, covering the title.
- Hand-off: the page slides up out of the frame in the last 0.3 s. The outro card comes up 520 px
  with ease_out_back over 0.5 s; Bubi waves as two poses (±6° about his feet, 6 swaps of 0.2 s).
  The symbol is one bitmap, so the swing is the whole figure, not the arm alone.
- The three cached outros were redrawn keeping their audio ($0, no TTS).

Addendum B:
1. Tick gap: TICK_GAP 10 → 24 (≥ 14 px of paper from the word's ink; tested in how_do_you_say,
   level_test, say_it_level, phrases_level); choose_level places the tick after the circle and
   the strike (`choose_tick_x`), tested on every fixture row.
2. Pencil: 200 px long, drawn after the tilt, clipped to the frame only; tested over the whole
   choose_level timeline (sprite inside 1080×1920) and on row 6 (every pixel lands).
3. The diagonal seam was the legacy fallback gradient (`src/video/backgrounds.py`, used when no
   footage is set: stills and tests), not a layer edge: `ratio % 1.0` wrapped the last colour to
   the first. It now folds (0→1→0). Production renders use footage and never reached it.
