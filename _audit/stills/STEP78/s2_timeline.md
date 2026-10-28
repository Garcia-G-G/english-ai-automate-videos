# STEP 78 §2 — one timeline from the voice

`src/video/series/`: `beats.py` (voice → beats), `series_kit.py` (what the four styles share),
`render.py` (the driver). Styles arrive in §3–§6, one module each.

- The voice lines are joined and voiced through the existing bilingual path (tts_bilingual: the
  STEP 76 `[[ ]]` segmenter, stitch rule, `output/cache/tts`, eleven_v3). Its timed words are
  aligned back onto the lines: one beat per line, with the time of every `[[English]]` phrase.
- eleven_v3 refuses `previous_text`/`next_text` (HTTP 400); the bilingual path now sends no
  context to it (NO_CONTEXT_MODELS) — tested against a fake client, turbo still gets it.
- Comic: 3.0 s of room tone (−62 dB) after its countdown line, or before the reveal when the
  script has none; everything later moves by 3.0 s.
- Gate: 25–60 s for the whole Short, outro included.
- Driver: narration levelled to −14 LUFS per beat (loudness.prepare_narration), the style's
  procedural sounds under it (STEP 77 §7), the outro variant's own cached voice, frames in the
  STEP 77 pool, x264 medium + BT.709, the Bubi outro card with «¿Acertaste?» and the answer from
  2 s. Smoke clips: estimated beats and silent audio, no TTS. A sidecar JSON next to each MP4.
- Kit: canvas, safe areas (top 8 %, bottom 22 %, the STEP 77 rail), faces, `fit` (text fits its box
  or raises Overflow — never drawn past it), level pill, challenge card, outro.

Voiced so far: hc_c001 (comic), ≈ $0.07 (307 characters × $0.22/1k; that first run's cost was not
written to the log — `voice_timeline` now saves it). Its beats: every English phrase heard where
the voice says it; the countdown at 9.23–12.23 s; 31.45 s of voice (+4 s outro = 35.5 s).
