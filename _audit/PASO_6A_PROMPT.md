# Paso 6a — `fit_text_font` → caja medida

**Prompt para Claude Code.** Leído contra `HEAD 30477ca`.

**Va DESPUÉS de 5a.** El motivo está escrito en el ROADMAP v11: puse 6a por delante con la hipótesis de que el layout era causa del desplome de retención, y esa hipótesis quedó falsada (el evento visual dura 0.4 s, el desplome dura 3-4 s). Sin ella, 6a es deuda de calidad real pero sin evidencia de que mueva ningún número, y todo lo medible está bloqueado por volumen.

Lo dejo escrito ahora porque el diagnóstico está fresco y porque el paso es pequeño si se ataca por la raíz.

---

## La raíz, medida en el código de hoy

`src/video/utils.py:233-246`:

```python
def fit_text_font(text, max_font, min_font, max_width, max_height=None) -> tuple:
    """Returns (font_obj, actual_size, lines, total_height)."""
    for size in range(max_font, min_font - 1, -2):
        f = font(size)
        lines = line_break(text, f, max_width)
        line_h = int(size * 1.35)          # <-- estimación
        total_h = len(lines) * line_h      # <-- estimación
        if max_height is None or total_h <= max_height:
            return f, size, lines, total_h
```

Tres hechos, todos verificables en ese bloque:

1. **El ancho se mide, la altura se estima.** `line_break` (`:201`) usa `draw.textbbox`, que es medición real. La altura sale de `size * 1.35`, una constante mágica que no consulta la fuente. Ascendente, descendente, altura real de línea de Manrope: nada de eso entra.

2. **Con `max_height=None`, el bucle devuelve `max_font` en la primera iteración.** La condición `max_height is None or total_h <= max_height` es verdadera siempre. Es decir: en esos sitios `fit_text_font` no ajusta nada, solo devuelve la fuente más grande y su estimación de altura.

3. **De los 9 sitios de llamada, solo UNO pasa `max_height`.**

| sitio | `max_height` |
|---|---|
| `quiz.py:305` | comprobar |
| `quiz.py:841` | comprobar |
| `true_false.py:336` | comprobar |
| `true_false.py:589` | comprobar |
| `fill_blank.py:126` | **no** |
| `fill_blank.py:320` | **no** |
| `educational.py:205` | sí (`max_h`) |
| `vocabulary.py:103` | comprobar |
| `vocabulary.py:338`, `:349` | **no** |

Y la función no devuelve caja: ni offset horizontal, ni bearing izquierdo, ni la altura real del bloque dibujado. El que llama recibe un número que **cree** que es la altura y posiciona con él.

**Los tres defectos registrados son consecuencia de lo mismo:** el solape en `pronunciation`, el descuadre con tipografía mixta, y la sombra fuera de la banda segura. Ninguno es un bug de posicionamiento. Los tres son "nadie sabe cuánto espacio ocupa realmente lo que va a dibujar".

---

## PROMPT — Paso 6a

````
You are in ~/Downloads/english-ai-videos. Steps 0-5a are done.

THE ROOT

src/video/utils.py:233-246, fit_text_font. It returns
(font, size, lines, total_height) where total_height is
len(lines) * int(size * 1.35) — an ESTIMATE. Width is measured via
draw.textbbox inside line_break (:201); height is not measured at all.

Two consequences, both live:

  1. When max_height is None the loop returns max_font on its FIRST iteration,
     because `max_height is None or total_h <= max_height` is always true.
     At those call sites the function does not fit anything.

  2. Callers get a number they treat as the block height and position with it.
     They cannot know the real bounding box — no ascent, no descent, no left
     bearing, no measured extent.

Three logged visual defects share this root: pronunciation text overlapping,
misalignment with mixed typography (Manrope + Instrument Serif), and shadow
falling outside the safe band. None of them is a positioning bug.

TASK

  a. Make fit_text_font return a MEASURED box. Use PIL's textbbox on the
     laid-out block, not size * 1.35. The return value should carry enough for
     a caller to place the block without guessing: measured width, measured
     height, and the offsets needed to align it (a small dataclass, not a
     wider tuple — nine call sites already unpack the current one).

     Keep line_height available if callers need it, but derive it from the
     font metrics rather than from a constant.

  b. Audit all 9 call sites (quiz.py:305,841 · true_false.py:336,589 ·
     fill_blank.py:126,320 · educational.py:205 · vocabulary.py:103,338,349).
     For each: does it pass max_height, and does it position using the
     returned height?

     Report the table BEFORE changing any of them. The ones that pass
     max_height=None are silently getting max_font today; changing that will
     change how they render, and I want to see which ones before it happens.

  c. Then fix the three logged defects using the measured box. If any of the
     three does NOT resolve from this change, say so — that means it has a
     second cause and I would rather know than have it patched separately.

SCOPE DISCIPLINE

If this overruns, land (a) and (b) and STOP. A measured box plus the audit
table is the whole value; the three defects are the demonstration. Tell me you
are stopping rather than half-landing all three fixes.

DO NOT build the layout engine. No sidecar, no declarative layout spec, no
collision solver. That is 6c and it needs this first.

PROOF — this one is visual, so measure AND show

  T1. Before/after frames for each of the three logged defects. Rendered
      frames, not descriptions.
  T2. For one video of each type, the measured box vs the old estimate for
      every text block: how far off was size * 1.35, per block, in pixels.
      That number is the finding — if it is small everywhere, the estimate was
      not the problem and I want to know that too.
  T3. Re-render one video of every type and diff frames against the previous
      render. Anything that moved, moved because the measurement changed.
      Report the count of changed videos and eyeball one frame from each.
  T4. QA gate over the corpus, diffed against qa_baseline_2026-08-03.json.
      Nothing that passed may fail.

OUT OF SCOPE
  - 6b (text grouping cutting mid-phrase). Different subsystem — that is
    segmentation by character budget, not layout.
  - config/layout.py constants. Do not retune SAFE_AREA_TOP/BOTTOM or any
    Y position to compensate. If a measured box says something does not fit,
    the answer is the box, not a new magic number.
  - Backgrounds, animation timing, anything R1 touched.

GIT: one commit per task, push after each.

HOW TO WORK

Do (a) and the (b) TABLE, then STOP and show me before changing any call site.
Five of the nine are silently getting max_font today and I want to see the list
before their rendering changes.
````

---

## Dónde está el corte

En la tabla de (b), antes de tocar ningún renderer. Cinco de los nueve sitios están recibiendo `max_font` sin ajustar nada; arreglar la medición les cambia el render a todos a la vez. Verlo antes cuesta un round-trip.

## Qué espero que salga mal

Que T2 diga que `size * 1.35` estaba **cerca** en la mayoría de bloques. Manrope no es una fuente de métricas raras y la constante probablemente acierta dentro de unos pocos píxeles en texto de una línea. Si es así, el defecto no es la constante — es el punto 2 de arriba, los sitios que pasan `max_height=None` y por tanto nunca ajustan. Serían dos bugs con la misma cara, y el segundo es el que importa.

**Si los tres defectos no caen con la caja medida, el diagnóstico compartido era falso** y hay que tratarlos por separado. Es un resultado válido y prefiero verlo declarado a que se parcheen tres cosas y se llame raíz común.
