# Test fixtures

Versioned regression corpus for the schema-validation and QA-gate work.

Everything here is a **copy**. The originals live under `output/`, which is
gitignored and gets cleaned by `python main.py clean` — so anything that
matters as a test input has to be duplicated somewhere durable. That is what
this directory is for.

## Layout

```
scripts/<video_type>/*.json   12 script JSONs, at least one per video type
known_bad/manifest.json       5 videos with observed, reproducible defects
```

## scripts/

One healthy representative per video type (educational, quiz, true_false,
fill_blank, pronunciation, vocabulary), plus the cases named in
`known_bad/manifest.json` so the corpus covers both shapes.

Two are worth knowing about:

- `fill_blank/heads_up_20260210_181915.json` — 67.96s, the longest content in
  the repo (2038 frames). It is the worst case behind the render timeout
  arithmetic in `src/pipeline.py`.
- `quiz/cool_20260416_084217.json` — the slowest whole-video frame rate
  measured (0.1121 s/frame).

These scripts are the *inputs* to TTS. They are not TTS output and carry no
word timestamps.

## known_bad/

Five videos that are known to be defective, each with the defect written down
as an observable claim plus the gate that should catch it. Two failure classes:

1. **Schema defects** (the `fabric` pair) — missing `full_script`, a Spanish
   word inside `english_phrases`, zero word timestamps.
2. **Render timeouts** (the three 2026-04-16 quizzes) — caused by the ffmpeg
   stderr deadlock fixed in `d96c65b`. Kept because they are the only inputs
   that ever reproduced it, so they are the natural regression check for the
   render path.

`source_media` points at the mp4 under `output/`. **The media itself is not
versioned** — those files are 22–31 MB each and belong in git-lfs or nowhere.
If `output/` gets cleaned the mp4s are gone; the scripts here are enough to
regenerate them, and the defect descriptions stand on their own.

## Regenerating a case

```bash
python main.py --script tests/fixtures/scripts/quiz/cool_20260416_084217.json
```
