# STEP 54 — The lessons explain a little more slowly

## What the owner said (2026-10-14)
The five re-rendered lessons are approved: none of the cuts or strange sounds he
complained about are left. One request: **explain a bit more slowly.**

## What changed the pace (read, not measured)
`gen_audio.py` has two speeds per lesson: `speed` (Spanish, default 1.0) and
`english_speed` (default 0.92, "slower English for learners"). On the old stitched path
each English segment got 0.92. On the new one-request path (STEP 51, line ~449) the whole
beat is sent with `lesson.speed` = 1.0 — **so since STEP 51 the English is no longer
slowed at all.** That alone can explain "faster". Confirm from the manifests of the five
renders (`voice_settings.speed` per beat) before changing anything.

## Probe first (≈ $0.20), then decide by ear
Same three beats as the A/B (make-vs-do b18, can-could-pedir b05 and b08), one
multilingual_v2 request per beat as now, 1–4 beeps before each variant, 320 kbps:

| # | variant |
|---|---|
| 1 | today: speed 1.0, current gaps |
| 2 | speed 0.92 for the whole beat |
| 3 | speed 0.88 for the whole beat |
| 4 | speed 0.92 + 0.5 s more silence after each sentence (room tone, not digital zero), and 0.8 s more between beats |

Check that ElevenLabs accepts `speed` on multilingual_v2 (gen_audio drops it with a note
when refused — if it is refused, say so: then only the pause lever exists, and variant 4
becomes "pauses only"). Report per variant: duration of each beat, $ spent, and whether the
onset detector still gives 0 / 0 / 0.

## After the owner picks a number
1. Make it the default for every lesson (`speed` in the lesson defaults, and the extra
   pauses in lesson_scene if he picks 4). The cache key must include speed so nothing
   old is reused.
2. Refit the duration estimate (`SECONDS_PER_WORD`) from the new renders.
3. Cost, to approve before running: re-render the 5 approved lessons again (≈ $2) and the
   other 17 (≈ $7) = **≈ $9**, ~1 credit per character with multilingual_v2. Do the 5
   first and stop for his ear; then the 17.
