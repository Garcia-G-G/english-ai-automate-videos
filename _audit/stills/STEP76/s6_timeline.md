# STEP 76 §6 — one PCM timeline

`tts_common.Timeline` (add_audio / add_silence / finalize) replaces the add_audio/add_silence
closure pairs of every generator — 6 in tts_elevenlabs, 4 in tts_openai, 1 in tts_google, 22
closures in all — and their ffmpeg concats, plus tts_bilingual's concat, the OpenAI countdown
fix's concat and the unused `concatenate_audio_files` (15 concat invocations). The timing
contract is the old one, so segment timings do not move; every piece is decoded to PCM and
placed at its declared sample, silences are seeded room tone as WAV, and the narration is
encoded once. `tests/test_generator_add_audio_arity.py`, which kept the copies in step, is gone;
`tests/test_timeline.py` replaces it.

Rates: ElevenLabs 44.1 kHz; OpenAI and Google 24 kHz — OpenAI's old concat was `-c:a copy` of
24 kHz speech with 44.1 kHz silences (and a 44.1 kHz stereo silence in its countdown fix), which
the timeline no longer mixes.

Proof — `give_up_20260113_185732` re-stitched from its cached clips ($0; the API client refuses,
so one uncached clip would fail the run), with the previous code (a worktree at 9de8a3c) and
with the timeline (`s6_restitch.py`): 11 cache hits, 0 misses each.

| | before (HEAD) | timeline |
|---|---|---|
| words (57), segments, clip spans | — | **byte-for-byte identical** |
| duration | 23.524 s | 23.524 s |

Seams (`seams.json`, the §2 measurement): silence between speech identical at every seam
(0.067 … 0.315 s). The largest sample step at a join is now ≈ −60 dBFS where it was ≈ −80: the
gaps carry room tone instead of digital zero (by design, GAP_FLOOR_DB). Seam 1 («give up» →
Spanish) steps −34 dBFS in both: that take still sounds at its 20 ms fade-out — the one seam
to listen to in §7.
