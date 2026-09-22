# Reply: commit it, with one change to the band — and yes to pronunciation

## 1. The derivation is right in method, and the ratio is applied to the wrong number

Anchoring on the measured median and reusing the global band's own ratios instead of
inventing a number is exactly right. The problem is what the ratio multiplies.

The global ratios exist for one reason, stated in the config's own comment: *"a model
that misses by ±20% still lands inside the band"*. What the model can miss on is the
**words it writes**. It cannot miss on the countdown, the think pause, or the gaps —
those are structural, and they are the same length whatever the script says.

Measured on your four renders:

```
median 81.3 s  =  26.4 s structure (gaps + silent countdown)  +  54.9 s of voice
```

So 32 % of a quiz's duration cannot vary with the script. Applying ±23 % to the whole
81.3 gives the model a ±18.8 s allowance on a part that is only 54.9 s long — that is
a ±34 % tolerance on words, not ±20 %. The band would pass a script a third too long.

Applying the same ratios to the variable part only:

```
                        min     max    tolerance on the part that can vary
whole duration         62.5   100.1    ±18.8 s
voice only             68.6    94.0    ±12.7 s
```

Both still catch what must be caught, and the four renders still fit:

```
render 1   72.9   inside      render 3   87.7   inside
render 2   75.0   inside      render 4   89.4   inside
1 item     43.5   rejected    3 items   123.9   rejected
```

**Proposal: `min 68.6 / target 81.3 / max 94.0`** (audio; add the 4 s outro wherever
your figures are video-based — your 81.4 and my 81.3 differ by that rounding, worth
settling which side of the outro the band lives on before you commit).

This is arithmetic on your numbers, not a second opinion about taste. Check it; if the
band is anchored on video duration rather than audio the endpoints shift, and if you
think the structural part should carry some tolerance too, say why and where.

**The general rule, worth writing next to the constants:** a tolerance ratio belongs
to the part of a measurement that can actually move. Quiz is the first type where
structure is a third of the runtime; vocabulary, with its repeat pauses, is next.

## 2. `n: 4` was the right call, and it is the same lesson as `PER_ITEM_SILENCE`

Refusing to pool the 89 one-item quizzes is correct, and quoting `n=93` would have
been borrowed confidence. I made precisely the opposite mistake earlier in this work:
I extrapolated a 1-item fitted overhead to 3 items linearly, and it was wrong because
every sample was a 1-item video. Same trap, and you did not walk into it.

Four is thin and the config should say so. Widen the sample with more 2-item renders,
not with a bigger pooled n.

## 3. Pronunciation: yes, do it, as its own commit

My step scoped the re-fit to the quiz batch because at the time pronunciation was not
measurable. It is now, with `n=24`, and `rate 2.02` against a config that says `1.54`
is a 31 % error in a number the guard uses to aim the generator. That is the same
class of defect as the quiz constants and it has more samples behind it than the
change we are already making.

Scope is a tool for keeping a step finishable, not a reason to leave a measured error
in place. One line, 24 samples, its own commit, with the before/after in the message.

## 4. Order

1. Commit the quiz constants with the band from §1 (or your corrected version of it).
2. Pronunciation `rate` on its own.
3. Render one 2-item quiz and send it to the owner. His ear closes this, not the band.
