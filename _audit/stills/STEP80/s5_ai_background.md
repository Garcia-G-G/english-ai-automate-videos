# STEP 80 §5 — AI background clip, as an A/B

- **The clip** (`src/ai_background.py`): `google/veo-3.1-lite` through OpenRouter's video API
  (`POST /api/v1/videos`, async: poll `GET /api/v1/videos/{id}`, download `/content?index=0`), 4 s, 9:16,
  720p, `generate_audio: false`. OpenRouter's public model list (`/api/v1/videos/models`, read 26 Oct)
  prices that SKU at **$0.03/s → $0.12 a clip**; the cost logged is OpenRouter's `usage.cost` when it
  answers with one. Prompt from the topic (calm, on theme, no text, simple centre behind the page).
  Cached per topic, forever: `assets/ai_backgrounds/<topic>/clip.mp4`.
- **Behind the notebook**: the clip is passed as tier 1 of `resolve_background` (`clips:<dir>`), where
  stock footage goes; the one-clip library loops on itself with a **1.2 s crossfade** (stock cuts keep
  0.5 s). It is not a pre-roll — frame 1 is the same page with the list.
- **The A/B**: every other `how_do_you_say` render is the «ia» group (only when the topic has a clip;
  otherwise «stock», with why); each render's group goes to `output/stats/background_ab.jsonl` and to
  the sidecar (`background_ab`). The stats snapshot carries each video's group by artifact;
  «Rendimiento» shows «Fondo IA contra stock» and compares once each group has 8 videos older than 3 days.
- **Only from a click**: «Crear» with «Cómo se dice» shows «Fondo IA para «tema» · $0.12» and «Generar
  fondo IA»; the call goes through the voice lock and the OpenRouter caps (per Short $0.25, month $15 —
  both count every `openrouter_*` row: voice, images, video).
- Fixed on the way (§4): OpenRouter serves its image models on `POST /api/v1/images` (`input_references`
  for the style image, `data[].b64_json` back), not chat completions; `meta/muse-image` and
  `bytedance-seed/seedream-5-0-flash` are both in its `/api/v1/images/models` list.
- **Not done**: no clip was generated ($0); the look of a real veo clip behind the page is not reviewed.
