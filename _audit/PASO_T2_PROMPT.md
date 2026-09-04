# T2 — precisión del contenido: objetivo por ítem, tema coherente, tiempos reales

Tres cosas, todas de contenido y precisión. Ninguna es fontanería.

---

## A · El objetivo de palabras tiene que ser por ítem

Tu diagnóstico es correcto: el modelo trata *"3 preguntas"* como vinculante y el conteo como orientativo. Pero eso no se arregla insistiendo.

*"3 preguntas, 107 palabras"* son **dos restricciones**, una contable y otra agregada. El modelo satisface la que puede contar.
*"3 preguntas, cada una con explicación de 35-40 palabras"* es **una sola**, contable, y la sigue.

Y no es relleno. Medido en los guiones reales:

| | explicación por pregunta |
|---|---|
| quiz de agosto | 24-30 palabras |
| quiz nuevo | **19-26 palabras** |

**Se acortaron.** Subirlas a 35-40 es donde vive la enseñanza, y ataca lo que el dueño dijo del guion: *"está bueno, no es nada del otro mundo."*

## B · El tipo de video y la categoría del tema se eligen por separado

Reportaste que `pronunciation` sacó *"How Are You? (Not a Real Question)"* y *"Double negatives (grammatical error)"*, y lo atribuiste a que los ficheros de temas dan títulos.

**No es eso.** Auditado `content/topics/pronunciation.json`: 56 temas, y los que parecen títulos son legítimos —`ship vs sheep`, `bit vs beat`, `REcord (noun)`, `water (British vs American)`— **pares mínimos y desplazamientos de acento**, que es exactamente el contenido que toca.

Esos dos temas **no están en el fichero de pronunciation**. Vienen de otras categorías.

La causa es estructural: `video_type` y `category` son **sorteos independientes**. `legacy_pipeline.generate()` resuelve el tipo desde la petición o el perfil, y por separado llama a `_random_topic(allowed_categories=...)` sin mirar el tipo. Nada impide que un video de `pronunciation` saque un tema de `grammar`.

No afecta solo a pronunciation: **cualquier cruce es posible hoy.**

## C · Los tiempos son estimados, y eso ya bloquea un tipo

```
pronunciation   final_qa PASS     51.5s   ← pausa de 0.03s
pronunciation   final_qa REJECT   52.7s   ← pausa de 0.90s, ['dead_air:3.184s']
```

**Arreglar la pausa es lo que provocó el rechazo.** La pausa es la pedagogía que el dueño pidió, y la puerta la refusa porque la declaración solo explica 0.33-0.44 s de cada hueco de 1.6 s — la estimación proporcional a caracteres se pasa ~1.2 s del final real del habla.

Es la deuda **D5**, aplazada "hasta que entre ASR" desde el Paso 2 en julio. Era tolerable mientras nada producía pausas reales.

**Y ya está pagada:**

| | |
|---|---|
| `requirements.txt:16` | `openai-whisper>=20231117` — *"Not imported anywhere today. Kept deliberately: local Whisper is planned"* |
| `tts_openai.py:337` | `extract_timestamps_whisper()` — ya existe, usa `whisper-1` |
| coste API | $0.006/minuto → **~$0.005 por video de 50 s** |
| coste local | **$0.00** |
| gasto histórico | 1 llamada, $0.0060 |

El camino de producción es ElevenLabs, y ése nunca pasa por Whisper. La función existe y la dependencia está declarada.

---

## PROMPT — T2

````
You are in ~/Downloads/english-ai-videos. Three items, all content
precision. Land them in order; each is independently useful.

A · THE WORD TARGET MUST BE PER ITEM

The three short types missed because the model treats "3 questions" as
binding and a whole-script word count as advisory. Do not push harder on the
aggregate — restate it as a per-item constraint the model can count:

    "3 questions, each with a 35-40 word explanation"
  not
    "3 questions, 107 words total"

This is not padding. Measured in the real scripts: August quizzes carried
24-30 word explanations per question; the new ones carry 19-26. They got
SHORTER. Restoring and deepening them is where the teaching lives.

Derive the per-item budget from the type's measured rate and overhead, the
same arithmetic as before — just expressed per item.

Also apply the umbrella-segment rate correction you found and left for me:
quiz 107 → ~114, fill_blank 115 → ~107. The figures in config.yaml are known
to be wrong; leaving them would be preserving a known error on purpose.

B · VIDEO TYPE AND TOPIC CATEGORY ARE INDEPENDENT DRAWS

Your finding was right, your cause was not. content/topics/pronunciation.json
is fine: its 56 entries include ship vs sheep, bit vs beat, REcord (noun),
water (British vs American) — minimal pairs and stress shifts, exactly the
right content in a different shape.

"How Are You? (Not a Real Question)" is NOT in that file. It came from
another category, because legacy_pipeline.generate() resolves video_type
from the request/profile and separately calls _random_topic() without
consulting it. Nothing constrains which categories a type may draw from.

This is not a pronunciation problem. Any mismatch is currently possible.

  b1. MEASURE FIRST. Across the whole corpus of rendered artifacts, how
      often did the drawn category not suit the video type? Report the rate
      and the worst examples. If it is rare, this is smaller than it looks;
      if it is common, a lot of past output was teaching the wrong shape.

  b2. Then constrain it: each video type declares which categories it may
      draw from, in config, next to the duration bands. Do not hardcode a
      mapping in the picker.

      Propose the mapping and give your reasoning per type — I will review
      it before it lands. pronunciation drawing only from pronunciation is
      obvious; the others are judgement calls and I want yours.

      A type with no valid category must fail loudly, not fall back to a
      random draw.

C · REAL TIMINGS, NOT ESTIMATES

pronunciation is IN BAND AND CANNOT SHIP: final_qa REJECT on dead_air:3.184s.
The 0.90 s pedagogical pause you correctly implemented is what triggers it,
because the declaration only explains 0.33-0.44 s of each 1.6 s gap.

That is D5 — char-proportional word estimation, deferred since July "pending
ASR". The deferral is over, because it now blocks a feature the owner asked
for.

And it is already paid for:
  requirements.txt:16   openai-whisper>=20231117, declared and never imported
  tts_openai.py:337     extract_timestamps_whisper(), exists, uses whisper-1
  cost                  $0.006/min API (~$0.005 per 50s video) or $0 local

The production path is ElevenLabs and never passes through Whisper.

  c1. Run ASR over the synthesised narration and use the real word and
      segment ends in place of the estimate. Prefer local Whisper — the
      dependency is declared for exactly this — and fall back to the API,
      reporting which ran and what it cost.

  c2. The declared-silence envelope then reflects real speech ends, and
      pronunciation's pauses become explained rather than dead air.

  c3. Report, do not fix: what this does to educational's karaoke alignment.
      D5 is also the mechanism behind the word-level lead reported back in
      March. If real timings improve it, that is a second debt closing and
      I want the measurement, not a change.

PROOF

  P1. A + the rate correction: one render of quiz, fill_blank and
      true_false. Duration, and the per-item explanation word counts.
      Types still out of band are the finding — report, do not retune.
  P2. b1's mismatch table before b2 lands, and your proposed mapping with
      reasoning.
  P3. pronunciation re-rendered with real timings: final_qa PASS, the pause
      still audible, and the dead_air figure before and after.
  P4. c3's educational measurement.
  P5. Which ASR ran, and the real cost.
  P6. Full test suite.

COST
  A handful of renders plus ASR. Well under the $0.30/video ceiling. Report
  the real figure.

OUT OF SCOPE
  - New video types.
  - vocabulary's row-5 text under its badge — logged, layout step.
  - The option-card contrast question still open from V1.

HOW TO WORK

Land A first — it is the smallest and its result is a clean number.
Then STOP after b1's table and your proposed mapping. The mapping is a
content decision and I want to see it before it constrains what gets drawn.
````

---

## Lo que espero que salga de b1

Que el cruce sea frecuente. Hay 20 categorías y 6 tipos sorteados por separado, así que el acierto por azar es bajo — y eso significaría que **una parte grande de lo publicado enseña la forma equivocada**: un video de pronunciación explicando un error gramatical, un vocabulary sobre un modismo. Si sale así, no es un defecto de un tipo: es la mitad del catálogo mal emparejado, y explica más de la sensación de *"no es nada del otro mundo"* que cualquier ajuste de guion.
