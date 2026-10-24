# STEP 77 §7 — sound design

File (gitignored): `s7_hdys_narration_sfx.wav` — cómo_se_dice_20261021_172946's levelled
narration with its effects, as the mux receives it.

- `src/video/notebook/sfx.py`, numpy only (no downloads, no licences, no music bed):
  pop (30 ms 600→900 Hz), swish (250 ms swept noise band), scratch (high-passed noise in ~11
  strokes a second, for as long as the pencil writes).
- Events come off the frames' own timeline (`how_do_you_say.sfx_events`): swish when the page
  comes in, turns (level pages) and leaves; pop on the hook, every emoji, every tick and the CTA;
  scratch while the pencil writes (not in true_false_level, where it only points).
- Level: 22 dB under the voice's RMS on its spoken segments; 6 dB lower again when the voice is
  actually sounding under the effect (within 15 dB of its RMS — a segment's own pauses do not
  count); the scratch sits 4 dB under the pops.
- Mixed in `pipeline.render_video` after the narration is levelled, notebook types only, same
  length. Measured on two cached narrations: −14.2 → −14.2 LUFS and −14.3 → −14.3 LUFS; true
  peak −2.5 → −2.3 and −2.4 → −2.3 dBTP. how_do_you_say 34 effects (16 ducked), level_test 25 (14).
