# 2026-10-08 — Biblioteca de guiones ampliada

## Qué entra
- 18 guiones cortos nuevos en `content/queue/` (3 por tipo), todos sobre topics libres
  (existen en `content/topics/`, sin producir, sin duplicado en cola ni en `_done/`).
  queue_guard: 0 BLOCKED, 0 avisos `length:` en los nuevos.
  - quiz: work002, so023, tr013 (66 / 65 / 69 palabras habladas, banda 48–76)
  - true_false: ff011, tech006, exp029
  - fill_blank: cm019, gr019, gr026
  - vocabulary: tr020, tr009, work010 (66 / 58 / 55, banda 47–82)
  - educational: bz007, so027, tr007 (128 / 118 / 127, banda 102–170)
  - pronunciation: pr016, pr018, pr014 (122 / 119 / 116, banda 89–150)
- 3 lecciones Manim nuevas: hacer-preguntas (33 beats, 7.6 min), gerundio-o-infinitivo
  (32, 6.8 min), used-to-soler (32, 7.1 min). validate() = 0, warnings() = 0.

## Hallazgo abierto (no corregido aquí)
true_false y fill_blank siguen con `items_spoken: 1`. Lo hablado es enunciado +
explicación (~25–30 palabras) y la banda pide 67–121 / 77–210. Los 10 true_false y
los 12 fill_blank de la cola dan aviso `duration`, los nuevos incluidos. No es un
problema de redacción: la explicación tiene tope de caracteres (242 / ~183), así que
un ítem no llega al suelo de 50 s. Opciones: pasar estos tipos a 2 ítems como el
quiz (decisión del dueño, por oído) o recalibrar la banda. Los guiones nuevos ya
traen 3 ítems, así que sirven para cualquiera de las dos.
