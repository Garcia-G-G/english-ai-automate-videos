# STEP 80 §1 — voice through OpenRouter

- **Provider** (`src/tts_openrouter.py`): `POST https://openrouter.ai/api/v1/audio/speech`,
  `elevenlabs/eleven-v4`, `response_format: "mp3"`, ElevenLabs options under
  `provider.options.elevenlabs` (`language_code`, `voice_settings` without `speed`, `previous_text`
  / `next_text`). Both ElevenLabs request points route through it when `config.yaml`
  `audio.provider` is `openrouter`: `tts_elevenlabs._elevenlabs_with_retry` (the level types, the
  outro) and `tts_bilingual._synthesize_segment` (Shorts and series). The `[[ ]]` marking and the
  stitch rule are untouched; the calls are the same calls.
- **Cache first**: a segment already voiced by ElevenLabs (its convert or with-timestamps entry) is
  used and nothing is asked; an OpenRouter segment has its own cache entry. Every re-render of
  something already voiced stays $0.
- **No timestamps** come back from OpenRouter: the word times of such a segment come from the local
  whisper ($0), else the existing estimate.
- **Before every request**, in this order: the voice's category, the caps (`costs.openrouter_per_short_usd`
  0.25, `costs.openrouter_monthly_usd` 15.00; Spanish refusals), the STEP 79 §00 voice lock (only
  the panel's click), and the key.
- **The key**: `secret_store.get` — the environment, else the Mac's Keychain (service
  «english-ai-videos», account `OPENROUTER_API_KEY`; Garcia saved it there). Never printed, logged
  or written; under pytest the Keychain is never read.
- **Price and log**: `elevenlabs/eleven-v4` $80 / 1M characters and `…-turbo` $40 in the one price
  table; each answered request is a row in `output/costs/` (`api_type: openrouter_tts`,
  `provider: openrouter`).
- **Fallback**: when OpenRouter refuses, ElevenLabs direct answers only if its plan has more than 5 %
  left (and its balance can be read).
- **Panel header**: «Voz ElevenLabs: N car.» and «OpenRouter: $X de $15 este mes» (from the cost
  logs, `&#36;` so it is not LaTeX). The panel's voice grant checks OpenRouter's monthly cap when it
  is the provider.

## The voice: Matilda, a female premade voice (Garcia's choice)

`GET /v1/voices/{id}` (free) answered **401 «Invalid API key»** with the ElevenLabs key in `.env`
(it read the balance fine on 23 Oct), and the Keychain holds only the OpenRouter key, so the channel
voice's category could not be read. Garcia decided on 26 Oct: a female voice, with the delivery
ElevenLabs can do. **Matilda** is an ElevenLabs premade voice (female, warm; already the lessons'
default), which OpenRouter can use without BYOK. `config.yaml` `audio.openrouter_voice:
{name: Matilda, category: premade}`; its id is `OPENROUTER_VOICE_ID` in `.env` (gitignored, never
committed). A named voice without its id is refused; a cloned or generated one is refused.

**The v4 humanizer** (`tts_openrouter.humanize`, `audio.humanize_v4: true`), on every OpenRouter
request, with cues taken from the script, never invented: tag-shaped placeholders that are not tags
go («[name]»); a laugh the script writes (jaja, haha, 😂 🤣 😅) → `[laughs]`; «…» → `[short pause]`; a
question the narration goes on to answer → `[short pause]` after it (the time to think); the v3 tags
v4 names differently are mapped.

**Not verified**: no real request was made (none may be, from Claude). The first panel click will be
the first time OpenRouter speaks with Matilda's id; if OpenRouter does not accept it, the error says
so and nothing is billed.

## Audio tags and v4

v4's published examples are `[curious]`, `[cheerfully]` and `[whispering]`. In the request,
`[cheerful]` → `[cheerfully]` and `[whispers]` → `[whispering]`. Used in the scripts and not among
v4's listed examples (kept as they are; v4's full list is not published): `[excited]` 798 times,
`[happy]` 397, `[thoughtful]` 200, `[warm]` 155, `[serious]` 42, `[calm]` 36, `[surprised]` 22.

Also: `manim_studio.start_job` writes its status file atomically (a test caught the page's reader
seeing it half-written).
