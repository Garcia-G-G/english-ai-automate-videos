# STEP 78 §1 — the series schema and its queue

- `script_schema.HechoConClaudeScript`: the ten common fields; optional caption, hashtags (exactly
  5), series, duration_target_s, voice_words; exactly one block per style (chat / scene / poster /
  quiz) and an id whose letter matches the style. `voice` lines: balanced `[[ ]]` (the STEP 76 check,
  now `check_english_markers`, shared with ScriptBase) and only known audio tags.
- `audio_tags.unknown_tags` no longer reads `[[I have cold]]` as the tag `[I have cold]` — it would
  have refused 105 of the 108 (and any marked text with an English phrase).
- All 108 drafts validate as written: nothing was changed, nothing reworded. 27 per style, 9 per level.
- `src/series.py`: drafts, the queue `content/queue/hecho_con_claude/` (§7 fills it), filtered
  `queued`/`pick` (a script that does not validate is never handed out), `counts`, and the upload
  metadata: title = `title`, description = `caption`, the 5 `hashtags` as they are.
- Panel: «Hecho con Claude» in the Generate page's type list, with «Estilo» and «Nivel» filters and
  the count of queued scripts; its button is enabled once the series renderer exists (§3).

Content notes for Claude (nothing changed):
- 26 of 27 comics never say «Tienes tres segundos»: some say «Tres, dos, uno…», others go from the
  options straight to «¡La B!». §2 puts the 3 s countdown after the countdown line when there is one,
  else just before the reveal line («¡La …!»).
- hc_c014 and hc_c021 never ask for a comment in the voice (the challenge card still shows
  «Escríbelo en comentarios»).
- Voice length: 51 (hc_p018) to 92 (hc_m021) words, median 69.
