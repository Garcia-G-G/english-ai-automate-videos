# Paso 0 — Prompts para Claude Code

Dos prompts, en este orden. **0A** es refactor mecánico y de bajo riesgo. **0B** es investigación y termina con una causa nombrada.

Los prompts van en inglés; las notas de alrededor son para ti. Cópialos tal cual — están escritos para alguien sin el contexto de esta conversación.

---

## Antes de empezar

```bash
cd ~/Downloads/english-ai-videos
git status                    # confirma que estás limpio
git checkout -b paso-0-unificar-pipelines
```

Si `git status` muestra cambios sin commitear, resuélvelo antes. Todo lo de abajo asume una rama limpia.

---

## Dos divergencias que encontré al preparar esto

No estaban en `AUDIT.md` y hay que decidirlas en 0A. Te las señalo porque son decisiones tuyas, no de Claude Code:

**1. El destino del video es distinto según la entrada.** `main.py` lo escribe en `output/video/<tipo>/`; `admin.py` lo escribe en `output/pending/<tipo>/` (`admin.py:238-241`), que es lo que alimenta la página de Review. **Recomiendo quedarse con `pending/`** — es el flujo que ya usas y donde el QA gate del paso 2 va a inyectarse. El prompt asume eso.

**2. `admin.py` nunca pasa el background.** `main.py:184-185` pasa `-b <background>` resuelto desde `config.yaml`; `admin.py:243-249` no lo pasa. Así que los videos del dashboard resuelven el fondo por otro camino. **Recomiendo unificar hacia el comportamiento de `main.py`.** El prompt asume eso.

Si prefieres lo contrario en cualquiera de las dos, cambia esa línea del prompt antes de pegarlo.

---

## PROMPT 0A — Unify the two pipelines

````
You are working in ~/Downloads/english-ai-videos, a generator of short vertical
videos (1080x1920) that teach English to Spanish speakers. Python, PIL -> ffmpeg
pipes, ElevenLabs and OpenAI for TTS, OpenAI for script generation.

PROBLEM CONTEXT

The repo has TWO independent production pipelines that produce DIFFERENT audio
from identical input:

- main.py (CLI) uses the provider factory in-process: main.py:119-143 ->
  tts_providers.get_tts_provider(name) -> provider.generate_from_script().
  For educational/pronunciation that routes to
  tts_bilingual.generate_bilingual_narration, which assigns a per-segment
  language_code (native accent for Spanish, English accent for the English terms).

- src/admin.py (Streamlit dashboard, the UI used daily) IGNORES that layer and
  spawns a subprocess into the TTS module's __main__: admin.py:198-208. That lands
  in tts_elevenlabs.py:1370-1501, which re-implements the type dispatch at
  :1392-1410 and, for educational, uses the legacy SINGLE-call path with NO
  language_code at all.

Verified consequences:
- The dashboard produces wrong accents where the CLI does not.
- The dashboard costs 2x for educational (eleven_v3 + paid Whisper, versus
  eleven_turbo_v2_5 with alignment included).
- admin.py never imports profiles -> the "kids" profile in config.yaml is inert
  from the dashboard.
- admin.py never imports cost_tracker, and TTS runs as a subprocess, so the
  in-process tracker dies unsaved. Every video generated from the dashboard is
  invisible to cost accounting.
- admin.py has no logging.basicConfig, so logger.error(...) at :283 goes nowhere
  visible.

GOAL

One shared pipeline, imported by both entry points. After this change, the same
script must produce identical audio regardless of which entry point is used.

TASKS, IN THIS ORDER

1. Create src/pipeline.py and move the shared logic there:

   - generate_tts(script_data, audio_path, script_path=None) -> (Path, Path)
     Extracted from main.py:106-171 (run_tts). Changes while extracting:
       * Drop the legacy `text` and `use_openai` parameters. The real path always
         passes script_data. If script_data is None that is an error, not an
         alternative mode.
       * KEEP the Edge TTS fallback from main.py:148-153, but turn it into an
         explicit parameter `allow_edge_fallback: bool = False`, DISABLED by
         default. That fallback silently changes voice, language handling and
         output schema; make it opt-in.
       * The merge of script_data into the TTS JSON (main.py:157-170) moves into
         its own function — see item 2.

   - merge_script_into_tts(script_data, json_path) -> None
     The guard at main.py:163-165 is BROKEN:
         if key not in tts_data or key != 'words':
     That condition is True for every key except 'words'-already-present, so
     'segments', 'segment_times' and 'duration' are NOT protected.
     admin.py:225 has the correct version:
         if key not in ('words', 'segments', 'duration', 'segment_times'):
     Use admin.py's version.

   - render_video(audio_path, data_path, video_path, video_type=None,
                  background=None, use_v2=False, timeout=None) -> Path
     Extracted from main.py:173-206 (run_video). Changes while extracting:
       * main.py:186-187 reads a module GLOBAL, `USE_V2_ENGINE`, assigned inside
         main() at main.py:513. Turn it into the explicit `use_v2` parameter.
         Leave no globals in pipeline.py.
       * Replace subprocess.run(capture_output=True) with Popen using
         stderr=subprocess.STDOUT and stdout=PIPE, reading line by line. Each
         line goes to logger.info AND into a ring buffer of the last ~80 lines.
         On TimeoutExpired: kill the process and raise an exception that INCLUDES
         that buffer. Today admin.py:250 uses capture_output=True, and
         subprocess.run DISCARDS TimeoutExpired.stderr — which is why render
         timeouts leave no trace of what the renderer was doing.

2. Rewrite admin.py:run_pipeline_with_tracking (admin.py:134-286) to use
   src/pipeline.py. Specifically:
   - Delete the tts_modules dict and the TTS subprocess (admin.py:173-211).
     Call pipeline.generate_tts().
   - Delete the inline merge (admin.py:222-231). Call
     pipeline.merge_script_into_tts().
   - Delete the video subprocess (admin.py:243-251). Call pipeline.render_video().
   - Video still goes to output/pending/<type>/ (admin.py's current behaviour,
     NOT main.py's output/video/).
   - Pass the resolved background, the way main.py:184-185 does. Today admin.py
     does not pass it, so backgrounds resolve through a different path.

   Watch out for a collision that exists today: admin.py:194-196 writes the script
   JSON to audio_dir/{unique_name}.json as the TTS INPUT, and the TTS then
   OVERWRITES that same path with its own output. Input and output are the same
   file. When refactoring, separate them or explicitly document why that is safe.

3. Rewrite main.py to import from src/pipeline.py. main.py keeps its argparse, its
   paths and its orchestration; it just stops owning the functions.

4. Delete the duplicated per-type dispatch blocks in the TTS modules' __main__.
   They are a third implementation of the same dispatch:
   - tts_elevenlabs.py:1392-1410
   - tts_openai.py:1524-1530
   - tts_google.py:498
   The modules may keep a __main__ for manual single-segment debugging, but not
   the video-type dispatch. If deleting the whole __main__ is cleaner, do that.

5. Delete the silent MoviePy fallback at src/video/__init__.py:333-336. It is a
   bare `except Exception` wrapped around the ENTIRE ffmpeg render that retries
   under MoviePy. It turns any data bug into a misattributed "FFmpeg renderer
   failed". Let the original exception propagate.
   Also remove `moviepy` from requirements.txt.
   The --renderer moviepy flag in src/video/__init__.py may stay or go, but NOT
   as an automatic fallback.

6. Add logging.basicConfig to admin.py (it has none; main.py:35-42 has one, copy
   that).

7. Complete requirements.txt. These are imported and NOT listed:
   elevenlabs, google-cloud-texttospeech, pydub, httpx.
   Remove `moviepy` (item 5). Do NOT remove `openai-whisper` — it will be used in
   a later step; leave it with a comment noting it is not imported today.

8. Delete src/__init__.py. It is a byte-identical clone of
   src/tts_providers/__init__.py (md5 ebd37ef2f22d0acfe14edeb420d6d1b7 for both).
   Before deleting, verify nothing needs it: main.py:705 does
   `from src.cost_tracker import print_report`, which only works because src/ is
   already on sys.path. If deleting breaks that line, fix the line — main.py:327
   uses `from cost_tracker import ...`, which is the correct form. Today those are
   TWO distinct module objects, each with its own _current_tracker global.

9. admin.py must import and use `profiles` and `cost_tracker`, the way
   main.py:327-328 and main.py:509-512 do.

OUT OF SCOPE — DO NOT DO THESE

- Do NOT touch src/video/v2/. It is frozen.
- Do NOT fix the quiz option timestamps or the audio segmentation
  (transition_duration = 1.5, per_option = /4 at tts_elevenlabs.py:589-591).
  That is a later step with its own plan. Leave it exactly as is.
- Do NOT add schema validation / pydantic. Later step.
- Do NOT delete src/quality_reviewer.py or src/video_analyzer.py. They are
  orphaned and harmless; they will be read before being deleted in a later step.
- Do NOT refactor the *_segmented TTS generators even though they are 0.72-0.84
  similar across providers. Later step.
- Do NOT change the TTS output format or the semantics of segment_times.

DEFINITION OF DONE — proof, not "it should work now"

I need to see real output, not claims.

A) Add a --dry-run flag to src/pipeline.py:generate_tts that resolves and LOGS the
   provider, model_id, voice_id and the per-segment language_code, without calling
   any API. Then run the SAME existing script through both entry points:

     output/scripts/educational/to_be_swamped_20260414_142502.json

   Paste both outputs. They must match on provider, model_id, voice_id and
   per-segment language_code. If they do not match, you are not done.

B) Once A matches, do one real run per entry point with that same script (~$0.09
   each). Diff the two resulting TTS JSON files. Report which fields differ and
   why. If `duration` or `segment_times` differ by more than encoder noise, you
   are not done.

C) Generate a video from the dashboard and show that output/costs/ recorded the
   cost. Today it records nothing from that entry point.

D) Force a render failure on purpose (for example, pass a corrupted data JSON) and
   show the error message the user sees. It must contain the renderer's actual
   last stderr lines, not a subprocess traceback.

E) `git diff --stat` at the end. I expect more lines deleted than added.

HOW TO WORK

Do items 1-3 first and STOP. Show me the diff and the output of proof A before
continuing with 4-9. Do not chain all nine items without showing anything in
between.
````

---

## PROMPT 0B — Find the cause of the render timeout

Córrelo **después** de que 0A esté mergeado (necesita el stderr streameado).

````
You are in ~/Downloads/english-ai-videos. It renders vertical 1080x1920 video at
30fps by generating frames with PIL and piping them to ffmpeg
(src/video/compositor.py).

THE PROBLEM

The last 3 dashboard jobs died on a 600-second timeout in the render step
(recorded in output/generation_jobs.json: jobs 3e0dd307 "cool", 3d42776b
"scared stiff", bbecac57 "lay vs lie" — all quiz type, all on 2026-04-16, spaced
~10m47s apart, meaning each one burned the full timeout).

I do not know whether the render is SLOW or whether it HANGS. That is the question
I want answered. A typical video is 30-40 seconds = 900-1200 frames.

YOUR TASK: MEASURE AND REPORT. Do not fix anything yet.

PHASE 1 — Cheap triage (do this first, it takes minutes)

Take an existing audio+data pair from output/audio/ and render it with timing. If
none is usable, generate one.

Measure:
  - wall-clock seconds per rendered frame
  - is it linear? (render 30 frames, then 300; does the time scale 10x?)

This answers the binary question immediately:
  - If 900 frames at X sec/frame exceeds 600s linearly -> it is per-frame cost,
    not a hang. Proceed to phase 2.
  - If time does NOT scale linearly, or it stalls dead at some frame -> it is a
    hang. STOP, tell me which frame and with what input, and do not proceed to
    phase 2.

PHASE 2 — Profiling (only if it is per-frame cost)

Profile the frame generator DIRECTLY, without the subprocess. Import the module,
build the frame generator the way src/video/__init__.py:generate_video does, and
call it ~100 times under cProfile.

Report the top 15 by cumulative time.

A prior audit identified three suspects. None is confirmed. Confirm or rule out
each ONE BY ONE, with numbers:

  SUSPECT 1 — config.yaml read from disk 30 times per second of video.
    src/video/utils.py:553-556 (finalize_frame) calls get_character_renderer() on
    EVERY frame. With character.enabled: false in config.yaml, the _renderer
    singleton stays None forever, so src/video/character.py:751-759 falls through
    to _load_config() -> os.path.exists + open + yaml.safe_load on every frame.
    The negative result is never memoized.
    MEASURE: how many times config.yaml is opened across 100 frames, and what
    percentage of total time that accounts for.

  SUSPECT 2 — full-canvas allocations per frame.
    Each 1080x1920 RGBA frame is 8.3 MB. create_base_frame
    (src/video/utils.py:535-544) allocates one. draw_rounded_card
    (src/video/utils.py:617-652) allocates TWO more per call (shadow + card).
    draw_glow, draw_pill_badge, draw_progress_timer_bar and every inline accent
    bar allocate another. A quiz frame with 4 option cards + question card +
    explanation card may be doing 15-25 full-canvas allocations.
    MEASURE: count Image.new and Image.fromarray calls per frame on a quiz, and
    total time spent in alpha compositing.

  SUSPECT 3 — pre-rendered background cache.
    src/video/__init__.py:136-137 calls bg.pre_render_loop(background,
    loop_duration=min(5.0, duration)), which at src/backgrounds.py:560-563 caches
    5 x 30 = 150 frames of 1080x1920x3 uint8 ~= 933 MB resident.
    MEASURE: process RSS before and after pre_render_loop. If the machine starts
    swapping, that would explain an apparent hang.

Also check whether the timeout is QUIZ-specific. All 3 failures were quizzes.
Render one educational and one quiz of comparable duration and compare sec/frame.
create_frame_quiz (src/video/quiz.py:572-847) is 276 lines and draws considerably
more per frame than the other types.

PHASE 3 — Only the fixes the profile justifies

Once you have numbers, apply ONLY the fixes the profile supports, and re-measure.
Show sec/frame before and after.

Example of a justified fix if suspect 1 scores high: memoize the None result of
get_character_renderer(). That is a three-line change.

Do NOT redesign the renderer. Do NOT touch src/video/v2/. If the profile does not
point to a clear cause, say so — the cheap way out is raising the timeout and
adding resume-from-audio, and that is my decision, not yours.

DELIVERABLE

A report containing:
  1. Slow or hung? With the number that proves it.
  2. Seconds per frame, by video type.
  3. Top 15 from the profile.
  4. The three suspects: confirmed or ruled out, each with its number.
  5. If you applied any fix: sec/frame before and after.
  6. Estimated render time for a 35s video after the fixes.

Stop and show me phase 1 before starting phase 2.
````

---

## Qué esperar

**0A** es mecánico. El riesgo real no es que rompa algo — es que se expanda. La sección `OUT OF SCOPE` está ahí porque cada punto es una tentación legítima con el archivo abierto. Si vuelve con la segmentación de audio "arreglada de paso", recházalo: ese cambio necesita la tabla de deriva del paso 2 para poder probarse.

**0B** puede terminar en tres sitios, y los tres son resultados válidos:

- Coste por frame identificado y reducido → sigues al paso 1
- Un cuelgue real en un frame concreto → es otro bug, y probablemente más barato
- Sin causa clara → subes el timeout, añades resume-from-audio, y sigues. En el paso 0 no se rediseña el renderer

**La prueba A de 0A es la que importa.** Si el dry-run coincide por ambas entradas, el paso 0 hizo su trabajo — y cuesta cero. Solo después, ~$0.18 en corridas reales para confirmar.
