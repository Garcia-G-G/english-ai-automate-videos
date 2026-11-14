# Retention baseline — 4 curves

Analysis only, 2026-08-03. No code changed. n=4 across 3 video types; treat
every number as a baseline to compare against, not a finding.

---

## 1. The cliff, mapped to the timeline

### Your hypothesis is FALSIFIED as a cause, but right about the location

**Where it starts:** yes, exactly at the options block. On both fill_blank
videos the decay begins within one sampling point of `options` onset.

**What causes the shape:** no. The layout completes far too fast.

```
_OPT_STAGGER = 0.10   ->  4 cards land within 0.4s of options onset
```

| | cards all on screen | decay runs |
|---|---|---|
| IQnppo8VeNs | 5.52 s (16 %) | 5.2 → 9.1 s (15 % → 26 %) |
| hZ_BwU8eSQQ | 4.40 s (12 %) | 4.8 → 8.1 s (13 % → 22 %) |

The visual event is over in 0.3–0.4 s. The decay continues for another
**3–4 seconds** after the screen has stopped changing. A layout event cannot
explain a decay that outlives it by an order of magnitude.

### What IS in that window: dead air on a static screen

`fill_blank` still sends its four options as ONE combined TTS call, so the
options segment is ~11 s of slow narration over a screen that has been static
since second 5.

```
IQnppo8VeNs  options 5.22-16.34s (11.1s)   4 internal silences, 2.46s = 22% dead
  6.61- 7.03  0.42s  (19%)
  8.70- 9.39  0.68s  (25%)
 11.17-12.00  0.82s  (32%)
 13.77-14.31  0.53s  (39%)

hZ_BwU8eSQQ  options 4.10-15.38s (11.3s)   4 internal silences, 3.64s = 32% dead
  5.38- 5.69  0.31s  (15%)
  7.08- 8.32  1.24s  (19%)
  9.85-10.91  1.05s  (27%)
 12.57-13.61  1.04s  (34%)
```

On `hZ_BwU8eSQQ` the 1.24 s silence spans 19 %→22 % and the decay stops at
22 %. The viewer has read four short words in about a second and then waits
through a second of nothing.

### Loss rate per phase — the dwell is the expensive part

Watch-ratio points lost per second:

| phase | IQnppo8VeNs | hZ_BwU8eSQQ |
|---|---|---|
| sentence (one card) | 0.036 | 0.056 |
| card stagger (0.4 s) | 0.094 | 0.000 |
| **options dwell** | **0.030** | **0.062** |
| think + countdown | 0.015 | 0.000 |
| answer + explanation | 0.017 | 0.011 |

The dwell is where the loss accumulates, because it is long. The stagger looks
steep on one video and flat on the other — over 0.4 s that is one sample and
carries no weight.

---

## 2. The natural control: true_false has the same layout and no cliff

`ZKE5riXqvx0` is the same pipeline, the same card-stagger renderer family, and
a **1.7 s options segment with zero internal silence** instead of 11 s at
22–32 % dead.

```
                   10%    15%    20%    25%    30%
  fill_blank A     1.19   1.02   0.85   0.81   0.79
  fill_blank B     1.36   1.16   0.92   0.80   0.72
  true_false       1.07   1.04   0.82   0.75   0.57
```

It holds essentially flat from 10 % to 15 % (1.07 → 1.04) where both
fill_blanks lose 0.17–0.20. Its own drop comes later, from 25 % onward — and
its `think` starts at 22 % with the silent countdown at 32–47 %.

Two types, same renderer, different options length, different curve shape. It
is n=1 per type and not proof, but it is the cleanest evidence available and
it points at **audio pacing over a static screen**, not at text layout.

---

## 3. The four curves

| elapsed | IQnppo8VeNs | hZ_BwU8eSQQ | ZKE5riXqvx0 | zG11azNZ0OI |
|---|---|---|---|---|
| **type** | fill_blank | fill_blank | true_false | educational |
| **duration** | 35 s | 37 s | 30 s | 59 s |
| **views** | 137 | 218 | 79 | 350 |
| 1 % | 1.34 | 1.56 | 1.21 | 1.05 |
| 5 % | 1.26 | 1.40 | 1.11 | 1.02 |
| 10 % | 1.19 | 1.36 | 1.07 | 0.86 |
| 15 % | 1.02 | 1.16 | 1.04 | **0.50** |
| 20 % | 0.85 | 0.92 | 0.82 | 0.50 |
| 25 % | 0.81 | 0.80 | 0.75 | 0.48 |
| 50 % | 0.64 | 0.68 | 0.46 | 0.29 |
| 100 % | 0.36 | 0.52 | 0.21 | 0.07 |
| **retained** | 27 % | 33 % | 18 % | **7 %** |
| **avg view %** | 68.2 | 76.5 | 54.0 | 36.5 |

**The 10–25 % cliff is NOT shared.** It is pronounced on both fill_blanks,
mild on true_false, and on the educational video the collapse is earlier and
far worse — 0.86 → 0.50 between 10 % and 15 %, losing 42 % of the audience in
under three seconds, then never recovering.

**`zG11azNZ0OI` cannot be mapped.** It has no local artifact (it is the March
video, and the only one with no matching file), and educational output carries
no `segment_times` at all — the bilingual path emits a word timeline instead.
So I can say the collapse is at 10–15 % and nothing about what is on screen
there. It is also the channel's most-watched video at 350 views and its worst
retention at 7 %.

### Two videos could not be included

`xHXkJuWuc1w` and `IvO969ZeQsM` return **zero retention rows** — not zero
values, no data. Both were published on 01 Aug evening; every video with a
curve is at least ~54 h old and both of these are ~38 h. That is a processing
lag, not a view-count threshold: `IvO969ZeQsM` has 225 views and no curve,
while `ZKE5riXqvx0` has 79 views and a full one.

---

## 4. The 15× anomaly: identical in everything we control

`xHXkJuWuc1w` (17 views) vs `IvO969ZeQsM` (225), published 70 minutes apart.

| field | run_out | foodie |
|---|---|---|
| duration | 26 s | 26 s |
| video type | true_false | true_false |
| privacy / uploadStatus | public / processed | public / processed |
| categoryId | 27 | 27 |
| defaultAudioLanguage | es | es |
| title length | 68 | 68 |
| `#Shorts` in title | yes | yes |
| bare-word keyword line | yes | yes |
| **description length** | 249 | **481** |
| **hashtags in description** | 6 | **12** |
| **API tags field** | 6 | **12** |
| **doubled hashtag block** | **no** | **yes** |

**Everything we control is identical except metadata volume — and that runs
the wrong way.** The video with 13× more views has twice the hashtags *and*
the doubled block; the cleaner one got 17 views. If metadata drove this, the
sign is backwards.

**What we do not control, and cannot separate at n=1:**

- Neither has traffic-source data yet, so I cannot see whether one got a
  Shorts-feed push. On the two that do have it, the feed is essentially the
  whole story — `IQnppo8VeNs` 126 of 134 views from `SHORTS`, `hZ_BwU8eSQQ`
  52 of 55.
- Publication time: 21:20 vs 22:30.
- `IvO969ZeQsM` had a private twin (`hPdSoqjvu3E`) posted 3 minutes earlier.

**Answer to your question: it differs in no way we control.** The variance is
in distribution, not in the artifact. Both counters are also still settling —
neither has analytics data, and on `hZ_BwU8eSQQ` the analytics view count (55)
still trails the public statistic (218) by 4×.

---

## 5. What this suggests for 6a — stated as hypotheses, not conclusions

1. **The strongest single lever is the fill_blank options block**: 11 s of
   audio, 22–32 % of it silence, over a screen that stops changing after 0.4 s.
   The same split already applied to quiz options in Step 3 would cut it. This
   is the one change with a mechanism and a control behind it.
2. **The opening works.** All four curves start above or near 1.0 and three
   hold it to 10 %. Nothing suggests touching the hook.
3. **Do not tune the card stagger.** It completes in 0.4 s and cannot account
   for a 3–4 s decay.
4. **The educational collapse at 10–15 % is the largest single loss measured**
   and is currently unmappable. Making educational emit `segment_times` would
   make it diagnosable — that is a measurement gap, not a fix.

---

# Addendum — 2026-08-06 re-pull

Analysis only. No code changed. The two videos that returned no rows on
08-03 were re-queried as scheduled; all six were re-pulled the same day
because the first section's numbers turned out not to be stable.

## 6. The processing-lag theory was RIGHT

Both now return a full 100-point curve.

```
  xHXkJuWuc1w   retention rows  0 -> 100      21 views
  IvO969ZeQsM   retention rows  0 -> 100     230 views
```

**It is not a view threshold.** `xHXkJuWuc1w` has **21 views** — fewer than
any other video on the channel — and returns a complete curve. The two were
~38 h old on 08-03 and every video that had data was ≥54 h old. Age was the
variable.

Both were also missing traffic-source data on 08-03, and now have it. That
closes section 4's open question.

## 7. The 08-03 numbers had not settled — cross-date comparison was unsound

Re-querying the same metric for the same videos three days later:

| video | 10 % then → now | 25 % then → now |
|---|---|---|
| IQnppo8VeNs | 1.19 → 1.15 | 0.81 → **0.74** |
| hZ_BwU8eSQQ | 1.36 → **1.20** | 0.80 → 0.79 |
| ZKE5riXqvx0 | 1.07 → 1.07 | 0.75 → **0.68** |
| zG11azNZ0OI | 0.86 → 0.83 | 0.48 → 0.48 |

Up to 0.16 of movement. Section 3's table compared videos measured on one
date, so it is internally consistent, but **any future comparison must
re-pull every curve on the same day.** Everything below is a single 08-06
pull.

## 8. All six curves, same-day

| | IQnppo8VeNs | hZ_BwU8eSQQ | ZKE5riXqvx0 | xHXkJuWuc1w | IvO969ZeQsM | zG11azNZ0OI |
|---|---|---|---|---|---|---|
| **type** | fill_blank | fill_blank | true_false | true_false | true_false | educational |
| **views** | 139 | 226 | 80 | **21** | 230 | 351 |
| **avg view %** | 61.9 | 63.6 | 53.0 | 51.3 | 47.4 | 36.4 |
| 1 % | 1.28 | 1.36 | 1.21 | 1.30 | 1.14 | 1.05 |
| 5 % | 1.21 | 1.26 | 1.11 | 1.30 | 0.98 | 1.02 |
| 10 % | 1.15 | 1.20 | 1.07 | 0.90 | 0.93 | 0.83 |
| 15 % | 0.96 | 1.03 | 1.04 | 0.90 | 0.90 | 0.50 |
| 20 % | 0.77 | 0.88 | 0.75 | 0.70 | 0.83 | 0.50 |
| 25 % | 0.74 | 0.79 | 0.68 | 0.50 | 0.71 | 0.48 |
| 50 % | 0.57 | 0.58 | 0.46 | 0.40 | 0.43 | 0.29 |
| 100 % | 0.30 | 0.35 | 0.21 | 0.30 | 0.12 | 0.07 |
| **10→25 loss** | 36 % | 34 % | 37 % | **44 %** | **23 %** | 43 % |

## 9. Does the cliff appear in the two new videos? Yes — and that is the problem

`xHXkJuWuc1w` loses 44 % between the 10 % and 25 % marks, `IvO969ZeQsM` 23 %.
So the answer to the question as asked is yes for both.

But the same window costs **every video on the channel 23–44 %**, across all
three types. Section 2 read `true_false` as a natural control that "holds
essentially flat" through this window on the strength of one video. With
n = 3 true_false, two of them drop as much as or more than either fill_blank.

**The 10–25 % window is not a fill_blank property.** Section 2's control
argument does not survive the larger sample and should not be relied on.

## 10. At full resolution, none of them is a cliff

The 100-point curves are smooth. Largest single-step drop anywhere in each:

```
  IQnppo8VeNs  0.11 @ 15%      xHXkJuWuc1w  0.20 @ 8%   (quantisation, 21 views)
  hZ_BwU8eSQQ  0.05 @ 11%      IvO969ZeQsM  0.07 @ 63%
  ZKE5riXqvx0  0.11 @ 20%      zG11azNZ0OI  0.12 @ 11%
```

`IvO969ZeQsM` has the best resolution available (230 views) and is a
monotone slope with no step at all. "Cliff" was an artifact of sampling at
10/15/20/25 % and reading the accumulated slope as an event. There is no
edge to align a visual or audio event to.

`zG11azNZ0OI` remains the real outlier: 0.88 → 0.50 between 9 % and 15 %,
then a hard plateau at exactly 0.50 for ten percentage points.

## 11. Counter-evidence to the dead-air hypothesis

`xHXkJuWuc1w` (run_out) has a **7.21 s continuous silence**, 6.49–13.70 s of
a 25.07 s video — 25.9 % to 54.7 % elapsed. Measured from the rendered mp4;
the artifact carries no `segment_times`.

Retention across it:

```
  23%  0.50   <- silence starts at 25.9%
  30%  0.50
  40%  0.50
  43%  0.50
  44%  0.40   <- one step, mid-silence
  54%  0.40   <- silence ends
```

**Flat through the longest dead-air block on the channel.** The decline
happens BEFORE the silence starts and stops once it begins. Section 5's
hypothesis 1 — that dead air over a static screen is the strongest lever —
predicts the opposite.

Caveat that matters: 21 views quantises this curve to steps of ~0.05, so
"flat" here means "below the resolution of 21 viewers." It is not proof the
silence is free. It is evidence against it being the dominant term, from the
only video that isolates a long silence.

## 12. The 15× anomaly, answered

Traffic sources are now available for both.

| | xHXkJuWuc1w | IvO969ZeQsM |
|---|---|---|
| SHORTS feed | **13** | **218** |
| YT_SEARCH | 2 | 7 |
| YT_OTHER_PAGE | 4 | 4 |
| SUBSCRIBER | 1 | 0 |
| YT_CHANNEL | 1 | 1 |
| **total** | **21** | **230** |
| **feed share** | **62 %** | **95 %** |

Every other video on the channel draws 90–96 % from the Shorts feed.
`xHXkJuWuc1w` is the only one that never got a feed push, and the entire
15× gap is that one number. Section 4's conclusion — the variance is in
distribution, not in the artifact — is confirmed with the data that was
missing when it was written.

## 13. What this changes for 6a

- **Hypothesis 1 (dead air) is weakened, not dead.** Section 11 is direct
  counter-evidence at n=1 with poor resolution. The R1 trim work already
  landed for other reasons (reproducibility); do not justify further pacing
  work on retention grounds without better evidence.
- **Section 2's true_false control is retired.** It was n=1.
- **The 10–25 % window is universal and has no edge in it.** Nothing to
  align a change to. Treat it as the shape of Shorts feed attention on this
  channel rather than a defect to fix.
- **The educational collapse remains the largest single loss** and is still
  unmappable — no `segment_times`, no local artifact.
- **Re-pull every curve on the same day** as anything you compare it to.
