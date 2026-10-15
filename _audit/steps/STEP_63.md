# STEP 63 — The long lessons on the notebook (approved design E)

The owner approved design E (2026-10-15). The mock is
`output/qa/design_proposals/E_leccion_libreta.png`; the before/after is
`E_leccion_antes_despues.jpg`. The Shorts proved one rule: the whole puzzle on screen
from the first frame. This step brings that rule and the notebook look into the Manim
lessons.

Run after STEP 61 (which adds the lesson end card's learningroutes.com line). Work in
`experiments/manim_voiceover_poc` (theme.py, lesson_scene.py). Apply it to make-vs-do
first.

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
