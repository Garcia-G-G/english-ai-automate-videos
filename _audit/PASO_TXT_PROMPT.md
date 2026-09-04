# TXT — la puntuación deja de ser una palabra

**Una cosa. Nada más.** Sin duración, sin tipos nuevos, sin dashboard, sin fondos.

---

## El defecto, visto y medido

Tres capturas del dueño, tres síntomas, **una causa**:

```
, que significa uno.          ← coma huérfana abriendo la tarjeta
. ¡Genial! Ahora, ... y       ← punto huérfano abriendo, y corte a mitad de frase
' four ' balloons             ← comillas flotando como palabras
a different size? .           ← punto huérfano, resaltado en azul como palabra
```

El último es de un render de hoy (`art_20260903_172117`), y ahí el punto se dibuja **resaltado por el karaoke**, como si fuera una palabra que se está pronunciando.

**Medido en todo el corpus** — 109 sidecars con timeline de palabras, **10 los tienen**, 63 tokens en total:

| forma | veces |
|---|---|
| `.` | 45 |
| `,` | 6 |
| `'` | 4 |
| `=` | 4 |
| `¿` | 3 |
| `?` | 1 |

## El mecanismo

La alineación de ElevenLabs devuelve la puntuación como **tokens independientes con su propio `start` y `end`**.

`src/animations/subtitle_processor.py:296`:

```python
lower = text.lower().strip('.,!?¿¡')
```

**El código ya sabe que la puntuación no es contenido: la quita para clasificar. Pero nunca quita el token.** Un token que es solo `.` deja `lower = ''` — y sigue en el grupo, ocupando sitio.

Peor, en la rama inglesa (`:312`):

```python
if last_lower in self.CONNECTORS or len(last_lower) <= 4:
```

`''` tiene longitud 0, así que **pasa el test de conector corto** y se arrastra al grupo inglés. Eso es exactamente `' four ' balloons`.

Y hay una tercera consecuencia que no se ve pero importa: un token huérfano **se queda con su propio tramo de tiempo**. En el trabajo de C se midió `'(noun)' 3.07 → 4.12` — 1.05 s para algo que no se pronuncia. Un `.` suelto hace lo mismo, y ese tramo entra en la declaración que el gate mide.

---

## PROMPT — TXT

````
You are in ~/Downloads/english-ai-videos.

ONE THING. Do not touch duration, new video types, the dashboard, or
backgrounds. When this is done and proven, we move on.

THE DEFECT

ElevenLabs alignment returns punctuation as SEPARATE tokens with their own
start and end. Nothing merges them back, so a token whose entire content is
punctuation survives into the word timeline and is treated as a word.

Three symptoms the owner reported, one cause:

    , que significa uno.        leading orphan comma
    . ¡Genial! Ahora, ... y     leading orphan period, phrase cut mid-clause
    ' four ' balloons           quote marks floating as words
    a different size? .         orphan period, HIGHLIGHTED by the karaoke

The last is from today's render, art_20260903_172117.

Measured across the corpus: 109 sidecars carry a word timeline, 10 of them
contain orphan tokens, 63 tokens in total —
    '.' 45   ',' 6   "'" 4   '=' 4   '¿' 3   '?' 1

THE MECHANISM, so you fix the cause and not the symptom

subtitle_processor.py:296

    lower = text.lower().strip('.,!?¿¡')

The code ALREADY knows punctuation is not content — it strips it to
classify. It just never removes the token. A '.' token leaves lower = '',
stays in the group, and takes a slot.

And at :312, in the English branch:

    if last_lower in self.CONNECTORS or len(last_lower) <= 4:

'' has length 0, so a punctuation token passes the short-connector test and
gets pulled into the English phrase. That is ' four ' balloons exactly.

WHERE TO FIX IT — this is the part that matters

Fix it in the TIMELINE, not in group_words.

The timeline is not only used for display. An orphan token keeps its own
time span — the C work measured '(noun)' spanning 3.07 → 4.12, 1.05 s for
something never spoken — and those spans feed measure_speech_end, the
declared-silence envelope and the QA gate. Fixing only the grouper leaves
the timing polluted and the gate still reading a span that is not speech.

Merge each punctuation-only token into the PRECEDING word: the merged word
keeps its own start, takes the punctuation's end, and its text gains the
mark. If there is no preceding word in the same segment, merge into the
following one instead. No token is dropped and no time is lost — the span
is absorbed, not deleted.

Then leave group_words alone unless a test shows it still misbehaves. If the
timeline is clean, the connector test at :312 never sees an empty string.

REPORT, DO NOT FIX

'=' appears 4 times as a spoken token. An equals sign is not something a
narrator says. Find where it comes from and tell me — that smells like a
script-generation artifact leaking into narration, and it is a different
bug.

PROOF

  P1. Re-run the corpus survey. Orphan tokens must be 0 across all 109
      sidecars after re-processing, or you must say which survive and why.
  P2. Render one educational video. Show three frames: one where a card
      previously began with orphan punctuation, one mid-card, one with an
      English phrase in quotes. No floating marks, no highlighted periods.
  P3. The same video's timing: no declared span belongs to a token that is
      not speech. Show a before/after on one segment.
  P4. Confirm the QA gate result is unchanged or better — this touches the
      declarations the gate reads, so it must not move dead_air the wrong
      way.
  P5. Full test suite, plus a test pinning that a punctuation-only token
      never reaches the grouper.

COST
  One render. Report it.

DO NOT
  - Touch duration, types, dashboard, backgrounds, the CTA.
  - "Improve" grouping while you are in there. If grouping still cuts badly
    after the timeline is clean, that is the NEXT thing, reported not fixed.
````

---

## Por qué el corte está en el timeline y no en el agrupador

Porque el mismo defecto tiene dos víctimas y solo una se ve. Arreglar `group_words` limpia la pantalla y deja al gate leyendo un tramo de 1 s que nadie pronunció. Ya nos pasó en C: el síntoma visible y el que mide estaban separados, y arreglar el visible habría dejado el otro vivo.
