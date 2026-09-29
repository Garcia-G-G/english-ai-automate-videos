# Step 5: the entries — and a hole Step 4 made visible

## 0. The ONE-LINE version of what the owner asked for

> "estoy empezando a escuchar más los audios de los videos no sé porque se escucha
> como cortado antinatural"

Words no longer get cut. The gaps are no longer dead. **What is left is how the voice
comes back in.**

---

## 1. First, the git locks are mine. Nothing is crashing.

You flagged it twice, so it needs closing properly rather than staying a mystery.

I run my commits through the device bridge, and **that bridge cannot delete files.**
Proof, run just now in this repo:

```
$ touch .git/PRUEBA.lock && rm .git/PRUEBA.lock
rm: cannot remove '.git/PRUEBA.lock': Operation not permitted
$ ls .git/PRUEBA.lock
.git/PRUEBA.lock          <- still there
```

`git` creates `HEAD.lock`, `index.lock`, `next-index-N.lock` and then tries to unlink
them. From my side the unlink always fails, so **every commit I make leaves its locks
behind.** They are stale the instant they are written. `_to_delete/git-locks/` already
holds 7 of them.

So: **in this repo, a lock with no live git process is debris, not a signal.** Do not
wait on one. Check for a process, and if there is none, move it and carry on. You lost
time waiting on a lock I left. That is on me, and it is not a crash to hunt.

---

## 2. Step 4 worked, and it made Defect C audible

Verified independently — 3.2 % / 3.2 % / 3.0 % exact zero, longest hole 1–8 ms, gap
floor −75.5 / −75.1 dB against voice at −15.5 / −16.2. Deriving `GAP_FLOOR_DB = −75`
by measuring gaps and clip interiors separately, rather than inheriting −58 from the
tail pad, was the right instinct — and catching your own blended-percentile error
before reporting it is the second time in this thread that a correction came from you
and not from me.

But now look at what happens at the start of an option, 10 ms frames, dB:

```
              -80  -70  -60  -50  -40  -30  -20  -10   +0  +10  +20  +30  +40  +50
option_b      -75  -75  -75  -75  -75  -75  -75  -75  -98  -62  -20  -12  -11  -10
option_c      -75  -75  -76  -75  -76  -75  -76  -75  -98  -61  -25  -13   -9  -10
option_d      -75  -75  -75  -75  -75  -75  -76  -75  -87  -61  -47  -14  -10  -10
```

The gap holds a steady −75 dB room tone. Then, at the exact sample the option clip
starts, it **drops to −98** — a hole punched in the floor — and slams to −12 within
30 ms.

`trim_clip_silence` keeps `TRIM_LEAD_PAD = 0.02` of the clip's *own* leading silence,
and that silence is ~23 dB quieter than the room tone we now put in the gaps. Before
Step 4 this was invisible: the gap was digital zero, so −98 was an improvement on its
surroundings. Now the gap has a floor and the retained lead-in punches through it.

**Step 4 did not cause this. It revealed it.** But the audible result today is a tick
before every option, which did not exist yesterday, so it is worth saying plainly.

Onset times to −25 dB, measured:

```
trimmed    transition 30 ms   option_a 20   option_b 20   option_c 20
untrimmed  question   50 ms   answer   40   explanation 30
```

20 ms from silence to full speaking level. No human onset does that.

---

## 3. The fix is the mirror of the one you already built

`repair_truncated_tail` gave clips a decay at the end. This is the same shape,
reversed: a lead-in that **starts at the gap floor** and rises, instead of a lead-in
that dips below it and jumps.

Concretely, after the trim:

- the retained lead-in sits at `GAP_FLOOR_DB`, not at whatever the clip's own
  pre-roll happens to be — so the floor is continuous across the join
- a fade-in over the length the *untrimmed* segments actually take, which measures
  40–50 ms, not the 20 ms a trimmed clip takes now
- the curve chosen the way you chose `esin`: by matching the measured natural onset,
  not by picking one

Raising `TRIM_LEAD_PAD` alone does not fix it — it keeps more of the same too-quiet
pre-roll, so the dip gets longer instead of going away.

**Timeline note:** `add_audio` measures after `_trim`, so lengthening the lead-in is
accounted for. But this one is not duration-neutral, unlike Step 4 — it adds ~20–30 ms
per trimmed clip, roughly +0.15 s on a quiz. Small, and it stacks with the tail pads.

---

## 4. What closes this step

1. The frame table above, after the fix: no frame below the gap floor at any segment
   start. That is the acceptance test, and it is a single table.
2. Onset-to-−25 dB for trimmed segments lands in the same range as untrimmed ones.
3. `corpus.py` CLIFF stays 0; exact-zero stays ~3 %.
4. One quiz re-rendered end to end.

## 5. After this

`duration_calibrate.py` is now stale on three axes — tail pads, the gap change, and
whatever this step adds. That makes re-fitting it the natural next step once a batch
of videos exists, and it is the last thing the audio work owes before the queue can
be trusted again. Defect C closes the "cortado antinatural" thread the owner opened.
