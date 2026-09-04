# Paso 3 — Prompt para Claude Code

El paso grande. Es donde "afabric" y el desfase se arreglan de verdad, donde el gate pasa a bloquear, y donde publicas el primer video.

**La tabla de deriva del Paso 2 es la especificación.** No hay que inventar umbrales: el propio corpus ya demuestra qué precisión es alcanzable.

---

## PROMPT — Paso 3: timing truth

````
You are in ~/Downloads/english-ai-videos. Steps 0, 1 and 2 are complete and
pushed (HEAD bccac51, 110 tests). The QA gate exists and runs in REPORT MODE.
Its baseline over 195 artifacts is committed at
tests/baselines/qa_baseline_2026-07-30.json.

That baseline is this step's specification. Do not invent thresholds — the
corpus already demonstrates what precision is achievable.

WHAT THE BASELINE SAYS IS WRONG

1. Quiz option boundaries are invented arithmetic.
   tts_elevenlabs.py:589-591: transition_duration = 1.5 (a guess at how long
   "Escucha las opciones." takes) then per_option = options_duration / 4.
   Measured on cool_20260416_084217: every NON-option boundary lands within
   0.12 s. Only option_a..option_d drift: +0.51, -0.70, -0.56, -0.50 s.
   User-visible effect: option cards B, C and D appear roughly half a second
   AFTER the voice has already spoken them.

2. Option letters are elided into their words. 38 of 42 quiz artifacts fail the
   >=250 ms letter-to-word assertion; several measure 0.000 s — the letter is
   not a separate speech chunk at all. Cause: tts_elevenlabs.py:562 builds
   f"Opción {letter}, {word}." and :565 joins all four plus the transition line
   into ONE utterance sent in a single TTS call.

3. Educational declared segment durations exceed actual speech.
   Starts are near-perfect (within 0.045 s). Every END overruns, monotonically,
   up to -1.29 s. Cause: each ElevenLabs segment file carries trailing silence
   after the speech, and the whole file duration is counted as segment duration.
   Effect: text holds on screen up to 1.3 s after the voice stopped.

4. 78 declared-silence violations across 26 of 67 countdown artifacts (39%):
   speech bleeding into the span declared as silent, up to 0.54 s at -0.9 dB —
   full speech level. The countdown numbers are drawn over spoken content.

SCOPE

  a. Split quiz options into real segments: letter -> >=250 ms silence -> word.
     One TTS call per part, concatenated, each clip measured with ffprobe the
     way add_audio already does. Delete transition_duration = 1.5 and
     per_option = /4 at tts_elevenlabs.py:589-591 and the three parallel sites.
  b. Stop counting trailing segment silence as segment duration. Derive segment
     end from measured speech end, not from file end.
  c. Fix the countdown silence violation (finding 4).
  d. Remove the group_words mutation that trims each group to
     next_start - 0.033 (animations/subtitle_processor.py:462-480).
  e. Port src/video/v2/timing_engine.py into the v1 path. It operates on
     data['_groups'], which v1 already produces. Freeze v2/ with a README saying
     what was extracted.

SCOPE DISCIPLINE — read this before you start

If this overruns, KEEP ONLY (a) and STOP. Splitting the quiz options resolves
"afabric" and the option drift on its own, and that alone justifies the step.
Tell me you are stopping there rather than half-landing five things.

DO NOT ATTEMPT: the word-level char-proportional estimation
(subtitle_processor.py:276-279). Per docs/step3-timing-spec.md it can only be
BOUNDED without alignment, not fixed. Bound it, record the bound, move on. ASR
is deferred.

DEFINITION OF DONE — internal controls, not invented numbers

Each target is "match the part of the same file that already works". Re-run the
gate over the full 195-artifact corpus and diff against the committed baseline.

  T1. Letter-to-word: 38/42 failing -> 0/42. Every option >= 250 ms.
  T2. Quiz option boundary drift must reach the same precision as the NON-option
      boundaries in the same file. Baseline: non-option within 0.12 s, options
      0.50-0.70 s. Target: options within 0.12 s.
  T3. Educational segment END drift must reach the same precision as the STARTS
      in the same file. Baseline: starts within 0.045 s, ends up to 1.29 s.
      Target: ends within 0.045 s.
  T4. Declared-silence violations: 78 -> 0.
  T5. No regression: nothing that passed in the baseline may fail after.

  Paste the before/after table for all five. T5 is the one that matters most —
  a fix that trades one failure class for another is not a fix.

THEN, AND ONLY THEN, FLIP BLOCKING

Set BLOCKING = True only after T1-T5 pass. Before flipping, confirm the gate
does not reject GOOD output: generate 3 fresh videos (one quiz, one educational,
one fill_blank), run them through the gate, and show they pass. If the gate
rejects freshly-fixed output, blocking is not ready and you say so.

Failed videos then go to output/rejected/ with a JSON report. One failure must
never abort a batch.

COST NOTE

(a) changes the number of TTS calls per quiz — from one combined options call to
one per part. Report the before/after per-video character count and cost. If it
increases materially, say so with the number; do not absorb it silently.

OUT OF SCOPE

- Layout, bounding boxes, safe area. That is a later step and needs the
  layout-box sidecar.
- ASR checks of any kind.
- The quiz answer-reveal render cost (7x step at t>=27 s). Recorded debt,
  deliberately untouched.
- src/video/v2/ beyond extracting timing_engine.
- The 27 type=None and 29 uncovered corpus artifacts. Those are historical
  output from old generator eras, not live defects. Do not chase them.

GIT

Same discipline: one commit per completed task, working state at every commit,
push after each. Keep _audit/ out of code commits.

HOW TO WORK

Do (a) alone first — the option split — then STOP and show me T1 and T2 before
touching anything else. It is the highest-value and highest-risk change in the
step, and the other four items are independent of it.
````

---

## Después del Paso 3, antes del Paso 4

**Publicas un video a mano.** Uno, en la cuenta real, sin outro y sin automatización, subido con el dedo.

Es el checkpoint que reinstauré en el roadmap v4 y es bloqueante. Es el primer momento en que el audio es correcto y el gate bloquea — o sea, el primer video defendible desde el 16 de abril. Si llegas al Paso 4 sin haberlo hecho, el plan falló y prefieres verlo ahí.

## Qué espero

T1 y T4 deberían caer limpios: son consecuencias directas de partir los segmentos. T2 y T3 son los que dirán si el diagnóstico era correcto — si las opciones no bajan a 0.12 s después del split, hay un segundo mecanismo que la tabla no capturó.

**T5 es el que de verdad importa.** Un arreglo que cambia una clase de fallo por otra no es un arreglo, y el corpus de 195 es lo único que puede demostrarlo.
