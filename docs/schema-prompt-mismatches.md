# Schema vs GPT prompts — the full diff

Recorded 2026-07-29, while deriving `src/script_schema.py`.

The schema was derived from `tests/fixtures/` (12 real historical scripts) plus
the `required_fields` dict at `src/script_generator.py:620-627`. This file
diffs that against what the prompt templates at `src/script_generator.py:255-581`
actually demand, and rules on each disagreement.

---

## Read this first: the corpus cannot adjudicate anything after 2026-03-17

Two prompt changes reshaped the contract:

| commit | date | change |
|---|---|---|
| `5c6c2f9` | 2026-03-17 | added the 3-item `questions` / `statements` / `sentences` arrays |
| `0a7535f` | 2026-03-24 | added `video_title` + `video_description` to **all six** templates |

Every fixture in the corpus except three is older than both:

| fixture | `_meta.generated_at` |
|---|---|
| true_false/actually.json | 2026-01-13 |
| educational/fabric_20260116_192025.json | 2026-01-16 |
| quiz/fabric_20260116_201133.json | 2026-01-16 |
| quiz/accepting_invitations.json | 2026-02-05 |
| pronunciation/asking_for_help_20260207_151200.json | 2026-02-07 |
| fill_blank/desert_vs_dessert_20260210_175642.json | 2026-02-10 |
| fill_blank/heads_up_20260210_181915.json | 2026-02-10 |
| vocabulary/pull_vs_pool_20260210_183300.json | 2026-02-10 |
| educational/actually.json | *(none — no `_meta.generated_at` at all)* |
| **quiz/cool_20260416_084217.json** | **2026-04-16** |
| **quiz/lay_vs_lie_20260416_082045.json** | **2026-04-16** |
| **quiz/scared_stiff_20260416_083126.json** | **2026-04-16** |

**Consequence:** for anything the prompts gained after 2026-03-17, the corpus
contains evidence for `quiz` and for no other type. Absence of a post-2026-03
field in a January fixture is age, not refusal.

### Resolved 2026-07-29 by a fresh generation

One script per type was generated from the prompts at HEAD and stored as a
separate tier, `tests/fixtures/scripts/current/`
(`tests/regenerate_current_fixtures.py`, ~$0.003, script generation only).
This closed every UNDECIDABLE below, and answered the larger question the
historical corpus could not: **all 6/6 current scripts validate clean against
the schema, with zero lint warnings.** The schema derived from history accepts
present-tense output.

It also surfaced M11, a live bug that the historical corpus had no way to
show.

---

## M1 — `video_title` / `video_description`: NOT a true_false prompt bug

**Claim under test:** "the true_false prompt demands `video_title` at
`:391-392` and real true_false output does not carry it."

**Finding: the premise holds, the diagnosis does not.** `video_title` is
demanded by all six templates, not just true_false — it was added to all of
them in one commit (`0a7535f`, 2026-03-24). The only true_false fixture is
dated 2026-01-13, **ten weeks before that commit existed**. It does not carry
`video_title` because the prompt that produced it never asked for one.

The three fixtures that postdate the commit are all quizzes, and all three
carry both keys. So the evidence we have says GPT honours the field; we simply
have no post-March sample of the other five types.

**Ruling: schema keeps both OPTIONAL, and this is a deliberate compromise.**
`validate_and_clean_script:703-714` synthesises a fallback for both keys
whenever they are missing, so any script that passes through the generator has
them regardless. Making them required in the model would reject the nine
historical fixtures to enforce something the generator already guarantees.
Only `metadata_generator.py:75-76` reads them, and it reads with a `""`
default.

**RESOLVED 2026-07-29.** All six freshly generated scripts carry a non-empty
`video_title` **and** `video_description`. There is no prompt bug and no
type-specific gap; the historical absence was purely age.

The schema keeps both Optional so the historical tier still validates, and
`tests/test_current_fixtures.py::test_publishing_metadata_is_emitted_by_every_type`
pins the present-tense contract instead. That split is the point of having
two tiers: the model tolerates history, the test enforces today.

---

## M2 — the dead arrays are dead in the *reader*, not the writer

`questions[3]` (`:321-340`), `statements[3]` (`:396-412`), `sentences[3]`
(`:465-490`) are demanded by the prompts, and `:346`, `:418`, `:495` add an
explicit instruction that the root-level fields must duplicate element `[0]`.

**Grep across `src/` and `main.py` finds zero readers.** Not in the TTS path,
not in any renderer. Only the root-level `question` / `options` / `correct` /
`explanation` are ever rendered, so elements `[1]` and `[2]` are generated,
billed, and discarded. A "3-question quiz" renders one question.

Historical corpus: `questions` present in all 3 post-2026-03-17 quizzes;
`statements` and `sentences` present in zero fixtures, but every true_false
and fill_blank fixture predates the prompt that asks for them.

**RESOLVED 2026-07-29.** The fresh generation emits all three arrays, 3 items
each, on all three types. GPT complies fully. So the payload is dead **in the
reader, not the writer**: elements `[1]` and `[2]` are generated, billed, and
discarded on every quiz, true_false and fill_blank the pipeline produces. A
"3-question quiz" renders exactly one question.

That reframes the deletion decision. It is not "strip an unused field" — it
is "either wire up questions 2 and 3, or stop paying GPT to write them."
Still out of scope for this step; recorded so the choice is made on the facts.

**Ruling: encoded OPTIONAL with a `DEAD PAYLOAD` comment at each of the three
sites, and not deleted.** Deleting them is a content decision (does the
product want 3-question videos or not?), not a schema decision. The pinning
test asserts they survive a round-trip.

---

## M3 — every prompt contradicts its own hashtag rule

Each template states a rule — "los hashtags deben ser 5-7" (`:242`, `:302`,
`:386`, `:449`, `:522`, `:563`) — and then hands GPT a worked example
containing 3 or 4:

| type | example line | items supplied |
|---|---|---|
| educational | `:265` | 3–5 (`_category_hashtags` output) |
| quiz | `:343` | 4 |
| true_false | `:415` | 3 |
| fill_blank | `:492` | 3 (hardcoded literal) |
| pronunciation | `:535` | 3 (hardcoded literal) |
| vocabulary | `:580` | 3 |

Historically GPT followed the example over the rule: **all 12 historical
fixtures carry 3–5 hashtags, none carries 5–7.**

**RESOLVED 2026-07-29 — current output complies.** All six fresh scripts carry
exactly 5 hashtags. Today's model follows the rule and ignores the
contradictory example, so this is a latent prompt defect rather than a live
one. The contradiction is still worth removing, because nothing guarantees the
next model resolves it the same way.

**Ruling: lint, not schema.** Hashtag count is decoration; it cannot make a
lesson wrong. `ScriptBase.lint()` reports it. The fix belongs in the prompts.

---

## M4 — `_category_hashtags()[:1]` guarantees a duplicate on 3 of 6 types

`_category_hashtags` (`:197-219`) always returns `["#AprendeIngles",
"#InglesConTiktok", ...]` — `#AprendeIngles` is **first for every category**.
Three templates then build their list as a literal that already contains
`#AprendeIngles` plus `_category_hashtags(category)[:1]`:

- `:274` quiz — `["#QuizIngles", "#AprendeIngles", "#TestTuIngles"] + [...][:1]`
- `:415` true_false — `["#VerdaderoOFalso", "#AprendeIngles"] + [...][:1]`
- `:544` vocabulary — `["#Vocabulario", "#AprendeIngles"] + [...][:1]`

The slice can only ever yield `#AprendeIngles`, so the duplicate is
unconditional. `quiz/accepting_invitations.json` shows it verbatim:
`["#QuizIngles", "#AprendeIngles", "#TestTuIngles", "#AprendeIngles"]` — a
4-item list carrying 3 distinct tags.

**Latent as of 2026-07-29:** none of the six fresh scripts contains a
duplicate — GPT silently dropped the repeat rather than copying the example.
The generator bug is still there; only the model's tolerance is hiding it.

**Ruling: lint (`hashtags contains duplicates`).** The real fix is `[:2]` or a
dedupe in `_category_hashtags`, and it belongs in a prompt commit, not here.

---

## M5 — `educational` has two incompatible shapes and the prompt only knows one

The current prompt (`:255-266`) demands `hook` + `full_script`. But
`educational/fabric_20260116_192025.json` has **neither**: it carries
`segments: [{id, text}]` instead, and `video/__init__.py:175-180` still has a
live fallback that estimates word timings from `segments` when `words` is
empty.

No commit in `script_generator.py` history ever emitted `"segments"` in a
prompt — so this shape came from a generator that no longer exists, and the
renderer fallback for it is now unreachable from the generator.

**Ruling: `full_script` and `hook` are REQUIRED; this fixture fails, by
design.** It is already recorded as a known-bad case in
`tests/fixtures/known_bad/manifest.json` with the assertion "schema validation
must reject an educational script with no full_script". `segments` stays
declared but unshaped on `ScriptBase` — it also collides with
`pipeline.TTS_OWNED_KEYS`, which claims the same key for timing data. That
collision is unresolved and should not be tightened blind.

---

## M6 — `type` is demanded by all six prompts and one fixture has none

`educational/actually.json` has no `type` key, no `_meta.video_type`, and no
`_meta.generated_at`. It renders today only because `video/__init__.py:100`
and `pipeline.py:143` both do `data.get('type', 'educational')` — it happens
to *be* educational, so the wrong-by-default guess is right by luck.

**Ruling: `type` is REQUIRED, with no per-subclass default.** The first draft
of the schema gave each subclass `type: Literal["quiz"] = "quiz"`, which made
the field optional and reproduced the exact bug. Removing the defaults is why
this fixture now fails. A quiz that loses `type` currently renders through the
educational renderer in silence; that must stop.

---

## M7 — fields the prompt demands, `required_fields` does not, and nothing reads

| field | prompt demands | `required_fields:620-627` | renderer reads | ruling |
|---|---|---|---|---|
| `fill_blank.explanation` | yes `:463` | no | no | OPTIONAL |
| `fill_blank.blank_position` | yes `:460` | no | no | OPTIONAL + lint if `!= correct` |
| `pronunciation.common_mistake` | yes `:531` | no | yes, `''` default | OPTIONAL (decoration) |
| `pronunciation.tip` | yes `:532` | no | yes, `''` default | OPTIONAL (decoration) |
| `educational.tip` | yes `:263` | no | no | OPTIONAL |
| `educational.cta` | yes `:264` | no | no | OPTIONAL |
| `vocabulary.difficulty` | yes `:571` | no | yes, `''` default | OPTIONAL + lint on value set |

`blank_position` is redundant: it equals `correct` in both fill_blank
fixtures. It is a candidate for deletion in a later step, not this one.

---

## M8 — fields the renderer reads that NO prompt ever emits

Found while triaging read sites. These are dead reads, the mirror image of M2:

- `quiz.py:584` — `data.get('difficulty', '')`. No quiz prompt emits
  `difficulty`; only the vocabulary prompt does. Always `''`.
- `quiz.py:585` — `data.get('question_number', '')`. Emitted by no prompt at
  all, and by no code. Always `''`.

**Ruling: not in the schema** (a key nothing writes has no contract). Recorded
here so the task-3 `.get(` triage classifies them as dead rather than
optional.

---

## M9 — prompt rules with no enforcement anywhere

Stated as ABSOLUTE in the prompts, checked by nothing:

- quiz rule 1 (`:290-292`): the 4 options must be distinct. → **lint**
- quiz `:346` / true_false `:418` / fill_blank `:495`: root-level fields must
  equal element `[0]` of the array. → **lint** (quiz only; the other two have
  no post-2026-03 sample)
- vocabulary rule 2 (`:557`): 6–10 pairs, while the worked example at `:572-576`
  shows 3. Another M3-shaped self-contradiction. → **lint**; hard floor is 2
- educational rule 1 (`:232`): English words must be inside single quotes.
  This is the rule the quote mangler at `:642-643` was supposed to protect and
  does not — **task 4**.

---

## M11 — `correct: false` is read as "missing", and skips the whole cleaner

Found by the fresh generation, not by the historical corpus — which is the
best argument for having generated it.

`tests/fixtures/scripts/current/true_false.json` carries
`"correct": false` (a real JSON boolean, first statement is FALSE) and *also*
carries `"_validation_errors": ["Missing required field: correct"]`.

The required-field check at `script_generator.py:630-632` is:

```python
for field in required_fields.get(video_type, ["full_script"]):
    if field not in script or not script[field]:
        errors.append(f"Missing required field: {field}")
```

`not False` is `True`. A legitimate `correct: false` is indistinguishable
from a missing key.

**The consequence is not a spurious log line.** `validate_and_clean_script`
returns early at `:634-636` the moment `errors` is non-empty, so everything
below that point is skipped for the affected script:

- quote normalisation (`:640-643`)
- the unbalanced-quote repair (`:646-665`)
- the `english_phrases` scrape (`:667-680`)
- whitespace / punctuation cleanup for TTS (`:682-687`)
- **the Spanish-countdown check and auto-fix (`:689-699`)** — so a true_false
  script that counts down in English ships that way
- `script["full_script"] = full_script.strip()` (`:701`)
- the `video_title` / `video_description` fallbacks (`:703-714`)
- hashtag normalisation (`:716-725`)

This fires on **any true_false video whose first statement is false** —
roughly half of them, since prompt rule 2 (`:380`) explicitly demands a mix of
true and false. Those videos have silently bypassed the entire cleaning stage
for as long as `correct` has been in `required_fields`.

`0` of the historical fixtures show it: the only true_false fixture is from
2026-01-13 and has no `_validation_errors` key at all, so the check either
postdates it or `required_fields` did. The bug is live at HEAD and was
reproduced on the first fresh generation.

**Ruling: fixed by task 2.** A presence check must test presence
(`field not in script`), not truthiness — and the pydantic model already does
exactly that, since `StrictBool` accepts `False` as a valid value. This is a
concrete example of the class of bug the schema replaces.

---

## M10 — confirmed, not a mismatch

Recorded so they are not re-litigated:

- `translation` (str) on fill_blank + pronunciation vs `translations` (dict)
  everywhere else. The prompts get this **right**: `:464` and `:534` ask for
  `translation`, the other four ask for `translations`. It matches all 12
  fixtures and both read paths (`video/karaoke.py:76` dict,
  `video/fill_blank.py:316` str). Encoded as two separate mixins.
- `options` is a dict on quiz (`:313-318`, read at `video/quiz.py:581`) and a
  list on fill_blank (`:461`, read at `video/fill_blank.py:314`). Prompts and
  renderers agree; only the shared key name is a hazard.
- `correct` is a letter / a bool / a word across the three types. Prompts and
  renderers agree. Encoded as `Literal["A"..."D"]`, `StrictBool`, and a
  membership check against `options` respectively. `StrictBool` is deliberate:
  the string `"false"` is truthy in Python, so lax coercion would render a
  FALSE statement as TRUE.
- `english_phrases` is demanded only by educational (`:261`) and vocabulary
  (`:579`), required by `required_fields` only for educational, and present in
  exactly those fixtures. Consistent.
