# STEP 31 — The vocabulary table draws text it already knows will not fit

Branch `6a-layout`, on top of `e366f7f`. One step. Nothing else in this pass.

---

## The defect

`_draw_vocab_rows` asks how the text should be laid out, throws the answer
away, and draws the raw string.

```python
# src/video/vocabulary.py:359-365   (the English column at :370-376 is identical)
lf, _, _, _ = fit_text_font(es_text, _ROW_FONT, 28, left_col_w)
lbbox = draw.textbbox((0, 0), es_text, font=lf)
lw = lbbox[2] - lbbox[0]
lx = div_x - gap - lw + x_off
draw_text_solid(draw, es_text, max(left_min_x, lx), ly, lf, COLOR_WHITE, row_alpha, outline=4)
```

Two failures, chained:

**1. `fit_text_font` never shrinks here.** `utils.py:548` is

```python
if max_height is None or box.advance_height <= max_height:
    return box
```

Both call sites pass no `max_height`, so the guard is `True` on the first
iteration and the function returns `_ROW_FONT` — 42px — every single time, for
every string, regardless of width. The call reads like a fit and is a constant.

**2. The wrapped lines are discarded.** `lf, _, _, _` drops `box.lines`, which
`line_break` had already cut to the column width. Then `draw_text_solid` is
handed the original unwrapped `es_text`. Whatever the fit decided, one long
line gets drawn.

## Measured, with the real font and the real columns

Columns are 400px (left) and 480px (right). `Inter-Bold.ttf` at 42px, against
`output/scripts/vocabulary/giving_compliments_20260904_121337.json`:

```
 1. ES  481px (+81)    EN  659px (+179)   Excelente presentación
 2. ES  787px (+387)   EN  820px (+340)   Has demostrado una habilidad notable
 3. ES  323px  ok      EN  495px  (+15)   Te queda genial
 4. ES  475px (+75)    EN  527px  (+47)   Eres muy bueno en eso
 5. ES  260px  ok      EN  220px   ok     Buen trabajo
 6. ES  806px (+406)   EN  679px (+199)   Eso es un gran trabajo en este proyecto
 7. ES  487px (+87)    EN  350px   ok     Impresionante esfuerzo
 8. ES  415px (+15)    EN  323px   ok     Me encanta tu estilo
 9. ES  392px  ok      EN  415px   ok     Eres muy talentoso
10. ES  685px (+285)   EN  668px (+188)   Tienes un gran sentido del humor
11. ES  483px (+83)    EN  443px   ok     Tu trabajo es inspirador
12. ES  278px  ok      EN  319px   ok     Eres increíble

9 of 12 rows overflow. 13 of 24 cells.
```

Rows 5 and the left of 3 are the only ones fully inside their column, and they
are exactly the ones that look right in the frame.

---

## THE TRAP — do not fix this by passing `max_height` and stopping

Shrinking the font to the 28px floor fixes 20 of 24 cells and leaves **four
still overflowing**:

```
 2 ES  "Has demostrado una habilidad notable"     524px @28  into 400
 2 EN  "You have demonstrated remarkable skill"   547px @28  into 480
 6 ES  "Eso es un gran trabajo en este proyecto"  537px @28  into 400
10 ES  "Tienes un gran sentido del humor"         457px @28  into 400
```

A width-only fix passes its own check and leaves the frame broken for the
longest entries — which are the ones that look worst. The fit has to be
two-dimensional: **width AND the row's own vertical budget**, with more than
one line allowed.

### It is achievable, and here are the numbers

`VOCAB_ROW_HEIGHT = 90`. With a vertical budget of 78px (90 minus 12 of air)
and lines allowed to wrap, searching 42 → 28 in steps of 2:

```
 1 ES  34px x1     1 EN  32px x2  "That's an excellent / presentation"
 2 ES  32px x2     2 EN  32px x2
 3 EN  40px x1     4 ES  34px x1     4 EN  38px x1
 6 ES  32px x2     6 EN  32px x2
 7 ES  34px x1     8 ES  40px x1
10 ES  32px x2    10 EN  32px x2
11 ES  34px x1

cells with no solution: 0 of 24
```

Seven cells need two lines; the rest need a font one or two steps down. Two
lines fit the row: `2 × line_height(32) = 78px`, and `2 × line_height(42) =
104px` does not — which is why the vertical budget, not a line count, is the
thing to pass.

---

## The contract

1. **One fit decides both axes.** `fit_text_font` already measures the block;
   give it the row's vertical budget so its own loop can shrink. Its overflow
   path (`utils.py:551-566`, which logs and returns the min font anyway) must
   stop being reachable from here — if it still fires, the budget is wrong, not
   the text.

2. **Draw the lines the fit returned.** Not the source string. This is the
   whole defect; a fix that keeps `draw_text_solid(draw, es_text, ...)` has not
   addressed it.

3. **Alignment survives wrapping.** The left column is right-aligned to the
   divider and the right column is left-aligned from it. With two lines, each
   line is placed on its own measured width — a block right-aligned by its
   widest line is not right-aligned.

4. **Vertical centring uses the real block height.** `ly` currently centres a
   single line's ink inside `VOCAB_ROW_HEIGHT`. A two-line cell centres its
   block, and the two columns of one row centre independently — a one-line
   Spanish cell next to a two-line English cell must still look like one row.

5. **Nothing silently disappears.** If a cell cannot fit even at the floor —
   it does not happen on this deck, but a longer pair could — say so in the log
   with the text and the overflow, the way `fit_text_font` already does. Do not
   truncate with an ellipsis and do not drop the row.

---

## Proof required

- A test that pins the measurement, not the intent: for each pair in the
  fixture deck, assert every drawn line's width is inside its column and the
  block's height inside the row budget. It must fail against `e366f7f`.
- One extracted frame at a time when at least eight rows are visible, showing
  row 2 and row 6 — the two worst — inside the card.
- State the font each of the 24 cells resolved to. If any resolved to 28, say
  which, because that is the floor and the next longer deck will breach it.

## Out of scope for this step

The empty white card while rows reveal one by one, `VOCAB_MAX_ROWS`, the title
overlapping the difficulty badge, and anything in another renderer. Note them
if you see them; do not fix them here.

## Cost

$0.00. Everything above is measurable from the fixture deck and the font. Do
not render a paid video to check a layout.
