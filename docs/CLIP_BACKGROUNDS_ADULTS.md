# Clip backgrounds for the adults profile — requirements

Report only. Nothing here is wired up, and where the clips come from is a
licensing decision that is not addressed.

All of it is read off `src/video/clip_background.py`,
`src/video/__init__.py:142-153` and `src/pipeline.py:109-117`, plus
measurements against the six Momo clips already on disk.

## Two different things read clips; only one is the background

Worth separating before anything else, because they disagree about folder
structure:

| | `ClipLibraryBackground` | `CharacterDirector` |
|---|---|---|
| file | `src/video/clip_background.py` | `src/video/v2/character_director.py` |
| role | the whole frame background | a character composited into the frame |
| used when | `background_mode: clips` | v2 renderer, `educational` only |
| folder names | **ignored** — flat `rglob("*.mp4")` | meaningful: `talking/`, `idle/`, `reaction/`, `celebrate/` |
| built by | `src/video/backgrounds.py:117` | `src/video/v2/educational.py:150` |

They never run together: `src/video/__init__.py:133` sets `background = None`
whenever v2 is active.

This document is about the first one — the background path, which is what the
kids profile uses today (`clips_dir: assets/clips/kids`, picking up the six
Momo mp4s). For that path the `talking/idle/reaction/celebrate` split under
`assets/clips/adults/capi/` carries no meaning at all: every mp4 anywhere
below the directory lands in one shuffled pool. Keeping the subfolders costs
nothing and leaves the files usable by `CharacterDirector` later, but the
background will not honour them.

## Wiring: two lines of config

`resolve_background` only emits a clips background when the *profile* asks for
it. `adults` currently inherits the base config, which is `background_mode:
random`. So:

```yaml
profiles:
  adults:
    video:
      background_mode: "clips"
      clips_dir: "assets/clips/adults"
```

Relative paths resolve against the project root
(`src/video/__init__.py:148-151`). No code change is needed.

## What the loader requires

| | requirement | if violated |
|---|---|---|
| extension | `.mp4`, **lower-case** | invisible (see below) |
| discovery | recursive from `clips_dir`, sorted | — |
| count | ≥1 readable clip | `ValueError` at first frame |
| codec | readable by this OpenCV build; `FRAME_COUNT > 0` and `FPS > 0` | that clip skipped with a warning |
| resolution | any; **1080x1920 or larger at 9:16 to avoid resampling** | scaled and centre-cropped, see table |
| fps | any, read from the container; falls back to 30 | timing drift if metadata lies |
| length | any; total footage ≥ video duration to avoid repeats | repeats inside one video |
| audio | ignored entirely | — |

### The extension check is case-sensitive

`rglob("*.mp4")` does its own matching, so it is case-sensitive even on
macOS's case-insensitive filesystem. Verified:

```
files:               ['a.mp4', 'b.MP4', 'c.mov']
rglob("*.mp4") finds ['a.mp4']
```

A folder of `.MP4` or `.mov` files reads as an empty folder — which raises
`ValueError: No .mp4 clips found`, not a warning about extensions.

### No synthetic camera

`_fit` takes no time argument: one scale, computed from the clip's own
dimensions, and a constant centre crop. Every frame of a given clip gets the
same rectangle. Whatever motion a clip background has is the motion that was
filmed — none of the Ken Burns zoom and pan in `docs/KENBURNS_DIAGNOSIS.md`
applies here, and the two share no code.

### Resolution: it always fills the frame, and that is the problem

`_fit` scales by `max(1080/w, 1920/h)` and centre-crops. Nothing is ever
letterboxed, so nothing ever *looks* wrong — it just quietly throws pixels
away:

| source | scale | frame area kept |
|---|---:|---:|
| 2160x3840 (4K 9:16) | x0.50 down | 100% |
| **1080x1920 (9:16)** | **x1.00 none** | **100%** |
| 720x1280 (the Momo clips) | x1.50 up | 100% |
| 1080x1350 (4:5) | x1.42 up | 70% |
| 1920x1080 (landscape) | x1.78 up | **32%** |

A landscape clip is upscaled 1.78x and reduced to the middle third of its
width. For scenery that is merely a bad crop; for a character it usually means
the head is gone or enormous. Landscape is accepted, never warned about, and
should be treated as unusable.

Upscaling uses `INTER_AREA`, which is an area-averaging filter intended for
*downscaling* — so sub-1080 sources come out softer than a plain bilinear
upscale would give. The existing Momo clips are 720x1280 and take that 1.5x
hit today.

**Target 1080x1920, or 2160x3840 if the source allows it.**

### Length and count drive within-video repetition

The playlist shuffles all clips and concatenates whole clips until the total
covers the video's duration. Two consequences:

- **Total footage below video length repeats.** The six Momo clips are 8.00s
  each — 48s in total, so a 60s video already replays one of them. For a 60s
  video with no internal repeat you need 60s of distinct footage: e.g. 8x8s,
  or 10x6s.
- **A single clip longer than the video means no variety at all** — the
  playlist takes one entry and shows only its first `duration` seconds.

Reference point, measured from what exists:

```
6 clips, 720x1280, 24.00fps, 192 frames, 8.00s each, 1.7-3.6 MB
```

That shape (8s, 24fps) works well. Only the resolution is short.

## Failure modes, by how loudly they fail

**Crashes at construction — the first frame of the render:**

- Empty directory, or one holding no lower-case `.mp4`:
  `ValueError: No .mp4 clips found in '<dir>' (searched recursively)`.
  **`assets/clips/adults/capi/` is empty right now**, so turning on
  `background_mode: clips` for adults today fails immediately.
- Every clip unreadable: `ValueError: No readable .mp4 clips in '<dir>'`.

**Silent — a warning in the log, then absent:**

- A clip whose codec this OpenCV build cannot open, or that reports
  `FRAME_COUNT <= 0` (some variable-frame-rate and fragmented mp4s do):
  `Skipping unreadable clip: <path>`. The render continues on whatever is
  left, so a library can quietly shrink to one clip.
- Wrong extension: not even a warning, since the file was never a candidate.

**Silent and only visible in the output:**

- Landscape or non-9:16 sources: cropped as tabulated above.
- Sub-1080 sources: soft.
- Lying fps metadata: the background drifts out of step with its own cut
  points, because the frame index is `int(local_t * fps)`.
- A decode hiccup mid-render: `get_frame` returns the last good frame, or
  black if it has not decoded one yet. It never raises after construction, so
  a partly-corrupt clip shows as a freeze rather than an error.

## Two knobs that exist but cannot be reached from config

`ClipLibraryBackground` accepts `dim` and `seed`, and
`src/video/__init__.py:144` will pass anything in `background_options` — but
`resolve_background` only ever emits the string `clips:<dir>`, and no caller
passes `background_options`. So today:

- `dim` is always **0.35** — every clip frame is multiplied by 0.65 before the
  text goes on. This is the clip path's entire answer to text contrast, and it
  is not tunable per profile. Whether 0.35 is enough depends on the footage:
  for reference, the photo backgrounds carry overlays of 0.04-0.20 and six of
  the eleven enabled presets still land under 3.7:1 contrast behind the
  headline.
- `seed` is always `None`, so clip order is different on every render. Fine in
  production, awkward if you ever want to reproduce a specific output.

Making either configurable is a change to background wiring, which is out of
scope here.

## Summary of what adults would need

1. Two lines of profile config (above).
2. At least one lower-case `.mp4` in `assets/clips/adults/` — the directory is
   empty, so this is the blocker.
3. Clips at **1080x1920 or larger, 9:16, 24-30fps, H.264**, sound irrelevant.
4. **Total footage ≥ the longest video** to avoid repeating inside one video;
   8 clips of 8s is a sensible floor.
5. A check that 0.35 dimming is enough contrast for the footage chosen, since
   it cannot currently be raised per profile.
