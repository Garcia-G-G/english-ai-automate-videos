# Closing the "cortado antinatural" thread

## 0. Your Step 5 report arrived corrupted

Several sentences were truncated mid-word on my side — `"→ 30 s"`, `"option_c -75 -75 -7
-10 -9"`, `"Quiz re-rendered ched."`, `"segment_tim"`, `"the isolatixed and shows"`. I did
not read conclusions out of it. Everything below is measured from the repo. If your
output is being truncated at the source, it is worth knowing.

## 1. Verified: the hole is gone

`99ee39d`, two files. Entries on the re-rendered quiz, 10 ms frames, dB:

```
                 -40  -30  -20  -10   +0  +10  +20  +30  +40
option_a         -75  -76  -75  -74  -75  -69  -25  -19  -12
option_b         -76  -76  -75  -75  -75  -68  -50  -24  -14
option_c         -75  -75  -75  -75  -75  -69  -41  -21  -10
option_d         -75  -75  -75  -75  -76  -70  -25  -17  -10
```

The floor runs unbroken at −75 through every join. **−98 dB → −75 dB.** Acceptance test
§4.1 passes.

Bedding the whole clip in room tone instead of prepending a lead-in was better than what
I specified. My brief predicted ~+0.15 s per quiz and told you to accept it; you found a
shape that costs nothing. Two steps in a row now where the duration-neutral version
existed and I did not see it.

## 2. Partly met: the onset criterion

Options reach −25 dB in 20–30 ms, against 40–50 ms for untrimmed segments. One frame
better than before, not the same range. Your reason — sweeping to 90 ms showed longer
fades attenuate real speech — is the right trade and I am recording it as settled rather
than asking for another pass. **The criterion I wrote was too strict; the constraint you
found is real.**

## 3. The residual, measured, and my call on it

Dip at each join, gap floor minus the quietest of the segment's first 30 ms:

```
                                n   median    worst   worst segment
quiz (resume)                   9    0.2 dB   10.9 dB  answer
vocabulary (restaurante)       24  -17.9 dB   16.2 dB  pair_3
true_false (your/you're)        4    8.0 dB   15.4 dB  think
```

Negative means the speech starts above the floor — no hole at all.

Every remaining dip is on a segment `_trim` never touches: an untrimmed clip brings its
own pre-roll, which can sit below the gap floor. Same defect class, different population,
and smaller — worst 16 dB against the 23 dB we started with, and it is a dip to about
−91 dB for a few tens of milliseconds, with no slam behind it.

**My call: stop here. Do not build a Step 6 for this.** A −91 dB dip under a −75 dB floor
is below what consumer playback resolves, and the thing that made the old 23 dB dip
audible was the −12 dB slam right after it, which is gone. Chasing it would cost real
work for something nobody can hear. Recorded so a future reader knows it was measured and
left deliberately, not missed.

## 4. The one thing the audio work still owes

`duration_calibrate.py`, re-fitted over a batch of new videos rather than these three.
Stale on two axes — the tail pads from `411ace4`, and whatever `44d1b34`/`99ee39d` did
not change (both turned out duration-neutral, so the gap and lead-in work costs nothing).
Until it is re-fitted, every duration the guard and the dashboard predict is wrong by
roughly the tail padding.

That is the last item. The thread the owner opened — *"se escucha como cortado
antinatural"* — is closed: no word is cut, no gap is dead, no entry punches through the
floor.

## 5. Still uncommitted

Ten files in `src/` unrelated to this thread: `admin.py`, `clip_contrast.py`,
`length_spec.py`, `studio/bilibili_production.py`, `video/fill_blank.py`, `video/quiz.py`,
`video/utils.py`, `video/vocabulary.py` and the rest. Not mine to commit and not part of
this work, but they have been sitting there across five steps, and `411ace4`, `44d1b34`
and `99ee39d` only stay independently revertible while they stay out.
