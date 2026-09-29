# Audit before the five new types: what a video type costs today

## 0. The ONE-LINE version of what the owner asked for

> Five new video types: **micro-diálogo (2 voces), pares mínimos, corrige el error,
> expresión del día, escalera.**

He has asked for these repeatedly and none has been started. This document is not the
build. It is what I found when I checked what "add a type" actually costs, because
building five of anything through a fourteen-door path is how the last six types ended
up with capabilities that have no door.

---

## 1. Adding one type means editing fourteen places

| # | where | what |
|---|---|---|
| 1 | `src/script_schema.py:61` | `VIDEO_TYPES` tuple |
| 2 | `src/script_schema.py:64` | `VideoType` Literal — **the same list again** |
| 3 | `src/script_generator.py:38` | `VIDEO_TYPES` list — **the same list a third time** |
| 4 | `src/video/__init__.py:568` | argparse `choices=[...]` — **a fourth time** |
| 5 | `src/video/__init__.py:~408` | the `elif video_type == …` dispatch chain |
| 6 | `src/video/<type>.py` | new renderer: `create_frame_<type>`, `resolve_<type>_timestamps` |
| 7 | `src/tts_elevenlabs.py` | `generate_<type>_audio_segmented` |
| 8 | `src/timing_contract.py:52` | `V3_TYPES` frozenset |
| 9 | `config.yaml:109` | `duration.types`: rate, silence, n, fixed_words, items_spoken |
| 10 | `config.yaml:~191` | topic categories allowed for the type |
| 11 | `src/metadata_generator.py:30,93` | title templates and hashtags |
| 12 | `src/clip_contrast.py:105` | the on-screen text band (y-range) the background must not fight |
| 13 | `src/admin.py:2623` | the dashboard's tab list |
| 14 | `src/length_spec.py:125` | layout capacity check |

Plus `tools/_queue_build.py` for authoring scripts of the new shape.

**Four of those fourteen are the same list, written out four times, independently.** A
type can be legal in the schema, illegal in the generator, absent from the CLI and
missing from the dashboard, all at once, and nothing fails loudly — it just does not
appear. That is this repo's signature failure verbatim: *una capacidad sin puerta es una
capacidad que no existe.*

Five types through this path is seventy edits and four chances per type to half-exist.

---

## 2. So the first step is not a type

**Make the list of video types exist once, and make the dispatch data-driven.**

There is already an idiomatic pattern in this codebase — `CHARACTER_REGISTRY` in
`src/generate_character.py:198`. One registry entry per type carrying its renderer, its
timestamp resolver, its audio generator, its duration constants, its text band and its
metadata templates; everything in §1 reads from it instead of restating it.

Done first, adding a type becomes: write the renderer, write the audio generator, add
one registry entry. **Three places instead of fourteen, and none of them duplicated.**

This is mechanical, it is testable (every existing type must render byte-identically
before and after), and it pays for itself on type number two. Doing it after the five
types would mean doing the fourteen-door dance five times and then refactoring anyway.

**Acceptance:** every one of the six existing types produces a byte-identical video to
the one it produces today. No behaviour change at all — this step is pure plumbing, and
if any output moves, the refactor is wrong.

---

## 3. A blocker the owner has to clear, and it is not a purchase

**There is exactly one ElevenLabs voice in this project.**

```
src/tts_elevenlabs.py:64   DEFAULT_VOICE_ID = VIDEO_PROFILE_VOICE_ID or ELEVENLABS_VOICE_ID
.env                        ELEVENLABS_VOICE_ID   (one, "ZOgeDYxfyev5qgOXq2lN")
```

Every call site resolves to that one. **Micro-diálogo a 2 voces cannot exist until a
second voice ID exists** — and that is the identical shape of the thing that has kept
Bilibili blocked on `BILIBILI_ADULTS_ELEVENLABS_VOICE_ID` and children's content blocked
on `CHILDREN_ELEVENLABS_VOICE_ID` for weeks.

Worth being precise with the owner, because it sounds like a cost and is not: an
ElevenLabs voice ID comes from the voice library on the existing plan. **It adds nothing
to the per-character price and needs no new subscription.** It is one line in `.env`.

Three voice IDs are now blocking four features. That is a five-minute task that has been
costing months.

---

## 4. Proposed order

1. **The registry** (§2). No new type, no visible change, fourteen doors become three.
2. **Micro-diálogo a 2 voces** — the owner's most-repeated ask and the most distinctive
   format on the channel. Needs the second voice ID; ask now so it is ready.
3. The remaining four, which by then cost a fraction each: *corrige el error* (reuses
   the quiz/true_false skeleton we just spent five steps repairing), *pares mínimos*
   (closest to `pronunciation`), *expresión del día* (closest to `vocabulary`),
   *escalera* (the only one needing a genuinely new on-screen pattern).

One type finished and rendered before the next is started.

## 5. What I supply, and when

The per-type spec — structure, fields, audio segment plan, layout, duration band, topic
categories, and the pre-written scripts — is mine, and I will write it **per type, at
the moment that type is built**, not five specs up front. Five speculative specs against
a path nobody has walked yet is exactly the kind of work that gets 20 % applied.

## 6. Not in this step

The audio thread is closed. `duration_calibrate.py` still needs re-fitting over a batch,
and a new type changes what it fits, so it waits until at least the first new type is
producing videos.
