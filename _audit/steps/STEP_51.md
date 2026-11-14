# STEP 51 — Owner's verdict on the Manim onset A/B (2026-10-14) — make variant 4 the default

## The verdict
The owner listened to all three A/B files (b18, b05, b08). **Variant 4 — one request per
beat, eleven_multilingual_v2 — is the ONLY one with no cuts and no strange sounds, in all
three.** Every other variant, including 6 (carrier word, 0 by the detector) and 5
(eleven_v3, 1 by the detector), sounds cut to him.

## What that says about the detector
It scored variant 4 as 2 / 1 / 0 dirty (b18: 3.55 s «do the beds», 8.34 s «do a test»;
b05: 1) and variant 6 as 0 — the opposite of the ear. On single-request audio the
"fragment" rule is producing false positives, and it missed whatever the owner hears in
6. Ear is ground truth. So:
- The onset gate must NOT re-request variant-4-style beats (it would pay for a full beat
  again to "fix" audio the owner calls clean). Disable it on the one-request path.
- Add the three variant-4 beats to the detector's fixtures as CLEAN (negatives), next to
  b18's five dirty points; report which rule fired on each and adjust until v4 = 0 and
  b18's old = 5. Don't widen anything until both hold.

## Make it the default (Manim lessons only — not the Shorts yet)
1. gen_audio.py: one request per beat with eleven_multilingual_v2, both languages in the
   same request, timings from the with-timestamps alignment (as in 4.words.json). Keep
   the stitching path behind a flag for comparison, off by default.
2. Cache keys (voices.py, b919fe2) must include the model and the request shape, so
   nothing old is reused.
3. COST — flag, approved by the owner's verdict: multilingual_v2 is $0.08/1K chars vs
   $0.04 for turbo v2.5. Measured narration: ~5,000 chars per lesson → ≈ $0.40 per lesson
   instead of ≈ $0.20. Report the real figure from the first lesson.
4. Regenerate audio and re-render the 5 batch lessons (hacer-preguntas, make-vs-do,
   used-to-soler, present-perfect-vs-past, preposiciones-in-on-at; 25,908 chars ≈ $2.07),
   with the caret fix. Sync gate and validate/warnings 0/0 as before.
5. STOP before the other 17 lessons (≈ $6 more at this rate) — the owner approves the
   five first.

## What I need back
Full paths of the five renders; per lesson: chars, $ spent, duration, sync-gate result;
the detector numbers after the fixture change (v4 beats and b18 old).
