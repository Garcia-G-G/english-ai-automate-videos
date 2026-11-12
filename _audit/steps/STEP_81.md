# STEP 81 — Make the engine produce what the channel's data says works


## Skills — use these explicitly (Garcia's instruction)

Before §1, check which of these skills you have, and say in your first reply which ones are present. Invoke each skill at the step named below, not from memory of what it says. If a named skill is not installed, say so in the report and follow its intent by hand. Do not silently skip it.

Every section:
- `agent-protocols:planning-and-task-breakdown` — at the start of the STEP, to break the sections into tasks with acceptance checks.
- `agent-protocols:incremental-implementation` — while building each section: small verified steps.
- `mattpocock-skills:tdd` (or `agent-protocols:test-driven-development`) — write the failing test first for every rule this STEP adds.
- `mattpocock-skills:diagnosing-bugs` (or `agent-protocols:debugging-and-error-recovery`) — whenever a test or render fails, before changing code.
- `agent-protocols:code-review-and-quality` — on your own diff before each commit.
- `agent-protocols:git-workflow-and-versioning` — for each commit and push.

STEP 81 specifically:
- §1–§2, the ranking, the scheduler and the YouTube/Facebook API calls: `agent-protocols:api-and-interface-design` for the scoring and slot interfaces. `agent-protocols:security-and-hardening` for the token handling and the snapshot of `.tokens` before any refresh write.
- §3, the comments page: `llm-secure-patterns:agent-action-surface`, because nothing is posted without Garcia's click. `llm-secure-patterns:output-validation`, for the LLM-drafted replies (length, no links, no personal data). `design:ux-copy` plus `vectorlab-ux-skills:verbs` and `vectorlab-ux-skills:errors`, for the Spanish button labels and error messages.
- §5, the vowel check and the voice scoring: `agent-protocols:research-spike-and-poc`. Write the measurement as a spike first; write findings, not conclusions.
- §7, the LatAm lint: `agent-protocols:test-driven-development`. Use a fixture per mapped word, including «tío», which stays.
- §4.4, the compilation: `agent-protocols:incremental-implementation`, one topic family first.

## Context

Claude's research of 12 Nov 2026 is the Claude Doc «English Unlimited: investigación del canal y plan para reforzar el core». The facts that drive this STEP:

- **Topic.** Basic everyday `how_do_you_say` categories get a median of 1,061 views (27 videos, min 553). Subtopics and situations get 296 (16 videos). Sequels of winners («MÁS …») get 855; MÁS FAMILIA had 1,202 in 3 days.
- **Format.** By median views: `how_do_you_say` 852, level_test 501, say_it 273, phrases 216, grammar formats 114–186, series 87 (its newer comic «RETO» Shorts get 415–537 on day 1), long lessons 25.
- **Timing.** 90 % of views come from the Shorts feed, and about 75 % arrive in the first 24 h.
- **Engagement.** 30 comments in 59,775 views; 0 % returning viewers; 2 subscribers per 1,000 views.
- **Engine findings.**
  - 12 queued scripts repeat 3–10 words of already published videos; MÁS COMIDA repeats all 10.
  - On 11 Nov, 9 uploads went out in ~2 minutes, and only 1 was `how_do_you_say`.
  - Halloween is still queued.
  - The title emoji comes from the first row («PROFESIONES 🍎»).
  - The AI-background A/B never ran: 16 of 16 stock.
  - «MÁS COLORES» was rendered 5 times.
  - Stats are refreshed only by hand.
  - Facebook has no `read_insights`.
- **Garcia's reports.** The Spanish «e» sometimes sounds like «i». He wants more subscribers.

Claude already queued 11 sequel scripts, `content/queue/how_do_you_say/bv101…bv111`, in commit ec2f3ab.

## Rules

- One commit per section with its tests; push each one.
- Run the full suite with `VIDEO_RENDER_WORKERS=2` and no pytest parallelism. Stop on failure.
- No attribution lines.
- **No paid call from you.** TTS, LLM, image and video calls only happen from Garcia's clicks in the panel, under the existing locks and caps. Tests mock every HTTP layer. Proofs come from cache.
- The Anthropic key Garcia keeps in the macOS keychain is **not** used by this STEP.

## §0 — Queue hygiene

1. **Repetition guard.**
   - A `how_do_you_say` or `phrases_level` script may not repeat more than 3 English items, compared case-insensitively against every published (`_done`) and queued script of its type.
   - This is enforced at queue time, at generation time and in `queue_guard.py`.
   - Move the current offenders to `content/queue/_rewrite/` with a `README.md` listing the repeated words: bv090, bv085, bv078, bv089, bv087, bv084, bv070, bv073, bv072 and bv079. Claude rewrites them.
   - Test it with bv090 (10/10 repeated) and with bv101 (1 repeat, passes).
2. **Seasonal calendar.**
   - Add `content_calendar` to `config.yaml`:
     - Navidad only from 1 to 20 Dec;
     - Halloween only from 1 to 31 Oct.
   - Out of window, the script is never picked. Move bv049 Halloween to `_skipped/` with «until 2027-10-01».
3. **Title emoji.** Use `_meta.title_emoji` if present. Otherwise use a theme→emoji map in `config.yaml` (profesiones 👷, cara 😊, …). The first row is only the last resort.
   - Add a guard: an emoji whose meaning clearly mismatches the theme, from a small denylist (fruit on non-food themes), is refused.
4. **No repeat renders.** If an MP4 for the same script id already exists in `pending/`, `approved/` or `uploaded/`, «Crear» refuses with a Spanish message unless Garcia ticks «Volver a renderizar».

## §1 — «Producir el siguiente mejor» decides with data

1. **Stats refresh themselves.** When the panel starts, and once every 20 h while it runs, read the YouTube stats as «Actualizar estadísticas» does. It is read-only and uses free quota. Store the result as today. If the read fails, show a warning; never block.
2. **Priority score**, explained in the panel in one Spanish line per script:
   `priority = format_score × topic_score × freshness`.
   - `format_score` = the median views of that format's videos aged 3 days or more, divided by the `how_do_you_say` median. It is recomputed from the stats daily. A format with fewer than 5 videos uses its config prior.
   - `topic_score`:
     - 1.0 for tier A, a config list of basic categories;
     - 0.85 for a sequel (`_meta.sequel_of` set) whose parent has ≥ 800 views;
     - 0.35 for tier C, subtopics and situations.

     When the stats allow, compute these from medians as well. Put the tiers in `config.yaml`, seeded with Claude's lists from the doc's «Plan».
   - `freshness` lowers a topic family published in the last 3 days (×0.5), so two kitchen videos never go out in a row.
3. **Daily mix enforced.** At most 4 uploads a day, filled as 3 from `how_do_you_say`/sequels and 1 «other». The other slot rotates: phrases_level (home and daily-life phrases first), series comic «RETO», then a level_test with a tier-A topic. Grammar formats get only a free slot.
4. **Sequel suggestions.** A published `how_do_you_say` that reaches ≥ 800 views by day 3 shows a card in «Inicio»: «Escribir la secuela: MÁS <TEMA>».
   - Claude writes these by default.
   - Optionally there is a «Generar borrador» button that uses the cheap model already in `config.yaml` (`anthropic/claude-haiku-5.5`), never Opus, through the repetition guard, for Garcia to approve.

## §2 — Scheduled publishing, no bursts

1. **YouTube.** Upload as `private` with `status.publishAt`. Slots are in Garcia's time zone (America/Costa_Rica): 08:30, 12:00, 16:00 and 19:30.
   - Never two videos less than 2.5 h apart.
   - Never more than 4 a day.
   - The queue fills the next free slot.
2. **Facebook.** Use the same slots, with the reels API's scheduled publish if the token allows. Otherwise post at the slot time from the existing `meta-tick`.
3. **Panel.** Show the next 8 slots and what fills them.

## §3 — Conversation

1. **A one-word question at the end.**
   - `how_do_you_say` and `phrases_level` outros end with a bonus question about one word not in the list: «Bonus: ¿cómo se dice "<palabra>"? Escríbelo en los comentarios».
   - The word comes from `_meta.bonus` if present. Otherwise use the next queued sequel's first item; otherwise a curated list in `config.yaml`.
   - The bonus line is voiced at render time inside Garcia's click, so its cost counts against the per-video cap.
2. **«Comentarios» page.**
   - List new YouTube comments using `commentThreads.list` (free quota), newest first, with the video title.
   - For each one, show a suggested Spanish reply drafted by the cheap model (≤ $0.001 each; generate only when Garcia opens the page, and cache it).
   - Garcia edits it and clicks «Responder» to send with `comments.insert`. Nothing is sent without that click.
   - Show the answer to the bonus question so his reply can confirm it.

## §4 — Subscribers

1. **Series hook.** When a script has a queued sequel, its outro adds «Parte 2 mañana: suscríbete para no perderla». It is voiced once and cached as a reusable line.
2. **Playlists.** Create one playlist per family once (Casa, Comida, Cuerpo, Animales, Ropa, Ciudad, Frases, Retos). Add each upload to its family's playlist with `playlistItems.insert` after publishing.
3. **Related video.** The API cannot set a Short's related video. The panel shows a checklist line after each upload: «Enlaza como relacionado: <parent or sequel URL>», with a copy button.
4. **Long compilations ($0 voice).** A new type, `compilation`: a 16:9, 8–10 min video built from cached audio and notebook pages of 6–10 published winners of one family, for example «100 palabras de la CASA en inglés».
   - It reuses cached intros and outros, adds chapters per topic and gets a thumbnail.
   - Proof: one compilation from cache. Claude reviews it.

## §5 — Spanish «e» heard as «i»

1. **Measure ($0).** Write `tools/vowel_check.py`:
   - Transcribe every cached Spanish narration segment with the local Whisper, language forced to `es`.
   - Align the transcript to the script words.
   - Count vowel swaps in short words (`de→di`, `que→qui`, `se→si`, `le→li`, `me→mi`, `te→ti`, `el→il`, `es→is`) and the overall WER, by format and by provider (direct v3 cache vs OpenRouter v4).
   - Write `_audit/stills/STEP81/vowels.md`.
2. **Series one-request path.** Make sure Spanish-led sentences send `language_code: "es"`. Add a test for it.
3. **Native voice candidates ($0).**
   - List Latin-American Spanish voices from the ElevenLabs voice library (the listing endpoint is free).
   - Download their free `preview_url` samples and score them with the same checker plus Whisper confidence.
   - Report the top 5 (name, voice id, accent, score) and put the two best samples in `_audit/stills/STEP81/voices/` for Garcia's ear. Change nothing in config.
4. **Gate.** A Spanish segment with a vowel swap is re-voiced once, inside the same click and cap. If the swap is still there, the video is REJECTed with the reason.

## §6 — Cleanup

- Remove the AI-background A/B path. Keep stock footage, and keep the code that generates clips only if something still uses it.
- `generate`: the script model stays the cheap one from `config.yaml`; never Opus for drafts.
- Facebook: detect a missing `read_insights` and show Garcia a step-by-step in Spanish to add it in Graph API Explorer. When it is present, read reel plays into «Rendimiento».

## §7 — Neutral Latin-American Spanish (the audience is MX 17 %, US 8 %, CR 7.5 %, GT 4.7 %, AR 4.3 %; Spain is not in the top 5)

73 queued scripts use Spain-only words. «Coger» is even rude in Mexico. Example: vf029 «ESTOY SIN BLANCA».
1. Write `tools/es_latam_lint.py`, a word map applied to Spanish fields only. It never touches English, `[[ ]]` or `translations` keys.
   - coger→tomar
   - móvil→celular
   - piso→departamento
   - zumo→jugo
   - patata(s)→papa(s)
   - vale→está bien
   - camarero→mesero
   - ordenador→computadora
   - gafas→lentes
   - grifo→llave del agua
   - tarta→pastel
   - melocotón→durazno
   - aparcar→estacionar
   - finde→fin de semana
   - fregar→lavar los platos
   - echar de menos→extrañar
   - sin blanca→sin dinero
   - vosotros→ustedes
   - chaqueta→chamarra

   Keep «tío» when it means the uncle.
2. Run the lint in report mode over the queue. Write `_audit/stills/STEP81/latam.md`: file, field, before → after.
   - Apply automatically only to scripts with no cached audio.
   - For scripts with cached audio, apply too, which means a re-voice on Garcia's next click.
   - Commit the rewrites as one commit. Titles are included.
3. Hook the lint into queue validation and into the generator, so new scripts are born in neutral LatAm Spanish.
4. Fix the four `phrases_level` titles that dropped «para»: vf010, vf015, vf020 and vf030, whose title came out as «10 frases dar las gracias…». The title becomes «10 frases para …».

## §8 — «Inglés para la vida real» (Garcia: «inglés para entrevistas, cosas que llamen y sirvan»)

Claude queued 6 `phrases_level` scripts: `content/queue/phrases_level/vr001…vr006`. They are the job interview (answers), the first day at work, the bank, the children's school, an emergency and the pharmacy. The existing vf022 (interview), vf007 (doctor), vf017 (phone) and vf038 (rent) belong to the same series.
1. Add the family «vida real» to the ranking. It takes the 20 % «other» slot ahead of grammar formats: `phrases_level` with the same title style made 583–1,004 views.
2. The first `compilation` (§4.4) is **«Inglés para tu entrevista de trabajo»**: vf022 and vr001, plus vr002 when it has audio. Long YouTube videos on that search get 175K–886K views. Build it from cached audio only. If audio is missing, wait for Garcia's normal renders; never voice from a STEP.

## Report

Give Claude:
- the commits;
- the suite totals;
- the `_rewrite` list;
- the priority table for the next 12 queued scripts, with each one's explanation;
- the slots for the next 2 days;
- `vowels.md`;
- the voice candidates;
- the compilation proof;
- `latam.md`;
- $ spent, which must be $0;
- anything not verified.
