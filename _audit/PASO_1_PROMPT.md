# Paso 1 — Prompt para Claude Code

Un solo prompt. El Paso 0 dejó el terreno listo: un pipeline único, el corpus congelado en `tests/fixtures/`, y dos bugs de config documentados esperando aquí.

**Novedad respecto al plan original:** el Paso 0 encontró dos formas de que la config mienta en silencio (el `voice_id` placeholder y la clave `model` ignorada). Las meto en este paso porque son la misma clase de fallo que el contrato de datos — algo declarado que no se valida.

---

## PROMPT — Paso 1: data contract

````
You are working in ~/Downloads/english-ai-videos. Step 0 is complete and pushed:
both entry points now share src/pipeline.py, and tests/fixtures/ holds a frozen
corpus of 12 real script JSONs plus 5 known-bad cases.

PROBLEM CONTEXT

There is no schema anywhere in this repo. No jsonschema, no pydantic, no
dataclass, no TypedDict. The contract for script JSON lives in three
unsynchronised places:

  1. GPT prompt f-strings          src/script_generator.py:255-581
  2. A manual required-key dict    src/script_generator.py:620-627
  3. dict.get(key, default) at every read site in src/video/

Validation exists but stops nothing. Missing keys go into
script["_validation_errors"] and the function returns early at :634-636;
generate_script only LOGS them at :833-834 and returns the script anyway.

And every renderer default is a plausible wrong answer:

  src/video/quiz.py:582          correct = data.get('correct', 'A')
  src/video/fill_blank.py:313-315 falls back to "I ___ to school" with
                                  options ['go','went','gone','going']
  src/video/pronunciation.py:42   falls back to the literal word "word"

A script that loses its `correct` key renders option A with a green card, a glow,
sparkles and "Respuesta: A". There is no "unknown" state anywhere in the render
path, so every data failure ships as a polished, confidently incorrect lesson.
At 2 videos/day unattended that is the failure that costs an audience, and no
audio or visual check catches it because the video is technically perfect.

TASKS

1. SCHEMA — derive it, do not hand-write it from the prompts.

   Source of truth for the real shape: tests/fixtures/ (12 scripts, all six
   video types) plus the required_fields dict at script_generator.py:620-627.

   Then DIFF your derived schema against what the GPT prompts actually demand
   (script_generator.py:255-581). The mismatches are bugs, not noise. One known
   example: the true_false prompt demands video_title at :391-392 and real
   true_false output does not carry it. Report every mismatch you find before
   deciding which side is correct — some will be prompt bugs, some schema bugs.

   Known shape hazards to encode explicitly, all verified:
     - `options` is a DICT for quiz (quiz.py:581) and a LIST for fill_blank
       (fill_blank.py:314)
     - `correct` is a letter (quiz), a bool (true_false), a word (fill_blank)
     - `translation` (str) for pronunciation/fill_blank vs `translations` (dict)
       everywhere else
     - `video_title`/`video_description` only appear in files dated 2026-04-14
       and later
     - `questions[3]` / `statements[3]` / `sentences[3]` are generated and read
       by NOTHING in the TTS or render path. Encode them as optional and add a
       comment saying they are dead payload — do not delete them in this step.

   Use pydantic. One model per video type, one shared base.

2. VALIDATE AT THREE POINTS
   - script_generator output
   - pipeline TTS input
   - renderer input

   Failures must be LOUD. Raise, with a message naming the video type, the
   missing/invalid field, and the file path.

3. REMOVE EVERY PLAUSIBLE DEFAULT in src/video/. Grep for `.get(` with a second
   argument across src/video/*.py and triage each one:
     - genuinely optional (a badge, a decoration) -> keep the default
     - load-bearing for correctness (correct, question, options, word,
       sentence) -> delete the default, let validation have caught it upstream

   Report the full triage list. I want to see what you classified as optional.

4. FIX THE QUOTE MANGLER — src/script_generator.py:642-643.
   Line 642 is `.replace("'", "'").replace("'", "'")` — ASCII to ASCII, a no-op
   twice over. Line 643 contains `"""`, which Python parses as a triple-quoted
   string opener, so instead of normalising typographic quotes it replaces the
   literal substring `, '").replace(` with `"`. Confirm this with ast.unparse
   before touching it.

   Everything downstream runs on un-normalised text: the balance count at
   :646-665 and the english_phrases extraction at :669. This is the origin of
   the "Unbalanced single quotes (51)" warning shipped inside
   tests/fixtures/.../cool_20260416_084217.json.

5. FIX THE english_phrases SCRAPER — src/script_generator.py:668-680.
   It appends every '...' span from full_script into english_phrases, guarded
   only by `if any(len(w) > 1 for w in phrase_words)`. Since the scripts quote
   Spanish material too, real files list Spanish as English: "me gusta tu
   outfit", "qué increíble", and "i can" / "m swamped with deadlines" (the
   apostrophe in "I can't" split the phrase).

6. UNIFY THE SPANISH STOPLISTS — carefully.
   Five divergent copies: tts_common.py:60-83, tts_segmenter.py:40-56,
   tts_elevenlabs.py:248-262, video/__init__.py:177-207,
   animations/subtitle_processor.py:201-247.

   IMPORTANT: extract to ONE module, but do NOT silently merge them. They differ,
   so unifying necessarily changes classification behaviour, and there is no QA
   gate yet to catch a regression. Instead:
     - document the differences between the five
     - pick one explicitly and say why
     - add a test that PINS current behaviour on the fixture corpus, so the
       behaviour change is visible in the test diff rather than in a video
   If the behaviour change looks non-trivial, stop and show me the delta before
   committing it.

7. CONFIG VALIDATION — two silent-lie bugs found during Step 0, both recorded
   and both belonging here:

   a. config.yaml:106 has voice_id: "KIDS_VOICE_ID_PENDIENTE". It resolves
      through profiles.py:83-86 and reaches the ElevenLabs API verbatim, failing
      at call time instead of at config load. Validate voice_id format at load.
      Note: src/config/secrets.py:126-154 already has per-key format regexes and
      a name allowlist, and is imported by nothing. Read it before writing new
      code — the better implementation may already exist, orphaned.

   b. The kids profile declares model: eleven_v3 but the resolved model_id is
      eleven_turbo_v2_5. The behaviour is correct (v3 does not support
      language_code, which the bilingual path requires) but the config lies
      silently. Either honour the key or warn loudly that it is being overridden
      and why. Do not fail the run for this one.

OUT OF SCOPE

- Do NOT fix the quiz option timestamps or audio segmentation
  (transition_duration = 1.5, per_option = /4 at tts_elevenlabs.py:589-591).
  That is Step 3 and it needs Step 2's drift table to be provable.
- Do NOT build the QA gate. That is Step 2.
- Do NOT touch src/video/v2/.
- Do NOT delete src/quality_reviewer.py or src/video_analyzer.py yet.
- Do NOT delete the dead questions[]/statements[]/sentences[] payload.
- Do NOT change TTS output format or segment_times semantics.

DEFINITION OF DONE — proof, not claims

A) Run the schema over all 12 fixtures in tests/fixtures/. Paste the result
   table: type, pass/fail, and for failures the exact field. I expect some
   fixtures to fail — they are real historical output and the corpus includes
   known-bad cases. Failing is information, not a problem.

B) Paste the prompt-vs-schema mismatch list from task 1.

C) Take a valid quiz fixture, delete its `correct` key, run it through the
   renderer. Paste the error. It must abort with a readable message naming the
   field — not render option A in green.

D) Re-run validation over the corpus after tasks 4 and 5 and show the
   _validation_warnings count before/after.

E) Paste the `.get(` triage list from task 3.

F) Paste the stoplist delta from task 6 before committing it.

GIT

Same discipline as Step 0: one commit per completed task, working state at every
commit, push after each. Keep _audit/ out of code commits.

HOW TO WORK

Do task 1 and STOP. Show me the schema and the mismatch list from proof B before
touching any renderer code. The schema is the decision everything else follows
from and I want to see it before it has consumers.
````

---

## Por qué el corte está en la tarea 1

El schema es la decisión de la que cuelga todo lo demás. Una vez tiene consumidores en tres puntos de validación, cambiarlo es caro. Verlo antes cuesta un round-trip y ahorra un rehacer.

Y la lista de discrepancias prompt-vs-schema es probablemente el hallazgo más interesante del paso: cada una es un sitio donde le pides a GPT algo que tu código no usa, o usas algo que nunca pediste.

## Lo que espero que salga mal

Que algunos fixtures fallen el schema. Es lo correcto — son salida histórica real de cuatro épocas distintas del generador, y el corpus incluye casos malos a propósito. **Si los 12 pasan a la primera, el schema es demasiado laxo** y hay que endurecerlo, no celebrarlo.
