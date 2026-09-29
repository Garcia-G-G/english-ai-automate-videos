# content/queue

Scripts waiting to be made into videos, one folder per type
(`educational/`, `quiz/`, `pronunciation/`, …).

## `_done/` is consumed, not lost

**A script missing from `content/queue/<type>/` and present in
`content/queue/_done/` has been consumed, not lost.**

When a video is produced, `tools/queue_guard.py --done` (called by
`queue_shelve()` in `src/admin.py`, only after the video exists) moves its script
from the type folder into `_done/`. In `git status` that shows up as a deletion
under `content/queue/<type>/`. It isn't one.

Do not restore these files. Moving them back puts topics that have already been
published back in the queue. The calibration in `config.yaml` cites some of them
(for example `pr002_bit_beat` and `pr003_cat_cut`) precisely because they were
rendered.

To check a "deleted" script:

```bash
ls content/queue/_done/<name>.json
```
