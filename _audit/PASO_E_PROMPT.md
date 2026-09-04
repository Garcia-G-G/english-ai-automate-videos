# Paso E — reestructurar el dashboard por el ciclo de vida del artefacto

**Leído contra `HEAD ad06c8c`.** Decisión del operador: reestructurar Streamlit (no un front-end nuevo), y **estructura antes que Paso D**.

---

## Lo que dijo

> *"que tenga apartado mejor de creación de videos, de creación de fondos entre otras cosas... el dashboard se siente bien pero se siente muy indie"*

Dos cosas mezcladas. Separarlas es el trabajo.

## Lo estructural, medido

**1 · Los fondos no tienen pantalla.** Ninguna. Solo un `selectbox` de `default_background` enterrado en Settings → Video Config. Hoy los fondos son: generación por tema, gate de contraste, scrim compuesto, fallback a paleta, espacio de 5120 combinaciones, 16 imágenes en disco y **$0.041 por video**. Un subsistema con coste recurrente y puerta de calidad propia, sin una sola vista.

**2 · Hay CUATRO puertas a la misma función.** Quick Generate (Dashboard, 4 tipos hardcodeados) · página Generate (dropdown completo) · Queue (lotes) · "Generate Batch Now" (Scheduler). Las cuatro llaman a `start_generation`.

**3 · Y esta es la que importa de verdad:**

| carpeta | artefactos |
|---|---|
| `output/pending` | 11 |
| `output/approved` | 1 |
| `output/uploaded` | 10 |
| `output/rejected` | **102** |
| **`output/video`** (salida de `--batch`) | **13** |

`get_library_videos()` lee `output/video/` y la página Library ofrece **preview y descarga, no subida**. Los seis videos del lote — los primeros del proyecto con el CTA de Learning Routes — **llevan desde el 18 de agosto sin poder publicarse desde la interfaz**. No es pereza del operador: la ruta no existe.

## Lo cosmético

Emojis en la navegación, 18 clases CSS a mano aplicadas de forma desigual en 23 sitios, métricas que nadie acciona ("Storage MB", "Video Types"), `st.expander` con dicts crudos. Se mejora, pero **Streamlit tiene techo** y hay que decirlo: esto va a seguir leyéndose como Streamlit. Es lo más barato de la lista y va al final.

---

## PROMPT — Paso E

````
You are in ~/Downloads/english-ai-videos. HEAD is ad06c8c.

Paso D is PAUSED by decision. D0 is landed and is data, not UI, so it
survives. D1-D4 will be built into the new structure rather than into pages
that are about to move.

THE PROBLEM

The dashboard is organised by feature. It should be organised by the
artifact's life: it is created, it is reviewed, it is published. Three
measured symptoms:

  1. Backgrounds have NO page. The only control is a default_background
     selectbox buried in Settings > Video Config. Backgrounds are now
     generation + a contrast gate + a composited scrim + a palette fallback +
     a 5120-combination prompt space + 16 images on disk + $0.041 per video.
     A subsystem with recurring cost and its own quality gate, with no screen.

  2. FOUR doors to the same function. Quick Generate (Dashboard, 4 hardcoded
     types), the Generate page, Queue, and "Generate Batch Now" (Scheduler).
     All four call start_generation.

  3. get_library_videos() reads output/video/ — the --batch output, 13
     artifacts — and the Library page offers preview and download but NO
     upload. The six batch videos carrying the first Learning Routes CTA have
     been unpublishable from the UI since 18 August. The route does not exist.

TASK — commit per step, push after each

  E1. THE UPLOAD ROUTE THAT DOES NOT EXIST. Do this FIRST; it is small and it
      unblocks six finished videos.

      Artifacts in output/video/ must be promotable to the upload flow, going
      through the SAME approval and the SAME publication-ledger guard as
      anything from output/pending/. Do not add a second upload path — this
      repo has had three of those and unifying them was Paso 5a.

      The idempotency guard is not optional here: get_approved_videos()'s
      docstring documents that a hand upload is exactly how hPdSoqjvu3E got
      published twice. Whatever you build consults publication_log.

  E2. ONE DOOR TO CREATION. Merge the four into a single "Crear" page: type,
      category/topic or random, count, optional background override, and the
      queue.

      Queue currently lives in st.session_state.queue_items, so it dies on
      refresh. Persist it to disk next to generation_jobs.json. It DOES work
      — it is consumed at :1532 — so this is durability, not a rewrite.

      Remove Quick Generate from the Dashboard and the Scheduler's batch
      button, and apply the already-decided Paso D5: delete the fake
      Start/Stop/interval controls and the dead scheduler_enabled /
      scheduler_config state.

  E3. THE BACKGROUNDS PAGE — the operator's named ask.

      A gallery of what output/backgrounds/ holds: image, topic, category,
      scene stem, palette, gate ratio, cost. Regenerate one on demand. Show
      the palette fallbacks that are still in the rotation. Show total
      background spend, and the count of images that were paid for and then
      refused by the gate — the job ledger already has at least one
      (palette/REJECT $0.041).

      Read from what exists. Do not invent a new store: the job rows carry
      the background payload from f112b2f, and the artifact meta carries it
      from D0.

  E4. THE LIFECYCLE. Regroup navigation around it, and make a video's state
      visible at every step:

        Inicio      what is in flight, what is blocked, what needs me
        Crear       E2, and Fondos as its sibling
        Revisar     the current Review
        Publicar    Upload + Library merged BY STATE, including E1
        Sistema     Costes, Registros, Ajustes

      The Dashboard becomes a real home, not a tile wall. Drop metrics nobody
      acts on ("Storage MB", "Video Types", "Total Videos").

  E5. THE SKIN, last and smallest. No emoji in navigation. Apply the 18 CSS
      classes that already exist consistently instead of half the time. Raw
      job dicts in expanders become labelled fields.

      Do NOT invent a new design language and do not add a CSS framework.
      Streamlit has a ceiling and we are not pretending otherwise.

REPORT, DO NOT SILENTLY FIX — three things I found while planning

  a. output/{scripts,audio,video,final} is a LITERAL directory name. Someone
     ran mkdir with brace expansion in a shell that does not do it. Tell me
     what is inside before anything touches it.

  b. output/published/ AND output/uploaded/ both exist. Which one is
     authoritative? Two folders for one concept is how an artifact goes
     missing. Report; do not merge them on your own.

  c. 102 artifacts in output/rejected/. Report the disk footprint and the
     date range. I am not asking you to delete anything.

PROOF

  P1. E1: screenshot of one output/video/ artifact promoted and uploaded
      through the normal flow, plus the publication_log entry it wrote.
      Then: attempt the SAME upload twice and show the guard refusing the
      second. That guard is the point of E1.

  P2. Screenshots of every new page.

  P3. grep proof that start_generation has exactly ONE caller in the UI, and
      that scheduler_enabled / scheduler_config no longer exist.

  P4. Full test suite. Report the count.

COST
  Zero. No API calls in this step, except any background regenerated to
  demonstrate E3 — one at most, and say so.

OUT OF SCOPE
  - A new front-end. The operator chose to restructure Streamlit.
  - D1-D4. They land in the new pages AFTER this.
  - F3 (d) and the watermark scrim — separate, still open.
  - Deleting anything under output/.

HOW TO WORK

E1 first and alone, then stop and show me P1. Six finished videos are stuck
behind it and it is the only item here with a real-world cost per day.

If merging Upload and Library in E4 turns out to entangle publication_log or
the idempotency guard, STOP and tell me. That machinery is what stops a
double publish, and no amount of layout is worth risking it.
````

---

## Dónde espero que falle

En E4, al fusionar Upload y Library. Las dos leen carpetas distintas y `get_approved_videos()` ya consulta el ledger para no ofrecer lo ya publicado. Una vista unificada por estado tiene que preservar esa consulta en todos los caminos, y es fácil perderla al reorganizar. Por eso el prompt pide parar antes que arriesgarla.

## Lo que esto NO arregla

Que se vea como Streamlit. E5 quita los emojis y aplica el CSS con consistencia, y ahí se acaba el margen. **Si después de E el operador sigue diciendo "se siente indie", la respuesta ya no es CSS: es que el techo de Streamlit es ese**, y entonces la conversación es un front-end propio — con el coste de mantener una superficie más, para una herramienta de un solo usuario.
