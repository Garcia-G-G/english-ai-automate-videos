# T1 — la duración pasa a ser una especificación, no un accidente

**Decisión del dueño:** todos los videos entre **50 s y 1:20 (80 s)**. Enfoque **mezclado** — más contenido en los que van muy cortos, repetición pedagógica en el resto.

---

## Dónde estamos, medido sobre los 29 videos que existen

| tipo | media | en 50-80 s |
|---|---|---|
| educational | 69.1 s | **4/6** |
| quiz | 44.0 s | 1/9 |
| fill_blank | 38.5 s | 0/5 |
| true_false | 27.7 s | 0/4 |
| vocabulary | 24.5 s | 0/3 |
| pronunciation | 20.6 s | 0/2 |

**5 de 29 en rango.** `educational` ya está dentro — pero uno de sus seis midió **86 s**, o sea que también necesita **techo**, no solo suelo. La petición es una banda, y hoy no hay nada que haga cumplir ninguno de los dos bordes.

## Y la duración no se pide en segundos, se pide en palabras

Tasa de habla medida sobre los sidecars de audio reales:

| tipo | palabras/s | overhead aprox. (video − narración) |
|---|---|---|
| educational | 2.21 | **~20.8 s** |
| pronunciation | 1.94 | ~2 s |
| fill_blank | 1.91 | — |
| quiz | 1.85 | ~10.7 s |
| true_false | 1.57 | ~3.5 s |
| vocabulary | **1.31** | ~3.1 s |

Mediana global 1.94 pal/s. **Pero usarla sería un error:** `vocabulary` habla a 1.31 y se pasaría un 45%.

⚠️ **Los overheads de arriba salen de conjuntos NO emparejados** — la media de audio de un grupo contra la media de video de otro. Este proyecto ya se equivocó así antes (*"medir en la etapa que envía"*). Hay que recalcularlos por artefacto emparejado antes de usarlos.

`educational` con ~21 s que no son narración conecta con el 30 % de aire muerto que R1 midió. **No lo arregles aquí**, pero anota si el número se confirma emparejado.

---

## PROMPT — T1

````
You are in ~/Downloads/english-ai-videos.

THE REQUIREMENT

Every video lands between 50 s and 80 s. Both edges matter: one educational
already measured 86 s, so this is a BAND, not a floor.

Today 5 of 29 videos are in range. Nothing in the pipeline aims at a
duration — it is whatever the script model happened to write, plus whatever
fixed structure the type adds.

THE APPROACH — the owner chose a mix

  more CONTENT for the ones that are far too short
      pronunciation  20.6 s  (needs ~3x)
      vocabulary     24.5 s
      true_false     27.7 s

  pedagogical REPETITION for the rest
      quiz 44.0 s · fill_blank 38.5 s

  a CEILING for educational, which is already in range and drifts over it

Repetition here means saying the English phrase two or three times with a
real pause — the "repeat after me" that language teaching actually uses. It
is not padding, and it must not become padding: no longer countdowns, no
dead air, no looping clips. The owner said the pacing is currently good and
this must not break it.

STEP 1 — MEASURE PROPERLY, BEFORE CHANGING ANYTHING

I measured speech rate per type from the audio sidecars:

    educational 2.21   pronunciation 1.94   fill_blank 1.91
    quiz 1.85          true_false 1.57      vocabulary 1.31   (words/s)

Global median 1.94, and using it would overshoot vocabulary by 45%.

But my overheads (video duration minus narration duration) come from
UNPAIRED sets — one group's audio mean against another group's video mean.
Recompute them per artifact, where the mp3 and the mp4 are the same video.

Report per type: speech rate, fixed overhead, and what those imply for a
50 s and an 80 s video:

    target_words = (target_duration - overhead_for_type) * rate_for_type

If a type's overhead turns out very different from mine, say so — that is a
finding, and for educational (~20.8 s by my rough figure) it touches the
30% dead-air measurement R1 made. Do not fix that here; report it.

STEP 2 — DURATION BECOMES A SPECIFICATION

  a. Each type carries a duration band and a derived word target, in config,
     not hardcoded in a prompt string. The script generator receives the word
     target and aims at it.

  b. AFTER TTS, measure the real narration and compute the projected video
     duration. Out of band is a recorded finding on the artifact, in the same
     shape as the gate verdict — not a silent pass.

     Language models do not hit word counts precisely. That is exactly why
     the check goes AFTER the synthesis and not before it: the specification
     is the duration, and the word count is only the lever.

  c. vocabulary is the one where this pays twice. More pairs makes it longer
     AND fills the card that is 61% empty today. VOCAB_MAX_ROWS is logged
     debt — it exists and has never been enforced. Wire it here.

  d. pronunciation needs roughly three times its current length. It is also
     the type where repetition IS the pedagogy — hearing the word several
     times is the lesson, not filler. Use both levers on it.

  e. Repetition needs a real pause between takes. Check it against the QA
     gate's speech_in_declared_silence flag: a repeat that lands inside a
     declared-silent stretch must not trip it, and if it does, the timing
     declaration is what is wrong, not the gate.

PROOF

  P1. The Step 1 table: rate, overhead and word targets per type, computed
      from PAIRED artifacts. Show your pairing.
  P2. One render of EVERY type. Report each one's duration and whether it
      landed in 50-80 s. Types out of band after the change are the finding —
      report them, do not retune until we have seen the list.
  P3. The vocabulary render: its duration AND its card fill, against today's
      61% empty.
  P4. The pronunciation render, with the repetition audible, and the gate's
      silence flags clean.
  P5. An artifact deliberately pushed out of band, showing the check
      recording it rather than passing quietly.
  P6. Full test suite.

COST
  Six renders, roughly $0.40 total at current per-video cost. The owner
  approved up to $0.30 per video. Report the real figure.

OUT OF SCOPE
  - educational's dead air. Report the number, fix nothing.
  - New video types. Separate, and next.
  - The option-card contrast question still open from V1.

HOW TO WORK

Step 1 alone, then stop and show me the table. My rates come from real
sidecars, but my overheads do not survive scrutiny and the word targets are
built on them. I would rather correct the arithmetic than have six renders
built on it.
````

---

## Lo que espero que salga

Que `quiz` sea el más difícil. Sus ~11 s de estructura fija —cuenta atrás de 7 s más outro— no se pueden alargar sin romper el ritmo, así que toda la duración extra tiene que salir de la narración, y una pregunta de quiz no da para 128 palabras sin volverse pesada. Si es así, la respuesta honesta para `quiz` no es alargar el guion: es una segunda pregunta, y eso es un cambio de formato que hay que decidir viéndolo.
