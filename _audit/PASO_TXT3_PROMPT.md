# TXT · tercera parte — una tarjeta, una oración

**Sigue siendo el mismo bug.** El dueño lo dijo así:

> *"hay una coma cerrando una oración, eso debería ser un punto, y si tiene que continuar debería estar la frase u oración entera"*

Una tarjeta que acaba en coma se lee como cortada. Y en el render limpio de `punctfix` la tarjeta dice `...to the meeting,` y ahí termina.

## Por qué se parte, medido

Oraciones de ese video, en palabras:

```
 2   ¡Hola, amigos!
 9   Hoy vamos a aprender el phrasal verb show up.
 8   Este verbo es muy útil y significa aparecer.
19   Por ejemplo, si digo He didn't show up to the meeting, significa que él no apareció...
20   También podemos usarlo en otras situaciones, como She always shows up late, ...
13   Y un último ejemplo: Thanks for showing up, que significa Gracias por aparecer
 9   Un tip para recordar esto: piensa en una fiesta.
 7   Si no show up, no te diviertes.
 7   Ahora, repite conmigo: He didn't show up.
 1   Excelente,
 2   ¡lo hiciste!
12   ¿Cuándo fue la última vez que show up en un lugar importante?
```

`subtitle_processor.py:140` — **`max_words_per_group = 8`**.

Ocho. Por eso una oración de nueve palabras se parte.

**Y no es un límite de espacio.** `MAX_CHARS_PER_LINE = 40` × 3 líneas ≈ 120 caracteres:

| oración | caracteres | ¿cabe en la tarjeta? |
|---|---|---|
| *Hoy vamos a aprender el phrasal verb show up.* | 45 | sí, de sobra |
| *Por ejemplo, si digo He didn't show up to the meeting, significa que él no apareció a la reunión.* | 97 | **sí** |

La tarjeta puede con ellas. **El tope de 8 es una política, no una restricción física.**

---

## PROMPT — TXT tercera parte

````
You are in ~/Downloads/english-ai-videos.

SAME BUG, STILL. This is the grouping half you were told to leave alone
while the timeline was being fixed. The timeline is clean; this is what
remains. Nothing about duration, types, dashboard or backgrounds.

THE RULE THE OWNER GAVE

  "a comma closing a sentence should be a period, and if it has to
   continue, the whole sentence should be there"

A card must not end on a comma. Prefer one whole sentence per card.

WHY IT SPLITS — measured, so you fix the cause

subtitle_processor.py:140 sets max_words_per_group = 8.

The sentences in the punctfix render run 1, 2, 2, 7, 7, 8, 9, 9, 12, 13,
19, 20 words. So a perfectly ordinary nine-word sentence — "Hoy vamos a
aprender el phrasal verb show up." — is split by an eight-word cap.

And 8 is NOT a space limit. MAX_CHARS_PER_LINE = 40 over three lines is
about 120 characters:

    "Hoy vamos a aprender el phrasal verb show up."          45 chars
    "Por ejemplo, si digo He didn't show up to the
     meeting, significa que él no apareció a la reunión."    97 chars

Both fit. The card can hold them; the policy will not let it.

TASK

  a. GROUP BY SENTENCE, NOT BY WORD COUNT.
     The unit is the sentence — the segment boundary you already respect.
     A sentence that fits the card goes on one card, whole.

     Drive the decision from MEASURED width and height, the way
     fit_text_font measures, not from a word count. A word cap can stay as a
     last-resort guard, but it must be far above 8 and it must never be what
     splits an ordinary sentence.

  b. WHEN A SENTENCE GENUINELY DOES NOT FIT.
     Some will not, even with the font scaled to its floor. Then:
       - split at a clause boundary, never mid-clause
       - and the card MUST NOT END ON A COMMA. If the natural split leaves
         a trailing comma, move the split.
     Say which rule you chose for choosing the split point and why.

  c. THE FONT MAY SCALE, BUT NOT WITHOUT A FLOOR.
     A whole sentence on one card means longer cards and smaller type. Set
     the floor deliberately and tell me what it is. Below it, (b) applies.

DEPENDENCY YOU MUST CHECK BEFORE YOU FINISH

Longer cards are TALLER cards, and this repo has an open, measured defect
where a card draws past its own budget and lands on the watermark:

  quiz.py:832-856 — slide_offset is charged to the text budget, and
  fit_text_font returns the minimum font even when nothing fits, and the
  caller draws it anyway. Logged as L1, not fixed.

If educational's card shares that shape, taller cards will re-create the
collision the owner already photographed. Check it. If it does, say so and
STOP rather than shipping a fix that re-opens a defect he has already seen
once.

PROOF — frames, as before

  P1. Re-render the same video. A frame of each card. No card ends on a
      comma; the nine-word and the 19-word sentences each hold together, or
      you name which could not and why.
  P2. Card height and the watermark's top edge, per card, measured. No
      overlap on any of them.
  P3. The smallest font any card used, against the floor you set.
  P4. Orphan tokens still 0 and closing-mark-leading segments still 0 — the
      earlier halves must not regress.
  P5. Full test suite, plus a test that no rendered group ends on a comma.

COST
  One re-render. Report it.

DONE MEANS
  The owner reads a card and it is a whole thought. Not a word count.
````

---

## Lo que espero que salga

Que las de 19-20 palabras entren, pero con la tipografía bastante más pequeña, y que ahí aparezca la colisión con el watermark que Garcia ya fotografió una vez. Si pasa, es mejor pararse ahí que entregar una tarjeta entera aplastando la marca — porque eso sería cambiar un defecto que ve por otro que también ve.
