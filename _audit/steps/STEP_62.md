# STEP 62 — Three more Shorts on the notebook engine (Completa, Elige, ¿Cómo se dice? frases), and an on-brand outro

The owner approved these designs on 2026-10-15. On vocabulary and quiz his words were
"les podemos dar un re design y un re do… en vez de borrarlos y descartarlos, los podemos
mejorar". So the new modes below replace them in production. The old types stay
registered, because old queue items and renders reference them.

Run after STEP 61. It reuses its blurred-reveal machinery. Do not touch how_do_you_say;
its pin stays.

Mocks (rendered with the real `create_frame_level` plus monkeypatches) are in
`output/qa/design_proposals/`. Their filenames start with:
- `B_` (fill_level)
- `C_` (outro)
- `F_` (phrases_level)
- `G_` (choose_level)

## 1. `fill_level` — «Completa la frase» in cascade (replaces fill_blank)

Draft: `content/drafts/fill_level/fc001_preposiciones.json`.

```
items[10]: sentence     English, exactly one "____"
           answer       the word(s) that fill it
           translation  Spanish, for the note while the answer is up
           cefr         same tier ranges as level_test
```

- **Frame 0:** all 10 sentences, each with its blank.
- **Reveal:** the answer is written **into the blank**, in blue, while the blank's underline
  fades. This is better than my mock, which puts it on the second line. Before the
  reveal, the blank shows the shared grey blurred placeholder, so the length of the
  answer gives no hint.
- **The second line** carries `translation` in muted ink. It appears with the answer.
- **Audio:** intro (ES), think_i (3.0 s, silence), answer_i = the **full sentence** in
  English with the answer in place ("I live in Madrid."). This is one EN clip that goes
  through the onset gate, with STEP 60's trim fix. Then tier lines, verdict and outro.
- Tiers: on.

## 2. `choose_level` — «Elige la correcta» in cascade (replaces quiz)

Draft: `content/drafts/choose_level/ec001_make_do.json`.

```
items[10]: sentence  English, exactly one "____"
           options   exactly 2 strings
           answer    index of the right option (0 or 1)
           cefr
```

- **Frame 0:** the sentence, and under it both options in muted ink: «make · do».
- **Reveal:** do not replace the line, as my mock does. The right option gets a hand-drawn
  green circle and the tick, and the wrong one gets a red strike-through. Both stay
  readable, so the viewer sees the contrast. The countdown dots go after the options,
  never over them; in my mock row 5 they collide.
- **Audio:** the full sentence in English with the right option, one EN clip.
- The schema also requires both answer indexes to appear 3 to 7 times per video, so the
  answer is not "always the first".
- Tiers: on.

## 3. `phrases_level` — «¿Cómo se dice?» with everyday phrases (replaces vocabulary)

Draft: `content/drafts/phrases_level/vf001_preguntas_pasado.json`. This is the format of
the owner's first reference Short (a list of «¿Cómo…?» questions).

- **No tiers.** This is the how_do_you_say look with sentences: title «¿Cómo se dice?»,
  no pills and no tier rules. Ten rows of the level layout: Spanish line printed, English
  line under it, with the blurred placeholder until the reveal.
- **Audio:** intro (ES), think_i 2.5 s (the Spanish is read off the page), answer_i =
  English once. No tier lines, no verdict; the outro asks how many they knew.
- The schema has no `cefr` and no `verdict`. It keeps 10 items (8 minimum, as in
  how_do_you_say).

## 4. The Shorts outro, on brand (mock `C_cierre_short.png`)

- Today the outro is black, with a thin serif face. It becomes the sand background and the
  sticker card (ink shadow, brand v2), with the symbol on top.
- On it: «Aprende inglés en» (Fredoka medium, ink), then **learningroutes.com** big in
  English blue over a yellow marker stroke.
- The small line under it, «Rutas para aprender lo que quieras», is my wording for the
  site. Keep it as a field in `outro.json`, so the owner can change it.
- Keep the three weighted variants and their `spoken` text unchanged. Only the picture
  changes, so the cached audio stays valid: $0.
- Render the three variants again (`ensure_outro(force=True)`). No other video is
  re-rendered.

## 5. Doors, for each new type

Same list as STEP 61 §Doors:
- registry and dashboard labels: «Completa (cascada)», «Elige la correcta», «¿Cómo se
  dice? frases»;
- `type_categories`: grammar, common_mistakes and confusing_words feed fill_level and
  choose_level; everyday_expressions, social and travel feed phrases_level;
- hashtags, title fallback, prompt builder, spoken-word count, ElevenLabs routing,
  OpenAI refusal;
- a `duration_spec` band per type, measured on its first render.

Move the old fill_blank, quiz and vocabulary buttons under the new ones, labelled
«(antiguo)».

## 6. Render and stop

- One render each: fc001, ec001, vf001. For each: final QA, duration, characters, cost.
- Stills: frame 0, a mid reveal, the last row.
- The three outro variants.
- **Stop.** After the owner's yes I write 40 scripts per type.

## Constraints

Only OpenAI and ElevenLabs are paid. Everything else is local and free. No MoviePy.
The ceiling is $0.30 per Short. No keys, `.env`, voice IDs or home paths in commits.
Commit messages carry no attribution lines. Do not commit the other session's
uncommitted files. how_do_you_say must render byte-identically.

## Report back

- Commit hashes, pushed.
- The numbers and stills per type.
- The outro stills.
- Test counts: pass / fail, naming any failure that is not yours.
