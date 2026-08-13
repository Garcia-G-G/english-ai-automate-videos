# Ken Burns: why the photo backgrounds move erratically

Diagnosis only. Nothing is tuned, and the numbers below are the evidence for
whoever does tune it.

Reproduce with `python3 tools/kenburns_trace.py --preset photo_earth`; the
per-frame trace lands in `_audit/kenburns/<preset>_trace.csv`.

## Answer

**Both faults are present, and they are working against each other.**

The camera moves far too fast — 158 px/s of pan on `photo_earth`, with a
zoom that changes direction every 1.5 seconds. That is the larger effect and
the one the operator is describing.

Underneath it there is also genuine frame-stepping: between 8% and 19% of
frames move the *opposite way* to the path the camera is actually on, purely
because the crop is truncated to whole source pixels.

The coupling is the part that matters. Slowing the motion down — the obvious
fix for the first fault — makes the second fault worse, because the slower
the true motion, the larger the share of it that truncation eats.
`photo_city_blur`, which pans at half the speed of everything else, already
demonstrates this: it has the calmest path and the worst stepping of the
eleven. Amplitude cannot be reduced on its own without switching to a
sub-pixel crop at the same time.

## What was measured

Per frame, at 30fps over the full 30s, the trace recomputes the crop
rectangle exactly as `photo_kenburns` does — every `int()` intact, since the
truncation is the thing under investigation — and then cross-checks against
real rendered frames so the trace is known to describe the running code.

Two reversal counts are the crux. On the **continuous** pan curve, a
direction reversal is the camera genuinely turning around, a property of the
amplitudes and frequencies. On the **quantised** integer offsets, extra
reversals appear that the path never made. The gap between the two is
stepping, isolated from motion.

| preset | pan_speed | pan px/s | frames stalled | steps going the wrong way | reversals/s quantised | reversals/s true | zoom reversals/s |
|---|---:|---:|---:|---:|---:|---:|---:|
| photo_abstract | 1.30 | 184 | 0.1% | 9.6% | 1.50 | 0.37 | 0.67 |
| photo_galaxy | 1.20 | 159 | 0.1% | 11.5% | 1.80 | 0.33 | 0.67 |
| photo_earth | 1.20 | 158 | 0.3% | 12.9% | 1.97 | 0.33 | 0.67 |
| photo_nature | 1.15 | 144 | 1.0% | 14.0% | 2.37 | 0.33 | 0.67 |
| photo_ocean_vibrant | 1.10 | 138 | 0.2% | 13.0% | 2.03 | 0.30 | 0.67 |
| photo_city | 1.10 | 137 | 0.2% | 13.1% | 1.43 | 0.30 | 0.67 |
| photo_ocean | 1.00 | 129 | 1.6% | 18.6% | 2.33 | 0.30 | 0.67 |
| photo_clouds | 1.00 | 129 | 1.6% | 18.6% | 2.33 | 0.30 | 0.67 |
| photo_sunset | 1.00 | 129 | 1.6% | 18.6% | 2.33 | 0.30 | 0.67 |
| photo_earth_dark | 0.90 | 109 | 0.8% | 7.8% | 2.13 | 0.27 | 0.67 |
| photo_city_blur | 0.60 | 72 | 4.8% | 17.5% | 4.40 | 0.17 | 0.67 |

## Fault 1 — too much motion

Not frame-stepping in the sense of the image sitting still: the crop moves on
99.7% of frames for `photo_earth`. It moves *a lot*.

```
mean step when it moved        4.08 source px  ->  5.29 screen px per frame
largest single step              10 source px  ->  13.2 screen px per frame
sustained pan rate                                 158 px/s
peak pan rate                                     ~400 px/s
```

158 px/s across a 1080-wide frame means the background traverses about 15% of
the screen width every second, indefinitely, in a loop that never settles.

The zoom is the worse half. `photo_kenburns` sums three oscillators
(`src/backgrounds.py:1503-1506`):

| term | period | share of the zoom range |
|---|---:|---:|
| `zoom_slow` | 30.0 s | 0.55 |
| `zoom_med` | 5.24 s | 0.35 |
| `zoom_fast` | 2.51 s | 0.15 |

Only the first is a Ken Burns move. The other two are a 5-second pulse and a
2.5-second shimmer riding on top, and together they carry 45% of the zoom
range. The result reverses direction **20 times in 30 seconds** — once every
1.5 s — against the single slow reversal the 30-second term would give on its
own. In screen terms the frame edge sweeps inward and outward at 23 px/s on
average and 73 px/s at its peak.

Each pan axis has the same three-oscillator construction
(`src/backgrounds.py:1510-1515`); for `photo_earth` the fastest pan component
cycles every 5.8 s.

One hypothesis worth recording as **ruled out**: `zoom_t` is clamped with
`min(1.0, ...)`, and the three terms sum to a theoretical 1.05, so the zoom
could in principle saturate and freeze. It never does — 0.0% of frames across
all eleven presets. That is not the problem.

## Fault 2 — frame-stepping, from three separate truncations

Three `int()` calls quantise the camera to whole source pixels:

```python
crop_w = int(self.width / zoom)                                 # :1518
crop_h = int(self.height / zoom)                                # :1519
center_x = photo.width  // 2 + int(pan_x * max_offset_x)        # :1525
center_y = photo.height // 2 + int(pan_y * max_offset_y)        # :1526
```

and `Image.crop` then takes an integer box, which is resized up to
1080x1920. Because the crop is smaller than the output, **one source pixel of
error becomes 1.13 to 1.47 screen pixels** — the `px_gain` column in the
trace. The camera therefore cannot move by less than roughly one and a half
screen pixels, ever.

Two consequences show up in the numbers:

1. **Steps in the wrong direction.** 7.8% to 18.6% of frames move against the
   direction the continuous path was heading. Truncation toward zero is not a
   symmetric operation, so a smooth sub-pixel drift becomes a ragged
   back-and-forth.
2. **Reversal counts inflated 6x to 26x.** `photo_earth` shows 1.97
   reversals/s in the rendered crop against 0.33/s in the underlying path.
   `photo_city_blur` shows 4.40/s against 0.17/s — twenty-six times more
   direction changes than the camera path contains.

`int()` truncating toward zero rather than rounding also biases the crop
centre toward the image centre on both axes, which is a smaller and separate
issue.

## Why the two faults are coupled

Truncation error is roughly constant per frame — about half a source pixel.
Its *visibility* depends on how much real motion it is competing with. Fast
pans bury it; slow pans expose it.

The table bears this out at both ends. `photo_abstract` pans fastest (184
px/s) and has the least jitter (9.6%). `photo_city_blur` pans slowest (72
px/s) and has both the most stalled frames (4.8%) and the most reversals per
second of any preset (4.40/s) despite having the calmest true path of the
eleven (0.17/s).

So the tempting single-line fix — turn `pan_speed` and the zoom range down —
would trade a fast erratic background for a slow juddering one. Anyone tuning
this should expect to change the sampling and the amplitudes together:
sub-pixel cropping (a float crop box, or `Image.transform` with an affine
matrix) removes the quantisation floor and only then can the amplitudes come
down safely.

## Scope

This is the code path any future clip or photo background would use, which is
why it was worth diagnosing with photos disabled. Nothing here has been
changed.
