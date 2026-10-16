# STEP 33 — The width check belongs in the shared function, and one more
# caller still throws its lines away

Small step, before educational. Both items came out of your pronunciation work.

---

## 1. `fit_text_font` still tests one axis

```python
# src/video/utils.py:539-549
for size in range(max_font, min_font - 1, -2):
    box = measure_block(line_break(text, f, max_width), f)
    if max_height is None or box.advance_height <= max_height:
        return box
```

Width is delegated entirely to `line_break`, which guarantees it **except for a
single token wider than the column** — it has to emit that token whole. You
proved this is not theoretical: `advertisement` at 160px is one unbreakable
1240px line that passed the height check and drew clipped at both frame edges.

You fixed it inside `_word_size`. It should be fixed in `fit_text_font`,
because the trap is not pronunciation's — it is the function's, and there are
**nine call sites across six renderers**:

```
quiz.py:307, 850        true_false.py:342, 604      fill_blank.py:130, 331
educational.py:211      vocabulary.py:158, 320
```

Educational is next in the queue and is one of them. Fixing the shared
function once beats each caller re-deriving the same guard, and it is the
difference between a fix and a habit.

The size is only acceptable if every line it produced fits the column. When
nothing in the range does, the existing overflow path already logs with the
text and the excess — it should say which axis failed.

## 2. `fill_blank.py:331` is the vocabulary defect, still there

```python
of, _, _, _ = fit_text_font(opt, 40, 28, _OPT_W - 120)   # lines discarded
th = _text_h(draw, opt, of)
draw_text_solid(draw, opt, cx + 85, ...)                  # the raw string
```

Same two failures you removed from vocabulary: no `max_height`, so it returns
40px for every option regardless of length, and `of, _, _, _` drops the wrapped
lines so the source string is drawn.

**It is latent, not live — I measured before asking for it.** Across the 139
distinct options on disk, none overflows at 40px into the 740px column. The
worst is `"This is John calling from Amazon"` at 646px, 87% of the column. So
this is not a bug you can photograph today; it is the same loaded gun, one
long option from firing, in a renderer whose card is a fixed 75px high.

Treat it as a consistency fix, not an emergency: same shape as `_draw_cell`,
same kind of test, and say in the report whether any real option changed size.
`fill_blank.py:130` already uses the box properly — that one is fine.

## Not in this step

Educational, grouping, and every other layout. This is the shared function and
one call site.

## Proof

- A test that pins the width axis on `fit_text_font` directly: a single token
  wider than the column must not come back at a size that overflows.
- The fill_blank test in the captured-draw style.
- Confirm the nine call sites still behave: the suite already covers them, so
  what matters is whether any golden frame moves and why.

## Cost

$0.00.
