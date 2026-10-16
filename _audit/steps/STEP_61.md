# STEP 61 — One step at a time: lessons upload like the Shorts, «¿Verdadero o falso?» in cascade, learningroutes.com everywhere

This step merges STEP 64 into STEP 61, at the owner's request (2026-10-15): «combínalo… simplemente que trabaje paso a paso».

**Work strictly in order, one part at a time: Part A, then B, then C, then D.** Each part
ends with its own tests passing and its own commit, pushed, before the next part starts.
If a part fails, stop there and report; do not start the next one on top of a broken part.

**When:** run right after STEP 59. STEP 60 follows this one; then STEP 62, then STEP 63.
Do not start `pronounce_level`.

The owner's decisions (2026-10-15):

1. **Long lessons upload to the same account, the same way as the Shorts.** In his
   words: «los videos se suben a la misma cuenta de la misma manera que se suben los
   shorts».
2. **The brand on screen is learningroutes.com.** That is his site, and the channel
   promotes it. The Shorts already carry it: the watermark and the outro («Aprende inglés
   en learningroutes.com»). It is still missing from the video descriptions and from the
   long lessons.
3. **true_false becomes a cascade.** Several statements on one page, like
   how_do_you_say. Each answer is blurred from the first frame and comes into focus after
   the pause. Videos get longer and more interactive.
4. **how_do_you_say is done.** It works as it is; do not change it. Its byte-identical
   pin stays.

## Part A — Lessons: review and upload like the Shorts, on one page (first: the owner is about to upload make-vs-do)

Today the owner's next upload, a Short or a lesson, would open a Google consent screen.
Part A removes that.

### A.1 What is already the same

`manim_studio.upload_to_youtube` uses:
- the same `UploadManager` and the same `.tokens/youtube_token.json`, so the same channel;
- the same `upload_guard.decide`, so no second publication;
- the same `publication_log` ledger;
- the same default visibility, `resolve_privacy("youtube")` = public.

Keep all of that.

### A.2 What is not, and must change

1. **The captions scope made every upload ask Google again.** STEP 56 appended
   `youtube.force-ssl` to `YOUTUBE_SCOPES`, and `authenticate()` treats every entry as
   required. The stored token was granted without it (I read its scope list: upload,
   readonly, yt-analytics.readonly). So `_missing_scopes()` is non-empty and the next
   upload of *anything*, Shorts included, forces a full re-consent. The owner did not ask
   for that, and the Shorts never needed it.
   - Split the list: `YOUTUBE_REQUIRED_SCOPES` (upload, readonly, yt-analytics.readonly)
     decides `authenticate()`. `YOUTUBE_OPTIONAL_SCOPES` (force-ssl) only enables
     captions.
   - `upload_captions` keeps its current behaviour when force-ssl is missing: skip with a
     note, never fail the upload.
   - A fresh consent (no token, or a revoked one) still asks for required **and**
     optional scopes in one screen, so a future re-auth picks up captions for free.
   - Test: a token with only the three old scopes authenticates **without** opening the
     browser, uploads, and skips captions with the note. A token with no scopes at all
     still forces consent.
2. **Lessons get a «Revisar y subir» page, like the Shorts, on one page.** The owner's
   verdict on today's panel (2026-10-15): «la parte de subir videos de lecciones está mal
   hecha, literal solo me deja subir videos que ni existen… que haya como en los shorts,
   una parte de revisar y una parte de subir, pero en una sola página».

   What I saw on his running panel (`?page=Manim`):
   - «Subir a YouTube» follows the lesson picked in «1 · Guion». With «Used to» picked,
     it offered `used-to-soler/20261014-093231…`, an old render he never reviewed, and
     not the make-vs-do he had just made.
   - «Vídeos renderizados» lists 22 renders side by side: three make-vs-do, four
     used-to-soler, demos. Nothing says which one is current, which is approved or which
     is uploaded.
   - There is no review step. Any render, superseded or never watched, can be uploaded.

   **Remove** the upload box from the lesson editor, and **do not** add «Subir →
   Lecciones» (drop it if it is already started). There is one door: a tab on the
   Lecciones page.

   ```
   Lecciones   [ Hacer lección ]  [ Revisar y subir (2) ]          ← two tabs; the count = items waiting
   ─────────────────────────────────────────────────────────────────────────────
   POR REVISAR (1)
   ┌ make-vs-do · 15 oct · 7:41 · voz v4 · ≈$0.39 ──────────────────────────────┐
   │ [player]          Palabras en inglés a escuchar: b04 «make», b34 «did»       │
   │                   (from english_audit.json; «0 avisos» when clean)           │
   │                   [ ✓ Aprobar ]   [ ✗ Rehacer ]   note: ____________        │
   └──────────────────────────────────────────────────────────────────────────────┘
   LISTAS PARA SUBIR (1)
   ┌ preposiciones-in-on-at · 14 oct · 7:46 ─────────────────────────────────────┐
   │ [thumbnail]  Título ______  Descripción ______  Etiquetas ____  Pública ▾    │
   │              [ Subir a YouTube ]   (progress bar, then «Subido · enlace»)     │
   └──────────────────────────────────────────────────────────────────────────────┘
   ▸ Subidas (0)          ▸ Versiones anteriores y rehechas (19)      ← collapsed
   ```

   Rules:
   - **One current render per lesson:** the newest one. Older renders of the same lesson
     go to «Versiones anteriores» automatically. They are never offered for upload unless
     the owner reopens one there («Usar esta versión»).
   - **Statuses:** `por revisar` → `aprobada` or `rehacer` → `subida`. Store them in
     `renders/reviews.jsonl`, append-only, one line per decision: {file, status, note,
     at}. A new render of a lesson starts at `por revisar`. «Subida» is read from the
     publication ledger, as today, never from this file.
   - **Por revisar** shows the player, which only loads when its card is opened (as
     today), plus duration, voice model and speed, and cost when known. It also lists
     the English-words audit flags for that render's voice, with the beat ids. Only the
     approve and redo buttons live here.
   - **Listas para subir** holds what is today's `_youtube_panel` body: title,
     description, tags, visibility, the thumbnail, the shared `_upload_button`. Only
     `aprobada` renders appear here.
   - Above «Listas para subir»:
     - the yellow consent note appears only when there is **no usable token at all**;
     - when only the captions scope is missing, show the grey line «Los subtítulos en
       español no se subirán: la cuenta no dio ese permiso. YouTube genera los suyos
       automáticamente.»;
     - the button always says «Subir a YouTube».
   - `rehacer` takes the card out of both lists, keeps the note, and shows a line «make-vs-do:
     marcada para rehacer — {note}» under the editor of that lesson in «Hacer lección».
   - Lessons whose id starts with `demo` and renders with `quality` under 1080p never
     appear (tests and drafts).
   - The files must exist on disk for every card. A render whose `.mp4` is gone is
     not shown anywhere except «Versiones anteriores», greyed, with «el archivo ya no
     está».
   - Today's renders start like this: for each lesson, the newest render is `por revisar`
     and every older one goes to «Versiones anteriores». No migration file is needed.
3. **Tests (AppTest plus pure functions):**
   - `current_render_per_lesson` picks the newest per lesson and hides demos and draft
     qualities;
   - the review ledger round-trips, and the last line wins;
   - only `aprobada` reaches «Listas para subir»;
   - a render with a missing file is never uploadable;
   - an uploaded render shows in «Subidas» with its link;
   - the editor has no upload button any more.

### Part A — done when

- The tests below pass, plus the proof with the real token, read only:
  - `_missing_scopes()` over the required set is empty;
  - over the optional set it returns force-ssl;
  - `authenticate()` returns True without opening the browser.
- Do not upload anything; the owner uploads.
- Snapshot `.tokens` first (`cp -r .tokens .tokens.bak-YYYYMMDD`). Never print a token or
  a client secret.
- Commit, push, then go on to Part B.

## Part B — New type `true_false_level`: a third mode of the notebook

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

### Part B — done when

The schema, the renderer mode, the audio plan and the doors are in, with their tests and
how_do_you_say's pin passing. Commit, push, then go on to Part C.

## Part C — learningroutes.com in the descriptions and the long lessons

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

### Part C — done when

The description line is in for Shorts and lessons, and the end card is drawn, with tests.
Commit, push, then go on to Part D.

## Part D — Render and stop

- One render of tf001: final QA, duration, characters, cost. Stills in `_audit/stills/`:
  frame 0, row 4 half in focus, row 10 revealed, the verdict note.
- One render of the make-vs-do lesson end card only (a still is enough), plus the new
  `.youtube.json` description of make-vs-do.
- **Stop** for the owner. After his yes I write the other tf scripts.

## Constraints

Only OpenAI and ElevenLabs are paid. Everything else is local and free. No MoviePy.
The ceiling is $0.30 per Short. Part A adds no paid calls.
No keys, `.env`, voice IDs or home paths in commits. Commit messages carry no attribution
lines. Do not commit the other session's uncommitted files. how_do_you_say must render
byte-identically.

## Report back (one report at the end, with one section per part)

- **A:**
  - the commit, pushed;
  - the new tests;
  - the read-only token proof;
  - a screenshot of «Lecciones → Revisar y subir» with make-vs-do under «Por revisar».
- **B:** the commit, pushed, and its tests.
- **C:**
  - the commit, pushed;
  - the new description texts: one Short and the make-vs-do lesson;
  - the end-card still.
- **D:**
  - tf001's final QA, duration, characters and cost;
  - its four stills.
- Test counts for the whole suite: pass / fail, naming any failure that is not yours.
