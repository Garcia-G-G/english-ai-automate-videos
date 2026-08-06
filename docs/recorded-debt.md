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

---

## 9. TikTok token exchange persists error responses as tokens (Step 5)

`TikTokUploader._exchange_code` (`src/uploader.py`) posts with `json=` and
checks only `raise_for_status()`. TikTok answers a malformed token request
with **HTTP 200 and an error body**, so nothing raises, and `_persist_token`
writes the error payload to `.tokens/tiktok_token.json` — stamping it with
`expires_at = now + 24h`:

```json
{"error": "invalid_request",
 "error_description": "Only `application/x-www-form-urlencoded` is accepted as Content-Type.",
 "expires_at": 1785617724.16}
```

Three consequences:

1. `_exchange_code` returns **True** on failure, so `authenticate()` reports
   success.
2. The file then looks like a fresh valid token for 24 hours, and
   `authenticate()` reuses it instead of re-authorizing — the failure is
   self-perpetuating.
3. The error text says TikTok requires `application/x-www-form-urlencoded`
   while the code sends JSON, which means **the TikTok code exchange has never
   worked**. YouTube's equivalent already uses `data=` and is correct.

Found by the new `python -m uploader auth` command, which is the first way to
exercise this path without a full paid pipeline run.

**Not fixed here** — `_exchange_code` is the upload path, which Step 5 owns.
The CLI defends itself instead: `_describe_token` treats a file with no
`access_token` as CORRUPT rather than valid, so `status` and `auth` cannot
repeat the lie. Fixing it properly means sending form-encoded data AND
treating an `error` key in a 200 response as a failure.

---

## 10. `uploader.py` never loads `.env`

Every other env-reading module in `src/` calls `load_dotenv` at import.
`uploader.py` does not — it has always been imported by `pipeline.py` or
`admin.py`, which load it first, so the omission was invisible.

Run standalone it sees no credentials and reports every platform as "not
configured" while `.env` holds valid ones.

The CLI calls `_load_env()` inside `main()` rather than at module import, so
the upload path keeps exactly its current import-time behaviour. Moving it to
module scope would be tidier and is safe as far as anyone can tell, but it
changes import-time side effects for every existing caller — a Step 5
decision, not a drive-by.

## `_build_fallback_title` re-randomises per platform

`generate_metadata` falls back to `random.choice(TITLE_TEMPLATES[...])` when
the script carries no `video_title`. Both admin's bulk path and — since
main.py joined the shared resolver — main.py call the resolver once per
platform, so on such a script YouTube and TikTok can be handed different
fallback titles for the same video.

main.py previously called `generate_metadata` once and adapted per platform,
which did not have this property. Joining the shared resolver traded that away
for having one resolver instead of three; the trade is deliberate.

ASLEEP BY CODE, NOT BY DATA — checked 2026-08-06. The earlier note said this
was unreachable because recent scripts happen to carry `video_title`, which
would be a property of GPT output and could change on any prompt edit. It is
stronger than that.

`script_schema` marks `video_title` Optional, so the schema alone guarantees
nothing. But `validate_and_clean_script` (script_generator.py:849-853)
synthesises a fallback for every script, and `generate_script` calls it on the
`--batch` path. Verified on a real script of each of the five types with
`video_title` deleted: all five came back with one.

The single path that SKIPS the synthesis is the early return on a missing
required field (script_generator.py:655-658). That cannot reach an upload:
the legacy `required_fields` map and the pydantic required set are identical
per type, so any script that takes the early return also raises at validation
point 1 and never renders.

So the fallback title cannot fire unattended. Fixing the per-platform
re-randomisation properly still means splitting generate from adapt in the
resolver's contract, which changes admin's two paths as well.

## The idempotency key is (artifact name, platform) — and what it misses

The guard added for the duplicate-publication defect keys on the artifact
name plus the platform, matching what the ledger and `unrecorded_platforms`
already key on. A content hash would be a truer identity, but introducing a
second identity would mean two guards that can disagree about whether the
same video is published, and disagreement is how the first duplicate
happened.

THE CASE IT DOES NOT COVER: **the same artifact name for different content.**
Re-render a topic to fix a bad video, keep the name, and the guard reads the
old publication row and refuses to publish the new file — silently, forever,
because a skip is not an error. This is the T3 failure mode moved one step
back.

Normal renders are safe: names carry a timestamp
(`foodie_20260731_163822`), so a re-render gets a new name and publishes.
The exposed route is `--name` / `run_from_text`, where the operator supplies
a name with no timestamp; publishing twice under one name is then indist-
inguishable from a duplicate.

Not fixed here because the safe direction is the one it already takes:
refusing to publish is recoverable by a human, a second live video is not.
The escape hatch when it bites is to remove the artifact's ledger row, which
is a deliberate append-only violation and should stay manual.

SECOND HOLE: a resumable session URI that 404s. Google's protocol says an
expired URI tells you nothing about whether the upload completed first, so
the guard HOLDS — it neither retries nor skips, and logs CRITICAL. That is a
video needing a human to check the channel by hand. It cannot be resolved
from the session alone; resolving it automatically would mean matching
recent channel uploads by title, which is a fuzzy match on the one decision
that must not be fuzzy.
