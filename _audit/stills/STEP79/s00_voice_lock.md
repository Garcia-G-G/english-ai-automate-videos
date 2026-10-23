# STEP 79 §00 — the ElevenLabs lock

## The lock (`src/voice_lock.py`)

- Every request that would reach ElevenLabs calls `voice_lock.check()` just before it is sent,
  after the cache lookup: `cost_tracker.check_tts_budget` (all of `src/`: Shorts, series, tools,
  the CLI) and `gen_audio.eleven_segment` (the lesson studio, its probes and `batch_run.py`).
  A cache hit never reaches it, so cached renders always work.
- Locked by default in every process. The only unlock is a grant the panel opens for its own
  click: «Crear video» (`admin.start_generation`, `start_series_generation`) and the studio's
  «Generar audio» / «Lanzar lote» (`manim_studio.start_job(..., voice_chars=…)`, passed to the
  subprocess as `ELEVENLABS_GRANT`). The grant is a one-off token file under
  `output/.voice_grants/`, removed when the job ends. Under pytest a grant is never honoured.
- `ELEVENLABS_LOCK=1` or `costs.tts_lock: true` is an emergency stop that locks the panel too;
  neither can unlock anything.

## The panel (`src/voice_credits.py`)

- Sidebar header: «Voz: N caracteres restantes», from GET /v1/user/subscription (free, cached
  60 s).
- Before a granted render: the characters the script would voice (its spoken text; the per-video
  cap in characters when the script is not known yet, e.g. a random pick; the stale beats' text
  for a lesson). Refused in Spanish when it is more than remains or would leave < 5 % of the plan.
  When the balance cannot be read, the job runs without a grant: cache only.

**Reading on 2026-10-23: 7.039 characters left of 173.743 (resets 2026-11-01).** That is already
under 5 % (8.687): the panel will refuse any render that needs voice until the reset; cached
renders still work.

## Spend since 1 October (numbers only, nothing changed)

From `output/costs/` (every ElevenLabs row from 2026-10-01; classified by its video id):

| category | characters | requests | $ | ids |
|---|---|---|---|---|
| Shorts | 23.660 | 1.014 | 5.08 | title-slug renders: cómo_se_dice, dilo_en_inglés, qué_nivel_tienes, … |
| series | 3.419 | 112 | 0.75 | hc_* — all of it STEP 78 / 78b proofs and the 78b panel test |
| tests/STEPs | 6.062 | 245 | 1.33 | script-id renders (bv001, lv001, sy001, ec001, …, *_step60, step76_*) |
| unknown | 0 | 0 | 0 | |
| **logged** | **33.141** | 1.371 | 7.16 | |

The lesson studio keeps no cost log. Its beat files dated on or after 1 October hold
**36.553 characters** (present-perfect-vs-past 5.497, used-to-soler 5.591, hacer-preguntas 4.993,
preposiciones-in-on-at 4.930, make-vs-do 4.897, can-could-pedir 4.573, comparativos-superlativos
4.371, demo-motion 1.207, third-person-s 494). That is a lower bound: a re-voiced beat keeps
only its last take, and 323 probe files under `audio/_probe/` (STEP probes, dated October) have
no text record.

The account says **166.704 used** this period. Logged Shorts/series/STEPs (33.141) plus the lessons'
lower bound (36.553) is 69.694: **≈ 97.000 characters are not in any log**. The likely places
are lesson re-voicings (multilingual_v2 / v4 takes overwritten), the studio probes and the series'
first hc_c001 voicing (unlogged, ≈ 307), but the logs cannot say.
