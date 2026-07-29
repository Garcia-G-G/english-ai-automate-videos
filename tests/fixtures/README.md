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

Cases grouped by the **layer** the defect lives in, because each layer needs a
different kind of gate.

**`acoustic_cases`** — defects that exist only in the waveform. The script JSON
is well-formed, so no amount of schema validation will ever see them.

- `afabric_option_letter_elision` — `Opción A, fábrica` is heard as
  `Opción afábrica`. Quiz options are built as `f"Opción {letter}, {word}."`,
  joined, and sent in **one** TTS call, so the bare vowel elides into the word
  after it. Recorded as a **TTS input string plus an assertion** (≥250 ms of
  silence between each letter and its word), not as a media file — that way it
  survives the audio-segmentation rework. It **fails by construction today**
  and must pass afterwards; the before/after is the whole point. It is also not
  specific to `fabric`: every quiz is built the same way.

**`schema_cases`** — defects visible in the script JSON: missing
`full_script`, the Spanish token `tela` inside `english_phrases`, zero word
timestamps. These are three independent defects that happen to share the
`fabric` topic with the acoustic case above. **They are not "afabric"** and
have unrelated root causes.

**`render_cases`** — the three 2026-04-16 quizzes, caused by the ffmpeg stderr
deadlock fixed in `d96c65b`. Kept because they are the only inputs that ever
reproduced it, so they are the natural regression check for the render path.

`source_media` points at the mp4 under `output/`. **The media itself is not
versioned** — those files are 22–31 MB each and belong in git-lfs or nowhere.
If `output/` gets cleaned the mp4s are gone; the scripts here are enough to
regenerate them, and the defect descriptions stand on their own.

## Regenerating a case

```bash
python main.py --script tests/fixtures/scripts/quiz/cool_20260416_084217.json
```
