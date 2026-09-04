# Paso 2 — Prompt para Claude Code

El QA gate, tier 1, **en modo reporte**. No bloquea nada todavía.

**Recordatorio de por qué no bloquea:** si lo pones a bloquear hoy, rechaza el 100% de los quizzes — con razón, porque los límites de las opciones son aritmética inventada (`transition_duration = 1.5`, `per_option = /4`). Un detector que dispara con todo transmite cero información, que es exactamente la patología del `video_analyzer.py` que vamos a borrar. El gate mide ahora, el Paso 3 arregla, y entonces bloquea.

Lo que produce este paso es la **tabla de deriva**: declarado contra medido, segmento a segmento. Esa tabla es el diagnóstico, la especificación del Paso 3, y la prueba de que el Paso 3 funcionó.

---

## PROMPT — Paso 2: QA gate tier 1, report mode

````
You are in ~/Downloads/english-ai-videos. Steps 0 and 1 are complete and pushed
(HEAD 43d8d04). The pipeline is unified behind src/pipeline.py, script JSON is
validated by src/script_schema.py, and tests/fixtures/ holds a frozen corpus
including 5 known-bad cases. 102 tests pass.

GOAL

Build a QA gate that runs on RENDERED ARTIFACTS — the waveform and the audio
files — never on the JSON the generator produced about itself. That distinction
is the entire point: the repo already contains two orphaned analyzers
(src/quality_reviewer.py 840 lines, src/video_analyzer.py 1838 lines) that
audited the generator's own self-report and therefore caught nothing in months
of real failures.

THIS STEP RUNS IN REPORT MODE ONLY. It writes to output/qa/, it moves no files,
it never changes an exit code. Blocking is switched on at the end of Step 3, by
flipping one flag.

Reason: quiz option boundaries are currently invented arithmetic
(transition_duration = 1.5 and per_option = options_duration / 4 at
tts_elevenlabs.py:589-591). A blocking gate would reject essentially every quiz
— correctly, but uselessly. A detector that fires on every input carries zero
information. Measure first, fix in Step 3, then block.

NO ASR IN THIS STEP. Everything is ffmpeg + ffprobe + arithmetic. Local, free,
deterministic.

CHECKS

1. DRIFT TABLE — the centrepiece.
   For quiz, true_false, fill_blank, vocabulary: for each declared entry in
   segment_times, compare the declared start/end against boundaries measured on
   the waveform via ffmpeg silencedetect. Emit declared, measured, delta.

2. WORD-TIMELINE CHECK — educational and pronunciation.
   These types do NOT emit segment_times; they carry a word timeline instead
   (verified in Step 0: pronunciation 0/14, and the bilingual path emits none
   for educational). A gate built only on segment_times would pass these two
   types by checking nothing at all. They need their own assertion: compare the
   word timeline against measured speech regions.
   Do not skip this. It is the known gap this step exists to close.

3. LETTER-TO-WORD SILENCE — quiz options.
   Assert >= 250 ms of silence between an option letter and its word. This fails
   by construction today: tts_elevenlabs.py:562 builds f"Opción {letter},
   {word}." and :565 joins all four options plus the transition line into ONE
   utterance sent in a single TTS call. Letter and word are separated by a
   comma inside one utterance.
   tests/fixtures/ already carries this as an input-string fixture with the
   assertion attached. The gate must reproduce that verdict from audio.

4. SEGMENT COUNT — detected speech regions vs declared speech segments.

5. CLIPPING AND DEAD AIR — volumedetect max_volume > -1.0 dB; dead air beyond a
   threshold you pick and justify.

IMPLEMENTATION TRAPS — read these before writing the detector. Each one will
cost you a day if you meet it by surprise.

  a. The countdown is 7 seconds of TRUE DIGITAL SILENCE with THREE declared
     segments on top of it (anullsrc, tts_elevenlabs.py:622-633). A naive
     "detected speech regions == declared segments" count will never reconcile.
     Assert against the DECLARED SILENCE MAP, not a raw region count.

  b. Inter-segment silence is NOT digital silence. The ElevenLabs path
     re-encodes through LAME (-q:a 2, tts_elevenlabs.py:688-692), so there is a
     noise floor. With a default threshold you detect nothing. Run volumedetect
     on a known-good file to find the actual floor and calibrate from there —
     typically -40 to -50 dB. DO NOT GUESS THIS NUMBER.

  c. silencedetect with d=0.25 cannot distinguish "exactly 250 ms" from "not
     detected". Use d ~= 0.10 and apply the 250 ms threshold in your own code,
     not in ffmpeg.

  d. Calibrate on ElevenLabs output, not OpenAI. The OpenAI path concatenates
     with -c:a copy (tts_openai.py:890-895), mixing unnormalised sample rates,
     so it carries drift of its own that is not the gate's fault.

  e. NEW, from Step 1: quiz runs on eleven_v3 and educational runs on
     eleven_turbo_v2_5 — two different models on the same provider. Calibrate
     the noise floor against BOTH, not against "ElevenLabs". Report the two
     floors separately; if they differ materially, the threshold has to be
     per-model.

OUTPUT

  output/qa/<name>.json  — per-artifact report carrying the drift table
  a console summary
  No file moves. No non-zero exit. output/rejected/ stays untouched this step.

FIRST ACTION, BEFORE ANY TUNING

Run the gate across the existing corpus and save the result as the BASELINE:
  output/scripts/  172 script JSONs
  output/audio/    202 paired TTS JSONs
Everything measured from here on is measured against that baseline. This is what
turns "it should be better now" into a number that moved.

ACCEPTANCE CRITERION FOR THE GATE ITSELF

It must FLAG the cases in tests/fixtures/known_bad/. If it passes them, the gate
is broken — and you already know exactly what that failure mode looks like.
Report the verdict on each known-bad case explicitly.

OUT OF SCOPE

- Do NOT fix the timing. Not transition_duration, not per_option, not the
  pre/post-concat reconciliation. That is Step 3, and the drift table you are
  building is its specification. Fixing now destroys the before/after.
- Do NOT add ASR checks (WER, per-segment language). Deferred deliberately.
  When they land, use LOCAL whisper — openai-whisper is already in
  requirements.txt and imported nowhere, while the paid whisper-1 API is what
  actually runs today.
- Do NOT add visual checks (bounding-box overlap, safe area). Those need the
  layout-box sidecar from the layout work, which has not happened. Adding them
  now means OCR, which is the wrong tool.
- Do NOT make the gate blocking.
- Do NOT touch src/video/v2/.

LAST TASK, ONLY AFTER THE GATE WORKS

Read src/quality_reviewer.py and src/video_analyzer.py for their check lists —
there are ideas in there worth stealing — then DELETE BOTH. 2,678 lines, both
orphaned (zero callers repo-wide), both auditing the generator's self-report.
One of them, analyze_layout_balance at video_analyzer.py:258-284, uses a metric
that is ANTI-correlated with the bug it should detect: two overlapping text
blocks produce a more centred mass than two separated ones, and
calculate_quality_score:1383-1384 awards +15 for being centred.
Do not build on them. Read, harvest, delete.

DEFINITION OF DONE

A) The baseline run over all 202 audio artifacts. Paste the summary and the
   drift table for one quiz and one educational.
B) The two calibrated noise floors (v3 and turbo_v2_5) with the volumedetect
   output you derived them from.
C) The verdict on each tests/fixtures/known_bad/ case.
D) The letter-to-word measurement on a real quiz — the number that Step 3 has
   to move above 250 ms.
E) Confirmation that educational and pronunciation are actually being checked,
   with the assertion used. Not skipped, not vacuously passed.

GIT

Same discipline: one commit per completed task, working state at every commit,
push after each. Keep _audit/ out of code commits.

HOW TO WORK

Build check 1 (the drift table) and the calibration first, then STOP and show me
the baseline output before writing checks 2-5. The calibration numbers determine
everything downstream and I want to see them before they have consumers.
````

---

## Dónde está el corte

La calibración y la tabla de deriva primero, luego para. Los umbrales de ruido determinan todo lo que viene después — si están mal, los cuatro checks restantes miden ruido.

## Qué espero ver

Deriva grande en las opciones de quiz (es aritmética inventada, tiene que salir) y deriva acumulativa creciente en educational (el timeline se construye pre-concat y se reproduce post-concat). Si la tabla sale limpia, **el detector está roto**, no el pipeline.
