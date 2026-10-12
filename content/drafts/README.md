# content/drafts

Scripts for video types that **do not exist yet**. They live here, not in
`content/queue/`, because `queue_guard` validates against `script_schema`, and a
type the schema does not know would be BLOCKED.

When a type is built, its brief adopts the shape below (or changes it, and the
drafts are migrated in the same commit), the drafts move to
`content/queue/<type>/`, and the `"draft": true` key in `_meta` is dropped.

Every draft follows the house rules (`english-unlimited-guionista` skill):
only allowlisted audio tags, one emoji glyph from the vendored Noto font (checked
with `src/emoji_font.emoji_problem`), English spans complete, nothing invented.

## fix_the_error — Corrige el error (6 drafts)

```
intro, outro                      Spanish, may carry one tag
items[3]: wrong                   the sentence with the error, shown in red
          error                   the exact wrong chunk inside `wrong` (underlined)
          right                   the corrected sentence
          fix                     the chunk that replaces `error` (green)
          translation             Spanish meaning
          explanation             why, ≤ 1 sentence + example; one [excited]
```
Two items spoken, the third seeds another video (same rule as the quiz).
Topics: `common_mistakes`, `spanish_specific`.

## conjugation_map — Mapa de conjugación (6 drafts)

```
verb, verb_es, tense              "be", "ser o estar", "presente"
rows[7]                           {pronoun: I/You/He/She/It/We/They, form}
highlight                         forms painted in the accent colour (the irregular ones)
examples[2], negative, question   {en, es}
tip                               the rule in one sentence (Spanish)
intro, outro
```
New topic category `verb_maps` (vm001 be · vm002 have · vm003 do · vm004 go ·
vm005 can · vm006 was/were; continue with like, want, get, past simple of go).

## minimal_pairs — Pares mínimos (6 drafts)

```
pair[2]: word, phonetic, meaning, emoji
sound_tip                         how to make the difference with the mouth
test[4]                           indices 0/1: the voice says pair[i]; viewer picks A or B
sentence                          {en, es} using both words
intro, outro
```
Topics: `pronunciation` (pr019, pr020, pr036, pr038, pr046, pr052).

## expression_of_day — Expresión del día (6 drafts)

```
expression, literal, meaning, register (informal|neutral|formal)
examples[2] {en, es}, equivalent_es, tip, intro, outro
```
Topics: `idioms`, `everyday_expressions`.

## ladder — Escalera (4 drafts)

```
theme
steps[5] {en, es, added}          each step adds one chunk (`added`) to the last
challenge {es, en}                the viewer builds a new sentence from the Spanish
intro, outro
```
New topic category `ladders` (la001 rutina · la002 cafetería · la003 trabajo ·
la004 fin de semana).
