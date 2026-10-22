# STEP 79 — Lessons: a redesign that holds attention (layout, motion, Bubi, thumbnails, chapters)

The long lessons are the Manim pipeline in `experiments/manim_voiceover_poc/`, driven by
`src/manim_studio.py`. There are 22 lesson scripts in `lessons/`. Nine have voice in `audio/`:
- can-could-pedir
- comparativos-superlativos
- demo-motion
- hacer-preguntas
- make-vs-do
- morning-phrasal-verbs
- preposiciones-in-on-at
- present-perfect-vs-past
- used-to-soler

third-person-s has 31 audio files but an old render. All 22 already carry `[[ ]]` English marks.

**This STEP spends $0 on voice.** It re-renders only from cached audio. Voicing the 12 unvoiced
lessons costs about $1.10 each (about 5,000 characters at $0.22 per 1k). That is Garcia's budget
call and is not part of this STEP.

Same rules as always:
- One commit per section with its tests; push each one.
- Run the full suite before every commit. On a failure, stop and report.
- No attribution lines.
- Proofs go to `_audit/stills/STEP79/`. Claude reviews them.

---

## §0 — One leftover from the series review (78b)

**mensajes:**
- At frame 0, the whole chat is visible, including the error bubble, under the hook card.
  Today frame 0 is a black screen with one card on it.
- The example cards (✓/✗) stack in the **lower** half, under the rule sticky. Today they pile up
  over the conversation at the top while the bottom half stays empty. They stay out of the bottom
  22 %.

Re-render hc_m001 from cache at $0.

## §1 — Baseline: one still per beat, all 22 lessons

Add a stills mode to the lesson renderer. It draws every beat at its midpoint, uses cached
timings where they exist and estimated timings otherwise, makes no TTS calls and encodes nothing.

Run it on all 22 lessons: one contact sheet per lesson plus `index.md`. This is the "before".

Claude's review of the `make-vs-do` render from 19 Oct (8 frames from 2 s to 455 s) found these
problems. §2 and §3 fix them:

1. **Lopsided composition.** The notebook page sits in the left ~55 % of the frame, and a wide
   strip of empty sand is left on the right.
2. **The caption sticky shows fragments and covers the page.**
   - The fragments cut sentences mid-way: «Una frase que se oye muchísimo: She did a» and
     «cabeza y completamente raro en la del otro.».
   - The sticky overlaps the page's bottom-right corner.
3. **Collisions.** In the dialogue beat, a bubble («Yes, and I made a few notes.») covers the
   section header, the progress bar and the site badge.
4. **Static frames.** For 7–8 minutes the frame is a still slide plus text. There is no character
   and no motion between beats.
5. **Inconsistent colour.** In list beats the English is not blue («Make coffee, make dinner…»),
   while in tables it is.

## §2 — Layout

1. **The page.**
   - Centred and wider: about 82 % of the frame width, inside title-safe (90 %), with even margins.
   - The header row (lesson name, progress, site badge) sits above the page, aligned to the
     page's edges.
2. **Captions as a band, not a sticky.**
   - One caption band under the page, on the sand, up to 2 lines, keeping the current font size or
     larger.
   - Chunk the captions by phrase from the word times: break at punctuation first, then at a
     natural pause. Never cut a phrase in the middle, and never leave a lone word on a line.
   - English inside captions stays blue (from `[[ ]]`).
3. **Collisions.**
   - Every element of a beat stays inside the page. The only exceptions are the header row and the
     caption band.
   - No two text boxes overlap.
   - Dialogue bubbles are laid out inside the page, in turns, and scroll up within it if needed.
4. **English in blue everywhere**, wherever the script marks it: list beats, tips and recaps, as
   well as tables.

Tests:
- re-run the §1 stills mode on all 22 lessons;
- a collision checker over the drawn boxes of every beat must pass on all of them, with zero
  overlaps and zero elements outside the allowed areas;
- one caption chunking test with the two fragment examples above.

## §3 — Motion and Bubi (attention)

Reuse the STEP 77 spirit: purposeful, never decorative.

1. **Bubi lives on the page**, small, in the lower-left margin. Use the v3 assets and the
   expressions `tools/extract_bubi_expressions.py` already cut out. He reacts on cue:
   - waves on the `title` beat;
   - thinks on `quiz`, during «Pausa y piénsalo»;
   - celebrates on the quiz answer;
   - points on `tip`;
   - nods on `recap`.

   Between cues he breathes, which is a slow 2 % scale.
2. **A page turn between Parts.** Each `heading` beat that starts a «Parte N» turns the page (0.6 s),
   with a paper sound from the procedural set at −22 dB under the voice.
3. **Pencil marks on the key word.** In `sentence` beats, the highlighted or wrong chip gets a
   hand-drawn circle or strike stroke by stroke (4× anti-aliased). The right chip gets a drawn tick.
4. **The stillness rule.** No still stretch longer than 5.0 s. Measure it as in STEP 78b, and add it
   to the lesson gate. Bubi's breathing and a very slow push-in (≤ 3 %) count as motion.
5. **The end card.** Use the v3 logo (Bubi plus the wordmark), as STEP 71 §2 intended; the 19 Oct
   render still shows the old one. Keep the two end-screen placeholders for YouTube.

## §4 — Thumbnail and chapters (free retention)

1. **A thumbnail** at 1280×720 for each lesson, from its first `sentence` beat:
   - the wrong form struck through and the right form below it, big;
   - Bubi;
   - the lesson title in at most 5 words;
   - readable at 320 px wide.

   Save it next to the render and use it when uploading. If the uploader already sets a thumbnail,
   use that hook instead.
2. **YouTube chapters in the description.** Use the `heading` beats' start times from the render
   timeline: `00:00 Intro` first, at least 3 chapters, each ≥ 10 s. Leave them out when they would
   break YouTube's rules.

## §5 — Re-render the voiced lessons from cache ($0)

Re-render, at 1080p30 with the STEP 75 final pass (x264, BT.709, −14 LUFS), all ten:
- the nine voiced lessons;
- third-person-s, if all of its beats are cached; if not, list the missing beats and skip it.

Each render must pass:
- the sync report;
- −14 LUFS ± 1;
- the collision checker;
- the 5 s stillness rule.

Proofs for each lesson:
- the MP4 path (it stays in `renders/`, not in git);
- a 10-frame sheet;
- frame 0;
- the thumbnail;
- the chapter list.

Report the render time per lesson.

## Report

Give Claude:
- the commits;
- the suite totals;
- $ spent, which must be $0;
- per-lesson gate results and the longest still stretch;
- the paths;
- anything not verified.
