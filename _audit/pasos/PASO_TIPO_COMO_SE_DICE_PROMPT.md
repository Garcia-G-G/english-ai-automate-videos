# Brief for Code — new video type #1: `how_do_you_say` ("¿Cómo se dice…?")

## 0. Context and order

The owner approved SIX new types (2026-10-08) and opened the channel to **A1**
for the two beginner formats:

| # | type id | Spanish name | status |
|---|---|---|---|
| 1 | `how_do_you_say` | ¿Cómo se dice…? (cuaderno) | **this brief** |
| 2 | `fix_the_error` | Corrige el error | spec when #1 is approved |
| 3 | `conjugation_map` | Mapa de conjugación | spec later |
| 4 | `minimal_pairs` | Pares mínimos | spec later |
| 5 | `expression_of_day` | Expresión del día | spec later |
| 6 | `ladder` | Escalera | spec later |

(micro-diálogo stays blocked on a second ElevenLabs voice ID in `.env`.)

**Rule, unchanged from `STEP_41.md` §4: one type built,
rendered and approved by the owner's ear and eye before the next one starts.**
The registry (`src/video_types.py`, 2af0f27) means a type is: renderer + audio
generator + one registry entry (+ schema, length_spec, duration, categories,
metadata, which all read from it or sit next to it).

Hard constraints (owner's words, still in force): OpenAI and ElevenLabs are the
only paid APIs; everything else local and free (ffmpeg, PIL, Python, Whisper).
**No MoviePy.** Flag anything that raises per-video API spend (ceiling $0.30).
No keys, `.env`, voice IDs or home paths in commits.

## 1. What the video is

Reference the owner sent: a spiral notebook, title "How do you say?", ten
Spanish words each with an emoji, a pencil pointing at the list. Ours does the
same thing **with the voice and the reveal**, in the English Unlimited brand.

Per item: the row lights up → the voice says the Spanish word → **1.8 s of
silence** (the viewer's turn to answer) → the voice says the English word
**twice** → the English word is written in to the right of the Spanish one while
the pencil moves along it. At the end, the voice reads all ten English words in
a row (recap) and asks how many the viewer knew.

Level A1. 10 items (8 minimum, 10 maximum).

## 2. Script schema

```json
{
  "type": "how_do_you_say",
  "video_title": "...", "video_description": "...",
  "title": "¿Cómo se dice…?",
  "theme": "la familia",
  "level": "A1",
  "intro": "[cheerful] ¿Sabes decir estas 10 palabras en inglés? Piensa antes de que yo lo diga.",
  "items": [{"emoji": "👪", "spanish": "Familia", "english": "family"}, "... 8-10 items"],
  "recap": "Ahora todas en inglés, conmigo: family, mother, ...",
  "outro": "[excited] ¿Cuántas sabías? Dímelo en los comentarios.",
  "full_script": "...", "translations": {"family": "Familia"},
  "english_phrases": ["family", "..."], "hashtags": ["..."],
  "_meta": {"category": "basic_vocab", "topic_id": "bv001", "video_type": "how_do_you_say"}
}
```

Validation (`script_schema` + `length_spec`):
- 8 ≤ len(items) ≤ 10; each `spanish` ≤ 14 chars, `english` ≤ 14 chars (measure
  against the real row width in `length_spec`, don't trust the number).
- `emoji`: ONE glyph that the vendored emoji font actually contains (single code
  point, optionally + U+FE0F). Check against the font's cmap, not a hand list. ZWJ
  sequences are rejected — they render as two emojis when the font lacks the
  sequence, and that is a silent defect.
- tags only from `audio_tags.TAGS`, only in `intro` / `recap` / `outro`.

Three ready scripts: `content/drafts/how_do_you_say/bv001_familia.json`,
`bv002_casa.json`, `bv003_comida.json`. Move them into
`content/queue/how_do_you_say/` once the schema accepts them; drop the
`"draft": true` key in `_meta`.

## 3. Audio — `generate_how_do_you_say_audio_segmented` (v3 family)

Segments, in order, each with measured boundaries (`segment_times`) like the
other v3 types:

```
intro
for i in items:  es_i  ("Familia.")          spoken
                 think_i (1.8 s)              generated silence, no API call
                 en_i  ("Family. Family.")    spoken, English text
recap                                          spoken
outro                                          spoken
```

- The **same single voice** for Spanish and English, `eleven_v3`, exactly as
  `vocabulary` does today — no second voice needed.
- en_i must pass through the existing seam/edge repair in `tts_common`
  (onset/tail), since it is a short English segment between silences — the case
  that produced the chopped-audio bug before. Verify with `tools/audio_seams`
  on the first render: no CLIFF/DROP flags on any en_i.
- Cost: ~450 characters of speech per video, ~22 segment calls. Well under the
  $0.30 ceiling; report the real figure from `cost_tracker` on the first render.

## 4. Picture — `src/video/how_do_you_say.py`

1080×1920, PIL only, brand v2 "Pegatina" from `brand.json` (Fredoka Bold,
yellow `#F2D66B`, blue `#1B6FA8`, ink `#1C1812`, sticker outline + shadow).

- **Background:** brand yellow, flat or with the existing background system —
  whatever `clip_contrast` accepts for the text band.
- **Notebook page:** off-white card (~ #FBF8F0) ~860×1420, rounded 28 px,
  sticker shadow, slight tilt (≤ 1.5°) fixed for the whole video; spiral rings
  down the left edge drawn as ink-outlined loops (≈ 18 rings).
- **Title:** "How do you say?" in brand blue Fredoka Bold ~76 px with a hand-drawn
  underline; theme line under it in ink ~40 px ("la familia").
- **Rows (10):** emoji ~96 px + Spanish word ink ~58 px on the left half; the
  English word appears in brand blue ~58 px on the right half. Row pitch so ten
  rows fit inside the text band with margins; `length_spec` owns the check.
  All Spanish words are visible from the first frame (the viewer can try them all).
- **Active row:** a soft yellow highlighter band behind it, fading in over 0.25 s
  when es_i starts; the emoji pops 0.85 → 1.0 (ease-out, 0.3 s).
- **Reveal:** the English word is written left-to-right with a clip mask, over
  the duration of the FIRST "Family." of en_i (not a fixed time). A small green
  tick appears after it.
- **Pencil:** drawn in PIL, sticker style — yellow body, wood cone, ink tip,
  ink outline. It eases (ease-in-out, 0.35 s) to the active row during es_i,
  then travels along the English word in sync with the reveal mask.
- **Countdown during think_i:** a thin ring or 3 dots beside the row emptying
  over 1.8 s, so the silence reads as "your turn", not as dead air.
- **Recap:** all rows complete; each English word pulses (scale 1.0 → 1.08 → 1.0)
  as the recap voice reaches it — timed from the recap segment's word timings if
  available, otherwise proportional by character inside the recap segment.
- Emoji rendering: **Noto Color Emoji** (SIL OFL, free), vendored under
  `assets/fonts/` with its licence file. PIL only rasterises it at size 109 with
  `embedded_color=True`; render at 109 and resize. Do NOT use Apple Color Emoji
  (licence not cleared for published video).

Registry entry: `timing: "v3"`, `text_band` measured from the real layout,
`dashboard: "Cómo se dice"`.

## 5. Duration

Expected per video: intro ~4 s + 10 × (es 0.8 + think 1.8 + en 1.6 + gap 0.4)
+ recap ~9 s + outro ~4 s + 4 s outro card ≈ **67 s**. Inside the global 50–80
band. No calibrated rate exists yet: the type uses the global band until
`duration_calibrate.py` has ≥ 4 renders of it, then gets its own row in
`config.yaml` (same discipline as quiz: n stated honestly).

## 6. Topics

New category `basic_vocab` → `content/topics/basic_vocab.json`, mapped ONLY to
`how_do_you_say` in `config.yaml type_categories` (so no existing type starts
drawing A1 topics). Twenty topics to start:

bv001 la familia · bv002 la casa · bv003 la comida · bv004 los colores ·
bv005 los números 1–10 · bv006 la ropa · bv007 el cuerpo · bv008 los animales ·
bv009 el tiempo (clima) · bv010 la ciudad · bv011 el trabajo · bv012 la escuela ·
bv013 las emociones · bv014 los días de la semana · bv015 los meses ·
bv016 la cocina (utensilios) · bv017 el transporte · bv018 la fruta ·
bv019 los deportes · bv020 los verbos básicos (comer, beber, dormir…)

## 7. Metadata

Title template: `¿Cómo se dice {THEME} en inglés? {emoji}`. Hashtags:
`#InglésParaPrincipiantes #VocabularioEnInglés #AprenderInglés #InglésFácil
#HowDoYouSay`.

## 8. Acceptance — proof, not claims

1. The six existing types render **byte-identically** before and after (the same
   test the registry refactor used).
2. `queue_guard` accepts the three moved scripts: 0 BLOCKED, 0 `length:`.
3. Render `bv001_familia` and report: video duration, segment table (start/end
   of every es_i / think_i / en_i), API characters and cost, `audio_seams` result
   on every en_i, and three stills: first frame, item 5 mid-reveal, recap.
4. The owner watches it. Type #2 (`fix_the_error`) does not start until he says yes.

## 9. Not in this step

The other five types; thumbnails; Manim; any change to the existing six types
beyond reading from the registry.
