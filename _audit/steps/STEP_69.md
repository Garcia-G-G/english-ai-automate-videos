# STEP 69 — Lesson notebook: the sticky note stays inside the frame, English column in blue; then stop

Run after STEP 63. Section by section: one commit per section, pushed. $0: cached audio.

I looked at the STEP 63 stills (`_audit/stills/STEP63/`).
- §0 is right: the pencil clears the last row, and the «Elige» circles clear the dividers.
- The notebook page reads well.
- Two things are left.

## §1 The sticky note leaves the frame

In `make-vs-do_word_chips_b10.png` and `make-vs-do_quiz_reveal_b33.png` the note's
bottom-left corner and its shadow run past the bottom edge of the frame.

The cause: `NOTE_BOTTOM = -3.86` sits under a −2° turn plus a 0.07 shadow. With a wide
note that puts the low corner at about −4.05, and the frame ends at −4.0.

The fix:
- Place the note from its rotated bounding box, shadow included, not from the
  unrotated rectangle.
- Every edge stays at least 0.15 units inside the frame.
- Keep it bottom right and keep the turn.

Test: for the widest note in make-vs-do and for a 2-line note, the rotated box with its
shadow is inside the frame with a 0.15 margin.

## §2 English in the table's first column is blue

The brand rule says English is blue (`brand.json`: `english_is_blue`). So:
- when the table's first column is English (the expressions in make-vs-do), it is blue;
- when it is not, it stays ink.

Decide by the lesson's own markup (what the script marks as English), not by guessing
from the words. «do time» keeps its green: it is the correct/featured colour, and that
wins over blue.

Test: make-vs-do's table has a blue first column; a table whose first column is Spanish
stays ink.

## §3 The production queue moves

Commit the 4 moves from today's dashboard runs (bv021, bv022, lv006, sy007 →
`content/queue/_done/`) in their own commit, as in STEP 68 §3.

## §4 Proof, then stop

1. Re-render make-vs-do from cached audio.
2. Report:
   - the same stills as STEP 63, in `_audit/stills/STEP69/`;
   - the duration (must stay 7:41);
   - the cue offsets against e07a631's render (within one frame).
3. **Stop** for the owner's eye on the video. The other lessons get the notebook look only
   after he approves it.

## Do not

- Do not touch the Shorts renderers.
- Do not commit keys, `.env`, voice IDs or home paths. No attribution lines.
