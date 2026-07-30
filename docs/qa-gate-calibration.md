# QA gate calibration

Measured 2026-07-30 on the frozen corpus (195 paired mp3+json artifacts under
`output/audio/`). Every number here came out of ffmpeg. None was guessed, and
none was carried over from the trap notes — two of those predictions did not
survive measurement, and that is recorded below.

All of it reproduces from `src/qa_gate.py`; the exploratory harness is in the
session scratchpad.

---

## 1. Which model produced which artifact

**The TTS JSONs do not record the TTS model.** `_meta.model` is `gpt-4o-mini`,
the *script* generator. Only three files carry `model_id`, and they are
`.ttsplan.json` dry-run plans, not audio metadata.

So artifacts are labelled by the code path that produces their type, from
`pipeline.py:157`:

| video_type | path | model |
|---|---|---|
| `educational`, `pronunciation` | `tts_bilingual.generate_bilingual_narration` | `eleven_turbo_v2_5` |
| `quiz`, `true_false`, `fill_blank`, `vocabulary` | `tts_elevenlabs.generate_*_audio_segmented` | `eleven_v3` |

This labelling is by *current* routing. Historical artifacts span four
generator eras and their true model is unrecorded, so the label is an
inference, not a fact, for anything older than the bilingual path. Recording
the model in the TTS JSON would remove the guess and is worth doing.

One confirmed case exists: `educational/to_be_swamped_20260414_142502` has a
paired `.ttsplan.json` declaring `model_id: eleven_turbo_v2_5`.

---

## 2. Noise floor — two models, measured separately

Method: find regions ffmpeg *actually* reports as quiet, inset each edge by
60 ms so speech at the boundary does not leak in, then `volumedetect` inside.
Measuring discovered silence rather than declared silence matters — see §3.

| group | files | n | p10 | median | p90 | worst |
|---|---|---|---|---|---|---|
| `eleven_v3` (quiz, true_false, fill_blank, vocabulary) | 30 | 288 | **-91.0** | -65.2 | -54.7 | -50.1 |
| `eleven_turbo_v2_5` (educational, pronunciation) | 19 | 169 | **-71.2** | -62.4 | -55.3 | -50.2 |

Per type:

```
eleven_v3  : quiz          files=12 n=119  p10 -91.0  median -68.0  p90 -54.2
eleven_v3  : true_false    files= 8 n= 69  p10 -91.0  median -63.9  p90 -54.2
eleven_v3  : fill_blank    files= 8 n= 80  p10 -91.0  median -63.3  p90 -56.2
eleven_v3  : vocabulary    files= 2 n= 20  p10 -91.0  median -71.2  p90 -57.2
turbo_v2_5 : educational   files=12 n=120  p10 -69.5  median -62.4  p90 -55.3
turbo_v2_5 : pronunciation files= 7 n= 49  p10 -73.4  median -62.0  p90 -55.2
```

**The two floors differ in shape, not at the decision boundary.**

`eleven_v3`'s p10 is exactly **-91.0 dB** — 16-bit digital silence — because
the quiz path splices `anullsrc` between segments
(`tts_elevenlabs.py:622-633`). Its floor is *bimodal*: spliced digital silence
at -91, natural pauses around -55 to -65.

`eleven_turbo_v2_5` has no synthesized silence anywhere, so its quiet is
entirely LAME room tone and its floor is *unimodal*, bottoming out at -71.

At the p90 end — where the threshold decision is actually made — they agree
within **0.6 dB**. One threshold therefore serves both. That is a measured
conclusion; had the p90s diverged, the threshold would have had to be
per-model.

### Correcting trap (b)

The trap predicted a LAME noise floor "typically -40 to -50 dB". Measured, the
floor is **-55 to -91 dB** — 10 to 40 dB lower. `-q:a 2` preserves near-silence
much better than the prediction assumed, and the quiz path's silence is
synthesized rather than recorded. Had -45 dB been adopted as the *floor* rather
than derived as the *threshold*, the gate would have classified genuine silence
as speech throughout.

---

## 3. Declared silence is not a safe calibration source

The first calibration pass derived gaps from each artifact's own declarations
and produced an incoherent answer: gaps taken from `segment_times` measured
**-91.0 dB unanimously**, while gaps taken from `words` measured **-7 to
-30 dB** — speech level.

That is not a calibration problem. It is a finding:

- Time base is sound. `last_word_end / measured_duration` has median **0.98**
  across 66 files with word timelines; 0 of 66 exceed the audio, 2 of 66 cover
  under 90%.
- So the word timelines *span* the audio correctly, but their inter-word gaps
  land mid-speech. They are **estimated, not measured** — plausible numbers
  that were never aligned to the waveform.

Consequence for the gate: the noise floor must be calibrated on *discovered*
silence, never on word-timeline gaps. Consequence for the product: for
`educational` and `pronunciation` there is no measured timing anywhere in the
pipeline, which is precisely the gap check 2 exists to close.

---

## 4. Threshold

```python
SILENCE_THRESHOLD_DB = -45.0
SILENCE_MIN_DUR      = 0.10
EDGE_INSET           = 0.06
```

`-45 dB` sits about **5 dB above the loudest silence observed in either model**
(-50.1 / -50.2) and about **27 dB below speech** (whole-file mean runs -15 to
-18 dB).

Justified by a boundary-stability sweep — for each declared segment start,
the distance to the nearest measured speech boundary, over 5 artifacts and 37
segments:

| noise | median abs drift | p90 | speech regions |
|---|---|---|---|
| -30 dB | 0.104 | 0.546 | 23.0 |
| -35 dB | 0.103 | 0.550 | 21.8 |
| -40 dB | 0.103 | 0.557 | 21.0 |
| **-45 dB** | **0.101** | **0.598** | **20.0** |
| -50 dB | 0.090 | 0.610 | 19.2 |
| -55 dB | 0.069 | 0.610 | 18.0 |
| -60 dB | 0.043 | 0.571 | 15.8 |
| -70 dB | 0.023 | **3.766** | **5.0** |

Flat from -30 to -60, then it **collapses at -70**: only 5 speech regions
survive and p90 drift explodes to 3.8 s, because at -70 dB the detector sees
only the spliced digital silence and swallows every natural pause. The
apparent improvement in median at -55/-60 is selection bias — fewer regions
means each declared boundary matches whatever is nearest, not what is correct.

`SILENCE_MIN_DUR = 0.10` is deliberately shorter than any threshold applied to
it (trap c). `silencedetect` with `d=0.25` cannot distinguish "exactly 250 ms"
from "not detected", so durations are compared in Python instead.

---

## 5. Trap (a): the countdown

The quiz countdown is ~7 s of `anullsrc` carrying **three declared segments**
(`countdown_3`, `countdown_2`, `countdown_1`). Any "detected regions ==
declared segments" count can never reconcile against it.

The gate checks those against the **declared silence map** instead: the span
must contain no speech. Measured on `quiz/cool_20260416_084217`, all three read
`max_volume = -91.0 dB` with `speech_overlap = 0.000 s`.

## 6. Trap (d): OpenAI excluded

The 5 OpenAI artifacts (`quiz_openai/`, `test_openai_*`) are excluded from
calibration. `tts_openai.py:890-895` concatenates with `-c:a copy` across
unnormalised sample rates, so they carry drift that is not the gate's to
measure.
