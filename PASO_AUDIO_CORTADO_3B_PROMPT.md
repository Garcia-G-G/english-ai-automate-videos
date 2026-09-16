# Step 3b: the instrument is fixed, the proof is still owed

## 0. The ONE-LINE version of what the owner asked for

Unchanged. **Make the audio stop sounding like spliced tape.**

---

## 1. I verified the repair myself. It works.

Not from your report — from the audio. I cut `pair_0` out of the concatenated
vocabulary file (3.12→5.12, one of the guillotined ones, tail −22.2 dB), ran
`repair_truncated_tail` on it, and profiled the result against a natural ending
from the same file.

Aligned to the end of speech, 10 ms frames, dB:

```
ms from speech end:      -30  -20  -10   +0  +10  +20  +30  +40  +50  +60  +70  +80  +90 +100 +110 +120
unrepaired               -23  -21  -20  -76  -79 -140 -140 -140 -140 -140 -140 -140 -140 -140 -140 -140
repaired                 -23  -21  -21  -53  -60  -65  -66  -68  -71  -71  -74  -75  -77  -79  -80  -82
natural (repeat_3_take2) -54  -57  -50  -56  -62  -69  -72  -68  -73  -77  -70  -68  -74  -76  -81  -73
```

Monotonic decay onto a noise floor, tracking the natural reference from +10 ms
onward. `esin` / 30 ms / 0.244 / noise-floor pad were good choices, and catching
that `apad` writes exact zeros — and that naive fade+apad would rebuild Defect B
*inside* every repaired clip — was the best call in the step. 35 dB → 4.93 dB is
the difference between a repair and a new defect.

---

## 2. The end-to-end proof does not exist on disk

`output/audio/vocabulary/vocabulario_restaurante_20260915_234047.{json,mp3}` is
still the original:

```
declared duration   62.56 s        (you reported 66.47 s)
pair_11 tail        -21.7 dB       (you reported -29.6 dB)
seam counts         6/25           (you reported 8/25 after)
```

Every seam value is identical to Step 1's measurement to the decimal. TTS varies
run to run, so identical numbers mean identical bytes: this file was not
regenerated. No file anywhere under `output/` has a duration near 66.47 s.

I am not guessing at what happened — most likely the regeneration went to a temp
directory that was cleaned up, in which case your numbers were real and simply did
not persist. But the artifact is the proof, and there is no artifact. **Re-run it
and let it land where it belongs.**

Also uncommitted, which is how it stays fragile: `src/tts_common.py`,
`src/tts_elevenlabs.py`, `src/admin.py`, `src/clip_contrast.py`,
`src/length_spec.py`, `src/studio/bilibili_production.py`, `src/video/fill_blank.py`,
`src/video/quiz.py`, `src/video/utils.py`, `src/video/vocabulary.py`. Commit the
tail repair on its own so it can be reverted on its own.

---

## 3. `corpus.py` was blind, not unusable. It is fixed.

You were right that it cannot see the repair, and right about why: the fade lands
*after* the recorded end, and every criterion the old metric had was anchored 60 ms
*before* it. Where you went one step too far is "treat its numbers as unusable" —
the instrument was repairable, and an auditor without an instrument is just an
opinion.

`tools/audio_seams/corpus.py` now reports two columns:

- **CLIFF** — loud tail **and** the audio sits at digital-zero territory 40–120 ms
  later (past the mp3 decoder ringing that follows any hard cut). This is the
  defect. A repaired clip stops being counted.
- **DROP** — the old metric, kept so before/after stays honest. It fires on any
  loud tail followed by a decay, natural or rebuilt, so **a DROP count that does
  not fall after a repair is not a regression. A CLIFF count that does not fall is.**

It separates cleanly on the three clips from §1:

```
pair_0 unrepaired   -140.0 dB
pair_0 repaired      -72.5 dB
natural healthy      -71.7 dB
```

The repaired clip is within 1 dB of natural. That is your acceptance test passing on
an instrument that can see it.

**Baseline to beat**, measured now, 181 videos, 1,850 segments:

```
type             CLIFF (the defect)   DROP (read with care)
educational              6/536 = 1%            58/536 = 11%
fill_blank             34/189 = 18%            41/189 = 22%
pronunciation             1/96 = 1%               6/96 = 6%
quiz                    49/586 = 8%            69/586 = 12%
true_false             40/103 = 39%            48/103 = 47%
vocabulary             99/340 = 29%           106/340 = 31%
TOTAL                229/1850 = 12%          328/1850 = 18%
```

---

## 4. What closes this step

1. Regenerate the vocabulary file and one true_false file **to their real paths**,
   and render both videos end to end. The owner watches videos; measured audio is
   not the same as a video seen.
2. `corpus.py` on those regenerated files. CLIFF must fall toward zero on the
   repaired types. Show the table.
3. Commit the tail repair as its own commit.

## 5. Agreed, and still out of scope

- **`duration_calibrate.py` deferred** — your reasoning is right and I am recording
  it rather than arguing: fitting 180 unpadded sidecars plus 1 padded one would bake
  in a wrong constant. It runs after a batch of new videos, not before. Until then
  every prediction the guard and the dashboard make is stale by roughly the padding,
  ~+3.9 s on a 12-pair vocabulary. That is a known-wrong number, not an unknown one.
- **`[pause]` at 8/12** — correctly rejected. 67 % is not a fix, and the repair
  covers 100 % of cases including those. Worth keeping in the notes: it is the only
  evidence we have about what the model responds to, if this ever needs revisiting.
- **Defect B** — next step, and smaller than it was: repaired clips now carry a
  noise floor instead of zeros, so the gaps between them are what is left.
- **Defect C**, `TRIM_LEAD_PAD = 0.02` — after B.
