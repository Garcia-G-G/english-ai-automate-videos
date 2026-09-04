# Paso F2 — adenda: el tercer sitio, y la decisión

**Claude Code paró en P1, como pedía el prompt, y tenía razón.** Comprobado línea por línea contra `HEAD 4dbe4e4`. La regla de parada funcionó: la premisa "dos rutas" era falsa y verlo costó un round-trip en vez de un rediseño.

---

## Lo que confirmo

`src/video/__init__.py:main()` **es camino de producción**, no una CLI de desarrollo. `pipeline.render_video()` (`src/pipeline.py:349`) lanza el renderer como subproceso:

```python
cmd = [sys.executable, "-u", "-m", "video", "-a", ..., "-d", ..., "-o", ...]
if background:
    cmd.extend(["-b", background])
```

`if background:` — con `None` **no se pasa `-b`**, y `main():581` elige paleta por su cuenta. Ese es el `gen_NNN` de cada log del dashboard. El diagnóstico del síntoma era correcto; el sitio donde se decide está un proceso más abajo de lo que yo escribí.

---

## Dos correcciones a su informe

### 1. `--fast` no es alcanzable desde producción

Lo presenta como defecto vivo — *"a generated image is silently discarded in fast mode"*. Cierto del código, falso de la ejecución. `--fast` aparece **tres veces en todo el repo**:

```
src/video/__init__.py:536   parser.add_argument("--fast", ...)
src/video/__init__.py:577   if args.fast:
src/video/__init__.py:584   fast_mode=args.fast, ...
```

`render_video()` no lo añade nunca al `cmd`. **Ningún llamador de producción puede activarlo.** Es una trampa esperando al primero que lo cablee, no una fuga de hoy.

Lo doblo dentro igual, porque son tres líneas y porque la trampa es exactamente la forma del defecto de kids. Pero **no justifica ampliar el alcance** — que se meta por barato, no por urgente. Si el paso se desborda, `--fast` es lo primero que se cae.

### 2. Falta un cuarto sitio, y es el que muerde

`fallback_preset()` (`src/topic_background.py:163`) y `get_default_background()` (`src/video/backgrounds.py:53`, rama `random`) son **el mismo algoritmo escrito dos veces**:

| | `fallback_preset()` | `get_default_background()` |
|---|---|---|
| lee | `config.yaml` → `video.enabled_backgrounds` | `config.yaml` → `video.enabled_backgrounds` |
| expande | `resolve_enabled(names)` | `resolve_enabled(...)` |
| filtra | `n in BACKGROUND_PRESETS` | `bg in BACKGROUND_PRESETS` |
| elige | `random.SystemRandom().choice(pool)` | `_sysrand.choice(valid)` |

Misma clave, misma expansión, mismo filtro, mismo generador aleatorio. Dos implementaciones.

**Por qué importa ahora y no en abstracto:** la criba de paletas (36 se quedan, 24 se van) sigue pendiente y `enabled_backgrounds` todavía contiene `generated:*`. Aplicarla en un sitio deja el otro sirviendo la rotación vieja — y el otro es justo el que atiende hoy al dashboard. Es la misma trampa que `_static_frame`: la prueba pasa por un camino y el operador vive el otro.

`get_default_background()` además cubre dos tramos que `fallback_preset()` no tiene: `mode == "fixed"` y `video.default_background`. La unificación tiene que absorberlos, no ignorarlos.

---

## LA DECISIÓN: 1 + 3, y un 4

Coincido con su recomendación. Con una condición que la hace verdad y no aspiración: **si `get_default_background()` se queda definida y sin llamadores, esto no se ha cerrado — se ha convertido en la séptima pieza de código correcto que nadie invoca.** Ese es el fallo dominante del repo. No lo reproduzcamos arreglándolo.

### PROMPT — F2 (revisado)

````
You are in ~/Downloads/english-ai-videos. HEAD is 4dbe4e4.

Your P1 stop was correct and the answer is: option 1 + option 3, plus a
fourth item you did not name. Read all four before starting.

CONTEXT CORRECTION — do not let this widen the task

--fast is NOT reachable from production. It appears three times in the whole
repo (argparse at :536, the branch at :577, the pass-through at :584) and
pipeline.render_video() never appends it to cmd. It is a trap, not a live
leak. Fold it in because it is three lines. If the task overruns, --fast is
the FIRST thing to drop.

THE FOURTH SITE — this is the one that matters

fallback_preset() (src/topic_background.py:163) and get_default_background()
(src/video/backgrounds.py:53, `random` branch) are the SAME algorithm written
twice: same config key (video.enabled_backgrounds), same resolve_enabled()
expansion, same `in BACKGROUND_PRESETS` filter, same
random.SystemRandom().choice.

The palette cull (36 keep / 24 drop) is still pending and enabled_backgrounds
still holds generated:*. Applying it in one of these leaves the other serving
the old rotation — and the other one is what serves the dashboard today. Same
trap as the _static_frame cache: the test passes down one path, the operator
lives the other.

get_default_background() also covers two tiers fallback_preset() does not:
mode == "fixed", and video.default_background. The unified resolver must
absorb both, not drop them.

TASK

  a. ONE resolver in src/pipeline.py, replacing resolve_background() and
     absorbing main.py:632 _background_for_topic(). Priority order — this
     order IS the specification:

        0. fast mode requested          → "dark_professional"
        1. explicit `background` arg    → return untouched
        2. profile background_mode=clips→ clips:<dir>
        3. topic + category present     → generate, GATE, photo:<path> on PASS
        4. config background_mode=fixed
           or video.default_background  → that preset
        5. terminal fallback            → a preset from the culled rotation

     It must NEVER raise and NEVER return None. Tier 5 is the floor: if the
     enabled pool is empty, return a hardcoded literal preset rather than
     None. `None` is what got us here — it is the value that let a lower
     layer decide.

     Log the reason on every fallback. The gate stays BLOCKING.

  b. The renderer subprocess never decides. Delete the fallback at
     src/video/__init__.py:581 and the one at :168. Make -b required in
     argparse. pipeline.render_video() always passes it, because (a) always
     returns a value.

     Delete the --fast override at :578-579. fast_mode still controls render
     settings; it no longer picks a background.

     KEEP the use_v2 discard at :161 (`if use_v2: background = None`). That
     is a renderer capability limit, not a decision — v2 cannot draw a
     background. Leave the comment saying so.

  c. Wire src/admin.py:329 to the unified resolver, passing the topic_name
     and category already in scope (set at admin.py:262-266). The `entry`
     parameter must be optional — admin has no batch entry dict. Record the
     same information into the job via update_job(): source, image,
     worst_ratio, gate, cost_usd. The dashboard should show which background
     a video got and whether the gate passed.

  d. Delete _background_for_topic from main.py. Remove the second
     resolve_background call at main.py:493 — it currently runs AFTER
     generation and returns the value untouched, which is how a clips-mode
     profile gets overridden on the batch path.

     Then: get_default_background() must have ZERO callers. Either delete it
     or make it a thin alias whose body is the unified resolver's tier 5. Do
     NOT leave it defined and uncalled — this repo's dominant failure is
     correct code nothing invokes, and we are not adding an instance of it
     while fixing one.

  e. The five direct generate_video() callers (tests/test_layout_pins.py:109
     and four _audit/layout/*.py) must now pass an explicit background. Use a
     fixed preset in the tests so their frames stay deterministic — do NOT
     let them call the generating resolver and spend money on every test run.

PROOF

  P1'. Re-run the P1 sweep. Show it. Exactly one function decides a
       background, and grep must show zero callers of
       get_default_background() (or that it no longer exists).

  P2.  Render one video THROUGH THE DASHBOARD — not --batch. Show the
       Background: line from its logs/*_job-*.log. It must read photo:<path>.

  P3.  Extract and show a frame from that video. A log line is not proof the
       image is on screen; the contrast gate scores BEST when there is no
       image at all, and we have been caught by exactly that.

  P4.  kids profile (background_mode: "clips"), BOTH paths. Both get clips:,
       neither gets a generated image. That is the latent defect at
       main.py:493.

  P5.  Force a gate REJECT on the dashboard path. It falls back to a palette,
       logs the reason, and the render survives.

  P6.  Empty the enabled pool and confirm tier 5 still returns a preset and
       the render completes. No None reaches the renderer.

  P7.  Full test suite. Report the count. Nothing that passed may fail.
       Confirm no test now spends money on image generation.

COST
  Each dashboard render adds one gpt-image-1.5 generation (~$0.10). Approved.
  Report the ACTUAL per-video cost from the tracker in P2.

OUT OF SCOPE
  - Ken Burns / motion calibration.
  - Applying the palette cull itself. This makes it applicable in ONE place;
    applying it is the next step.
  - Text layout, vocabulary/pronunciation.
  - The scheduler.

GIT
  One commit for (a)+(d) — the unification is one change.
  One for (b)+(e) — the renderer stops deciding.
  One for (c) — the dashboard.
  Push after each.

If (e) turns out to be more than a one-line change per caller, land (a)-(d)
and tell me. Do not half-land.
````

---

## Dónde espero que falle

En (b), al hacer `-b` obligatorio. `argparse` con `required=True` rompe cualquier invocación que no lo pase, y los cinco llamadores directos son los que conozco — si hay un script en `tools/` o un `Makefile` que llame `python -m video` sin `-b`, sale ahí y no antes.

## Lo que sigue sin arreglar esto

Que el fondo se **vea bien**. Esto garantiza que llega y que lo decide un solo sitio. La calibración del movimiento es el paso siguiente: `backgrounds.py:1518-1519, 1525-1526`, con la trampa registrada de que corregir solo la amplitud congela el 81.6% de los fotogramas.
