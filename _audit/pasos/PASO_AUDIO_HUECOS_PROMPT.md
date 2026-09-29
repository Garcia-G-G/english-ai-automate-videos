# Step 4: the gaps, not the cuts

## 0. The ONE-LINE version of what the owner asked for

> "estoy empezando a escuchar más los audios de los videos no sé porque se escucha
> como cortado antinatural"

Still the same line. The owner has confirmed the last step improved it. **No word is
cut any more. The holes between the words are what is left.**

---

## 1. Where it stands, measured now

Exact-digital-zero fraction, post-repair:

```
vocabulario_restaurante (repaired)   65.7 s   28.1 %
your_o_you_re          (repaired)    26.4 s   34.9 %
resume_no_es_resumir   (untouched)   38.2 s   33.7 %
no-brainer / educational             49.4 s    5.1 %
```

The repair moved vocabulary 30.3 % → 28.1 %: that difference is the repaired clips'
own noise-floor pads. The rest is `generate_silence`.

`src/tts_common.py:398` builds every gap with `anullsrc`, which emits exact zeros.
The voice's own floor measures around −80 dB. So the mix is: voice at −80 dB floor →
**absolute nothing** → voice at −80 dB floor, 8 to 25 times per video. The ear does
not hear the silence, it hears the floor vanish and come back. That is the remaining
half of "spliced tape".

16 call sites, one function. The fix is at the source.

---

## 2. The fix

`generate_silence` emits room tone at the measured floor instead of digital zero.
You already built the machinery for this inside `repair_truncated_tail` — `anoisesrc`
with a controlled amplitude — so this is the same idea applied to the gaps.

**Duration-neutral by construction**, and that gives the sharpest acceptance test
this defect has had: the function takes a duration and must return exactly that
duration. Every regenerated file's declared duration must come out **identical**, not
approximately identical. If any duration moves, the fix is wrong.

**Derive the level from measurement**, as before. Too low and the floor still
audibly vanishes; too high and you have added hiss to every video on the channel.
Measure the clips' own floor across several files and match it, rather than reusing
`TAIL_NOISE_DB` because it is already there — the pad's floor and a gap's floor are
different jobs and may want different numbers.

**The silent countdown is the biggest single hole**: 4.5 s of 72,000 consecutive zero
samples, the longest stretch of absolute nothing in any video, right before the
answer. It is by design as *silence* — the owner wants the pause — but it does not
have to be *dead* silence. It is the most audible instance of this defect.

---

## 3. The thing that could silently undo this

The concat re-encodes with `libmp3lame -q:a 2`. MP3's psychoacoustic model discards
content it judges inaudible, and very low-level broadband noise sitting next to loud
speech is exactly what it is built to throw away. **A gap file that measures −80 dB
on its own can come back as exact zeros after the concat.**

So: verify on the **final concatenated mp3**, never on the silence file. If the
encoder eats it, the options are raising the level (measure whether it is then
audible as hiss) or concatenating through a lossless intermediate and encoding once
at the end. Do not conclude the fix works from a measurement taken before the
encoder ran.

---

## 4. What closes this step

1. Exact-zero fraction on the final mix drops to near zero on a regenerated file of
   each affected type. Show the table against §1.
2. The gap floor in the final mix lands within a few dB of the surrounding clips'
   own floor — **not above it.** State both numbers.
3. Declared durations **identical** before and after.
4. `tools/audio_seams/corpus.py` CLIFF stays at 0 on the regenerated files.
5. One regenerated video rendered end to end. The owner watches videos.

---

## 5. Still out of scope

- **Defect C**, `TRIM_LEAD_PAD = 0.02` — options entering from silence to −11 dB in
  30 ms. After this.
- **`duration_calibrate.py`** — still deliberately stale, still waiting on a batch of
  new videos rather than two. This step should not change it at all, since it must
  not change any duration.
- **The ten uncommitted files** in `src/` — not mine to commit, but they are still
  sitting there, and `411ace4` is only revertible on its own while they stay separate.
