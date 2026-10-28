# STEP 79 §5 — the voiced lessons, re-rendered from cache ($0)

1080p30 through `renders.register` (Manim, then the STEP 75 final pass: x264, BT.709, −14 LUFS),
with `ELEVENLABS_LOCK=1`. Every render passes `renders.lesson_gate` (sync report, −14 LUFS ± 1, no
still over 5.0 s); the collision checker ran on the same scene code in `s3` (0 problems).

| lesson | length | gate | LUFS | max cue lag | longest still | chapters | thumbnail | render / with encode + gate |
|---|---|---|---|---|---|---|---|---|
| demo-motion | 136 s | PASS | -14.0 | 0.033 | 0.27 s | 0 | yes | 108 s / 169 s |
| make-vs-do | 462 s | PASS | -14.0 | 0.16 | 0.27 s | 10 | yes | 459 s / 678 s |
| can-could-pedir | 395 s | PASS | -14.0 | 0.1 | 0.3 s | 9 | yes | 454 s / 645 s |
| hacer-preguntas | 467 s | PASS | -14.0 | 0.065 | 0.27 s | 9 | yes | 504 s / 728 s |
| morning-phrasal-verbs | 445 s | PASS | -14.0 | 0.032 | 0.3 s | 8 | yes | 453 s / 651 s |
| preposiciones-in-on-at | 467 s | PASS | -14.0 | 0.065 | 0.27 s | 9 | yes | 500 s / 741 s |
| present-perfect-vs-past | 506 s | PASS | -14.0 | 0.072 | 0.3 s | 10 | yes | 587 s / 2532 s |
| used-to-soler | 508 s | PASS | -14.0 | 0.098 | 0.3 s | 10 | yes | 540 s / 797 s |

The render times were measured with the machine loaded; present-perfect-vs-past's 2 532 s total is
the final encode and the gate running while memory was short, not the render (587 s).

**Not rendered** (they need new voice, and this STEP spends none):
- **comparativos-superlativos**: the lesson gained 5 beats after its audio was made; b28–b38's
  narration no longer matches its audio and b39 has none (12 beats).
- **third-person-s**: b30's narration changed after its audio was made (1 beat).

demo-motion has no headings, so no chapter list (YouTube needs three).

Proofs per lesson in `s5/`: `<lesson>.json` (MP4 path, gate, chapters, times), `<lesson>_sheet.png`
(10 frames), `<lesson>/frame0.png`, `<lesson>/thumbnail.jpg` (images stay local). The MP4s stay in
`experiments/manim_voiceover_poc/renders/<lesson>/`.

Seen on the sheets, not caught by the checker (it reads each beat's midpoint, not its transitions):
a chip flying into a `sort` bin crosses the bin's label for a moment (used-to-soler), and the last
frames of a page turn leave a narrow grey strip by the rings. Frame 0 of each render is the page
before the first beat draws (the YouTube thumbnail is `thumb.jpg`, not frame 0).

## Chapters, from each render's own timeline

**demo-motion**

```
```

**make-vs-do**

```
00:00 Intro
00:25 Parte 1 · El problema
01:15 Parte 2 · Make crea
02:00 Parte 3 · Do realiza
03:06 Parte 4 · Las parejas traicioneras
03:56 Parte 5 · En una conversación real
04:26 Parte 6 · El do que además ayuda
04:58 Parte 7 · En el trabajo
05:48 Parte 8 · Practica
06:47 Parte 9 · Resumen
```

**can-could-pedir**

```
00:00 Intro
00:11 Parte 1 · El error de estructura
01:02 Parte 2 · Los tres trabajos de can
01:50 Parte 3 · Could no siempre es pasado
02:32 Parte 4 · La escalera de la cortesía
03:14 Parte 5 · En una conversación real
03:43 Parte 6 · Pedir favores en el trabajo
04:51 Parte 7 · Practica
05:44 Parte 8 · Resumen
```

**hacer-preguntas**

```
00:00 Intro
00:29 Parte 1 · El problema
01:29 Parte 2 · La fórmula
02:32 Parte 3 · Preguntas de sí o no
03:23 Parte 4 · Cuando no hace falta do
04:30 Parte 5 · En una conversación real
05:11 Parte 6 · El error más común
05:49 Parte 7 · Practica
06:52 Parte 8 · Resumen
```

**morning-phrasal-verbs**

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

**preposiciones-in-on-at**

```
00:00 Intro
00:28 Parte 1 · La imagen que lo ordena todo
01:55 Parte 2 · El tiempo funciona igual
02:58 Parte 3 · Los que hay que saberse
03:44 Parte 4 · El error más repetido
04:40 Parte 5 · En una conversación real
05:11 Parte 6 · Quedar con alguien
05:58 Parte 7 · Practica
06:50 Parte 8 · Resumen
```

**present-perfect-vs-past**

```
00:00 Intro
00:25 Parte 1 · Por qué nos cuesta tanto
01:32 Parte 2 · Qué dice cada uno
02:36 Parte 3 · Las palabras que te avisan
03:37 Parte 4 · Since o for
04:25 Parte 5 · En una conversación real
05:12 Parte 6 · El error de nivel alto
05:47 Parte 7 · Ponerse al día
06:30 Parte 8 · Practica
07:27 Parte 9 · Resumen
```

**used-to-soler**

```
00:00 Intro
00:27 Parte 1 · El problema
01:38 Parte 2 · Used to: lo que ya no haces
02:40 Parte 3 · Preguntas y negativas
03:27 Parte 4 · Be used to: otra cosa distinta
04:30 Parte 5 · En una conversación real
05:04 Parte 6 · El error más común
05:33 Parte 7 · Hablar de tu infancia
06:35 Parte 8 · Practica
07:34 Parte 9 · Resumen
```
