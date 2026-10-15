# STEP 61 — «¿Verdadero o falso?» in cascade on the notebook, and learningroutes.com everywhere it should be

The owner's decisions (2026-10-15):

1. **The brand on screen is learningroutes.com.** That is his site, and the channel
   promotes it. The Shorts already carry it: the watermark and the outro ("Aprende inglés
   en learningroutes.com"). It is still missing from the video descriptions and from the
   long lessons.
2. **true_false becomes a cascade.** Several statements on one page, like how_do_you_say.
   Each answer is blurred from the first frame and comes into focus after the pause.
   Videos get longer and more interactive.
3. **how_do_you_say is done.** It works as it is; do not change it. Its byte-identical pin
   stays.

Run after STEP 60. Do not start `pronounce_level`.

## 1. New type `true_false_level`: a third mode of the notebook

A mock of the four key frames is at `_audit/stills/A_verdadero_falso.jpg` (frame 0 at
full size: `A_verdadero_falso_frame0.png`). I rendered it with the real
`create_frame_level` and three monkeypatches, so the geometry is the production one.

| | frame 0 shows | reveal |
|---|---|---|
| `true_false_level` | the 10 statements (Spanish, English word in «»), and under each one the **same** grey placeholder «VERDADERO · FALSO», blurred | the placeholder cross-fades to the real answer while the blur goes 14 px → 0 |

- **Answer line:** `VERDADERO` in `correct` green with the tick, or `FALSO · {correction}`
  in `error` red with an ✗. The ✗ is drawn like `_draw_tick`: an ink stroke under a red
  stroke.
- **No hint before the reveal.** The placeholder is identical on every row, and grey,
  never coloured. In my first mock the blurred real text leaked red/green and its length,
  and it was readable as a hint. Do not blur the real answer.
- **Blur:** a Gaussian blur on the answer strip, done on the strip and not on the frame,
  and cached per (text, radius step). Use radius steps of 2 px so the cache stays small.
  The frame stays a pure function of t.
- Tiers, pills, rule lines, the highlighter, the countdown dots, the pencil and the
  verdict note are exactly as in the level modes.
- The pencil does not write here; it points at the active row while the answer comes
  into focus.

### Script shape (draft: `content/drafts/true_false_level/tf001_falsos_amigos.json`)

```
title, theme, intro, outro, verdict, video_title, video_description, hashtags[5] (first #VerdaderoOFalso), _meta
items[10]: statement   Spanish, the English word in «», one line at the level column width
           truth       bool
           correction  Spanish, required when truth is false ("es alfombra"), absent when true
           cefr        same tier ranges as level_test
```

The schema also requires 3 to 7 true items per video, so «siempre falso» is not a
strategy. tf001 has 4.

### Audio: Spanish only, nothing in English is spoken

- intro: Spanish, may carry one tag.
- No prompt segment: the statement is read off the page.
- think_i: 4.0 s of declared silence (reading plus deciding). Measure. If tf001 lands
  over 85 s, use 3.5 s.
- answer_i: "Verdadero." or "Falso: {correction}." This is pure Spanish, so there is no
  English onset risk.
- tier_4 and tier_8: the cached tier lines.
- verdict and outro.

My estimate is about 79 s with the outro. Give the type its own band in `duration_spec`,
with `reject_max_seconds = 95`, as for say_it_level.

### Doors

Do the same as for the level modes in 8149548:
- registry: dashboard label «Verdadero o falso (cascada)»;
- `type_categories`: `false_friends` feeds this type too;
- hashtags, title fallback, GPT prompt builder, spoken-word count;
- provider routing, with OpenAI refusing.

The old single-statement `true_false` type stays registered (do not delete it, old queue
items still reference it), but its dashboard button moves under the new one, labelled
«Verdadero o falso (uno)».

## 2. learningroutes.com in the descriptions and the long lessons

- **Shorts descriptions** (`metadata_generator`): add the line
  `Más lecciones en https://learningroutes.com` after the body and before the hashtags,
  in every type. It is a plain line, with no tracking parameters.
- **Lesson descriptions** (`.youtube.json` builder in manim studio): the same line, after
  the chapters and before "Suscríbete…".
- **Lesson end card:** under «Sigue aprendiendo» add «Más lecciones en
  **learningroutes.com**», the URL in a blue sticker pill (brand v2). The mock is
  `_audit/stills/D_cierre_leccion.png`. The two end-screen slots must keep their
  position and size, because YouTube's end-screen elements are placed on them.
- English Unlimited stays as the channel's name and logo; the site is where viewers go.
  These are not two competing brands.

## 3. Render and stop

- One render of tf001: final QA, duration, characters, cost. Stills in `_audit/stills/`:
  frame 0, row 4 half in focus, row 10 revealed, the verdict note.
- One render of the make-vs-do lesson end card only (a still is enough), plus the new
  `.youtube.json` description of make-vs-do.
- **Stop** for the owner. After his yes I write the other tf scripts.

## Constraints

Only OpenAI and ElevenLabs are paid. Everything else is local and free. No MoviePy.
The ceiling is $0.30 per Short. No keys, `.env`, voice IDs or home paths in commits.
Commit messages carry no attribution lines. Do not commit the other session's
uncommitted files. how_do_you_say must render byte-identically.

## Report back

- Commit hashes, pushed.
- The tf001 numbers and stills.
- The new description texts: one Short and the make-vs-do lesson.
- The end-card still.
- Test counts: pass / fail, naming any failure that is not yours.
