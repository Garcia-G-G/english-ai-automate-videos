# STEP 60 — Owner's verdict on lv001 and sy001: the format is approved; fix the cut words and give long sentences more time

The owner watched both renders on his phone (2026-10-15). His verdict: **"la categoría en
sí está muy bien"**. He asked for two changes:

1. "Unas pares de palabras se escuchan cortadas, sobre todo en cocina" (lv001).
2. "El ritmo podría bajar un poco en oraciones muy largas como restaurante. En vez de
   3 s, 5 s, para que el usuario tenga más tiempo de pensar" (sy001).

Run this after STEP 59. If STEP 59 has not started, do STEP 59 §1 (push) first and then
this, and treat STEP 59 §2 (onset gate) together with §1 below: they touch the same clips.

## 1. Cut words: the trim eats the first consonant

What I measured in `output/artifacts/lv001_cocina/audio/narration.mp3`: the first 80 ms
of every prompt, in 10 ms steps, in dB relative to that clip's peak. The 80 ms before
every clip sit at -71 to -75 dB, i.e. digital room tone.

| word | first 10 ms | reading |
|---|---|---|
| fridge, frying pan, oven, colander, cutting board, ladle | -72 to -75, then a ramp | onset intact |
| **knife** | **-27** | starts mid-consonant: hard cut |
| **spoon** | **-59**, no ramp from the floor | /s/ chopped |
| **sink** | **-53**, no ramp | /s/ chopped |
| **stove** | **-53**, no ramp | /s/ chopped |

Cause: `trim_clip_silence` cuts at `measure_speech_start` minus `TRIM_LEAD_PAD = 0.02 s`,
and speech start is where the level first crosses `SPEECH_EDGE_THRESHOLD_DB = -45 dBFS`,
an absolute threshold. A soft /s/ or /n/ sits below -45 dBFS for its first 30–100 ms, so
the cut lands inside the consonant. The tag at line 269 ("only avoids clipping the attack")
was measured on option clips that start with vowels and loud consonants.

The fix is in `src/tts_common.py`, and you are authorized to change it:

- Lead pad 0.02 → **0.08 s**, plus a **5 ms linear fade-in** on the trimmed clip, so no
  clip ever starts on a non-zero sample.
- Find the speech start with a threshold **relative to the clip's own peak** (start with
  -50 dB re peak; measure), not with the absolute -45 dBFS. Keep the absolute value as a
  floor for near-silent clips.
- Add a regression test: a synthetic clip of 100 ms of silence, 80 ms of noise at -50 dB
  re peak (the "s"), then a vowel at peak. The trimmed clip must keep ≥ 70 ms of the
  noise.
- Re-measure the table above on a fresh lv001. All ten rows must ramp up from the floor.
  STEP 59's onset-gate table (which takes are "dirty") must be redone after this fix: some
  "dirty" verdicts may have been this cut, not the voice.

The trim also runs for how_do_you_say. Existing renders do not change; new ones do.
`test_how_do_you_say_renders_byte_identically` pins frames, not audio, so it is
unaffected.

## 2. More thinking time for long sentences (say_it_level)

The owner asked for 5 s instead of 3 s on very long sentences. I measured what a flat 5 s
would cost: +20 s on every video. sy001 would go from 77 s to about 97 s. The
how_do_you_say Shorts that work run about 70 s. So scale the pause by sentence length:

| `spanish` length (characters) | think |
|---|---|
| ≤ 20 | 3.0 s |
| 21–27 | 4.0 s |
| ≥ 28 | 5.0 s |

- Over the 100 scripts this adds +2 to +18 s (median +9.5 s).
- sy001 adds +10 s: rows 1, 5, 7 and 9 get 5 s, rows 6 and 10 get 4 s. Expected total
  about 87 s with the outro.
- Put the rule in `LEVEL_PLANS["say_it_level"]`, next to `think`, as a function of the
  prompt text. The timeline already reads per-segment durations, so the renderer should
  not need changes; confirm it.
- **Duration ceiling:** give `say_it_level` its own `reject_max_seconds = 95` in
  `duration_spec` (STEP 49 §5 lever 4: the owner chose more thinking time over the 80 s
  ceiling). If any of the 100 scripts would still go over 95 s, list them, and I shorten
  them.
- level_test keeps `think = 1.7 s`; the owner did not ask to change it.

## 3. Re-render both and stop

- Re-render lv001 cocina and sy001 restaurante. Reuse cached clips where the text is
  unchanged. A clip whose trim changed must be re-trimmed from the original download, if
  it is kept. Otherwise re-ask it and count the cost.
- Then **stop**. The owner listens to knife, spoon, sink and stove in lv001, and to the
  long rows of sy001.
- `pronounce_level` (all English words, so all exposed to this cut) starts only after he
  confirms the fix.

## Constraints

Only OpenAI and ElevenLabs are paid. Everything else is local and free. No MoviePy.
The ceiling is $0.30 per Short. No keys, `.env`, voice IDs or home paths in commits.
Commit messages carry no attribution lines. Do not commit the other session's
uncommitted files.

## Report back

- The §1 table re-measured on the new lv001: all ten words, first 80 ms.
- The new test, and how many STEP 59 "dirty" takes turn clean after the trim fix.
- sy001: the duration, the think per row, and the cost. The duration of all 100
  say_it_level scripts as predicted by `duration_calibrate` (min / median / max) and any
  over 95 s.
- Paths of both new renders.
- Test counts: pass / fail, naming any failure that is not yours.
