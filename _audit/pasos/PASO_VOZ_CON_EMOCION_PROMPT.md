# Step: close the audit, then make the voice sound the way the scripts were written

Supersedes the earlier version of this file (`7516563`). One brief, in order.

## 0. The ONE-LINE version of what the owner asked for

> "mejora esos diálogos, que haya más contenido en esos videos" — and before that,
> repeatedly: "los diálogos se sienten muy directos, sin personalidad… recuerda que a
> ElevenLabs le puedes poner emociones".

**More content per video, and a voice with emotion.** Finding 3 delivers the first half.
This brief delivers the second, and fixes one thing finding 3 makes worse.

---

## 1. Audit status — verified, good work

`da82ac6` `30d2f13` `45e305a` `3a65ad8` are in. 1630 passed, 1 skipped. Finding 2 closed
as not a defect.

On finding 3, three catches that would each have shipped a silent one-item video: the
door on the wrong provider (`resolve_provider_name()` defaults to elevenlabs), the
`transition` key with three writers in `emit_split_options`, and `questions` missing from
the audio json the renderer actually loads. And pins verified red against HEAD, not just
green against yours. 64.3 s for a 3-item quiz clears the 50 s floor.

Checked on my side: `_strip_audio_tags` (`src/video/__init__.py:25`) recurses into dicts
and lists, so items 2 and 3 of `questions` are cleaned for screen like the root. With tags
about to reach the audio (§3), that door had to be closed, and it is.

Commit finding 3 when the suite reports. **Then §2 is the very next commit, and no quiz is
rendered in between.**

## 2. First: the blank is deleted, and finding 3 multiplies it

`clean_for_tts` (`src/tts_common.py:682`) removes `___` without replacing it:

```
screen: The dog wagged ___ tail happily.
voice : The dog wagged tail happily.
```

That is the its/it's quiz the owner rejected. Now that items 2 and 3 are spoken, it gets
worse. Measured on the queue:

```
quiz in queue: 9 scripts, 25 questions, 7 with a blank
broken sentences spoken  before finding 3: 3
                         after  finding 3: 7
```

`gr004_first_conditional.json`, as it would render today:

```
If I time, I will call you tonight.
If it tomorrow, we'll stay home.
She you if she finds the keys.
```

Three ungrammatical English sentences in a row, on an English-teaching channel. fill_blank
goes through the same function (`tts_elevenlabs.py:919`), 17 queue scripts in total.

**Fix:** in the spoken text only, the blank becomes an audible pause (`...`, which v3 reads
as a hesitation). The screen keeps `___`. `fc702a9` fixed the opposite problem (scripts
that said "guion bajo" out loud) — this is the other half.

**Proof:** `clean_for_tts("I need to ___ a phone call.")` must not return
`"I need to a phone call."`, pinned by a test that is red against HEAD.

## 3. Every emotion tag is deleted before the API call — all six types

The same function strips square-bracket tags:

```
'[excited] ¡Correcto!'          -> '¡Correcto!'
'[curious] Sarah will ___ it.'  -> 'Sarah will it.'
```

It sits on every path to the API:

```
quiz          tts_elevenlabs.py:601, 604, 607
fill_blank    tts_elevenlabs.py:919, 1066
true_false    tts_elevenlabs.py:1181, 1294
vocabulary    tts_elevenlabs.py:1465, 1490, 1506
educational   tts_segmenter.py:522  (via tts_bilingual.plan_calls)
pronunciation tts_segmenter.py:522
```

Dry run on a real pronunciation script: four tags written, **zero sent**. Across
September's sidecars, **0 of 344** spoken segments carry one. The ~550 tags written into
the queue this month have never reached ElevenLabs. That is my miss as much as anyone's:
I wrote them and never checked they arrived.

Second layer, same result: in quiz, true_false, fill_blank and vocabulary, **240 of 340
tags (71 %)** sit in `full_script`, which those generators never read.

### The fix

Tags survive **only when the target model honours them**:

- **`eleven_v3`** (`V3_TYPES`: quiz, true_false, fill_blank, vocabulary): keep them. They
  are already kept off the screen (§1) and out of the word list (`tts_elevenlabs.py:325`).
  Use `src/audio_tags.py` — the one definition. No second regex.
- **`eleven_turbo_v2_5`** (`TURBO_TYPES`: educational, pronunciation): turbo does not
  interpret tags. Strip them, as today, but deliberately and in one place, not as a side
  effect of a cleaning function. Emotion for these two needs a different lever
  (`voice_settings.style`, wording). Flag it; do not switch models in this step.

**Proof:** a dry-run log of the exact text sent to the API for one quiz, with the tags in
it, including items 2 and 3.

## 4. The fixed quiz phrases are identical in every video

`tts_elevenlabs.py:719, 735, 764`: every quiz says *"Escucha las opciones." / "¡Piensa
bien!" / "Correcto. La respuesta es A, its."* — flat, identical, and no script can change
them. With three items per video, the listener now hears the answer line three times.

Replace each with a small pool, chosen **deterministically per `topic_id` and item index**
(same script re-rendered says the same thing; the three items of one video do not repeat):

```
transition  "[curious] Mira bien las opciones."
            "[playful] Ahí van las cuatro."
            "[curious] Escucha las opciones, que hay trampa."
think       "[thoughtful] Piénsalo un segundo."
            "[playful] ¿La tienes? Piensa."
            "[thoughtful] Tómate tu tiempo."
answer      "[excited] ¡Eso es! La respuesta es {L}, {text}."
            "[cheerful] ¡Correcto! Es la {L}, {text}."
            "[excited] ¡Bien! La buena es la {L}, {text}."
```

Keep `add_natural_pauses` (`tts_elevenlabs.py:123-126`) working — it matches on
`La respuesta es` / `Correcto` — or update it in the same commit. Same treatment for the
fixed phrases in fill_blank and true_false.

## 5. Then: the owner listens

**One rendered 3-item quiz with §2–§4 in it, sent to the owner.** Whether it sounds
charismatic is his call, not a number. Use `content/drafts/cw006_its_v2.json` — it was
written for exactly this: three questions, each explanation inside the 183-char layout
limit. It stays in `content/drafts/`, outside the queue, by the owner's decision; render it
by path, do not move it into the queue.

## 6. Two small ones

- **Wrong file name.** The rejected its/it's quiz is saved as
  `output/rejected/quiz/i_went_to_there_20260908_231253.mp4`; its script says "ITS o IT'S".
  Stale slug. Anyone looking for it by name will not find it.
- **Duration predictor off for pronunciation.** `rate 1.54` (n=12, marked indicative)
  predicted 77.5 s for `pr002`; the real video is 57.5 s. And quiz now speaks three items.
  Both go into the recalibration of `tools/duration_calibrate.py`, which should run once
  there is a batch of new videos, not before.

## Order

finding 3 commit → §2 → §3 → §4 → §5 (render for the owner) → §6.
One commit each. Nothing rendered for publishing until §2 is in.

## Out of scope

Rewriting more scripts. There is no point until §3 lands. The drafts in `content/drafts/`
(`pr002_bit_beat_v2`, `cw006_its_v2`) wait there.
