# Step: make the emotion reach the voice

## 0. The ONE-LINE version of what the owner asked for

> "mejora esos diálogos, que haya más contenido en esos videos" — and before that,
> repeatedly: "los diálogos se sienten muy directos, sin personalidad… recuerda que a
> ElevenLabs le puedes poner emociones".

**The voice has to sound like the scripts were written to sound.** Today it cannot,
and rewriting the scripts again would change nothing. Here is why.

---

## 1. Every emotion tag is deleted before the API call. All six types.

`clean_for_tts` (`src/tts_common.py:682`) strips square-bracket tags:

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

Proven end to end on a real script, dry run: `plan_calls()` on a pronunciation script
with four tags sends **zero** tags. And across September's sidecars, **0 of 344 spoken
segments** carry one.

So the ~550 tags written into the queue this month have never reached ElevenLabs. That
is my miss as much as anyone's: I wrote them, and I never checked they arrived. This is
the repo's signature failure one more time — correct content that never receives the
door it needs.

**Second layer, same result:** in quiz, true_false, fill_blank and vocabulary, 240 of
340 tags (71 %) sit in `full_script`, which those four generators never read. They
build audio from structured fields only.

### The fix

Tags survive `clean_for_tts` **when the target model honours them**, and are removed
everywhere else:

- **`eleven_v3`** (quiz, true_false, fill_blank, vocabulary — `V3_TYPES`): keep them.
  They are already kept off the screen (`_strip_audio_tags` at render load) and out of
  the word list (`tts_elevenlabs.py:325`). `src/audio_tags.py` is the one definition —
  use it, do not write a second regex.
- **`eleven_turbo_v2_5`** (educational, pronunciation — `TURBO_TYPES`): turbo does not
  interpret tags. Strip them, as today, but deliberately and in one place — not as a
  side effect of a cleaning function. Emotion for these two types needs a different
  lever (voice_settings `style`, wording). Flag it; do not switch models in this step.

## 2. The blank is deleted, so the voice speaks broken English

The same function removes `___` without replacing it:

```
screen: The dog wagged ___ tail happily.
voice : The dog wagged tail happily.
```

That is what the owner heard in the its/it's quiz he rejected. **17 scripts in the queue
today** have a blank in a spoken field. On an English-teaching channel the voice is
modelling ungrammatical English.

Fix: in the spoken text only, the blank becomes an audible pause (`...`, which v3 reads
as a hesitation). The screen keeps `___`. `fc702a9` fixed the opposite problem (scripts
that said "guion bajo" out loud) — this is the other half.

## 3. The fixed phrases are identical in every quiz

`tts_elevenlabs.py:719, 735, 764`: every quiz says exactly *"Escucha las opciones." /
"¡Piensa bien!" / "Correcto. La respuesta es A, its."* — flat, and the same every time.
Nothing in the script can change them.

Replace each with a small pool, chosen **deterministically per `topic_id`** (so a
re-render of the same script says the same thing):

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

Keep the `La respuesta es` / `Correcto` substrings working with `add_natural_pauses`
(`tts_elevenlabs.py:123-126`), or update it in the same commit. Same treatment for the
equivalent fixed phrases in fill_blank and true_false.

## 4. More content in quiz = the multi-item emission (your finding 3)

A quiz speaks one question: ~40 s, under the 50 s floor. The only way it gets more
content is speaking all three authored items. `content/drafts/cw006_its_v2.json` is
written for exactly that — three questions, each explanation inside the 183-char layout
limit. It stays out of the queue until the `iN_` ids are emitted, or it will render as a
one-question video again.

## 5. Two small ones

- **Wrong file name.** The rejected its/it's quiz is saved as
  `output/rejected/quiz/i_went_to_there_20260908_231253.mp4`; its script says
  "ITS o IT'S". The file name comes from a stale slug. Anyone looking for the its/it's
  video by name will not find it.
- **Duration predictor is off for pronunciation.** `rate 1.54` (n=12, marked indicative)
  predicted 77.5 s for `pr002`; the real video is 57.5 s. Add it to the recalibration.

## Order and proof

1 → 2 → 3 → 4, one commit each.

Proof for 1: a dry-run log of the exact text sent to the API for one quiz, with tags in
it. Then **one rendered quiz for the owner to listen to**, because whether it sounds
charismatic is his call, not a number.

Proof for 2: `clean_for_tts`-level test — `"I need to ___ a phone call."` must not
become `"I need to a phone call."`.

## Out of scope

Rewriting more scripts. There is no point until 1 lands. The drafts in `content/drafts/`
(`pr002_bit_beat_v2`, `cw006_its_v2`) wait there, outside the queue, by the owner's
decision.
