# Three "level test" Shorts formats — script spec

Audience: Spanish speakers (Spain + Latin America) learning English. Vertical Shorts,
50–80 s. Every video is TEN items in RISING difficulty with three tiers:

| items | tier | on-screen label |
|---|---|---|
| 1–3 | básico | BÁSICO |
| 4–7 | intermedio | INTERMEDIO |
| 8–10 | experto | EXPERTO |

The hook: "¿Hasta qué número llegas?" — if you get up to 3 you are básico, up to 7
intermedio, all 10 experto. The difficulty curve MUST be real: items 1–3 a beginner
knows, 4–7 a solid intermediate knows, 8–10 make an advanced learner hesitate (but are
still genuinely USEFUL, real, current English — no obscure dictionary trivia, no
archaic words, nothing offensive, no brands, no real people).

Tier announcements ("Ahora, nivel intermedio." / "Y ahora, nivel experto.") are FIXED
by the format, recorded once — never write them into the script.

## House rules (all three types)

- JSON, UTF-8, `ensure_ascii=False`, indent 2. One file per video:
  `<topic_id>_<slug>.json`, slug = short ascii snake_case of the theme (e.g. `lv001_cocina.json`).
- Spanish: correct spelling WITH accents and ¿¡. Neutral Spanish understood in Spain
  and Latin America; when a word differs, prefer the most widely understood one, or
  give both "Ordenador / computadora" only if it fits the length limit.
- English: General American spelling and pronunciation.
- Audio tags: only in `intro` and `outro`, at the very start, ONE tag, from this list:
  excited, happy, curious, cheerful, warm, surprised, thoughtful, calm, serious.
  Written `[cheerful] ...`.
- `video_title`: Spanish, ≤ 70 characters, ends with exactly ONE emoji (single code point,
  no ZWJ sequences, no flags, no skin tones). Must contain the theme. Vary the wording
  across videos — do not reuse the same title pattern more than ~10 times per type.
- `video_description`: one Spanish sentence, ≤ 120 chars, ends with one emoji (same rules).
- `intro`: Spanish, 1–2 short sentences, ≤ 110 chars after the tag; says what the
  viewer must do. Vary it across videos.
- `outro`: Spanish, ≤ 90 chars after the tag, asks for a comment ("¿Hasta qué número
  llegaste?" style). Vary it.
- `verdict`: Spanish, spoken after item 10, ≤ 130 chars, states the three tiers by
  number 3 / 7 / 10, e.g. "Si llegaste a la tres, eres nivel básico. Hasta la siete,
  intermedio. Y si sabías las diez, eres experto." Vary the wording.
- `hashtags`: exactly 5, each starting with #, no spaces. First is the type tag below.
- Nothing in one video may repeat (no duplicate english, no duplicate spanish).
- Across ALL videos of a type, avoid reusing an English item. A few unavoidable repeats
  are tolerated, but aim for zero.
- `_meta`: {"category": <category>, "topic_id": <id>, "video_type": <type>,
  "model": "manual", "draft": true}

---------------------------------------------------------------------------

## Type 1 — `level_test` · "¿Qué nivel tienes?" (English → Spanish meaning)

Category `level_vocab`, ids `lv001`–`lv100`. Type hashtag `#NivelDeInglés`.

The English word or expression appears and is said once; the viewer says what it means;
after a pause the Spanish meaning is revealed and said.

```json
{
  "type": "level_test",
  "video_title": "¿Qué nivel de inglés tienes? 10 palabras de COCINA 🍳",
  "video_description": "De fácil a experto: ¿cuántas palabras de cocina conoces? 🍳",
  "title": "¿Qué nivel tienes?",
  "theme": "la cocina",
  "intro": "[cheerful] Diez palabras de cocina, de fácil a experto. Di qué significan antes que yo.",
  "items": [
    {"english": "fork", "spanish": "Tenedor", "cefr": "A1"},
    ...10 items...
  ],
  "verdict": "Si llegaste a la tres, tienes nivel básico. Hasta la siete, intermedio. Y si sabías las diez, eres experto.",
  "outro": "[excited] ¿Hasta qué número llegaste? Cuéntamelo en los comentarios.",
  "hashtags": ["#NivelDeInglés", "#VocabularioEnInglés", "#AprenderInglés", "#InglésOnline", "#TestDeInglés"],
  "_meta": {...}
}
```
- `english`: a word or a fixed expression/phrasal verb/idiom, ≤ 24 chars, lowercase
  unless it needs a capital. No article unless part of the expression.
- `spanish`: the meaning, Capitalised first letter, ≤ 28 chars. For an idiom give the
  natural Spanish equivalent or a short meaning ("Romper el hielo", "Ser muy fácil").
  Exactly the meaning in THIS sense; if a word has several, pick the one the theme implies.
- `cefr`: A1/A2/B1/B2/C1/C2. Non-decreasing through the list. Items 1–3 ∈ A1–A2,
  items 4–7 ∈ A2–B2 (at least two of them B1 or B2), items 8–10 ∈ B2–C2 (at least two C1/C2).
- Mix: most videos are single words; phrasal-verb and idiom themes are expressions.

## Type 2 — `say_it_level` · "Dilo en inglés" (Spanish → English)

Category `say_it`, ids `sy001`–`sy100`. Type hashtag `#DiloEnInglés`.

A Spanish sentence appears and is said; the viewer says it in English; after a pause the
English is revealed and said. The tiers here are about STRUCTURE: 1–3 short, direct
sentences; 4–7 need a real structure (past, present perfect, modals, would, going to,
phrasal verbs); 8–10 are TRAPS — sentences where the literal translation is wrong and a
Spanish speaker usually fails ("Tengo 30 años" → "I'm 30", "Me da igual" → "I don't mind",
"Llevo dos años aquí" → "I've been here for two years", "Se me olvidó" → "I forgot").

```json
{
  "type": "say_it_level",
  "video_title": "¿Sabes decir esto en inglés? En el RESTAURANTE 🍽️",
  "video_description": "...",
  "title": "Dilo en inglés",
  "theme": "en el restaurante",
  "intro": "[cheerful] Te digo la frase en español y tú la dices en inglés. Diez frases, de fácil a experto.",
  "items": [
    {"spanish": "Una mesa para dos, por favor.", "english": "A table for two, please.", "cefr": "A1"},
    ...
    {"spanish": "Me da igual dónde sentarnos.", "english": "I don't mind where we sit.", "cefr": "B2",
     "alt": "I don't care where we sit.", "tip": "«Me da igual» es I don't mind, no «it gives me equal»"}
  ],
  "verdict": "...", "outro": "...", "hashtags": [...], "_meta": {...}
}
```
- `spanish`: ≤ 42 chars, a natural sentence a person would really say in that situation,
  with final punctuation and ¿? / ¡! where needed.
- `english`: ≤ 42 chars, the most natural spoken English (contractions: I'm, don't,
  I've). It must be a correct translation of `spanish`, not a loose paraphrase.
- `alt` (optional): another correct, natural answer, ≤ 42 chars (e.g. British "bill" vs
  American "check"). Use when a common alternative exists, so viewers who said it feel right.
- `tip` (REQUIRED on items 8–10, optional elsewhere, usually absent on 1–3): Spanish,
  ≤ 60 chars, explains the trap in plain words. Shown on screen, not spoken.
- `cefr`: as in type 1 (1–3 A1–A2, 4–7 A2–B2, 8–10 B1–C1 allowed here because traps are
  hard by structure, not by vocabulary). Non-decreasing.

## Type 3 — `pronounce_level` · "¿Sabes pronunciar estas palabras?"

Category `pron_level`, ids `pl001`–`pl100`. Type hashtag `#PronunciaciónEnInglés`.

The English word appears, NOT said; the viewer says it out loud during a pause; then the
voice says it twice and the respelling + trap appear.

Difficulty here is about how hard it is FOR A SPANISH SPEAKER to say correctly:
1–3 words most people already say right or nearly right; 4–7 classic traps (silent letters,
vowel surprises, stress); 8–10 words even advanced learners (and some natives) get wrong.

```json
{
  "type": "pronounce_level",
  "video_title": "¿Sabes pronunciar estas 10 palabras de COMIDA? 🍔",
  "video_description": "...",
  "title": "¿Cómo se pronuncia?",
  "theme": "la comida",
  "intro": "[curious] Lee la palabra en voz alta antes de que yo la diga. Diez palabras, de fácil a experto.",
  "items": [
    {"english": "pizza", "respelling": "PIIT-sa", "ipa": "ˈpiːtsə", "trap": "La ZZ suena «ts»"},
    ...
    {"english": "Worcestershire", "respelling": "UUS-ter-sher", "ipa": "ˈwʊstɚʃɚ", "trap": "Se comen media palabra: 3 sílabas"}
  ],
  "verdict": "...", "outro": "...", "hashtags": [...], "_meta": {...}
}
```
- `english`: one word (a two-word compound only if very common), ≤ 18 chars.
- `ipa`: General American, primary stress mark ˈ before the stressed syllable, no slashes,
  no secondary stress marks, and no syllabic-consonant diacritics: write "button" as
  ˈbʌtən (with ə), so every syllable has a written vowel. Use ɚ for unstressed r-colored
  and ɝ for stressed ("bird" ˈbɝd), ɑ for "hot", ɔ only where GA really has it. Write
  near/square/cure vowels as ɪr / ɛr / ʊr ("beer" ˈbɪr), never ɪə/ɪɚ.
- `respelling`: how a Spanish reader should say it, syllables separated by "-", the
  STRESSED syllable in CAPITALS, the rest lowercase. Conventions (use them consistently):
  `a`=/ʌ/ /ə/ /ɑ/ as in cup, `e`=/ɛ/ /ə/, `ii`=/iː/ (long ee), `i`=/ɪ/, `uu`=/uː/, `u`=/ʊ/,
  `ei`=/eɪ/, `ai`=/aɪ/, `ou`=/oʊ/, `au`=/aʊ/, `oi`=/ɔɪ/, `o`=/ɔ/,
  `er`=/ɚ/ /ɝ/ (r-colored), `sh`=/ʃ/, `ch`=/tʃ/, `i`=/j/ before a vowel ("yes" → IES),
  `y`=/dʒ/ at the start of a syllable ("job" → YAB), `dch` at the end ("judge" → YADCH,
  "orange" → OR-endch), `zh`=/ʒ/, `j`=/h/, `th`=/θ/, `dh`=/ð/, `u` before a vowel for /w/ ("UO-ter"),
  `z`=/z/, `v`=/v/, `k`=/k/ (never c/qu), `g`=/g/ always hard. Stressed syllable in CAPS
  (accents are not used). Number of syllables in the respelling MUST equal the number of
  vowel sounds in the IPA. One-syllable words are all caps ("NAIF").
- `trap`: Spanish, ≤ 45 chars, the ONE thing that makes it hard ("La K no suena",
  "Acento en la primera: VE-", "Dos sílabas, no tres"). Required on every item.
- No `cefr` field in this type.
- Never pick words whose mispronunciation becomes a rude word joke (sheet/beach/focus/
  piece, etc.) — the brand stays clean.
