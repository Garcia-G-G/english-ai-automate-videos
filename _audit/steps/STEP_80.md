# STEP 80 — Replicate what works, OpenRouter for voice and visuals, and a faster, better panel

## Context: Claude's data, read from the public channel page on 26 Oct

105 Shorts. Sorted by views:

- **The top 16 are all `how_do_you_say`, between 1.0K and 1.3K views each.** Their titles are
  «¿Cómo se dice(n) [CATEGORÍA A1 de todos los días] en inglés? + emoji». The categories are CASA,
  ANIMALES, CUERPO, COMIDA, COLORES, BAÑO, FRUTA, BEBIDAS, DÍAS, COCINA, ESCUELA, ROPA, VERBOS,
  POSTRES, DEPORTES and VERDURAS. All of them show the full 10-item list on frame 1.
- **Next come error hooks:** «¡No digas 'I go to home'!» 994, and V/B pronunciation 951.
- **The same title with a situational topic does worse:** HOTEL 140, RESTAURANTE 100,
  DORMITORIO 134, PLAYA 213. Some of these are recent, but the pattern holds: the more basic and
  searched the category, the more views.
- **phrases_level with the same title format:** «¿Cómo se dice «¿ME TRAE LA CUENTA?»…» 647 in a few
  days. That is good.
- **Level tests and «Dilo en inglés»:** 130–600.
- **Grammar formats are the weakest:** choose, fill, true/false and «Completa» get 85–450, median
  about 150.
- **The long lessons barely get watched:** «In, on, at» has 12 views in 5 days.

**Decisions (Claude):**
1. **Production mix.**
   - About 70 % `how_do_you_say` on basic A1 categories.
   - About 20 % error hooks: the series' mensajes and póster styles, and phrases_level.
   - About 10 % everything else.

   Grammar types (choose, fill, true_false_level) drop to the back of the queue. Keep them; don't
   delete them.
2. **Lessons are done for now.** STEP 79 is complete (9daf122 … 564dc47). No more lesson work
   until the long-form numbers improve. The 8 re-rendered lessons can be published as they are.
3. **Never break frame 1.** The full list visible on frame 1 is the trait the winners share. No
   new feature may cover it or delay it.

## Hard rules for this STEP

- **OpenRouter is now an allowed paid API, capped at $15/month.** Garcia puts
  `OPENROUTER_API_KEY` in `.env` himself. Never print it, log it or commit it.
- **No proof spends anything.**
  - Proofs come from cached audio and images.
  - A real paid call happens only from Garcia's own click in the panel, under the STEP 79 §00 lock.
    Extend that lock to OpenRouter: the same rule, the same panel-only permission.
- **Per-Short cap:** $0.25 across OpenRouter (voice + images + clip). **Monthly cap:** $15. When the
  cap is hit, the panel refuses with a Spanish message.
- Same rules as always:
  - one commit per section with tests; push each one;
  - run the suite with `VIDEO_RENDER_WORKERS=2` and no pytest parallelism, to keep memory low;
  - stop on failure;
  - no attribution lines.

## §0 — Two visible bugs

1. **Titles with empty quotes are live on YouTube:**
   - «¿Sabías que '' NO significa lo que crees? 😱»;
   - «Llevas TODA tu vida diciendo '' MAL 😬».

   Find the template that drops the quoted word. Fix it, and add a guard: no title or description
   may contain empty quotes ('' "" «») or a stray `{}`. Run the guard over everything queued, and
   list the published ones so Garcia can edit them by hand.
2. **The panel's cost line renders as LaTeX** («media $0.0943 (OpenAI 0.0053 · ElevenLabs 0.0890)»
   comes out in italic math). Escape `$` in every `st.markdown` that shows money.

## §1 — Voice through OpenRouter (it unblocks production; ElevenLabs has 7K chars left until 1 Nov)

- **Provider.** Add `openrouter` as a TTS provider: `POST https://openrouter.ai/api/v1/audio/speech`.
  - model `elevenlabs/eleven-v4`, at $80/M characters;
  - `response_format: "mp3"`;
  - ElevenLabs options under `provider.options.elevenlabs` (`language_code`, `voice_settings`,
    `previous_text`/`next_text`);
  - no `speed`, because v4 rejects it.
- **Pricing and logging.**
  - Add `elevenlabs/eleven-v4` at 80.00 per 1M and `elevenlabs/eleven-v4-turbo` at 40.00 per 1M
    to the price table.
  - Log every call in `output/costs/` with provider `openrouter`.
  - Keep the `[[ ]]` English marking and the stitch rule exactly as they are.
- **Voice.**
  - Use the configured voice ID. First, check its category with ElevenLabs' free
    `GET /v1/voices/{id}`.
  - If it is `premade` or a public library voice, pass that ID through OpenRouter as `voice`.
  - If it is `cloned` or `generated`, it only works with BYOK, which would spend the same
    ElevenLabs quota. In that case stop and report; do not pick another voice on your own.
- **Audio tags.** v4 audio tags: keep the existing tags. Report any tag v4 doesn't list. The
  blog's examples are `[curious]`, `[cheerfully]` and `[whispering]`. `[cheerful]` is not listed;
  map it to `[cheerfully]` if needed.
- **Provider order.** `config.yaml`: `audio.provider: openrouter`, with `elevenlabs` as the
  fallback only while that account has characters above 5 %.
- **The panel header.** It shows both balances: «Voz ElevenLabs: N car.» and «OpenRouter: $X de
  $15 este mes».
- **Tests.** Mock the HTTP layer. No real call in tests.

## §2 — Performance page, and the queue ordered by what works

1. **New panel page «Rendimiento».**
   - A button «Actualizar estadísticas» reads the YouTube Data API `videos.list` (statistics,
     snippet) for every YouTube URL in `output/published/ledger.jsonl`. It uses the existing token,
     read-only. Quota is free; the Mac has network.
   - If a token refresh happens, save it the way the uploader already does, and snapshot `.tokens`
     first.
   - Facebook reels too if the Page token allows (`video_insights`); otherwise skip with a note.
   - Store the result in `output/stats/youtube_YYYY-MM-DD.json`.
   - Show:
     - views by format (median, mean, count);
     - top 10 and bottom 10;
     - views by category word;
     - a «días publicado» column, so a 2-day-old video isn't judged as dead.
2. **Format score.**
   - Each video type gets a score: the median views of its videos older than 3 days.
   - Each queued script gets a priority from its type's score, plus a boost for basic A1 category
     words (a list in `config.yaml`: casa, comida, animales, cuerpo, colores, fruta, bebidas, días,
     cocina, escuela, ropa, verbos, postres, deportes, verduras, números, meses, familia, cara,
     profesiones…).
   - It must be explainable: the panel shows why a script is next.
3. **The button «Producir el siguiente mejor».** It takes the top-priority queued script, then
   renders, gates and files it, under the locks and caps. This becomes the main action on «Inicio».

## §3 — A faster panel

1. **Profile first.**
   - Measure the time to render each page (Inicio, Crear, Cola, Revisar, Subir, Biblioteca, Temas,
     Programar, Ajustes, Registros, Rendimiento) and write the "before" table.
   - **Target: every page ≤ 1.0 s on a warm rerun, ≤ 2.5 s cold.**
2. **Fix what the profile shows.** Typical fixes:
   - cache sidecar/ledger/cost reads with `st.cache_data` keyed on file mtimes;
   - don't re-scan every queue folder on every rerun;
   - small cached thumbnails instead of decoding MP4s;
   - load heavy pages lazily.
3. **«Crear» stops repeating «Inicio».** Today the whole Inicio content is pasted under the form.
4. **All labels in Spanish.** «Configuration», «Video Type», «Topic Selection», «Random» and the raw
   type keys (`choose_level`) become «Tipo de vídeo: Elige la correcta» and so on.
5. Report the "after" table.

## §4 — Show what's being taught: an illustration for each item

- When a row is active in `how_do_you_say` (and later the other list types), show an
  **illustration of that word**. It is a card about 30 % of the page width that pops next to the row.
  - The full list stays visible on frame 1, and the card never covers the active row.
  - It is drawn in one house style: flat, thick ink outline, brand palette, cream background, no
    text in the image.
- **Model.**
  - `meta/muse-image` through OpenRouter, at $0.01 per image. It supports a reference image for a
    consistent style.
  - Use one style reference image (Claude provides it under `assets/illustrations/style_ref.png`;
    until then, use the Bubi sheet).
  - Fallback: `bytedance-seed/seedream-5-0-flash`, from $0.018 per image.
- **Library and cache.** Keep the images in `assets/illustrations/<english_word>.png`. A word is
  generated once, ever, then reused in every video. Example: *apple* is drawn once.
  - Generate only from a panel click, under the cap, and only for missing words.
  - The panel shows «N ilustraciones nuevas · $X» before generating.
- **Tests.** Layout tests with placeholder images (no API). Frame 1 is unchanged with or without
  illustrations.

## §5 — AI background clip, as an A/B test

- Generate a 4 s, 9:16, 720p, `generate_audio: false` clip with `google/veo-3.1-lite` through
  OpenRouter's video API, at about $0.03 per second, so $0.12. The prompt comes from the topic:
  a calm, on-theme scene, for example a warm kitchen for COCINA.
  - Use it as the **background behind the notebook**, where today's stock footage goes. Loop it with a
    slow crossfade. It is NOT a pre-roll: frame 1 still shows the full list.
  - Cache it per topic.
- **The A/B.** Every other `how_do_you_say` Short gets the AI background; the rest keep stock
  footage. The sidecar records the variant. «Rendimiento» compares the two groups once each has
  ≥ 8 videos older than 3 days.
- Generate only from a panel click, and count it in the per-Short and monthly caps.

## §6 — A better outro for LearningRoutes

Replace the end card in Shorts and the series. It is about 2.5 s; keep the current length.
- Bubi waving, with the v3 logo.
- Big: **learningroutes.com**, with the line «Rutas para aprender lo que quieras».
- One concrete next step, drawn from the queue's next topic of the same type: «Mañana: ¿Cómo se
  dicen los ANIMALES DEL MAR? 🐬». If there's none, use «Síguenos para el siguiente».
- A small «Link en la bio».
- Everything inside the safe areas.
- Reuse the outro's cached audio. If it needs a new line, it's voiced once from a panel click,
  then cached forever.

## Report

Give Claude:
- the commits;
- the suite totals;
- the "before" and "after" panel timings;
- the voice-ID category result;
- the stats table, if Garcia clicked «Actualizar estadísticas» (otherwise say so);
- $ spent, which must be $0 in this STEP;
- anything not verified.

Proofs come from cache, and Claude reviews them.
