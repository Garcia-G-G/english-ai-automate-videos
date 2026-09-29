# Step: two questions per quiz — and the band that cannot serve six types

## 0. The ONE-LINE version of what the owner decided

> **Two questions per quiz.** He listened to both cuts and picked the 1:24 one.

Not because three is too long in the abstract: because the same *"piensa bien,
tres, dos, uno"* three times in two minutes is where a viewer leaves. The third
authored item is not wasted — it seeds another video.

## 1. Measured, on your render

```
3 items   123.9 s   40.7 s with no voice  (33 %)   13.6 s per item
2 items    83.7 s
1 item     43.5 s   (under the 50 s floor)
```

The 40.7 s is gaps (27.2 s) plus the countdown, which is silent by design (13.5 s).
Your 13.2 s per item was right; my first count missed the countdown and I am
correcting it here rather than leaving two numbers in circulation.

## 2. Do NOT just raise `max_seconds`

`config.yaml:62-64` is **one band for all six types**:

```yaml
duration:
  band:
    min_seconds: 50.0
    max_seconds: 80.0
    target_seconds: 65.0
```

There is no per-type override — `duration.types` carries `rate`, `silence`, `n`,
`fixed_words`, `items_spoken`, and no band. So raising the ceiling to fit a 2-item
quiz also stops the guard catching a runaway educational or vocabulary video. One
number cannot describe six formats whose natures differ by design.

**The fix is a per-type band**, falling back to the global one where a type does not
override it. Quiz gets its own ceiling, derived from §3's measurement and not from a
round number. The owner has already withdrawn the 80 s ceiling verbally — *"para
arriba no tiene techo, siempre y cuando no sean videos de 10 minutos"* — so the
global `max_seconds: 80.0` is stale for every type, but that is a separate decision
and it stays his.

## 3. The recalibration is now blocking, not optional

With `items_spoken: 1` the predictor says a 2-item quiz is **45.5 s**. Your render
says a 3-item quiz is **123.9 s**. The constants were fitted over 1-item videos and
`spoken_words` only counts the items config says are spoken, so today the generator
is being aimed at a target that does not exist.

Order matters:

1. `items_spoken: 2` for quiz in `config.yaml:114`.
2. Render a batch of 2-item quizzes.
3. Re-fit `tools/duration_calibrate.py` over that batch — `rate`, `silence`, and the
   `PER_ITEM_SILENCE` you already moved to 13.2 in `e6b205a`.
4. Set quiz's per-type band from what step 3 measures, with the same reasoning you
   used for the tail constants: derived, not chosen.

Doing 4 before 3 puts a guessed number into a guard, which is the shape of defect
this repo keeps paying for.

## 4. What closes this step

- One 2-item quiz rendered end to end, **sent to the owner to listen to**. His ear is
  the acceptance test, as before.
- `corpus.py` CLIFF still 0 and exact-zero still ~3 % on it.
- The predicted duration for that script within a few seconds of its real length.

## 5. Agreed, not actioned

- **The rename stays undone.** Your reasoning is right: the stale name is a key in
  four places including `replaces_rejected`, and renaming would sever the draft from
  the video it replaces. The two-line root cause at `admin.py:685` waits for whoever
  touches that file next.
- **`[playful]` → `[cheerful]` was my error**, not a judgement call: I put a tag in
  the pools without checking it against the allowlist, and v3 speaks a tag it does not
  know. Your swap is the fix.
- **Finding 2 stays closed.** Recoverable is not the same as ought to be recovered.
