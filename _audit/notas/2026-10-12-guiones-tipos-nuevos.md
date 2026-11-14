# 2026-10-12 — Guiones para los tipos nuevos

## how_do_you_say: 15 guiones nuevos en la cola
bv004, bv006–bv014, bv016–bv020. Schema OK, 0 avisos `length:`, emojis
comprobados contra la fuente. bv002/bv003 retocados igual que los nuevos.

Dos temas de `basic_vocab` NO caben en el formato tal como está:
- **bv005 números 1–10**: los emojis de dígito (1️⃣) son secuencias keycap y
  `emoji_font` las rechaza, con razón. Opciones: que la fila acepte un número
  dibujado como texto en un círculo en lugar de emoji, o cambiar el tema.
- **bv015 meses**: son 12 y el máximo es 10. Opciones: dos vídeos (enero–junio /
  julio–diciembre no llega al mínimo de 8) o subir el máximo a 12 si caben.
Los dos son decisión del dueño, no del guion.

## Duración: el primer render está en el techo
bv001_familia (render de Code): **80,2 s**, banda global 50–80. El brief estimaba
67 s; el recap solo dura 15,0 s (la voz pausa en cada coma). Para dar margen,
los guiones nuevos acortan la intro ("Diez palabras. Piensa antes de que yo lo
diga.") y el arranque del recap. Hay que medir de nuevo con el siguiente render.
Si sigue cerca de 80, la vía correcta es la banda propia del tipo en
`config.yaml` (ya prevista en el brief tras ≥ 4 renders), no recortar palabras.

## Borradores de los otros cinco tipos
28 borradores en `content/drafts/<tipo>/` con la forma propuesta en
`content/drafts/README.md`: fix_the_error 6, conjugation_map 6, minimal_pairs 6,
expression_of_day 6, ladder 4. 0 etiquetas desconocidas, 0 emojis rechazados.
