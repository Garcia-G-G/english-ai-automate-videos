# STEP 78 — Polish the notebook Shorts, then build the «Hecho con Claude» series renderer

Renumbering: this was planned as "lessons". Lessons move to STEP 79 and structure to STEP 80.
Garcia's priority is real, finished videos. This STEP ends with the first four series videos
rendered, and the 108 series scripts queued.

Rules, as always:
- One commit per section, each with its tests. Push each one. Run the full suite before every commit.
  On any failure, stop and report.
- No attribution lines. Git identity is the repo-local one.
- No new paid services. Voice is ElevenLabs `eleven_v3` through the existing TTS path and cache.
  Everything else is local: PIL, numpy, ffmpeg, the existing transcriber. No MoviePy.
- Per-video TTS cap: $0.30. Total TTS spend for this STEP: ≤ $0.80. Report it.
- Proofs go to `_audit/stills/STEP78/`. Claude reviews them; do not ask Garcia to watch or listen.

---

## §0 — Polish from Claude's review of the STEP 77 §9 proofs

Reviewed: the four `s9/*_sheet.png`, `fill_level_3.png`, `phrases_level_4.png`, and frames at
0.4 s and at the end of the MP4s. Loudness is −14.1/−14.2 LUFS on all four, which is fine. Fix these,
each with a test:

1. **The pencil covers text while the viewer thinks.** On row 10 of fill_level ("her coat on th…"),
   phrases_level ("¿Puedo pagar con tarje…") and choose_level ("you how happy"), the pencil sits on
   the sentence. This happens on the last row of a page whose text reaches the right edge. The
   parked pencil must not intersect the ink bbox of any text, tick, emoji or tab on the page.
   If the right margin has no room, park it lower-right, outside the page.
   Test: for every row index on every page of the four §9 scripts, the parked pencil's alpha does
   not overlap any text box.
2. **The filled blank leaves wide gaps.** fill_level shows "He   held   his breath" and "The
   price   rose   by ten". The answer is centred in the fixed blank width. Once the answer is
   written, lay the line out again: normal word spacing on both sides. Keep a short hand-drawn
   underline under the answer only, so it still reads as a filled gap.
   Test: the gap between the answer's ink and each neighbour is ≤ 1.6 × the font's space width.
3. **Tier tab labels overflow.** On a page that holds only row 7, "INTERMEDIO" runs past the top of
   its yellow tab. The label must fit inside its tab. Shrink it down to 22 px minimum; below that,
   use the short label (`BÁSICO` / `MEDIO` / `EXPERTO`).
   Test: the label bbox is inside the tab bbox for tabs of 1 to 5 rows.
4. **Rows half-drawn in the cascade.** At t = 0.4 s of choose_level, row 5 shows its blank line and
   options but no sentence. A row enters as one unit, with one alpha and one offset for all its
   parts. Test: in every cascade frame, each row's parts share the same alpha.
5. **Footage doesn't match the theme.** phrases_level "en un restaurante" shows a dirt road and
   night streets, and the grammar Shorts show aerial fields.
   - Themes that name a place or activity (restaurante, aeropuerto, hotel, médico, compras,
     gimnasio, cocina, taxi…) must get footage of that place. Use the same footage source and
     licence the repo already uses, with no new service.
   - Grammar and abstract themes get one calm, consistent set: desk, notebook, café, a window
     with soft light. No random landscapes.

   Log the query and the clip id in the render's JSON sidecar, and show the five clips picked for
   the four §9 scripts in a contact sheet.

Not in §0: render speed. It stays at about 110 s per 80 s Short, which is accepted.

## §1 — The series schema and its queue

- In `src/script_schema.py`, add `HechoConClaudeScript` for the 108 drafts in
  `content/hecho_con_claude/drafts/hc_{m,e,p,c}NNN.json`. Ten fields are common to all styles:
  `id`, `style`, `level`, `level_label`, `angle`, `title`, `hook_text`, `correction{wrong,right,rule}`,
  `voice[]` and `challenge{prompt,answer}`.
  - Optional fields: `caption`, `hashtags` (exactly 5), `series`, `duration_target_s` and
    `voice_words`.
  - Each style has exactly one block: `chat{contact,messages[[who,text,(error)]]}` for
    mensajes, `scene{location,take1,take2,note}` for escena, `poster{error_no,big_wrong,big_right,examples[]}`
    for poster, and `quiz{prompt,options[3],answer,after}` for comic.
  - English inside `voice` is marked `[[…]]`; reuse the STEP 76 segmenter rules. Audio tags, if
    any, must be known tags.
- Validate all 108. Fix only mechanical problems such as whitespace or a missing field that can be
  derived. Do not reword anything. List any content problem for Claude in the report.
- Queue folder: `content/queue/hecho_con_claude/`. In the panel, add one type, "Hecho con Claude",
  with optional filters for style and level. The upload metadata is
  - title = `title`,
  - description = `caption`,
  - the 5 `hashtags` as they are.

## §2 — One timeline from the voice

- Synthesize the `voice` lines through the existing TTS path (cache in `output/cache/tts`, the
  stitch rule from `src/stitch.py`, English segments from `[[ ]]`). Get word times from the existing
  local transcriber.
- Build a beat list: one beat per voice line, with its start and end, and the time of every
  `[[English]]` phrase inside it. Each style animates on these beats. Nothing is timed by hand.
  - Gate: 25–60 s total, with `duration_target_s` = 42 as the aim.
  - The silence before the reveal in comic: the voice says «Tienes tres segundos». Insert 3.0 s of
    room tone after that line and show the countdown there.
- Reuse the STEP 77 machinery: 4× anti-aliased drawing and caches, the frame process pool,
  x264 medium with BT.709 tags, −14 LUFS, the procedural sounds of §7, and the Bubi outro card.
  New code goes under `src/video/series/`, one module per style, plus a shared `series_kit.py`.

## §3 to §6 — The four styles

The visual targets are Claude's mockups, committed with this STEP under
`_audit/series/reference/`:
- `estilo_mensajes.jpg`, `estilo_escena.jpg` and `estilo_poster.jpg`;
- `fotograma_1..3.jpg`, three frames of the comic style;
- `serie_estilos.jpg`, all four side by side.

Garcia approved these. Match their layout, type scale and colours. The motion is yours, in the
spirit of STEP 77: purposeful, never decorative.

Common to all four styles:
- **Hook (0–1.5 s).** `hook_text` is on screen from frame 0, because frame 0 is the feed thumbnail.
- **Level pill.** `level_label` sits at the top, inside the safe area.
- **Correction.** The wrong form is struck through or ringed in red. The right form is big and
  blue or yellow, with the rule underneath.
- **Challenge card.** `challenge.prompt` shows with «Escríbelo en comentarios». The answer appears
  on the outro card after 2 s, small, under «¿Acertaste?».
- **Outro.** Bubi waving, as in the notebook Shorts.
- **Safe areas.** Nothing important in the bottom 22 % or the top 8 %. Reuse the STEP 77 §4 check.
- **No platform trade dress.** No "iMessage" label, no real app logos. The chat is a generic dark
  messenger with the input placeholder «Mensaje».
- **Fonts.** Use the brand fonts in the repo. For poster and escena, Inter (OFL) may be vendored
  into `assets/fonts/` with its licence file if it isn't there.

The four styles, one section each (§3 mensajes, §4 escena, §5 poster, §6 comic):

- **§3 mensajes.**
  - The header shows the contact from `chat.contact`.
  - Messages arrive one by one, timed to the beats. Each "them" message has a short typing
    indicator; each message has a pop sound.
  - The `error` message gets a red ink ellipse drawn stroke by stroke and an arrow drawn on.
  - The «Se dice: …» card drops in, then the rule sticky.
- **§4 escena.**
  - Letterbox bars and film grain, with `hook_text` as the slate line. A timecode ticks.
  - The clapper opens and snaps shut (clap sound) on «Toma uno».
  - `take1` is a yellow subtitle. A red marker strike, then «¡CORTEN!» punches in.
  - «TOMA 2»: `take2` types in. `note` sits below.
- **§5 poster.**
  - The red bar wipes across `big_wrong`. The type is set with the poster's black display weight
    and fits the width; long lines step down in size.
  - The red block slides up with `big_right`, then the `examples` lines.
  - Footer: `ERROR Nº {error_no}`, plus the page counter.
- **§6 comic.**
  - The yellow halftone and speed-line background, with Bubi reacting (surprised, then happy) using
    the existing v3 mascot assets.
  - `quiz.prompt` in a speech card. The three options pop in.
  - The 3-second countdown, then a «¡NO!» stamp on the wrong options and a ring on the right one.
  - `quiz.after` as a sticky.

Each section's tests:
- the style renders a 2-second smoke clip from every one of its 27 scripts without error, using
  cached or silent audio, with no TTS spend;
- the layout stays inside the safe areas;
- no text overflows its card.

Then render **one** full proof from cached or new audio. Across the four proofs, cover all three
levels, for example `hc_m001`, `hc_e00x medio`, `hc_p00x difícil` and `hc_c001`. For each proof, save
the MP4, a 5-frame contact sheet and the frame at 0.0 s.

## §7 — Quality gate and queue

- Extend the existing quality gate to the series:
  - duration 25–60 s;
  - −14 LUFS ± 1;
  - every `[[English]]` phrase heard in the transcript (the STEP 76 check);
  - frame 0 shows `hook_text`;
  - nothing outside the safe areas.
- Copy all 108 validated drafts into `content/queue/hecho_con_claude/`, leaving the drafts in place.
  Report the count per style and level.
- The board item "Serie nueva hecha con Claude" is Claude's to update; just report.

## Report

Give Claude:
- the commit list;
- the suite totals;
- TTS spend per proof and in total;
- render time per proof (CPU s, as in STEP 77);
- the proof paths;
- any script that failed validation, and why;
- anything you could not verify.
