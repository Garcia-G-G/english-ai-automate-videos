# STEP 76 §4 — every TTS call cached

`src/tts_cache.py`: a content-addressed cache in `output/cache/tts/` (never deleted by
`make clean`). Key: sha1 of voice, model, final text, voice settings, language, previous/next
text, output format, endpoint, plus the take index (so the onset gate's re-asks are their own
entries). Each entry keeps the raw audio and the alignment. `_elevenlabs_with_retry` (convert,
every v3 path) and `tts_bilingual._synthesize_segment` (with timestamps) look there first; the
take index is passed down from both onset gates. Tests point the cache at their tmp tree.

Proof — `give_up_20260113_185732` through tts_bilingual twice (`s4_cache.py`, counting the
client's HTTP calls):

| run | HTTP calls | characters sent | cost (turbo $0.11/1k) | cache hits / misses | wall |
|---|---|---|---|---|---|
| 1 (cold) | 11 (9 clips + 2 retakes) | 340 | $0.0374 | 0 / 11 | 23.6 s |
| 2 | **0** | 0 | **$0** | 11 / 0 | 10.0 s |

Found on the way: the two runs gave different files although every clip came from the cache.
The room tone tts_common mixes into trimmed clips (anoisesrc) had no seed, so each stitch drew
new noise and the mp3 encode then differed throughout (decoded difference up to −12.8 dBFS).
`ROOM_TONE_SEED` fixes it: two stitches of the same cached clips now decode identically, words
and gains included. The cache test asserts that too.

`_synthesize_segment` now builds the API client only on a cache miss.

Cost of this section: $0.0374 (run 1).
