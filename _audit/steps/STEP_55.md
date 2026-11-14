# STEP 55 — English words said with Spanish sounds inside the lessons

## What the owner hears (2026-10-14)
Audio quality is now "buenísimo", but sometimes an English word inside a beat is read
with Spanish phonetics: «make» comes out as «maque» or «meike» (then correct the next
time), «does» is read letter by letter as Spanish «does» instead of /dʌz/. Intermittent:
the same word is fine elsewhere in the same lesson.

## Why it is plausible (to confirm, not assume)
Since STEP 51 a whole beat goes to eleven_multilingual_v2 as ONE request with both
languages, and that model has no per-span `language_code`. A short English word surrounded
by Spanish («la diferencia entre make y do») is exactly where it can guess Spanish. The
stitched path had language_code per segment but produced the cuts the owner rejected, so
going back is not an option.

## Step 1 — find every case automatically (free, local)
Write `probes/english_words_audit.py`: for each of the 5 approved renders, take the beat
audio (manifest + words.json timings), cut each English span the lesson marks with
`[[ ]]`, and transcribe it with the local Whisper already in the repo
(`src/asr_timings.py`), `language="en"`, word timestamps. A span FAILS when the
transcript does not match the expected English words (normalised: case, punctuation,
contractions). Also run it with `language="es"`: a span that Whisper-es transcribes as a
Spanish word («maque», «does» as /does/) is the strongest signal.
Output `audio/_probe/english_words/report.json` + a short table: lesson, beat, time,
expected, heard-en, heard-es, verdict. Then cut a 3-second clip of each FAIL into one
`fails.mp3` with a beep between clips, so the owner can confirm by ear in a minute.
No API calls in this step.

## Step 2 — probe the fixes on the failing spans only (≈ $0.30)
Same beats as the fails, 1–4 beeps per variant:
| # | variant |
|---|---|
| 1 | today (multilingual_v2, one request) |
| 2 | same request, English words written so the model reads them as English: each `[[ ]]` span wrapped in double quotes and preceded by a comma pause (e.g. «la diferencia entre, "make", y "do"») |
| 3 | an ElevenLabs pronunciation dictionary (alias rules: the problem words → their English respelling the model reads correctly) attached to the request — check first that multilingual_v2 honours alias rules |
| 4 | eleven_v4 (same price as multilingual_v2, $0.08/1K), one request per beat, `language_code: "es"` |
Score each with the Step 1 audit (FAIL count) AND the onset detector (must stay 0/0/0 on
b18, b05, b08 — no trading pronunciation for the old cuts).

## Step 3 — make the winner a gate, not a hope
Whatever wins becomes the default, and the Step 1 audit runs after every lesson's audio
is generated: a beat with a FAIL is re-requested once (one beat ≈ 200 chars ≈ $0.016);
if it still fails, the render stops and lists it. Nothing is re-rendered until the owner
has picked a number for STEP 54 (pace) too — both changes go into ONE re-render of the
lessons, not two.
