# STEP 31b — VOCAB addendum — the badge gutter. Same step, not a new one.

Your report is accepted and your numbers reproduce exactly. I re-measured
independently: circle 72..104, column origin 80, so a left line wider than
376px lands on the badge, and **7 of 12 rows do** — rows 1, 4, 6, 7, 8, 9, 11,
by 8 to 19px. Same seven you found.

**My brief was wrong, and in a way worth naming.** I measured
`left_col_w = div_x - gap - left_min_x = 400` and never asked what else
occupies x 80..104. The declared width and the usable width disagreed, and
every number in my table inherited that. It is the same error I have been
pointing at all session — measuring against the wrong boundary — so the fix
should remove the boundary from being a number at all.

## Do it now, in this step

The table is not finished while 7 of 12 rows draw over the badge. You were
right not to change it mid-fit; this is the moment to.

1. **The column origin is derived from the badge, not written down.** The
   number circle already knows where it ends: `num_cx + num_r`. The column
   starts a gutter past that. One place decides, the way `watermark_top()`
   decides the vertical floor — a future change to `num_r` or `num_cx` must
   not be able to walk the text back under the circle.

2. **The test pins the gutter too.** Add to the same captured-draw test: no
   drawn left-column line starts left of the circle's right edge plus the
   gutter. Without that assertion the next edit to the origin silently
   reintroduces this, and the test you just wrote would still pass.

3. Your costing is confirmed. At origin 112 (`left_col_w = 368`):
   0 rows on the badge, 0 cells at the 28px floor, 4 two-line cells in the
   left column, sizes `{32: 7, 36: 1, 38: 1, 42: 3}` — identical to what you
   measured. Origin 120 also clears it but pushes 7 cells to two lines.

## One thing to report, not to fix

At origin 112 the worst cell fills **100%** of the column. The geometry has no
headroom left on this deck: one longer phrase drops that cell to 30, then 28,
then out. The durable lever there is the pair length in the vocabulary prompt,
not more column. Say so in the report with the actual figure and leave it.

Still out of scope: the title under the MEDIO badge, the empty card during the
row reveal, `VOCAB_MAX_ROWS`.

Cost: $0.00. Same fixture deck, same font.
