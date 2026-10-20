# STEP 76 §5 — cost accounting that is true

- **Once per 2xx.** `_elevenlabs_with_retry` logged the cost before the request, once per call
  whatever the retries did; `_synthesize_segment` logged before its request too, and its
  plain-convert fallback logged again (two rows for one clip). Now each logs after a 2xx that
  carried audio; the fallback logs its own.
- **One price table** (`cost_tracker.PRICING`): `eleven_v4` and `eleven_flash_v2_5` added.
  Full-credit models (v3, v4, multilingual) $0.22/1k, turbo and flash $0.11/1k — v4 and flash
  by that rule, not an invoice yet. `gen_audio.PRICE_PER_1K_CHARS` and
  `manim_studio.PRICE_PER_1K_CHARS` read it at the lessons' model (eleven_v4): their estimate
  goes from $0.10/1k to $0.22/1k. If the plan really bills $0.10, the table is what to change.
- **No hidden paid transcriber.** A failed bilingual run fell back to the single-call path
  plus OpenAI whisper-1, unreported; it now raises `TTSError`. The single-call path (only with
  `ELEVENLABS_BILINGUAL=0`) takes its word timings from `asr_timings` (local Whisper first,
  the backend recorded).
- **Retries** only on 429, 5xx and timeouts, honouring `Retry-After` (capped at 60 s); a 401/4xx
  fails at once. `with_timestamps` is tried once before the plain stream.
- **Per-video budget** `costs.per_video_tts_usd` (config.yaml, 0.25): before every call the
  job's TTS spend plus that call's price is checked; crossing it stops the job with «Presupuesto
  de voz superado: …» and asks nothing. Over 176 videos: median $0.073, p90 $0.137; sy001 ($0.30)
  and gr004 ($0.28, rendered 2026-10-20) would have stopped — raise the key if that is wrong.
- **PRONUNCIATION_HINTS** apply only to non-v3 models; the table stays for the old ones. The
  owner ear-checks a v3 «schedule»/«through» clip in §7.

Tests: `tests/test_tts_costs.py` (7). No TTS in this section.
