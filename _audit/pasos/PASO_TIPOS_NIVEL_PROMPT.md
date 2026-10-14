# Brief for Code — the "level" family: three new Short types on one engine

## 0. Context and order

The owner asked (2026-10-13) for formats like one he sees a lot: ten words in rising
difficulty, and the viewer learns their level — up to item 3 = **básico**, up to 7 =
**intermedio**, all 10 = **experto**. He asked for at least three such types and 100
scripts each. The scripts are written and checked; this brief is the build.

| order | type id | on-screen name | the viewer… | drafts |
|---|---|---|---|---|
| 1 | `level_test` | ¿Qué nivel tienes? | hears/sees an English word or expression, says what it means | `content/drafts/level_test/` lv001–lv100 |
| 2 | `pronounce_level` | ¿Cómo se pronuncia? | reads an English word aloud before the voice says it | `content/drafts/pronounce_level/` pl001–pl100 |
| 3 | `say_it_level` | Dilo en inglés | reads a Spanish sentence, says it in English (8–10 are traps) | `content/drafts/say_it_level/` sy001–sy100 |

Same rule as every new type: **build #1, render one, the owner approves by eye and ear,
then #2, then #3.** But design the renderer and the audio generator ONCE for the family
(§3–§4): #2 and #3 should be a mode, a segment plan and a registry entry, not a copy.
(`fix_the_error`, type #2 of the earlier list, still waits for the owner's verdict on bv001.)

Read first: `content/drafts/LEVEL_TYPES_SPEC.md` (the script shapes and every rule),
`content/drafts/README.md` (§ The level family), `tools/level_drafts_check.py` (the checks
the 300 drafts pass today: 0 errors, 0 cross-video repeats). Topic files ready to move:
`content/drafts/topics/{level_vocab,say_it,pron_level}.json`.

Hard constraints (owner's words): OpenAI and ElevenLabs are the only paid APIs; everything
else local and free (ffmpeg, PIL, Python, Whisper). **No MoviePy.** Per-video ceiling
$0.30; flag anything that raises spend. No keys, `.env`, voice IDs or home paths in commits.

## 1. What the video is

Vertical Short, English Unlimited brand v2 (`brand.json`, Fredoka), same family look as
how_do_you_say but not a notebook: a **level meter** — a column (or arc) of ten notches
in three bands, básico (green, 1–3), intermedio (amber, 4–7), experto (red/brand accent,
8–10). The current item's notch lights up; the item card shows the big number ("4/10"),
the prompt, then the reveal. At item 4 and item 8 a banner slides in: «NIVEL INTERMEDIO»,
«NIVEL EXPERTO» while the fixed tier line plays. After item 10 a verdict card shows the
three thresholds (3 → básico, 7 → intermedio, 10 → experto) while `verdict` is spoken,
then `outro`. Pure function of t; no segment_times is a refusal, as in how_do_you_say.

Per type, the item card:

| type | prompt (before the pause) | reveal (after the pause) |
|---|---|---|
| level_test | `english` (big), spoken once | `spanish` (meaning) written in + spoken |
| pronounce_level | `english` (big), NOT spoken | voice says `english` twice; `respelling` (stressed syllable is the CAPS one — draw it in the accent colour) + `ipa` small + `trap` (Spanish, one line) |
| say_it_level | `spanish` sentence (see §5 for whether it is spoken) | `english` written in + spoken; `alt` small ("también: …") if present; `tip` (items 8–10, Spanish) as a one-line note |

## 2. Schema (`script_schema`, `length_spec`)

Port the rules in `tools/level_drafts_check.py` / LEVEL_TYPES_SPEC.md into the schema
(exactly 10 items; CEFR non-decreasing with the per-tier ranges; tags only in intro/outro
and only from `audio_tags.TAGS`; one Noto-valid emoji at the end of title/description;
hashtags[0] is the type tag; respelling syllables == IPA nuclei and the CAPS syllable is
the ˈ syllable). Then **measure** every text field against the real card widths with
`length_spec` (the char limits in the spec are a first guess, not a layout). Report any
draft that does not fit — I will rewrite it rather than shrink the font below brand minimum.

`translations`, `english_phrases` and `full_script` are derived at migration time, the way
how_do_you_say's were (one script, run once, committed with the moved files). Drop
`"draft": true` when a file moves to `content/queue/<type>/`.

## 3. Audio — one generator, three segment plans (v3 family)

| segment | level_test | pronounce_level | say_it_level |
|---|---|---|---|
| intro | ES, tag allowed | same | same |
| prompt_i | `english` once (EN) | — (silent; text only) | `spanish` (ES) — see §5 |
| think_i | generated silence 2.0 s (no API call) | 2.2 s | 2.5 s |
| answer_i | `spanish` (ES) | `english` twice, "Comfortable… comfortable." (EN; clamp_take_gap as in how_do_you_say) | `english` once (EN) |
| tier_4, tier_8 | fixed lines, **recorded once per voice and cached** («Ahora, nivel intermedio.» / «Y ahora, nivel experto.») — zero per-video cost | same | same |
| verdict | ES, no tag | same | same |
| outro | ES, tag allowed | same | same |

- Language per segment explicit. Apply the Manim finding (618b044): **no previous/next
  context across a language switch** — the onset stutters («m-make», «d-do») came from it.
  Run the onset gate (3ad373d) on every EN segment that follows an ES one.
- think_i is declared silence for `qa_gate` (as how_do_you_say's `think_<i>`), and the
  gaps carry room tone (`generate_silence`), never digital zero.
- NOTE from today's log: `cómo_se_dice_20261013_160104` (bv004 colores) was QA-REJECTED
  with `dead_air:3.427s`. Find where 3.4 s of undeclared silence came from before cloning
  that segment plan — the same hole would land in all three new types.

## 4. Registry and doors

One entry each in `src/video_types.py` (timing "v3", text band measured from the card,
dashboard labels «¿Qué nivel tienes?», «¿Cómo se pronuncia?», «Dilo en inglés»), plus the
doors that read from or sit beside it, as in 8eed421: `type_categories` (level_test →
level_vocab, pronounce_level → pron_level, say_it_level → say_it), hashtags in config,
title template, GPT prompt builder, spoken-word count, provider routing (OpenAI provider
refuses these types, like how_do_you_say). Move the topic files into `content/topics/`
in the same commit that moves that type's drafts into the queue.

## 5. Duration — decide with a measured render, not with my estimate

My estimate (words at 2.4 w/s + think + per-segment overhead fitted on bv001's 70.3 s):

| type | median | range | vs 50–80 s band |
|---|---|---|---|
| pronounce_level | ~71 s | 67–81 | fits |
| level_test | ~84 s | 79–102 | at/over the ceiling |
| say_it_level (ES + EN spoken) | ~117 s | 105–130 | over |
| say_it_level (ES on screen only) | ~95 s | 89–103 | over |

Levers, in this order, measuring after each: (1) trim lead/tail silence of every API
segment to ≤ 0.15 s (bv001 spent ~1.2 s per API segment beyond its words); (2) think 2.0 →
1.7 s (level_test/pronounce) and 2.5 → 2.2 s (say_it); (3) say_it_level: Spanish on
screen only, not spoken (the viewer reads it during think_i; give think ≥ 3.0 s then);
(4) if a type still lands over 80 s, **do not cut items** (the 3/7/10 format needs ten) —
give it its own `reject_max_seconds` in `duration_spec` and tell me the number; the owner
decides whether that type may run to ~95 s.

## 6. Proof I need back

- The six/seven existing types render byte-identically before and after (layout pins).
- One full render of `level_test` (lv001 cocina): final QA PASS, 0 CLIFF on EN segments,
  duration, characters, cost per video. Stills of: item 1 prompt, item 1 reveal, the
  intermediate banner, item 10 reveal, the verdict card → `_audit/stills/`.
- `length_spec` report over all 100 level_test drafts (which fields fit, which do not).
- Then stop for the owner's eye and ear before `pronounce_level`.
