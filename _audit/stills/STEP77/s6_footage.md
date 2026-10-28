# STEP 77 §6 — footage

Still (gitignored): `s6_crossfade.png` — a real cut in cómo_se_dice_20261021_172946's clips,
at −0.4, −0.15, 0, +0.15, +0.4 s.

- Theme first: `topic_clips.footage_themes` turns a how_do_you_say page's English words into
  queries («pillow close up», «blanket close up» …, at most 4) that go BEFORE the category's
  subjects; the panel reads them from the artifact and threads them through resolve_background
  to fetch_for_topic. Other types carry no English, visual theme and keep the category only.
  The STEP's example («bedroom interior») needs an English theme the scripts do not have; the
  items' own objects are the theme on screen.
- 0.5 s crossfades: two decoders open at a cut; the clips blend linearly across it.
- One grade: on top of STEP 75's soft look, each softened clip gets per-channel gains toward the
  set's median colour (5 frames sampled, gains 0.8–1.25), applied on the quarter-res frame.
  Measured on that set: gains from 0.81 to 1.25.
- Frame index from timestamps: `frame_index` = floor(t·fps + 1e-6). `int(t*fps)` turned
  0.1 s × 30 fps into frame 2 (2.9999…) and showed it twice; 29.97 / 59.94 use their real rate.
- Behind the page no watermark scrim is solved any more (§4 removed that watermark).
