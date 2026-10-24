# STEP 79 §3 — motion and Bubi

1. **Bubi on the page**, small (0.95 units tall, at most 1.0 wide), on the page's lower-left
   corner, half over the rings, z above the page and under the captions. v3 poses only:
   «hola» (simbolo_512, waving), and «wow», «lo lograste», «bien hecho» cut out by
   `tools/extract_bubi_expressions.py`. Cues: `title` → waves; `quiz` «Pausa y piénsalo» → «wow»
   with a slow tilt and three thinking dots over his head, until the answer; the answer → «lo
   lograste» with a jump; `tip` → «bien hecho» leaning in (**there is no pointing pose in the
   brand guide**, so the thumbs-up stands in); `recap` → «bien hecho» nodding. Between cues he
   breathes, a 2 % scale on a 2.6 s cycle. An updater on the clock: he adds no time to a lesson.
2. **Page turn**: a `heading` that starts «Parte N» turns the page — a sheet the colour of the
   page folds from its right edge to the rings in 0.6 s, its underside a shade darker — with a new
   procedural paper sound (`sfx.page`, 0.55 s) 22 dB under the voice, ducked on a word.
3. **Pencil marks**: a highlighted chip in a `sentence` gets a hand-drawn loop in its role
   colour, drawn stroke by stroke (`Create`; Manim's Cairo renderer antialiases the strokes),
   unless a tag sits under it; a `fix` strikes the wrong chip in red first, and the right chip
   gets a drawn tick after it turns green.
4. **Stillness**: `renders.lesson_gate` (sync report, −14 LUFS ± 1, no still stretch over 5.0 s)
   runs on every registered render and is written to the ledger. The measure is `src/stillness.py`,
   shared with the series' gate. A demo-motion render from cache: longest still 0.2 s (Bubi
   breathes on every frame). The 20 s end card was a still: its logo now breathes 1 %. The camera
   push is 1.03× (≤ 3 %).
5. **End card**: `brand_logo()` already read the v3 `logo_horizontal.png` (Bubi + wordmark); the 19 Oct
   render predates the logo's commit (20ee6cc, that evening). Stills mode now also keeps a frame
   of the end card, which shows the v3 logo and the two end-screen frames.

Final run: **0 problems in 22 lessons, 782 stills** (`s3/index.md`).

The collision checker now includes Bubi: he must not cover any text. One overlap in the first run
(used-to-soler b30, the arms-up pose is 1.47 units wide) → every pose is fitted to 1.0 wide and
Bubi sits a little further onto the sand.
