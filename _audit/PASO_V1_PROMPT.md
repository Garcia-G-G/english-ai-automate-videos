# V1 — fondos que se mueven de verdad

**Coste: $0.00 por video.** Y sustituye a los $0.041 de imagen generada.

---

## Lo que el dueño pidió, y lo que ya existe

> *"los fondos son planos, me gustaría que fueran fondos animados y no solo con el típico movimiento de ffmpeg... alguna galería de videos... un avión volando sobre un río, un tipo andando en kayak"*

**Está construido.** `src/video/clip_background.py` escanea un directorio, arma una playlist barajada que cubre la duración, sirve fotogramas por tiempo y ya aplica `dim=0.35` para que el texto encima siga legible. El dispatch está cableado en `__init__.py:201`. `pipeline.resolve_background` ya devuelve `clips:<dir>` en su tramo 2.

`assets/clips/adults/` y `assets/clips/kids/` existen y están **vacíos**.

Novena instancia del fallo dominante. Y **es mía**: taché `4b · Fondos de clips` en el roadmap como *"sustituido por F"* cuando decidimos generar imágenes. Sustituí la ruta que el dueño pedía por fotos fijas con paneo de ffmpeg — literalmente lo que dice que no quiere.

## La fuente, verificada

| | |
|---|---|
| Endpoint | `GET https://api.pexels.com/v1/videos/search` |
| Auth | header `Authorization: <key>` · gratis, sin suscripción |
| Límite | 200/hora · 20.000/mes |
| Vertical | `orientation=portrait` ✅ |
| Calidad | `size=medium` (Full HD mínimo) |
| Respuesta | `video_files[]` con `link`, `quality`, `width/height`, `fps`, y `duration` |

**Licencia** (leída, no supuesta): uso comercial ✅, modificación ✅, YouTube monetizado ✅, atribución **no** obligatoria. Prohibido revender copias sin alterar, implicar respaldos de marcas, y redistribuir en otras plataformas de stock — nada de eso aplica aquí.

**Matiz que sí aplica:** los términos *de la API* piden un enlace visible a Pexels aunque la licencia general no exija atribución. Se cumple con una línea en la descripción del canal.

---

## PROMPT — V1

````
You are in ~/Downloads/english-ai-videos.

THE ASK

The owner has repeatedly asked for MOVING backgrounds — real footage, not a
still with a Ken Burns pan. His words: "un avión volando sobre un río, un
tipo andando en kayak por el mar muerto".

IT IS ALREADY BUILT. src/video/clip_background.py plays a library of mp4s as
the frame background: it scans a directory, builds a shuffled playlist
covering the video's duration, serves RGB frames by time, and applies a dim
so overlaid text stays readable. __init__.py:201 dispatches "clips:<dir>".
pipeline.resolve_background already returns clips:<dir> at tier 2.

assets/clips/adults/ and assets/clips/kids/ exist and are EMPTY. The feature
has been starved of assets, not missing.

THE SOURCE — verified, do not re-research

  GET https://api.pexels.com/v1/videos/search
  header: Authorization: <PEXELS_API_KEY>
  free, no subscription, 200 req/hour, 20,000/month
  orientation=portrait   size=medium
  response: video_files[] with link / quality / width / height / fps, plus
            the video's duration

  License: commercial use, modification and monetised YouTube all permitted;
  attribution not required by the license. The API terms DO ask for a visible
  Pexels link — satisfy it with one line in the channel description and say
  where you put it.

TASK

  a. src/topic_clips.py — per-video clip fetch, mirroring the shape of
     topic_background.py.

     Search terms come from the topic AND the category, composed the way F3
     composes image prompts. THE LESSON FROM F3 APPLIES DIRECTLY AND IS NOT
     OPTIONAL: 11 of 14 generated images came out alike because 11 of 20
     categories fell through to one DEFAULT prompt stem. If the search query
     collapses to one stem, every video gets the same footage and we have
     rebuilt the same failure with video instead of stills.

     Build the query space from content/topics/ — all 20 real categories, no
     catch-all — and report its size.

     Download enough clips to cover the video's duration, into the
     ARTIFACT'S OWN directory, not a global one.

  b. resolve_background gains a tier that returns clips:<artifact dir>.
     Keep the existing priority order and its reasoning intact; slot this in
     and say where and why.

     THIS ALSO CLOSES A LOGGED GAP. legacy_pipeline.py:244 deliberately omits
     topic/category with the comment "the legacy topic tier writes to global
     output/backgrounds and has no destination argument". Clips written into
     the artifact directory remove that objection, so the Studio path can
     finally receive a real background. Confirm it does.

  c. READABILITY IS THE RISK, AND IT IS DIFFERENT FROM STILLS.

     A still is measured once. A CLIP CHANGES EVERY FRAME — a dark opening
     can brighten into white surf behind white text halfway through. The
     current uniform dim=0.35 is a blunt instrument and a single-frame gate
     reading is blind to this by construction.

     Sample contrast at multiple points across the clip's duration, not one.
     Report the worst point, not the average.

     THE OWNER SUPPLIED THE ANSWER, in a reference frame he sent: every text
     element sits on its OWN OPAQUE PLATE — a yellow highlight behind the
     title, solid black boxes behind the tier labels, filled black circles
     behind the numbers. Nothing floats on the footage.

     That guarantees contrast PER ELEMENT and is immune to what the video
     does behind it, which a global dim and a single band scrim are not. It
     is also cheaper: no measurement of the footage is required for the plate
     to work.

     Prefer per-element plates over dimming the whole frame. Keep the dim as
     a mild secondary so the footage reads as background rather than subject,
     but the plates are what makes the text safe. Then measure anyway, and
     report the worst frame — a plate that is too small for its text is the
     failure mode that replaces the old one.

     A background that is beautiful for 20 seconds and unreadable for 3 is a
     failure, and today nothing in this repo would catch it.

  d. Cache downloads by query so the same search does not re-download, and
     keep an eye on disk — these are megabytes, not kilobytes. Report what
     one video's clips weigh.

PROOF — visual, as with F3. Numbers cannot settle this.

  P1. A contact sheet: 8 videos across at least 6 categories, three frames
      each (start / middle / end), card in place. I need to see motion and
      variety, and whether the text survives all three moments.
  P2. Worst-case contrast per clip across sampled frames, with the sampling
      interval stated. Not the average.
  P3. Distinct search queries across the 8. If two land on the same footage,
      say so rather than shipping it — that is the F3 failure returning.
  P4. One video rendered through the STUDIO path carrying clips, proving (b).
  P5. Disk cost per video, and the total for the 8.
  P6. Full test suite.

COST
  $0.00 in API charges. It also REPLACES the $0.041 image generation on
  videos that use clips — say what the net per-video cost becomes.

OUT OF SCOPE
  - New video types. Separate and larger; the owner wants all four.
  - The text grouping bugs (stray commas, phrases split across screens).
  - The Learning Routes CTA rework.
  - L1's layout overflow.

HOW TO WORK

Land (a) and produce the P1 contact sheet BEFORE (c). If the footage is
wrong — repetitive, irrelevant, or ugly — the readability work is wasted.
The sheet is what tells us.
````

---

## Lo que espero que salga mal

Que los clips verticales de calidad sean escasos para temas abstractos. "Un avión sobre un río" existe; *"phrasal verbs"* no. La consulta tendrá que buscar la **escena**, no el tema — igual que F3 aprendió a pedir un escenario y no una ilustración de la frase. Si la búsqueda vuelve vacía a menudo, el fallback correcto es la imagen generada que ya funciona, no una paleta.
