# The quiz floor is tight because one number is doing two jobs

Reply to the review of the per-type band commits. Items 1, 2, 4 and 6 are text
fixes and the reviewer is right on all four — take them. This note is only about
item 3, the floor, and about the 17 deleted scripts.

## The floor: 2.2 s of room is not a margin, and widening it is not a compromise

Measured, video duration (narration + 4 s outro):

```
1 item        47.5
2 items       76.9   79.0   91.7   93.4      <- the four fitted renders
3 items      127.9
band         74.7   85.3   96.0
```

2.2 s under the shortest render, 2.6 s over the longest, from four samples whose own
spread is ±10 %. The fifth good render lands outside on either side with ordinary luck.

**But the floor is not too tight by accident — it is tight because `band()` is used
for two different jobs.** `word_target` and `word_range` read it to *aim* the
generator; `check()` reads the same numbers to *reject* an artifact. Those want
opposite things:

- **Aiming** wants a narrow window. Telling the generator "write for 85 s ±11 s" is
  what makes scripts land the right length. That window is correct as committed.
- **Rejecting** wants a wide one, because the two errors are not symmetric. A video
  a few seconds short is a mild quality problem. A false reject **stops production** —
  and that already happened here: the owner's *"se generan y no aparecen"* was a
  guard refusing work for reasons that were not correctness.

What does the floor actually have to catch? One thing: a quiz that spoke one item
instead of two. That is 47.5 s against a shortest real 76.9 s. Anywhere in between
separates them:

```
midpoint 1-item / shortest 2-item   62.2      14.7 s of room under the shortest render
midpoint longest 2-item / 3-item   110.7      17.2 s of room over the longest
```

A rejection threshold at 62 / 111 still catches both wrong formats by a wide margin
and cannot plausibly block a good video. The aiming window stays 74.7 / 85.3 / 96.0.

**Proposal:** keep `band()` as it is for aiming, and give `check()` its own
`reject_min` / `reject_max`, falling back to the band where a type does not declare
them. Same shape as the per-type band you just built, one layer along.

If that is more machinery than it is worth today, the cheap version is to widen
quiz's `min_seconds` to ~62 and accept that the aiming window and the rejection
window are the same, looser, number — but then say so in the comment, because a
future reader will otherwise read 62 as "this is the length we want".

Either way, the reviewer's instinct is right and worth writing down: **a threshold
derived symmetrically from a median is not a threshold derived from what it has to
catch.**

## The 17 deleted scripts are not a deletion

Third time this alarm is raised, third time it is the same answer. All 17 are in
`content/queue/_done/`:

```
bz003 cm015 cw002 cw003 cw005 exp003 exp004 ff005 ff012 ff013
ff020 ff028 ff032 food003 pr002 pr003 pr006          17 of 17 present
```

`--done` moves a script there when it has been made into a video. `pr002_bit_beat`
and `pr003_cat_cut` are cited by the calibration precisely *because* they were
rendered — that is where the samples come from. Restoring them would requeue topics
that are already published.

It is worth adding a line to the queue's own docs so the fourth reviewer does not
have to ask: **a script missing from `content/queue/<type>/` and present in
`content/queue/_done/` is consumed, not lost.**

## Agreed without comment

Items 1 (the self-contradicting silence comment), 2 (the two "no type overrides
anything yet" docstrings), 4 (the rounded floor in the reason message) and 6 (the
redundant `.lower()`). All four are text against code, and the code is right.

And item 5 is mine: the note is moved to `_audit/notas/` with a superseded header,
and the other eleven briefs went with it to `_audit/pasos/`.
