# STEP 76 — Voice (audit wave 2)

Source: `_audit/AUDIT_2026-10-20.md` §C. Do this after STEP 75. Section by section: tests and one pushed commit per section; stop at the first failure. Cost: every re-synthesis in this STEP must be announced in the report with its character count and price; total ≤ $1.50 for the whole STEP. Snapshot `.tokens` first.

## §0 Leftovers from STEP 75
- `config.yaml`: a duration window for `how_do_you_say`. Approved renders measure 72.7, 74.6, 75.2 and 82.8 s (with the outro). Set `min 66 / target 76 / max 86`, `reject_min 55 / reject_max 95`, with the same comment style as the other types (what it aims at, what it rejects). The final-length gate then rejects, not warns, for this type too. Test.
- The ledger row of the make-vs-do lesson that §7 re-encoded in place: update its size/bitrate fields (or whatever the row records) so the ledger matches the file. The original stays in `output/rendering/step75_s7/`.

## §1 English is marked, not guessed [20]
- `tts_segmenter`: segment on explicit `[[...]]` markers first (same markup as the lessons and the hecho_con_claude drafts); the heuristic runs only when a script has no markers at all, and logs that it did.
- `script_generator`: the prompts for educational and pronunciation (and any type that still uses the heuristic) ask the model to wrap every English word or phrase in `[[ ]]`; `script_schema` validates balanced markers; `qa_gate` rejects a script with English outside markers when markers are present (use the existing `collect_english_terms` as the detector).
- Regression test: «I have a [[meeting on Wednesday]]» and «[[I have a meeting on Wednesday]]» both produce ONE English segment; the Wednesday script from `output/audio/pronunciation/wednesday_20261008_130901.json` no longer splits «I have a | meeting».
- No re-synthesis in this section.

## §2 One stitch rule for every path [21, 12]
- Port the lesson pipeline's rule into `tts_bilingual` (and any other path that stitches): at a language switch send `next_text` only, never `previous_text`; per-segment `trim_clip_silence`; the onset gate with up to 2 retakes; per-clip level match (the same helper STEP 75 §5 added). Shared code, not a copy.
- Proof: re-synthesise ONE educational script that showed «m-make»/«d-do» in the past (pick it from the reviews/ledger notes; if none is recorded, pick the shortest educational script in output/audio) and report: seams measured (clicks/onsets), gap lengths vs the configured pauses, cost.

## §3 Onset gate calibrated by ear [22]
- `tools/onset_calibrate.py` over the English clips already on disk (no new TTS): histogram of first-10 ms levels; propose a threshold that flags the clips starting at −16…−20 dBFS and keeps the ones rising from the floor. Apply it for eleven_v3; apply the gate to Spanish clips too. Test with the stored clips.

## §4 Cache every TTS call [23]
- Content-addressed cache keyed on sha1(voice_id, model_id, final text, voice_settings, language_code, previous_text, next_text, output_format, take index); stores the raw audio and the alignment. Wrap `_elevenlabs_with_retry` and `_synthesize_segment`.
- Test: a second run of the same script makes zero HTTP calls. Proof on a real script: run it twice with the dry-run cost log; second run = $0.

## §5 Cost accounting that is true [24]
- Log cost once per attempt, only after a 2xx. Add `eleven_v4` and `eleven_flash_v2_5` prices; one price table used by Shorts and lessons (`gen_audio.PRICE_PER_1K_CHARS` reads it). Remove the hidden paid-Whisper fallback in `elevenlabs_provider` (raise `TTSError`; `asr_timings` is the only transcriber). Retry only 429/5xx/timeouts with Retry-After; try `with_timestamps` once before falling back.
- Hard cap: a per-video TTS budget (`costs.per_video_tts_usd`, default 0.25); crossing it aborts the job with a clear Spanish message before the next call.
- `PRONUNCIATION_HINTS` [25]: apply them only to non-v3 models (v3 pronounces «schedule», «through» correctly); keep the table for the old models. Garcia will ear-check one v3 clip of «schedule» in §7.

## §6 One PCM timeline [26]
- A `Timeline` in `tts_common` (add_audio / add_silence / finalize) replaces the 22 `add_audio` closures and the 15 concat invocations; every intermediate is WAV; one encode at the mux. The arity test that kept the copies in sync goes away.
- Proof: byte-for-byte identical segment timings on a re-stitch of an existing script's cached clips ($0), and the seam measurement from §2 repeated.

## §7 Listen, then stop
- Report the STEP's total TTS spend.
- Files for Garcia: the §2 educational re-synthesis, and one short v3 clip of a sentence with «schedule» and «through» (≈ $0.01) so he can say whether the hints should stay off.
- `git log --oneline -12`, `git status --short`. Stop.
