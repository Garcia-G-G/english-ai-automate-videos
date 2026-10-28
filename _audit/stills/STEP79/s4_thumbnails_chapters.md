# STEP 79 §4 — thumbnails and chapters

## Thumbnails (`thumbnail.py`, 1280×720)

The lesson's first wrong → right pair: a `transform` first, then a `sentence` with a `fix`, then a
sentence with a red highlight. The right form is the closest later sentence or `[[English]]` a
narration says that is the same sentence corrected (≥ 50 % of its words shared, a whole sentence):
a script's `fix` changes one chip («more» → «taller») and applied literally it gave «taller tall»,
«I have a.», «If it rains rain», so it is never applied. Two vocabulary lessons whose red marks
emphasis, not an error, carry an override in their JSON (`"thumbnail": {wrong, right}`):
morning-phrasal-verbs and phrasal-verbs-oficina. The wrong form struck in red, the right one big in
green with a tick, Bubi celebrating, the title in ≤ 5 words on the yellow marker; the forms never go
under 64 px (16 px at 320 wide). `renders.register` writes `<render>.thumb.jpg` and the ledger's
`thumbnail`; the YouTube upload sets it, falling back to the poster frame.

Sheet at 320 px wide: `s4/thumbnails_320.png` (local).

| lesson | hook |
|---|---|
| articulos-a-an-the | I have car. → I have a car |
| can-could-pedir | I can to swim. → I can swim |
| comparativos-superlativos | My brother is more tall than me. → My brother is taller than me |
| condicionales-0-1-2 | If it will rain, I will stay home. → If it rains, I will stay home |
| demo-motion | Where you live? → Where do you live? |
| falsos-amigos | Actually I live in Madrid. → Currently I live in Madrid |
| futuro-will-going-to | I will to call you tomorrow. → I will call you tomorrow |
| gerundio-o-infinitivo | I'm looking forward to see you. → I'm looking forward to seeing you |
| hacer-preguntas | What means this word? → What does this word mean? |
| make-vs-do | She did a mistake. → She made a mistake. |
| morning-phrasal-verbs | I wake up me at seven. → I wake up at seven. |
| much-many-a-lot | I have much work today. → I have a lot of work today |
| past-simple-irregulares | I goed to the office. → I went to the office |
| phrasal-verbs-oficina | I called off it. → I called it off. |
| preposiciones-in-on-at | I arrived to the airport in time. → I arrived at the airport on time. |
| present-perfect-vs-past | I have been to Paris last year. → I went to Paris last year |
| pronunciacion-ed | — (no correction: the poster frame stays) |
| reported-speech | She asked me where do I live. → She asked me where I lived |
| simple-vs-continuous | She working now. → She is working now. |
| there-is-there-are | In my street have a pharmacy. → In my street there is a pharmacy |
| third-person-s | He have coffee. → He has coffee. |
| used-to-soler | I am used to go there. → I used to go there. |

## Chapters (`renders.chapters_text`)

`00:00 Intro`, then each heading at its start in the render's timeline; a heading closer than 10 s to
the previous chapter or to the end is left out; under 3 chapters, no list. Below, the voiced lessons
from the s3 stills timelines (recorded timings; third-person-s has one estimated beat). §5's
renders write theirs from their own timelines.

**can-could-pedir** (394 s)

```
00:00 Intro
00:11 Parte 1 · El error de estructura
01:02 Parte 2 · Los tres trabajos de can
01:50 Parte 3 · Could no siempre es pasado
02:31 Parte 4 · La escalera de la cortesía
03:13 Parte 5 · En una conversación real
03:43 Parte 6 · Pedir favores en el trabajo
04:51 Parte 7 · Practica
05:43 Parte 8 · Resumen
```

**comparativos-superlativos** (506 s)

```
00:00 Intro
00:16 Parte 1 · El error de poner more a todo
01:10 Parte 2 · Cómo saber cuál es corta
02:26 Parte 3 · El than obligatorio
03:02 Parte 4 · El superlativo
03:58 Parte 5 · Los irregulares
04:29 Parte 6 · Cuando son iguales
05:10 Parte 7 · En una conversación real
05:47 Parte 8 · De compras
06:41 Parte 9 · Practica
07:29 Parte 10 · Resumen
```

**demo-motion** (136 s)

```
(fewer than 3 chapters: left out)```

**hacer-preguntas** (466 s)

```
00:00 Intro
00:29 Parte 1 · El problema
01:29 Parte 2 · La fórmula
02:32 Parte 3 · Preguntas de sí o no
03:22 Parte 4 · Cuando no hace falta do
04:30 Parte 5 · En una conversación real
05:11 Parte 6 · El error más común
05:49 Parte 7 · Practica
06:52 Parte 8 · Resumen
```

**make-vs-do** (461 s)

```
00:00 Intro
00:25 Parte 1 · El problema
01:15 Parte 2 · Make crea
02:00 Parte 3 · Do realiza
03:06 Parte 4 · Las parejas traicioneras
03:55 Parte 5 · En una conversación real
04:26 Parte 6 · El do que además ayuda
04:58 Parte 7 · En el trabajo
05:47 Parte 8 · Practica
06:46 Parte 9 · Resumen
```

**morning-phrasal-verbs** (444 s)

```
00:00 Intro
00:19 Parte 1 · ¿Qué es un phrasal verb?
01:04 Parte 2 · Los cinco de la mañana
02:57 Parte 3 · La gramática que esconden
03:45 Parte 4 · Una mañana real
04:26 Parte 5 · El error más común
05:12 Parte 6 · Practica
06:23 Resumen
```

**preposiciones-in-on-at** (466 s)

```
00:00 Intro
00:28 Parte 1 · La imagen que lo ordena todo
01:55 Parte 2 · El tiempo funciona igual
02:58 Parte 3 · Los que hay que saberse
03:44 Parte 4 · El error más repetido
04:40 Parte 5 · En una conversación real
05:10 Parte 6 · Quedar con alguien
05:58 Parte 7 · Practica
06:49 Parte 8 · Resumen
```

**present-perfect-vs-past** (505 s)

```
00:00 Intro
00:25 Parte 1 · Por qué nos cuesta tanto
01:32 Parte 2 · Qué dice cada uno
02:35 Parte 3 · Las palabras que te avisan
03:36 Parte 4 · Since o for
04:24 Parte 5 · En una conversación real
05:12 Parte 6 · El error de nivel alto
05:47 Parte 7 · Ponerse al día
06:30 Parte 8 · Practica
07:26 Parte 9 · Resumen
```

**used-to-soler** (507 s)

```
00:00 Intro
00:27 Parte 1 · El problema
01:38 Parte 2 · Used to: lo que ya no haces
02:40 Parte 3 · Preguntas y negativas
03:26 Parte 4 · Be used to: otra cosa distinta
04:29 Parte 5 · En una conversación real
05:03 Parte 6 · El error más común
05:32 Parte 7 · Hablar de tu infancia
06:35 Parte 8 · Practica
07:33 Parte 9 · Resumen
```

**third-person-s** (470 s)

```
00:00 Intro
00:14 Parte 1 · El problema
01:19 Parte 2 · No es solo have
02:32 Parte 3 · Las tres formas de la ese
04:17 Parte 4 · Un diálogo real
05:39 Parte 5 · Practica
06:49 Resumen
```
