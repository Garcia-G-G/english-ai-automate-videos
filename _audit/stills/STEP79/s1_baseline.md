# STEP 79 §1 — the «before», and the lesson studio's cost log

## Stills mode

`lesson_scene.py` with `STILLS=1 STILLS_OUT=…` (driven by `tools/lesson_stills.py`): every beat drawn
at its midpoint. Only the animations that hold a midpoint are drawn; every other one is skipped
(Manim jumps it to its end state and moves the clock on). `--dry_run`: nothing is encoded.
`voices.StillsService` uses a beat's recorded audio when it is cached and still matches the
narration, and otherwise a silent clip of the estimated length (0.434 s per word, the fitted rate,
plus the beat's pauses) with its words spread evenly. It never asks for voice, and the tool runs
with `ELEVENLABS_LOCK=1` anyway.

All 22 lessons: `s1/index.md`, one sheet per lesson `s1/<lesson>.png` (the PNGs stay local). The run
also found what §5 needs to know:
- **comparativos-superlativos**: 12 beats (b28–b39) no longer match their cached audio, so they
  were estimated. §5 cannot re-render it from cache without new voice.
- **third-person-s**: 1 beat has no cached audio, so it was estimated. §5 skips it.
- The other 8 voiced lessons are fully cached.

The «before», as the review says: the page sits left with an empty strip of sand on the right,
the caption sticky cuts sentences («Casi todo el mundo cree que ha dicho actualmente vivo en») and
overlaps the page's corner, and the English in list beats is not blue (falsos-amigos b11).

## Every studio request is logged

`gen_audio.eleven_segment` writes one row to `output/costs/costs_<day>.jsonl` (the Shorts' format)
right after each answered request: `characters`, `model`, `cost_usd`, `video_id`
(`lesson_<id>`), `lesson`, `beat` and `reason` (`beat`, `onset_retake`, or `probe` for a probe
calling it directly). A refused request is not billed and not logged. Before this, the studio logged
nothing, which is where most of the ≈ 97 000 unlogged characters of §00 came from.

## Housekeeping before §1 (Garcia's request)

The six series videos that passed the gate are in `output/pending/hecho_con_claude/`, re-gated with
the current gate (all PASS): hc_m001 (STEP 79 s0), hc_p019, hc_m010, hc_e001, hc_p011 and hc_c019
(STEP 78b). Each has a sidecar in the house shape (gate, blocking_flags, gate_checks, title,
description = caption, hashtags), and its script is in `content/queue/_done/`. `admin.get_pending_videos()`
lists all six with «PASS». $0.
