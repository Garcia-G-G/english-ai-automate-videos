# STEP 82 — «Tablero»: a new look for the Shorts, replacing the notebook. Run this BEFORE STEP 81.

Garcia: «quiero que se barra el diseño actual y se mejore x1000». This STEP replaces the notebook look of `how_do_you_say` with a new design system, «Tablero». Claude designed it, and it is drawn and committed as the reference:

- `_audit/design/tablero/tablero_f0.png` — frame 0;
- `_audit/design/tablero/tablero_f1.png` — mid-video;
- `_audit/design/tablero/tablero_f2.png` — the end card;
- `_audit/design/tablero/nuevo_diseno_tablero.png` — all three side by side;
- `_audit/design/tablero/tablero_mock.py` — the PIL script that drew them. It holds every measure and colour; read it, don't guess.

Match the mockups. Where this text and the mock disagree, the mock wins.

What is kept from today, because the data says it works:
- **Frame 0 shows the full 10-item list and the question.** That is the trait every 1K-view Short shares.
- **The «¿Cómo se dice…?» title formula.**
- **The audio and its beats are unchanged:** each item is said in Spanish, then a pause, then the English twice. Proofs re-render from cache at $0.

Rules, as always:
- One commit per section with tests; push each one.
- Run the suite with `VIDEO_RENDER_WORKERS=2` and no pytest parallelism. Stop on failure.
- No attribution lines.
- No paid call from you; proofs come from cache. Claude reviews them in `_audit/stills/STEP82/`.

## §1 — The Tablero kit (`src/video/tablero/`)

- **Canvas and background.**
  - The canvas is 1080×1920.
  - The background is a vertical gradient per topic family, with a white dot grid every 54 px at 10 % and a few soft circles at 5 %.
  - Put the families in `config.yaml` → `tablero.families`, each a pair of colours:
    - casa: coral #FF7A59 → #D63E5C (as in the mock);
    - comida: green;
    - cuerpo: violet;
    - animales: teal;
    - ropa: blue;
    - ciudad: indigo;
    - emociones: pink;
    - clima: sky;
    - vida real: navy.

    Each needs WCAG AA contrast for white text over its darkest stop.
- **Header.** «¿CÓMO SE DICE?» in Fredoka Bold 92 over a yellow highlighter bar (#F2D66B) rotated −1.5°. Under it, the topic chip: a paper card with a 6 px ink outline, an 8 px offset ink shadow, rotated +2°, holding the emoji and the topic in uppercase at Fredoka 64.
- **Grid.** 2 columns × 5 rows of tiles 474×186. x0 = 36, y0 = 430, column gap 30, row pitch 212.
  - Each tile is a paper card: radius 34, 6 px ink outline, 10 px offset ink shadow.
  - It holds a 124 px white emoji disc with an ink ring, the Spanish word in Fredoka 52 and the index number at the top right.
  - It draws at 4× and is anti-aliased, like STEP 77.
- **Three tile states.**
  - `blank`: the first letter of the English word in blue, then one dash per letter, spaced to fit the tile.
  - `active`: yellow fill, scale 1.07, rotated −1.5°, a soft glow, and a coral timer bar shrinking over the thinking pause.
  - `done`: blue fill (#1B6FA8). The Spanish is white, the English is yellow in Fredoka 56 (auto-fit down to 36), followed by the figured pronunciation `«jáus»` in Manrope 28 at 85 % white.
- **Counter and Bubi.** Bottom left, an ink pill «3/10» that bounces when it increments. Bottom right, Bubi from the v3 expressions:
  - `simbolo` at frame 0, with the speech card «¿Cuántas sabes?»;
  - `wow` while a tile is active, with «¡Dilo antes que yo!»;
  - `bien_hecho` on every third reveal;
  - `lo_lograste` at the end.

  Bubi and the counter are decorative and may sit in the bottom caption zone. No tile may go below y = 1475.
- **The outro card.** The video dims to 47 %. The paper card reads «¿Cuántas sabías? Escríbelo en comentarios 👇». The blue pill reads «PARTE 2 MAÑANA · SUSCRÍBETE» when a sequel of this topic is queued; otherwise «SÍGUENOS PARA MÁS». Bubi stays on top of the dim. learningroutes.com sits at the bottom.
- **Tests.** Every text stays inside its tile for the longest words in the queue («toilet paper», «dental floss», «hair dryer»). Contrast is AA in every family. No tile sits below 1475 or above 150.

## §2 — Motion, on the existing beats

- **Frame 0 is static and complete,** with all tiles `blank`: no cascade that hides the list. Idle motion only: the dots drift slowly, Bubi breathes.
- **When an item's Spanish starts,** its tile goes `active` (0.18 s ease-out), with a soft pop sound at −22 dB.
- **At the English onset,** the letters fill the dashes left to right in 0.35 s. Then the tile flips: scaleX 1 → 0 → 1 over 0.25 s, from yellow to blue, with a swish sound. The counter increments.
- Use the stillness rule from STEP 78b (≤ 4 s); idle motion counts. Keep the render speed within the current numbers. Report the CPU s for a whole Short.

## §3 — Figured pronunciation

- Add an optional item field `pron`, and a dictionary at `assets/pron/es_figurada.json` (English word → figured pronunciation for Spanish speakers).
  - Write it in Spanish spelling with an accent on the stressed vowel: «jáus», «kíchen», «uíndou», «báz-rum».
  - No IPA. Maximum 14 characters.
- Claude delivers the dictionary for all queued and published `how_do_you_say` words in a separate commit. Until then, tiles without `pron` show the English only.
- In the generator, missing words get a cheap-model draft (the `config.yaml` model, never Opus), inside Garcia's click only. It is cached in the dictionary and marked `"review": true` for Claude.
- Validation: lowercase letters, accents, hyphens; no IPA symbols; ≤ 14 characters.

## §4 — Rollout as a measured switch

- Tablero becomes the default for `how_do_you_say`.
- For the next 2 weeks, 1 of every 4 `how_do_you_say` keeps the notebook as a control. Record `design_variant: tablero|cuaderno` in the sidecar.
- «Rendimiento» compares the two groups by views at day 3 and average % viewed, within topic tier A only, once each group has ≥ 6 videos.
- If Tablero loses by more than 20 %, the panel says so in red. Garcia decides.

## §5 — Proofs (from cache, $0)

Re-render 2 published `how_do_you_say` whose narration is cached, preferring CASA (bv002) and one sequel. Save each MP4, a 6-frame sheet (frames 0, 25 %, 50 %, 75 %, the outro and the end) and frame 0 to `_audit/stills/STEP82/`.

## §6 — Next formats (after Claude approves §5)

`phrases_level` gets the Tablero look: one column of 8–10 phrase tiles, the Spanish phrase on the tile and the English revealed in the `done` state, auto-fit to two lines. `level_test` and `say_it_level` follow in a later STEP.

## Report

Give Claude:
- the commits;
- the suite totals;
- CPU s per Short, before and after;
- the proof paths;
- anything that had to differ from the mock, and why;
- $ spent, which must be $0.
