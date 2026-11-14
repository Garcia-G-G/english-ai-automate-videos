# STEP 53 — More, and less repeated, background footage

## What the owner asked
"Add more videos to the gallery so we can keep changing and varying" — the Pexels
footage behind the Shorts.

## Measured (2026-10-14)
Over `output/`: 54 videos placed 295 clips, **177 distinct; 58 reused, the top four 6–7
times each**. Cause: each category had 6 subjects × 5 camera motions = 30 queries, and
`fetch_query()` caches exactly ONE clip per query and returns it forever. The cache is
253 query folders, 1.6 GB.

Already done (commit with this step): `CATEGORY_FOOTAGE` grows from 6 to **20 subjects per
category** (21 categories, 2,100 possible queries; no subject repeats across categories;
`tests/test_topic_clips.py` passes). The three level categories get theirs with STEP 49b.

## What this step does (free: Pexels API, 200 req/h, 20k/month, already in `.env`)
1. **Several clips per query.** One search already returns up to 8 results; keep up to 3
   usable ones per query in the cache slot (still ≤ 12 MB each), and pick among them with
   the existing deterministic `_axis_pick` on the topic, so a re-run reproduces the video.
   No extra API calls; at most 3× the bytes for the queries actually used.
2. **Don't repeat recent footage.** Keep a small ledger (`output/.cache/clip_usage.json`:
   pexels id → last N videos that used it). When choosing within a slot, and when a slot
   only offers clips used in the last 15 videos, try the next subject instead. Never fail
   a video for this — fall back to the least recently used.
3. **A «Fondos» page in the dashboard** — the gallery the owner means: a grid of cached
   clips (first-frame thumbnails via `src/thumbnails.py`, lazy, nine per page like the
   Library), filter by category, times used, and a **«No usar»** toggle that writes a
   blocklist (`content/footage/blocklist.json`, committed) that `fetch_query` respects.
   Players open on demand only (`lazy_video`) — the dashboard rules from de83198 apply.
4. Optional, behind a button with a disk budget: **«Precargar fondos»** fetches one clip
   per subject for a chosen category (≤ 100 requests, shows MB used), so variety exists
   before the videos are made. Default budget 2 GB total for `assets/clips/_cache`, oldest
   unused evicted first.
5. Nothing changes the attribution line: one Pexels link in the channel description.

## Proof I need back
- Re-run the measurement above on the next 10 renders: distinct/placed and the max reuse.
- Screenshot of «Fondos» with one clip set to «No usar», and the next render not using it.
- Cache size before/after; Pexels requests used.
