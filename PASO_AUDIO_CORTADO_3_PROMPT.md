# Step 3: try not to lose it, then reconstruct what is lost

## 0. The ONE-LINE version of what the owner asked for

> "estoy empezando a escuchar más los audios de los videos no sé porque se escucha
> como cortado antinatural"

Unchanged. Step 1 found the cause, Step 2 measured the damage, this step repairs it.

---

## 1. My threshold was the wrong instrument, and your profile was the right one

Stopping at the gate was correct. But the gate I wrote was badly built, and you
found it: **span length is not a measure of missing audio.** It sums three things
that have nothing to do with each other — delivery rate inside a bilingual
utterance, the measurement-window difference between a file end and a −45 dB
crossing, and actual absent content. My ">80 ms means content is lost" rule read
123 ms and called all of it loss. Only ~30 ms of it was.

Your aligned tail profile is the instrument that answers the question I was
actually asking:

```
mono_2   -28  -29  -31  -32  -35  -41  -52  -65  -68  -71   <- decays past the end
bi_2     -31  -26  -29  -26  -24  -26 -140 -140 -140 -140   <- full level, then nothing
```

**Rule, for the next time this comes up: measure the envelope aligned to the end of
speech, not the length of the span.** A span difference has confounds; an envelope
that stops existing does not.

Also right: re-running with one method across both conditions after spotting that
the first pass used `measure_speech_start` for mono and `silencedetect` for
bilingual. Same +123 ms, so the method was not the confound — and now we know it
rather than assuming it.

---

## 2. What is actually missing, and why that changes the verdict

Not a phoneme. Not a syllable. Whisper hears `menu` in 6 of 6 clips. What is gone is
**~30 ms of amplitude decay** — the die-away at the end of the word.

That distinction decides the whole step, because of one asymmetry:

> A missing phoneme cannot be reconstructed. A missing amplitude envelope can be,
> because an envelope *is* an amplitude curve, and that is exactly what a fade
> produces.

So the "fix that hides its own failure" framing I wrote in the previous brief does
not apply here the way I expected it to. A fade is not papering over a lost sound.
A fade is the die-away, resynthesised. That is a legitimate repair — **provided we
prove the resynthesised curve matches the natural one, instead of assuming a round
number does.** §4 makes that provable.

None of which means we should accept the loss if we can avoid it. §3 first.

---

## 3. First: try to make ElevenLabs not cut it

Your proposal, and it is the right order of operations — do not repair what you can
avoid breaking. ~60 characters per variant, 3 takes each.

Test whether anything appended to the text makes the API return the decay:

| # | text sent | idea |
|---|---|---|
| 1 | `la carta... the menu. ` | trailing space |
| 2 | `la carta... the menu.\n` | trailing newline |
| 3 | `la carta... the menu...` | terminal ellipsis |
| 4 | `la carta... the menu. Sí.` | monolingual Spanish guard, trimmed off after |
| 5 | `la carta... the menu. [pause]` | v3 audio tag as guard (`src/audio_tags.py` already owns tag parsing) |

Measure each with the **aligned tail profile**, not with span length. A variant
passes only if the profile decays like the monolingual reference.

Note on variant 4: it works even if the trigger is "contains a transition" rather
than "ends in the other language", because it moves the cut point onto throwaway
audio. It costs a trim step — `silencedetect` the internal pause, cut before the
guard — so prefer 1–3 if any of them pass. Do not build the trim unless 1–3 all
fail and 4 passes.

**If a variant passes, that is the fix and §4 is unnecessary.** Report which one and
stop. Confirm it on a second word pair before believing it — one word is one word.

---

## 4. If nothing passes: reconstruct the decay, and prove the shape

Apply only to clips measured as truncated (`duration - measure_speech_end < TAIL_MIN`),
so healthy clips are never touched. Applied right after `generate_segment_audio`
returns and **before** `add_audio` measures the clip, so the timeline stays consistent.

```
afade = t:out, st = <dur - FADE>, d = FADE, curve = <chosen>
apad  = pad_dur = <TAIL_PAD>
```

Three constants, and **none of them is a round number you pick.** Derive each from
the monolingual reference clips you already have:

- **FADE** — from the measured natural decay. Your monolingual median is 30 ms to
  fall −40 → −60 dB. Bilingual clips end at a median −38 dB, so the fade has to
  cover roughly that same drop from roughly that same level.
- **curve** — `afade` offers `tri`, `exp`, `log`, `qsin` and others. A linear fade
  from −38 dB is close for the first two thirds and then dives to −∞ faster than
  speech does. Try the curves, keep the one whose profile lands nearest the
  monolingual reference. This is the difference between reconstruction and masking,
  and it costs one loop over a handful of files.
- **TAIL_PAD** — the corpus median of healthy tails, which Step 1 measured at
  0.244 s. Not 0.25 because 0.25 is tidy.

### Acceptance test — this is the point of the step

Overlay the aligned tail profile of a repaired bilingual clip on the monolingual
reference. **They should be hard to tell apart.** Show both rows, the way you showed
`mono_2` and `bi_2`. If the repaired curve still stands out, the constants are wrong
and the fix is a mask — go back and pick better ones rather than shipping it.

Then, as before:

1. `tools/audio_seams/corpus.py` before and after, both tables, hard-cut counts per type.
2. One regenerated vocabulary video and one true_false video, end to end.
3. Re-run `tools/duration_calibrate.py` — padding lengthens videos (~+6 s on
   vocabulary) and every prediction it makes is stale until it is re-fitted.

### Record the residual

Whatever the outcome, write into the code — not into a commit message that scrolls
away — that these clips carry a reconstructed decay rather than the model's own, and
what the measured residual is. A future reader measuring these files deserves to
know the envelope at the end is ours.

---

## 5. Still out of scope, on purpose

- **Defect B**, the `anullsrc` digital zeros filling 29–38 % of the segmented types.
  Next step. Duration-neutral fixes only; no crossfades.
- **Defect C**, `TRIM_LEAD_PAD = 0.02`. After B.
- **No TTS model change.** The cross-tab is still confounded; every video type uses
  exactly one model.
- **The shadowed keys in `~/.bash_profile`** — recorded in the Step 2 brief §6, still
  the owner's shell to fix, still not a commit here.
