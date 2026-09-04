# Paso F3 — el catálogo se mudó a los prompts

**Leído contra `HEAD b187ec3`.** Sucesor de `FONDOS_HALLAZGO.md`.

---

## Lo que observó el operador

> *"esta bien el concepto pero llevo los fondos a un lugar que no se, osea empezó a hacer fondos muy similares de un concepto que podría funcionar pero no es lo mejor"*

## Medido

14 imágenes generadas. Reconstruyendo qué prompt recibió cada una:

| escenario | imágenes |
|---|---|
| **`DEFAULT_SCENE`** — *"a quiet interior at night, one warm light source, most of the frame in shadow"* | **11** |
| `social` — low-lit bar table | 1 |
| `common_mistakes` — notebook on a dark desk | 1 |
| `business` — dark office after hours | 1 |

**11 de 14 con el prompt idéntico**, variando solo la frase del tema. Por eso todas son el mismo bar nocturno.

## La causa estructural

`CATEGORY_SCENES` tiene **11 claves**. `content/topics/` tiene **20 categorías reales**. Once caen al `DEFAULT_SCENE`:

`confusing_words` · `cultural` · `everyday_expressions` · `food_restaurant` · `grammar` · `kids_colors` · `kids_numbers` · `pronunciation` · `slang` · `spanish_specific` · `work_office`

Y dos claves son huérfanas — ninguna categoría las usa: `daily_life` y `food`. Las reales se llaman `everyday_expressions` y `food_restaurant`. El diccionario se escribió de memoria en vez de leer la carpeta.

**Además, una escena por categoría no basta.** Aunque estuvieran las 20, dos videos de la misma categoría comparten el mismo cuadro. `social` sale 6 veces en el historial.

## Mi error, y es de fondo

Argumenté que un catálogo escala como √N (40 imágenes → repetición en el video 8) y que generar por video **no se repite nunca**. La aritmética del catálogo era correcta. La conclusión no.

**El catálogo no desapareció: se mudó de las imágenes a los prompts.** Y ahí es un catálogo de tamaño ~1. Conté imágenes y no conté el espacio de prompts, que es lo que de verdad determina la variedad.

## Y engancha con el otro hallazgo

Los 11 escenarios dicen *dark / dimly lit / low-lit / at night / shadowed*, y `EXPOSURE` añade *"deep shadow"* y *"rich dark tones"*. El prompt se escribió **para pasar el gate de contraste**, y el gate premia la oscuridad.

Las dos cosas son la misma raíz: **un solo escenario oscuro satisface al gate perfectamente, así que nunca hubo presión para escribir más.** Variedad y viveza no las mide nadie.

---

## PROMPT — Paso F3

````
You are in ~/Downloads/english-ai-videos. HEAD is b187ec3.

STOP whatever is in flight on Paso D after the current commit. This comes
first: it is what the operator actually sees in every video.

THE FINDING, MEASURED

14 generated backgrounds. Reconstructing the prompt each one received:

  11x  DEFAULT_SCENE  "a quiet interior at night, one warm light source,
                       most of the frame in shadow"
   1x  social         "a low-lit bar table with glasses and a jacket"
   1x  common_mistakes "an open notebook and a pen on a dark desk"
   1x  business       "a dark modern office after hours"

Eleven of fourteen got the IDENTICAL prompt stem, varying only by the topic
phrase. That is why they all look like the same night bar.

Two structural causes:

  1. CATEGORY_SCENES has 11 keys. content/topics/ has 20 real categories.
     Eleven fall through to DEFAULT_SCENE: confusing_words, cultural,
     everyday_expressions, food_restaurant, grammar, kids_colors,
     kids_numbers, pronunciation, slang, spanish_specific, work_office.

     Two keys are orphans no category uses: daily_life and food. The real
     ones are everyday_expressions and food_restaurant. The dict was written
     from memory instead of from the directory.

  2. Even with all 20, ONE scene per category means two videos in the same
     category share a frame. social appears 6 times in the job history.

  3. Every stem asks for darkness (dark / dimly lit / at night / shadowed)
     and EXPOSURE adds "deep shadow" and "rich dark tones". The prompt was
     written to satisfy the contrast gate, and the gate REWARDS darkness —
     the darker the image, the higher the ratio. v_vs_b_sounds scored
     14.882:1 against a 4.5 floor because the background is barely there.

     Variety and vividness are measured by nothing. The gate is the only
     measured thing, and one dark stem satisfies it perfectly, so there was
     never pressure to write more.

WHAT THE OPERATOR ASKED FOR, VERBATIM, AND IS NOT GETTING

  "un fondo lindo como los vistosos de antes ... prefiero eso que estos
   solo de colores"

Vivid. Not a black frame with a lamp in it.

TASK

  a. STOP ASKING THE GENERATOR FOR DARKNESS.
     Remove dark / night / dimly lit / low-lit / shadowed / at dusk from the
     scene stems, and rewrite EXPOSURE. Ask for a vivid, colourful,
     well-lit image with an UNCLUTTERED middle band — uncluttered is a
     composition instruction, not a brightness one. Keep the "no text, no
     letters, no watermark, no legible faces" constraints exactly.

  b. COMPOSE THE READABILITY BAND IN CODE, NOT IN THE PROMPT.
     After the image is generated, composite a soft vertical gradient scrim
     over the band where the card sits, using the geometry already in
     config/layout.py. Soft and generous at both edges — a hard seam will
     look worse than the dark image did, and that is the main risk here.

     This is the point of the change: contrast becomes guaranteed BY
     CONSTRUCTION instead of being begged from the generator and checked
     afterwards. The gate goes back to being a safety net.

  c. FILL THE PROMPT SPACE. This is the part that fixes the operator's
     actual complaint.

     Build the scene table FROM content/topics/*.json — all 20 categories,
     no DEFAULT catch-all for a category that exists. Fix the two orphan
     keys.

     Give each category a LIST of scenes, not one. And make the prompt a
     COMPOSITION of independent axes rather than a single string:

        scene (per category, several)
      x light / time of day
      x palette
      x camera framing

     With ~4 scenes and ~4 light/palette variants the space per category is
     16+, and across 20 categories it is in the hundreds. Repetition becomes
     arithmetic instead of hope. Report the size of the space you built.

  d. SELECTION: deterministic per topic, but non-repeating in sequence.
     Seed from the topic slug so the same topic reproduces the same image,
     AND keep a small ledger of the last N (category, scene, palette) triples
     so consecutive videos do not land on the same combination. N is a
     judgement call — pick one and say why.

PROOF — this one is VISUAL. A number cannot settle it.

  P1. CONTACT SHEET. Generate 12 backgrounds spanning at least 8 different
      categories, including several from the same category, and compose them
      into ONE image, labelled with category + scene + palette.

      That sheet is the deliverable. The operator judges variety and beauty
      by eye; nothing else decides this.

  P2. Same 12, but rendered as actual video frames with a card on them, as a
      second sheet. Pretty and unreadable is a failure, and so is readable
      and dull. I need to see both together.

  P3. Report worst_ratio for all 12 and confirm every one clears the floor.
      IMPORTANT: a HIGH ratio is no longer a good sign. It is a floor check,
      not a score. Do not tune anything to raise it.

  P4. Distinct (category, scene, palette) triples used across the 12. Show
      the count. If any stem repeats within the sheet, the space is too
      small — say so rather than shipping it.

  P5. Full test suite. Report the count.

COST
  12 images x $0.041 = ~$0.49, plus whatever the frame renders need.
  Approved — the operator said "no pasa nada por el precio" for backgrounds.
  Report the actual figure from the ledger.

OUT OF SCOPE
  - Ken Burns amplitude. RENDER_ZOOM_RANGE stays (1.0, 1.0): the composition
    lives in the full frame and any zoom crops it away. Do not touch it.
  - The QA gate's own thresholds. We are removing its influence over the
    design, not recalibrating it.
  - Paso D (dashboard). Resume after this.
  - Text layout, vocabulary/pronunciation.

HOW TO WORK

Land (a) + (b) + (c) and produce the P1 sheet BEFORE (d). Selection strategy
is worthless if the images are still wrong, and the sheet is what tells us
whether they are.

If the scrim seam looks bad on any of the 12, STOP and show me that frame
before tuning it away. A visible seam may mean the whole scrim approach is
wrong, and I would rather see that than have it hidden under a softer
gradient.
````

---

## Dónde espero que falle

En (b), la costura del scrim. Sobre una imagen oscura no se ve nada; sobre una imagen viva y con textura, una banda oscura puede leerse como una barra pegada encima. Si pasa, la alternativa es pedirle a la imagen que tenga el sujeto arriba y abajo con centro liso — pero eso es volver a confiar en el generador, que es de lo que estamos saliendo. Por eso el prompt pide **ver** el frame malo antes de suavizar nada.

## La regla que sale de aquí

> **Contar el espacio, no las muestras.** Un catálogo de 40 imágenes se repite en el video 8 por √N. Generar por video parecía inmune — pero la variedad no la da el número de imágenes, la da **el número de prompts distintos**. 14 imágenes con 4 prompts son 4 imágenes con ruido.
