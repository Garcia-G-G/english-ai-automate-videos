# Recorded debt

Findings deliberately NOT fixed when found, with the reason and the step that
should take them. Recorded so they are not rediscovered from scratch, and so
nobody mistakes "known" for "unnoticed".

---

## 1. Quiz letter clips are regenerated every video (Step 5)

Splitting the quiz options took TTS calls per quiz from **1 to 9**. Cost
actually fell 12.7% (the old combined call carried `" ... "` separators the
split does not need), but **latency and per-call failure surface both rose**,
and at batch scale that matters more than the money.

`"Opción A."` is byte-identical audio every single time. Caching the four
letter clips once removes **4 of the 9 calls** and, as a bonus, makes the
option letters acoustically identical across every video instead of
re-rolled per render.

The implementation already exists: `get_or_generate_word` at
`tts_openai.py:666-687`, written, documented as the caching architecture, and
**never called** — same orphan pattern as `config/secrets.py`.

**Do not build this before Step 5.** It changes what audio is produced, so
doing it mid-verification adds a variable to the T1-T5 diff.

---

## 2. `cost_tracker` only persists through the pipeline

`cost_tracker` logs per-call cost to the console but writes
`output/costs/*.jsonl` only when invoked through `src/pipeline.py`. Calling a
generator directly — `generate_quiz_audio_segmented(...)` — produces console
output and **no file**. The Step 3 regeneration spend went unrecorded for
exactly this reason.

Same family as the Step 0 dashboard finding: the number exists, it is shown,
and it is not durably recorded anywhere.

Direct generator calls are dev work, so this is low-severity today. It stops
being low-severity the moment anyone runs a **batch** that way — the entire
spend would be invisible.

---

## 3. `ELEVENLABS_API_KEY` pattern is stale — and the file is now half-wired

`config/secrets.py` demands `^[a-f0-9]{32}$`. The live key is **64
characters**, so the pattern would reject a working key.

The trap is not the stale regex on its own; it is that Step 1 wired
`voice_id_pattern()` / `is_valid_voice_id()` from this same file into
`profiles.py`, where they are live and enforced. So the module now holds one
verified, load-bearing pattern directly beside several unverified ones.
Whoever enables `validate_all_keys()` next will reasonably assume they are of
equal quality.

Annotated in place at the definition. Every pattern needs checking against a
real key before that function is enabled.

---

## 4. `video/quiz.py:130` — the render-side `/4` estimator

The three GENERATOR copies of the invented option arithmetic are gone. This
one survives because it is render-side: it runs only for artifacts carrying no
`segment_times`, and deleting it today would stack option cards at t=0 for the
22 historical quiz artifacts instead of spreading them approximately.

Under the Step 1 triage rule it is nonetheless a defect of the worst class —
it invents timing and presents it as sound, the same shape as `correct = 'A'`.

**Ruling: make it FAIL LOUD at the moment BLOCKING is flipped, not before.**
"No `segment_times` -> rejected" is the blocking policy anyway, and at that
point this branch becomes dead code that deletes cleanly. Doing it earlier
just adds a variable to the T5 diff.

---

## 5. Educational `segment_times` have no live producer (found in Step 3)

T3 targeted educational segment END drift (up to -1.29 s). It cannot be fixed
by changing code, because **no generator in the repo emits those segments.**

- Only 6 of 50 educational artifacts carry `segment_times` at all, in **three
  different key-sets** (`hook/meaning/example1-3/tip/cta`,
  `hook/intro/reveal/example1-2/tip/cta`, and one with `contrast`) — three
  dead generator eras.
- A repo-wide grep for those ids finds **zero** `add_segment` call sites.
- `pipeline.py:157` routes educational to `tts_bilingual`, which emits **no
  `segment_times` whatsoever**.

So the -1.29 s overrun is a fossil. The live educational defect is different
and already characterised: char-proportional word estimation that was never
aligned (mechanism B in `docs/step3-timing-spec.md`), which the QA gate covers
via check 2 at sentence granularity and which cannot be fixed without ASR.

The `measure_speech_end` fix from scope item (b) is still correct and still
applied — it just cannot reach educational, because educational does not use
the `add_audio` / `add_segment` path at all.

---

## 6. The committed baseline mixes four generator eras

`tests/baselines/qa_baseline_2026-07-30.json` spans four generator eras.
**Any target derived from it must be liveness-checked before use.**

This is the general form of an error made twice in Step 3:

- **T3** targeted educational segment END drift. No live generator emits
  educational `segment_times` at all — the six artifacts that have them come
  from three dead eras. Target withdrawn.
- **T4** targeted 78 declared-silence violations. Every one of them comes from
  the spoken-countdown era; the 38 live-era artifacts have **zero**. The
  target was measuring dead code, and the gate itself was wrong to assume
  "countdown means silent" — `tts_google` speaks it today.

The check is cheap: compare the artifact's shape against what the live
generator actually emits (segment ids, segment text, characteristic widths),
not against what the corpus contains. Liveness is a property of the producing
code, and the corpus cannot report it.

It will recur, because the corpus is the only large sample available and it is
permanently historical.

---

## 7. Educational has a systematic sentence-drift tail (measured, not blocking)

Three freshly generated educational artifacts, check-2 sentence drift:

| artifact | sentences | median | p90 | max |
|---|---|---|---|---|
| actually | 10 | 0.065 | 0.524 | **1.148** |
| give_up | 6 | 0.052 | 0.072 | 0.126 |
| freak_out | 9 | 0.070 | 0.529 | **3.205** |

Two of three exceed 0.9 s, so the tail is **systematic, not a one-off**. The
median is good — better than the same artifact's historical 0.135 — but
individual sentences land up to 3.2 s from where they are declared.

This is mechanism B from `docs/step3-timing-spec.md`: char-proportional word
estimation that was never aligned to the waveform. Fixing it needs forced
alignment, i.e. ASR, which is deliberately deferred.

**Deliberately NOT a blocking flag.** Blocking on it would reject educational
wholesale for a limitation we have decided not to remove yet. It is measured,
reported in every QA report, and recorded here so that when ASR lands there is
a number to beat.

---

## 8. `timing_engine` constants are INHERITED-UNVALIDATED — and now ship

`TAIL_PAD`, `MIN_HOLD`, `PER_CHAR`, `HOLD_GAP`, `HOLD_RELEASE`, `FADE_IN`,
`FADE_OUT`, `MERGE_MAX_CHARS`, `MERGE_SHORT_AUDIO`, `MERGE_MAX_GAP`, `CTA_LEN`.
None has a recorded derivation.

The engine's **invariants** are tested (`tests/test_timing_engine.py`) and its
logic is sound. The specific numbers are not measured against anything.

This mattered less when the engine was reachable only from the dormant v2
renderer. Step 3 wired it into v1, so these values now affect **every video
that ships**.

The QA gate cannot help: it reads audio, and these are display timings.
Deriving them needs the layout work plus a way to measure on-screen text
against the waveform. Annotated in place as INHERITED-UNVALIDATED so nobody
mistakes them for calibrated.
