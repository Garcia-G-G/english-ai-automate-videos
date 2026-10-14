# STEP 47 — Manim Phase C: neutral stage by default, and more life

## 0. The owner's verdict on the demo

He loved it ("mejoró muchísimo"). He asked for two things:

1. **Neutral backgrounds by default, not black.** Dark stays available as an
   option ("déjalo como opción").
2. **"Hazlo mejor."** Push the motion further.

Constraints, unchanged: ElevenLabs and OpenAI are the only paid APIs and
everything else runs locally. No MoviePy. The Shorts pipeline must stay
byte-identical. No keys, `.env` values, voice IDs or home paths in commits.

## 1. Themes — neutral is the default, dark is an option

- Add `brand.json → manim.themes` with three themes and a
  `manim.default_theme`:
  - **`sand` (default)**: warm paper.
    `BG #F3EEE4 · CARD #FFFFFF · CARD2 #EAE3D6 · TEXT #1C1812 · MUTED #7A7164 ·
    YELLOW #F2D66B (fills and highlighter, never text on paper) · BLUE #1B6FA8 ·
    GREEN #2E8B57 · RED #C8453B`
  - **`stone`**: cooler grey paper. `BG #E9E6E1`, with every other token as in sand.
  - **`dark`**: today's tokens, unchanged.
- **Selection order:**
  1. the `THEME` environment variable;
  2. else `"theme"` in the lesson JSON;
  3. else `manim.default_theme`.

  The Manim page in the dashboard gets a theme dropdown.
- **No flat backgrounds.** Add a very soft radial vignette (centre +3 %, edges −4 %
  lightness) and a faint static paper grain (2 % noise, generated once with numpy
  and cached as a PNG). Both are per theme and both must be subtle.
- **Contrast check in tests:** for every theme, text on BG and text on CARD must
  reach ≥ 4.5:1, and BLUE / GREEN / RED on BG must reach ≥ 3:1. Yellow is only
  ever a fill.
- The end-screen logo on sand and stone does not need the light plate. On dark
  it keeps it.

## 2. Polish from the demo review

1. **The hook shows the error at once.** On a `transform` that adds words, mark
   the gap before the morph with a red caret ‸ between the neighbouring chips,
   and make it pulse twice. The caret becomes the new green word when it drops in.
2. **Centre the visual block** vertically in the space above the captions. Today
   it sits high and leaves an empty band.
3. **Camera focus (3Blue1Brown style).** Switch to `MovingCameraScene`. During a
   transform morph, a sentence `fix` or a sort drop, ease the frame to about 1.06×
   towards the active element over 0.6 s, then ease back on the next beat. It must
   never crop the captions; keep the caption layer fixed in frame.
4. **Continuity between beats.** If a `transform`'s `from` equals the sentence
   already on screen (the previous `sentence` beat's text), do not clear and
   redraw: morph straight from what is there.
5. **Chapter progress at the top.** Show a thin segmented bar, one segment per
   `heading` ("Parte N"). The current segment fills as the lesson advances, and
   the part name appears small beside it. Viewers see where they are, which helps
   retention.

## 3. New beat type `syllables` (pronunciation lessons)

```json
{"type":"syllables","word":"comfortable","parts":["COMF","ta","ble"],"stress":0,
 "gloss":"cómodo","narration":"…"}
```

- The syllables are drawn as chips with a small gap between them. The stressed
  chip is 1.3× larger with a yellow fill.
- When the narration says `word`, a dot hops chip to chip across the duration of
  that word.
- Then the chips close the gaps to form the whole word. Use this for "suena en
  tres golpes, no en cinco".
- Validation:
  - 2–6 parts;
  - 0 ≤ stress < len(parts);
  - `"".join(parts).lower()` equals `word` with spaces and hyphens removed. A
    respelling is allowed if `"respelling": true`.
- Cue: `word`.

## 4. Optional sound effects, generated locally

- Synthesise the sounds with numpy. No downloads and no libraries.
  - soft **pop**: a 30 ms sine burst, 600→900 Hz, with fast decay; plays on chip
    drops and sort landings;
  - **whoosh**: 250 ms of band-passed noise with a frequency sweep; plays on
    transform moves and camera pushes;
  - quiet **tick**: once per second during a quiz pause.
- Mix them at −22 dB under the voice, and never over a word. If a cue lands on
  speech, duck the effect −6 dB more.
- Default: ON for sand and stone, ON for dark. `SFX=0` turns them off.
- Acceptance: the integrated loudness of the voice track must not change by more
  than 0.5 LU with the effects on versus off.

## 5. Acceptance — proof, not claims

1. Add one `syllables` beat to `lessons/demo-motion.json` (after the sort):
   `comfortable`, parts `["COMF","ta","ble"]`, stress 0. Generate audio for that
   beat only (≈ $0.01). Every other beat must reuse its cache.
2. Render the demo twice, once with `THEME=sand` and once with `THEME=dark`.
3. Send the owner one contact sheet per theme, showing: the hook with the caret;
   the transform mid-morph with the camera pushed in; the timeline; the sort; the
   syllables beat; the quiz; the end screen. Include the progress bar in at least
   two of the stills.
4. Include the contrast-test table, the loudness check, durations, and validate
   / warnings = 0 / 0 for every lesson. The Shorts frames must stay byte-identical.
5. Commit in logical steps. **Do not batch-render the other lessons.** The owner
   picks the theme first, and I am rewriting five lessons with the new beats in
   parallel (`lessons/` — merge carefully, I only touch lesson JSON files).
