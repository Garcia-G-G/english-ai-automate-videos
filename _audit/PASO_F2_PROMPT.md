# Paso F2 — el fondo generado solo existe en `--batch`

**Leído contra `HEAD 4dbe4e4`.** Diagnóstico antes del prompt, porque el prompt no se entiende sin él.

---

## Lo que reportaste

> "lo que veo es que en mi generacion de video no estan presentes los fondos"

Es cierto y es comprobable. No es percepción.

## La prueba

Cada render del dashboard escribe su propio log en `logs/<fecha>_job-<id>.log`. El último fondo de cada uno:

```
20260817_job-c0aab9be.log | Background: gen_008
20260820_job-45a6d006.log | Background: gen_023
dashboard.log             | Background: gen_023
repro_fresh.log           | Background: gen_056
```

`gen_NNN` es una **paleta procedural**, no una imagen. Los renders que sí llevan imagen generada están en otros logs — los del lote:

```
Background: photo:.../output/backgrounds/the_cat_says_meow.png
Background: photo:.../output/backgrounds/go_viral.png
Background: photo:.../output/backgrounds/to_have_a_sweet_tooth.png
```

Ningún `job-*.log` tiene una sola línea `photo:`. **Cero.**

## La causa

`_background_for_topic()` está en `main.py:632`. La llama `main.py:729`, dentro de `generate_and_run` — la ruta `--batch`.

El dashboard no pasa por ahí. `src/admin.py:329` hace:

```python
background=pipeline.resolve_background(profile, background),
```

Y `src/pipeline.py:109` — la función *compartida* — es esto entero:

```python
def resolve_background(profile, background=None):
    if background:
        return background
    video_cfg = (profile or {}).get("video", {}) or {}
    if video_cfg.get("background_mode") == "clips":
        return f"clips:{video_cfg.get('clips_dir', 'assets/clips')}"
    return background          # ← None
```

No sabe generar. Nunca supo. Devuelve `None`, y `None` en el renderer significa "elige una paleta del rotativo". De ahí `gen_023`.

**El fondo generado se construyó, se probó, pasó el gate 6/6 — y se conectó a una sola de las dos rutas.**

Es la firma de este repo otra vez: *código correcto que nunca recibe lo que necesita*. Quinta vez, y las cinco son la **misma** divergencia `main.py` / `admin.py`:

| # | qué se quedó en una sola ruta | dónde se cerró |
|---|---|---|
| 1 | los dos pipelines de TTS | Paso 0 |
| 2 | la tercera ruta de subida (`main.py:137`) | 5a · Prompt 1 |
| 3 | `finalize_video` con 0 llamadores (gate + outro) | 5a · Prompt 4 |
| 4 | `_static_frame` cacheando sin mirar el preset | 4b3bd19 |
| 5 | **el fondo generado por video** | ← aquí |

## Un segundo defecto que aparece al mirar esto

En la ruta `--batch` el orden está invertido:

- `main.py:729` genera el fondo (`generate_and_run`).
- `main.py:493` llama `resolve_background(...)` **después**, ya dentro de `run_pipeline`.

`resolve_background` devuelve `background` tal cual si ya no es `None`. O sea: con el perfil **kids** (`config.yaml:148`, `background_mode: "clips"`), el lote genera una imagen y **pisa silenciosamente el modo clips del perfil**. Nadie lo ha visto porque el lote no se ha corrido con kids.

Unificar las dos funciones arregla los dos defectos a la vez. Por eso el prompt pide **una** función, no copiar la llamada a `admin.py`.

---

## PROMPT — Paso F2

````
You are in ~/Downloads/english-ai-videos. HEAD is 4dbe4e4.

THE FINDING (verified, not a hypothesis)

Every dashboard render logs `Background: gen_NNN (preset)` — a procedural
palette. Not one `logs/*_job-*.log` contains a `photo:` background. The
generated per-video backgrounds from 6ff1768 only exist on the --batch path.

Why: _background_for_topic() lives in main.py:632 and is called from
main.py:729 inside generate_and_run(). The dashboard never goes through
generate_and_run — src/admin.py:329 calls pipeline.resolve_background(),
which has no notion of generating anything and returns None, and None means
"pick a palette" downstream.

This is the fifth main.py/admin.py divergence in this repo (after the two TTS
pipelines, the third upload path, finalize_video's zero callers, and the
_static_frame cache). Do not fix it by calling _background_for_topic from
admin.py — that creates a sixth thing to keep in sync. Move it.

SECOND DEFECT, same root — fix it in the same change

On the --batch path the order is inverted. main.py:729 generates the
background, and main.py:493 calls resolve_background() afterwards inside
run_pipeline(). resolve_background returns `background` unchanged when it is
not None, so a clips-mode profile (kids, config.yaml:148
background_mode: "clips") gets silently overridden by a generated image on
the batch path. Nobody has hit it because the batch has not been run with
kids. One unified resolver removes it.

TASK

  a. Move _background_for_topic() out of main.py into src/pipeline.py and
     merge it with resolve_background() into ONE function that both entry
     points call. It must resolve in this priority order, and the order is
     the specification:

        1. an explicit `background` argument   → return it untouched
                                                 (--background is an
                                                  instruction, not a default)
        2. profile background_mode == "clips"  → return clips:<dir>
        3. topic + category available          → generate, GATE, and return
                                                 photo:<path> on PASS
        4. gate REJECT / generation failed /
           module unavailable / no topic       → fallback_preset()

     Keep every property _background_for_topic already has: it must never
     raise (a background problem must not cost the video), it must log the
     reason on every fallback, and the gate stays BLOCKING — a rejected image
     becomes a palette, it does not ship.

     src/topic_background.py and src/topic_background_gate.py stay where they
     are. Do not rewrite them.

  b. Wire src/admin.py:329 to the unified function, passing the topic_name
     and category it already has in scope at that point (they are set at
     admin.py:262-266 and written to the job at :267).

     admin.py has no batch `entry` dict — the `entry` parameter must be
     optional. Where main.py records the decision into `entry["background"]`,
     admin.py should record the same information into the job via
     update_job(), so the dashboard shows which background a video got and
     whether the gate passed. Same fields: source, image, worst_ratio, gate,
     cost_usd.

  c. Delete _background_for_topic from main.py and point main.py at the
     unified function. main.py must not keep a private copy.

     Because resolve_background now runs once and returns a final answer,
     remove the second call at main.py:493 or make it a no-op for an already
     resolved value — whichever leaves exactly ONE place where a background
     is decided.

PROOF — the standing rule: show it, do not assert it

  P1. grep the whole repo for every place a background is decided. Show me
      the output. There must be exactly one function, and both main.py and
      admin.py must call it. If a third caller exists, name it before you
      touch anything.

  P2. Render one video THROUGH THE DASHBOARD PATH — not --batch. Show the
      `Background:` line from its logs/*_job-*.log. It must read
      photo:<path>, not gen_NNN (preset). This is the whole point of the
      task; a --batch render proves nothing here.

  P3. Extract a frame from that dashboard video and show it, so I can see
      the image is actually on screen and not just named in a log. We have
      been burned by that exact gap before (the ceiling-blind gate: no image
      at all scores BEST on contrast).

  P4. Render one video with the kids profile (background_mode: "clips") on
      BOTH paths. Both must get clips:, not a generated image. That is the
      second defect, and it is the reason for unifying rather than copying.

  P5. Force a gate REJECT (feed it an image that fails) on the dashboard
      path and show that it falls back to a palette and logs the reason,
      without killing the render.

  P6. Full test suite. Report the count. Nothing that passed may fail.

COST

Each dashboard render now costs one gpt-image-1.5 generation (~$0.10). That
is expected and approved. Report the actual per-video cost from the tracker
in P2 so we see the real number, not the estimate.

OUT OF SCOPE
  - Ken Burns / motion calibration. Separate step.
  - The palette cull (enabled_backgrounds still holds generated:*).
  - Text layout, vocabulary/pronunciation cards.
  - The scheduler.

GIT: one commit for (a)+(c) — the unification is one change — and one for
(b). Push after each.

HOW TO WORK

If P1 shows a third place that decides a background, STOP and tell me before
changing anything. Two known paths is the premise of this task; three would
mean the premise is wrong.
````

---

## Dónde espero que falle

En (c). `main.py:493` está dentro de `run_pipeline`, que también se llama desde `run_from_text` y probablemente desde algún sitio más — quitarlo sin mirar quién llama a `run_pipeline` con `background=None` y sin topic deja esos casos sin fondo ninguno. El prompt pide "exactamente un sitio donde se decide", y ese es el punto donde la respuesta puede ser fea.

## Lo que NO arregla esto

Que el fondo se **vea bien**. Esto solo garantiza que llega. La calibración del movimiento (lo que pediste: *"que se genere el fondo y simplemente se calibra el movimiento"*) es el paso siguiente, y ya sabemos dónde: `backgrounds.py:1518-1519, 1525-1526`, amplitud de pan a 158 px/s y zoom sumando tres osciladores. Ese arreglo tiene una trampa registrada: corregir solo la amplitud congela el 81.6% de los fotogramas.
