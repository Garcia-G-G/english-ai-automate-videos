# `src/video/v2/` — FROZEN

Frozen 2026-07-30 (Step 3). Do not develop this further without an explicit
decision to revive it.

`v2` is a second educational renderer, reachable only via
`generate_video(engine_version="v2")`. It is not what ships: `pipeline.py`
does not pass `engine_version`, so **every video rendered today goes through
v1**. It was left in the tree because one part of it was genuinely better than
its v1 equivalent.

## What was extracted into v1

**`timing_engine.py` — now the display-timing authority for BOTH engines.**

It was written for v2 and reachable only from v2, which is why v1 — the path
that actually renders — kept the bugs the engine was built to fix. Step 3
wired it into the v1 path (`video/__init__.py`, consumed by
`video/educational.py`).

It fixes two things v1 had been doing wrong for its whole life:

1. **`SubtitleProcessor` trimmed audio timestamps to solve a display
   problem.** `end = next_start - min_gap/2`, then `next_start - 0.033`. A
   group's end moved EARLIER whenever two groups were close, so text vanished
   while the audio was still speaking its last word — a real contributor to
   the reported "animation runs ahead of the voice". Worse, it edited the
   AUDIO timestamps, so every later consumer inherited a group whose `end` no
   longer described the sound. That block is deleted; the engine derives
   `display_start` / `display_end` without touching the timestamps.

2. **v1 faded a group only AFTER its end, and only when no other group was
   active.** Back-to-back groups popped out with no exit animation. Alpha now
   comes from `timing_engine.group_alpha`, which owns the smoothstep in and
   out and guarantees both transitions fit the window.

`CTA_LEN` also moved into `timing_engine`, because both engines need it and
v1 previously had no CTA reservation at all. `v2/educational.py` now
references `TE.CTA_LEN` rather than keeping a private copy.

## What was NOT extracted

`educational.py`, `cards.py`, `layout.py` and the rest of the v2 design system.
They are a different visual language from v1 and swapping them is a product
decision, not a refactor. They also depend on the layout-box work that has not
happened.

## Rules while frozen

- `timing_engine.py` is now shared. Changing it changes **v1**, which is what
  ships. Treat it as production code and run `tests/test_timing_engine.py`
  plus the QA gate after any edit.
- Everything else here is dormant. Do not import it from v1.
- If v2 is ever revived, note that its renderer has never been measured by the
  QA gate — the gate reads audio, and v2's differences are entirely visual.
