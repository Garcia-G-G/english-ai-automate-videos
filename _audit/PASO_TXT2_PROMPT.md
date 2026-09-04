# TXT · segunda mitad — terminar el mismo bug

**No es un paso nuevo. Es el mismo, sin acabar.**

Los tokens huérfanos están a cero: 118 sidecars, 63 → 0. Eso está bien hecho, y la decisión de no fusionar hacia atrás entre clips es correcta — habría estirado el fin declarado sobre el hueco entre clips y recreado el defecto que cerró C, a cambio de algo cosmético.

Pero el criterio acordado es que el dueño lo vea limpio en un frame. **El frame sigue diciendo `.Este verbo es muy útil`.**

## Lo que queda, medido

```
segmentos analizados: 92
que empiezan con puntuación de CIERRE (. , ; :): 4     ← todos en art_20260903_175853

  '.Este verbo es muy útil y significa aparecer'
  '.Por ejemplo, si digo He didn't show up to la meeti'
  '.Un tip para recordar esto: piensa en una fiesta.'
  '.Excelente,'
```

Medí primero con una regla demasiado ancha —20 de 70— y contaba `¿` y `¡` abriendo frase, que son correctos. Afinada a puntuación de cierre: **4**. Concentrados, no dispersos.

Y el segundo caso lleva **los dos defectos que quedan a la vez**: abre con punto pegado, y contiene `didn'tshow`.

---

## PROMPT — TXT segunda mitad

````
You are in ~/Downloads/english-ai-videos.

STILL ONE THING. This is the same bug, unfinished — not a new step. Nothing
about duration, types, dashboard or backgrounds.

The orphan-token half is done and correct: 63 → 0 across 118 sidecars, and
you were right not to merge backwards across clips. Two visible defects
remain, and the owner's criterion is a clean frame.

1 · SENTENCE-FINAL PUNCTUATION LEADS THE NEXT CHUNK

Measured, narrowed to CLOSING marks only (an opening ¿ or ¡ is correct and
must stay):

    92 segments analysed · 4 begin with a closing mark, all in
    art_20260903_175853

      '.Este verbo es muy útil y significa aparecer'
      ".Por ejemplo, si digo He didn't show up to the meeting"
      '.Un tip para recordar esto: piensa en una fiesta.'
      '.Excelente,'

Note there is no space after the period — it is glued to the next word.

Your own diagnosis names the place: tts_segmenter puts the period at the
START of the following chunk instead of keeping it with the sentence it
ends. Fix it there. A chunk must end with its own closing punctuation and
must not begin with someone else's.

Do NOT solve this by merging backwards at timeline level. You already
established why, and that reasoning stands.

2 · THE MISSING SPACE AT AN APOSTROPHE

    He didn'tshow up to the meeting

You measured that the timeline is right — didn't (10.49→10.75) and show
(10.78→10.97) are separate, correct tokens — and that the group text keeps
its space. So the defect is at DRAW time, in how the karaoke renderer lays
words out.

Find it and fix it. Report what it actually was; I have not verified a
mechanism for this one and I am not going to guess one for you.

PROOF — the owner judges this, so it is frames

  P1. The corpus check again: closing-mark-leading segments must be 0, and
      orphan tokens must still be 0. Both, so the first fix has not
      regressed.
  P2. Re-render the SAME video, art_20260903_175853. Frames of the four
      cards that currently open with a period, and the one carrying
      didn'tshow. Clean, or say which are not.
  P3. Opening ¿ and ¡ still open their cards correctly — show one. If the
      fix eats those, it is worse than the bug.
  P4. The QA gate unchanged or better, and the timing declarations
      untouched: this must not move dead_air.
  P5. Full test suite, plus a test pinning that no segment begins with a
      closing mark.

COST
  One re-render. Report it.

DONE MEANS
  A frame the owner can look at with no punctuation opening a card, no
  floating marks, and no glued words. Not "the tokens are zero".
````

---

## La regla que este paso deja

> **Cero en la métrica no es cero en la pantalla.** Los tokens huérfanos llegaron a 0 y el defecto seguía siendo visible, porque el síntoma tenía dos causas y la métrica solo cubría una. La condición de terminado la pone el frame, no el contador.
