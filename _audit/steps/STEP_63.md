# STEP 63 — Three fixes from the STEP 62 renders (§0), then the long lessons on the notebook (approved design E)

The owner approved design E (2026-10-15). The mock is
`output/qa/design_proposals/E_leccion_libreta.png`; the before/after is
`E_leccion_antes_despues.jpg`. The Shorts proved one rule: the whole puzzle on screen
from the first frame. This step brings that rule and the notebook look into the Manim
lessons.

Run now (STEP 61 and STEP 62 are closed). Work section by section: each section has its own tests and its own pushed commit. Stop and report if a section fails. Work in
`experiments/manim_voiceover_poc` (theme.py, lesson_scene.py). Apply it to make-vs-do
first.

## 0. Three fixes from the STEP 62 renders (do these first, one commit)

I read the stills in `_audit/stills/STEP62/`.

1. **The pencil covers the last answer.** In `fc001_preposiciones_last_row.png` the
   pencil sits on top of «Depende de ti». The viewer can't read it, and that is the last
   frame they see. When the last row is revealed, the pencil parks to the right of that
   row's text and covers no glyph of it.
   - Test, for every level type: in the final frame, the pencil's box does not intersect
     any text box.
2. **«Elige» circles touch the level dividers.** In `ec001_make_do_last_row.png` the
   yellow line under row 3 and the red line under row 7 run into the circles of «do» and
   «did». Leave at least 8 px between any answer circle or strike and a divider. Get that
   space from the row layout, not by shrinking the text.
   - Test: geometry check on choose_level with the longest option pair.
3. **The render timeout is too tight.** fc001 took 1189 s and ec001 1008 s, against
   `RENDER_TIMEOUT_S = 1200` (`src/pipeline.py`).
   - Raise the limit to 1800 s for the level types only. The other types keep 1200 s.
   - STEP 65 already blocks the upload of a render that was killed, so a longer limit
     can't bring back the empty-title upload.
   - Log each render's wall time in its sidecar.
   - Test: a level type gets 1800 s, and a non-level type keeps 1200 s.

Proof: re-render fc001 and ec001 **from cached audio** ($0). Report their new stills
(`_audit/stills/STEP63/`) and wall times. Then go on to §1 without stopping.

## 1. What changes

1. **The page.** Content sits on a landscape notebook page:
   - the paper colour and ink outline with a hard ink shadow;
   - spiral rings on the left;
   - the beat or section title in Fredoka with the yellow marker stroke.

   The sand background stays around the page. The top bar (lesson title and progress
   dashes) stays above the page.
2. **Tables show every row from the start.** The left column (the English expression) is
   printed on frame 1 of the beat. Each meaning sits as a grey blurred placeholder and
   comes into focus when the narration reaches it, with the active row on the yellow
   highlighter. This is the same reveal as the Shorts (STEP 61), not rows appearing one
   by one under empty ruled lines.
3. **Practice beats** (A/B/C options): every option is visible from the start (already
   true). The right answer is revealed with the green circle and tick, and the wrong ones
   with a red strike, as in `choose_level` (STEP 62).
4. **The caption bar becomes a sticky note.** The full-width white bar at the bottom is
   replaced by a yellow sticky note, bottom right, slightly rotated, with an ink shadow.
   English stays blue, Spanish ink. The note shows the line being said, as the bar does
   today. Its width is measured, and it wraps to at most 2 lines.
5. **Site badge.** A small blue pill «learningroutes.com», top right under the progress
   dashes, on every beat. It is ≤ 28 px text and never covers content.
6. Word chips (the «She made a decision» beats) stay as they are, placed on the page.

Keep the sand, stone and dark themes working: each gets a matching paper colour, and
every theme keeps passing `theme.py`'s contrast rules.

## 2. Proof

- make-vs-do re-rendered **from cached audio** ($0). The narration does not change; only
  the picture does.
- Stills of:
  - a word-chip beat;
  - the Parte 4 table at its start (all expressions visible, meanings blurred);
  - the same table mid-way;
  - a practice question after the reveal;
  - the end card.
- Duration identical to the last render (7:41), and the cue offsets unchanged.
- **Stop** for the owner's eye before the other lessons get it.

## Constraints

Local and free: Manim, PIL, ffmpeg. No MoviePy. No new paid calls (cached audio). No keys,
`.env`, voice IDs or home paths in commits. Commit messages carry no attribution lines.
