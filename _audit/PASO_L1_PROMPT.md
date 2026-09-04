# L1 — la caja dice que no cabe, y se dibuja igual

**Presupuesto nuevo, decidido por el dueño: hasta $0.30 por video.** Hoy un quiz cuesta $0.070 y un educational $0.0995, así que hay margen de sobra. **Nada de este paso cuesta dinero** — el defecto es de layout.

---

## El mecanismo, entero

`src/video/quiz.py:832-856`:

```python
slide_offset = int(60 * (1.0 - ease_out_cubic(slide_progress)))
exp_y_base   = COUNTDOWN_ZONE_TOP + 10
exp_y        = exp_y_base + slide_offset
max_exp_h    = watermark_top() - exp_y - exp_padding * 2

ef, exp_font_size, exp_lines, exp_text_h = fit_text_font(
    clean_exp, 42, 28, max_exp_w, max_exp_h
)
exp_height = len(exp_lines) * exp_line_h + exp_padding * 2
```

### Defecto 1 · El desplazamiento de la animación se cobra del presupuesto de texto

`slide_offset` es un desplazamiento **visual** de la entrada de la tarjeta: empieza 60px más abajo y sube en 0.4 s. Pero entra en `exp_y`, y `exp_y` es de donde sale `max_exp_h`.

Resultado: **el presupuesto se encoge 60px al principio de la animación y crece mientras la tarjeta sube.** Y `fit_text_font` se llama por fotograma, así que el texto se re-ajusta contra un presupuesto que se mueve.

En el primer fotograma de la explicación el presupuesto es el mínimo. El log lo midió: **53px**.

Esto es exactamente la deuda registrada de 6c — *"`exp_y` + `slide_offset` llevan el presupuesto a −6px"*. Está en producción.

### Defecto 2 · Y éste es el de fondo

Con 53px de presupuesto, ni la fuente más pequeña (28) cabe: tres líneas necesitan ~105px. `fit_text_font` **devuelve el mínimo igualmente**, y el llamador dibuja.

Y la altura de la tarjeta sale de las líneas, no del presupuesto:

```python
exp_height = len(exp_lines) * exp_line_h + exp_padding * 2
```

**El presupuesto se respeta al calcular y se ignora al dibujar.** No existe el resultado "no cabe".

Por eso `learningroutes.com` acaba encima de la tercera línea: la tarjeta crece hacia abajo y atraviesa la marca. El `watermark_top()` que se añadió en 6a para evitar justo esto se consulta correctamente — y luego se desborda por encima de su propia respuesta.

> Es la hermana de una regla que este repo ya se ganó: *un default solo puede renderizar MENOS, nunca algo falso.* Aquí: **cuando la caja dice que no cabe, dibujar igual es la falsedad.**

### Y el gate lo aprobó

`final_qa: PASS` sobre ese fotograma. El gate mide contraste de texto contra fondo; **no mide texto contra texto.** Un elemento tapando a otro puntúa perfecto. Cuarta instancia de ceguera del techo.

---

## PROMPT — L1

````
You are in ~/Downloads/english-ai-videos. Budget is now up to $0.30 per
video, but nothing here costs money — this is layout.

THE DEFECT, MEASURED

In art_20260902_213027_1319e696 (which passed the gate) the watermark
"learningroutes.com" is drawn ON TOP of the third line of the quiz
explanation card. Two causes, in quiz.py:832-856.

  1. THE ANIMATION'S OFFSET IS CHARGED TO THE TEXT BUDGET.

       slide_offset = int(60 * (1.0 - ease_out_cubic(slide_progress)))
       exp_y        = exp_y_base + slide_offset
       max_exp_h    = watermark_top() - exp_y - exp_padding * 2

     slide_offset is a VISUAL entrance displacement. It has no business
     shrinking the space the text is allowed to occupy — but it feeds exp_y,
     and exp_y is what the budget is computed from. So the budget shrinks by
     60px at the start of the animation and grows as the card rises, and
     fit_text_font re-fits every frame against a MOVING budget.

     At the first explanation frame the budget bottoms out. Measured: 53px.

     This is the logged 6c debt — "exp_y + slide_offset driving the budget to
     -6px" — live in production.

  2. THE BUDGET IS HONOURED IN THE CALCULATION AND IGNORED IN THE DRAWING.

     At 53px not even the 28px floor fits: three lines need ~105px.
     fit_text_font returns the minimum font anyway, and the caller draws it.
     The card's height then comes from the LINES, not the budget:

       exp_height = len(exp_lines) * exp_line_h + exp_padding * 2

     So the card grows downward through the watermark. There is no
     "does not fit" outcome anywhere in this path.

TASK

  a. MEASURE FIRST, ACROSS THE CORPUS. Do not fix anything yet.

     For every quiz and true_false artifact on disk, report:
       - the explanation's character count
       - the budget it would get at slide_offset=60 and at slide_offset=0
       - the height the fitted text actually needs
       - by how much it overflows, if it does

     I want to know whether this is one long explanation or the normal case.
     The answer changes the fix: if most explanations overflow, the card is
     positioned wrong; if one does, the generator is producing text longer
     than the design allows. Report the table before proposing anything.

  b. THE BUDGET STOPS PAYING FOR THE ANIMATION.
     Compute max_exp_h from exp_y_base. The slide is a DRAW-TIME transform:
     apply it to where the card is painted, never to how much room its text
     is allowed. Same defect exists at true_false.py:601 — check and fix
     both.

  c. "DOES NOT FIT" MUST BE A REAL OUTCOME.
     fit_text_font must be able to say the block does not fit at the minimum
     size. What the caller then does is a design decision, and I want your
     recommendation with reasoning rather than a silent choice. The options
     I see:
        - raise the card (takes space from the options block)
        - cap explanation length at generation time
        - clamp and truncate (loses part of the lesson — I dislike this)
        - refuse, and let the gate reject the artifact
     Say which and why. Whatever you pick, drawing past the budget is not
     one of the options.

  d. THE GATE LEARNS TO SEE OVERLAP.
     This artifact scored final_qa: PASS with the brand mark on top of the
     lesson. The gate measures text against background, never text against
     text. Add an overlap check between the watermark's box and any drawn
     card. Without it this recurs and passes again.

PROOF

  P1. The (a) table, before any fix.
  P2. The same artifact re-rendered: frame at the first explanation frame
      and at +0.5s. The watermark clear of the card in both.
  P3. A deliberately over-long explanation, showing whatever (c) chose,
      behaving as designed rather than overflowing.
  P4. The gate REJECTING a synthetic overlapping frame, and PASSING the
      fixed render.
  P5. Full test suite. Report the count.

OUT OF SCOPE
  - The Studio not receiving generated backgrounds. Separate, logged.
  - 6c's full layout engine. This is the one card, not the engine.
  - E2/E3/E5, D1/D2/D4, Task 8, Bilibili.

HOW TO WORK

(a) alone, then stop and show me the table. The fix depends on whether this
is the normal case or an outlier, and I would rather see the numbers than
have the fix chosen for me by a guess.
````

---

## Lo que espero que salga de (a)

Que la mayoría de explicaciones desborden. 122 caracteres en tres líneas no es un caso raro: es lo que produce el generador cuando le pides que explique una expresión con un ejemplo. Si es así, el defecto no es la explicación larga — es que la tarjeta está colocada donde no cabe una explicación normal, y `COUNTDOWN_ZONE_TOP + 10` es el número a mirar.
