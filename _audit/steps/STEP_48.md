# STEP 48 — Manim lesson audio: harsh "s" and stutters at the start

## 0. What the owner hears (his words)

- "las s suenan muy SSS": the sibilants are harsh.
- "a veces es como que se corta o aparece un sonido raro… dice «i-i can swim»…
  en vez de «mira la tabla» dice «i-ira la trabla»". Something stutters or
  glitches right before the voice starts.

Both are in the long Manim lessons (gen_audio.py → eleven_turbo_v2_5,
bilingual segments, stitched). Examples he named:
- `audio/can-could-pedir/english-teacher/b08.mp3` ("Mira la tabla.")
- `b05.mp3` ("…I can swim…")
- `audio/make-vs-do/english-teacher/b18.mp3`

Rules from the chopped-audio thread still apply: **measure before fixing, and
one cause at a time.** Constraints are unchanged: ElevenLabs and OpenAI only,
everything else local, no MoviePy, no keys / voice IDs / home paths in commits.

## 1. What I measured (offline, no API) — evidence, not a verdict

- **can-could b08, 5 ms envelope, first 120 ms:** a ~50 ms burst (−14 dB) at
  30–70 ms, a dip to −38 / −42 dB at 80–90 ms, then speech from 100 ms. There is
  no stop consonant inside "Mira" to explain a dip there. This matches a short
  fragment before the word: "i-…ira".
- **make-vs-do b18 and present-perfect b10:** "Mira la" is squeezed into
  180–310 ms. That is very short for two syllables plus "la", which suggests the
  onset is truncated.
- A crude burst / dip / burst scan of the first 250 ms of all 288 beats on
  disk flags 41. **This detector has false positives**: stop-consonant
  closures (p, t, k) dip naturally, so do not use the 41 as a number.
- **Sibilance:** the 5–10 kHz share of energy on voiced frames, 95th
  percentile, is −3 to −11 dB across lesson beats and Shorts narrations. I have
  no reference for "good", so this needs an A/B by ear plus a metric.

## 2. The decisive instrument — raw vs processed

Add `--keep-raw` to gen_audio.py. It saves every segment exactly as ElevenLabs
returned it (`audio/<lesson>/<voice>/_raw/<beat>_<n>_<lang>.mp3`), together with
the request body minus the key: text, previous_text / next_text / ids present
yes or no, language_code, speed.

Regenerate only these beats with `--keep-raw` (≈ $0.05):
- can-could-pedir b05 and b08
- make-vs-do b18
- present-perfect-vs-past b10

Then, for each segment:
- If the **raw** file already starts with the glitch, the cause is upstream
  (model or stitching). Go to §3.
- If the raw file is clean and the **processed** one is not, the cause is
  ours: `silenceremove` at −42 dB eating a soft nasal onset ("M"), the 12 ms
  fade-in landing mid-voicing, or level_match gain. Go to §4.

Report a table: segment, language, starts after a language switch (y/n),
raw onset clean (y/n), processed onset clean (y/n). Attach 1 s clips of raw
and processed for each.

## 3. If upstream — test the stitching, one variable at a time

Same text, same voice, four variants per segment (≈ $0.10 total):
- (a) current: previous_text + next_text + previous_request_ids
- (b) without previous_request_ids
- (c) without previous_text and previous_request_ids (next_text only)
- (d) none

Hypothesis to test: stitching context from the **other language** (an English
segment before a Spanish one, or the reverse) makes turbo begin with a
carried-over phoneme. If (b) or (c) is clean and (a) is not, use that variant
only at language switches, and keep full stitching within the same language.

## 4. If ours — fix the edge processing

- Trim with an onset detector that finds the first speech frame and backs off
  30 ms before it, instead of a fixed −42 dB gate that a soft "m" or "n" can
  fall under.
- Start the fade-in before the first voiced sample, never on it.
- Prove it on the raw files from §2: the processed onset must keep the
  consonant. Check this with the envelope and by ear.

## 5. Sibilance — A/B, then a rule

Generate one test beat (≈ $0.02) with many s sounds, in both languages:
"Las cosas sencillas se aprenden despacio. [[She sells sea shells, so she
says yes.]]"

Make these variants. A–C are new generations; D and E are offline processing:
- A: current settings
- B: style 0.3 → 0.1
- C: use_speaker_boost false
- D: A plus ffmpeg `deesser` (start i=0.4, m=0.5, f=0.5; tune)
- E: A plus mp3 at 192 kbps instead of 128 (128 k MP3 can smear sibilants)

Deliver a single `sibilance_ab.mp3` with a spoken label before each variant
(the labels can be ffmpeg sine beeps; no extra API cost). Report the 5–10 kHz
p95 metric per variant.

**The owner picks by ear; the metric only confirms.** Whatever he picks
becomes the default in gen_audio.py.

## 6. Then

- Scan every beat on disk with the fixed onset detector. Regenerate only the
  beats that still glitch: no blanket re-generation, and report the cost.
- Re-render none of the lessons until the owner has approved the A/B and one
  re-generated beat.
- Commit in logical steps.

## 7. Shorts

The Shorts use another path (`src/tts_common.py`, eleven_v3 / turbo with seam
repair). Do not touch it in this step. Once the Manim cause is known, write
one paragraph on whether the same cause can apply there.
