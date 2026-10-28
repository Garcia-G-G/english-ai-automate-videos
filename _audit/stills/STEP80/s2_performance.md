# STEP 80 §2 — Rendimiento, and the queue ordered by what works

- **«Rendimiento»** (a new page in Producción): «Actualizar estadísticas» reads YouTube Data API
  `videos.list` (statistics, snippet) for every YouTube video in `output/published/ledger.jsonl`, with
  the uploader's own token (when it has expired, `.tokens` is copied to `output/stats/.tokens-<time>`
  first, then the uploader's own refresh saves it). Facebook reels through `video_insights` with
  `FB_PAGE_TOKEN` — or a note saying why not. The snapshot goes to `output/stats/youtube_YYYY-MM-DD.json`.
  The page shows views by format (median, mean, count, and the same on videos older than 3 days), the
  top 10 and the bottom 10 with «días publicado», views by category word (CASA, FRUTA… from the
  title; the format otherwise) and the queue's priority with its reasons.
- **Format score** (`src/queue_priority.py`): a type's median views over its videos older than 3 days,
  once it has 3 of them; until then the prior in `config.yaml` `queue_priority.prior_views` (Claude's
  26 Oct reading: how_do_you_say 1150, pronunciation 950, phrases_level 650, the series 600, level
  tests 300, grammar formats 150). A script whose topic is a basic A1 category
  (`queue_priority.a1_categories`) ×1.5. Each priority carries its reason, e.g. «how_do_you_say: 1150
  vistas (estimación previa) × 1.5 por categoría A1 «cara»».
- **`queue_pick` hands out the queue in that order** (grammar types drop to the back; nothing is
  deleted), so every render — «Crear», the batch, the button — takes the best safe script.
- **«🚀 Producir el siguiente mejor»** is the first action on «Inicio»: it names the next script and
  why, and starts its render under the usual locks and caps.

With the priors only (no statistics read yet), the first 100 of the 547 queued scripts are
phrases_level 38, how_do_you_say 26, level_test 23, say_it_level 7, pronunciation 6; the top is the A1
how_do_you_say (CARA, PROFESIONES, ANIMALES, CASA, VERBOS…).

**Not done by Claude**: «Actualizar estadísticas» reads the live channel with Garcia's token; it is
his click. No statistics table yet.
