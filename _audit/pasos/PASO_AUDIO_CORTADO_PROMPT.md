# Step: the audio sounds chopped

## 0. The ONE-LINE version of what the owner asked for

> "estoy empezando a escuchar más los audios de los videos no sé porque se escucha
> como cortado antinatural"

**Make the audio stop sounding like spliced tape.** Nothing else. This step does not
touch scripts, duration, content, or the renderer.

---

## 1. What was measured, and with what

All local, no API, no cost. Scripts committed at `tools/audio_seams/`:

| script | what it does |
|---|---|
| `seams.py <mp3> <json>` | RMS in the 60 ms before each segment's `end` and the 100 ms after |
| `onset.py <mp3>` | 10 ms-step profile of onsets and offsets |
| `tail.py <mp3> label@t ...` | the 200 ms around a given instant |
| `corpus.py` | sweep of all 181 videos that have a sidecar |

Method: decode to PCM s16le mono 16 kHz, compute RMS in numpy.

**Do not use per-slice `astats`.** My first attempt did, and its regex returned
`None` on all 13 rows, which printed "0 of 13 hard cuts" — a false zero. That zero
was not a result. If you extend these scripts, assert that every row has a real dB
value before believing any count.

---

## 2. Defect A — CORRECTNESS, blocks

**Bilingual clips end dead: they are cut at the instant the voice stops.**

Measured over the 19 vocabulary files in the corpus, using timeline arithmetic
(`declared_gap − PAUSE`, with `repetition_pause() = 0.9` and 0.5 between pairs):

```
clips "spanish... english."  (pair)    n=139   tail = 0.000 s in 138  (99.3%)   median 0.000 s
clips "english." alone       (repeat)  n=127   tail = 0.000 s in  52  (40.9%)   median 0.244 s   max 1.766 s
```

Same voice, same model, same call, same settings. Only the text differs. The
bilingual clip **never** carries trailing silence; the single-phrase clip carries a
median of 0.244 s.

10 ms profile of the end of `pair_0` ("la carta... the menu."), dB, relative to the
sidecar's `end`:

```
        -100  -90  -80  -70  -60  -50  -40  -30  -20  -10   +0  +10  +20
pair_0   -23  -22  -23  -24  -23  -25  -24  -23  -21  -20  -76  -79 -120
pair_3   -47  -48  -49  -50  -49  -48  -51  -45  -53  -66  -92 -120 -120   <- healthy ending
```

`pair_0` is at **−20 dB — full speaking level — 10 ms before it disappears**. There is
no decay. That is a guillotine, not an ending. `pair_3` does decay.

Corpus sweep (segments whose 60 ms tail is above −30 dB and drop ≥6 dB immediately
after), 181 videos, 1,860 segments:

```
true_false    44/98   (44.9%)
vocabulary   106/340  (31.2%)
fill_blank    41/189  (21.7%)
quiz          69/590  (11.7%)
educational   58/546  (10.6%)
pronunciation  6/97   ( 6.2%)
```

### What I could NOT determine

**Where the cut happens.** I ruled out what can be ruled out by reading the code:

- `_elevenlabs_with_retry` writes the whole stream; it does not truncate.
- vocabulary does **not** call `trim_clip_silence`; clips are concatenated whole.
- the concat re-encodes with `libmp3lame`; it does not copy frames.
- there is no `silenceremove`, `atrim` or `loudnorm` anywhere in `src/`.
- `add_natural_pauses` and `enhance_bilingual_text` append nothing at the end.

One hypothesis is left alive: **ElevenLabs returns the clip already cut.** I could not
test it. Regenerating `"la carta... the menu."` from this environment fails with
`httpx.ProxyError: 403 Forbidden` against `api.elevenlabs.io` — the VM's proxy blocks
that host.

**The missing test, which you can run** (~60 characters of API, negligible cost):

```python
# src/ on the path, .env loaded
from tts_elevenlabs import generate_segment_audio
from tts_common import get_audio_duration, measure_speech_end
for txt in ["la carta... the menu.", "the menu.", "la carta the menu."]:
    p = f"/tmp/probe_{abs(hash(txt))}.mp3"
    generate_segment_audio(text=txt, output_path=p, segment_type='options')
    print(repr(txt), get_audio_duration(p), measure_speech_end(p))
```

Three outcomes, three different fixes:

- **Raw API clip already has tail 0.000** → it is ElevenLabs. The fix lives in what we
  send (terminal punctuation, a guard character, or a trailing space) or in padding
  the clip after the call. Report which of the three texts reproduce it — that tells
  us whether it is the `...` or the code-switch.
- **Raw clip has a tail, concatenated file does not** → the cut is in our pipeline and
  I was wrong to rule it out. Say so and I will redo the analysis.
- **Neither reproduces** → the defect is intermittent and the probe needs N=10 per
  text before anything is concluded.

**Do not build the fix before you know which one it is.**

---

## 3. Defect B — QUALITY, warns

**Every join is voice → absolute digital zero → voice.**

`generate_silence` uses `anullsrc`, which emits exact zeros. Verified at sample level:
the quiz countdown is **72,000 consecutive samples exactly equal to zero**.

A real recording never drops below its own noise floor. Measured, the ElevenLabs floor
sits at −90 dB; our gaps sit at −120 dB. The ear does not hear the silence — it hears
**the noise floor vanish** and come back, 8 to 25 times per video. That is precisely
the timbre of spliced tape.

How much of the audio is exact zero:

```
educational / pronunciation      2.3 – 5.1 %
quiz / fill_blank / true_false  29.3 – 38.5 %
vocabulary                      30.3 %
```

That table is the answer to why some types sound fine and others do not.

**It is not the TTS model.** I checked the model × type cross-tab and it is
**confounded**: `turbo_v2_5` is used only for educational and pronunciation, `v3` only
for the other four. No video type uses both models, so the 4% vs 29% that appears when
grouping by model **proves nothing about the model**. I am writing this down because I
nearly reported it as a finding.

### Constraint any fix must respect

**The fix must not move the timeline.** `segment_times` drives the renderer; an
`acrossfade` shortens the total and desynchronises every text reveal. Only
duration-neutral fixes qualify:

- fill the gaps with noise at the clip's own floor level instead of `anullsrc` (same
  duration, same `running_time`), or
- a 10–15 ms fade **inside** the clip's existing boundaries, on entry and on exit.

Whichever you pick, re-run `tools/audio_seams/corpus.py` on a before/after pair and
show the two tables. "It sounds better now" is not a status report.

---

## 4. Defect C — QUALITY, warns

**Trimmed clips slam in.**

`TRIM_LEAD_PAD = 0.02` leaves 20 ms of lead-in. 10 ms profile from segment start, dB:

```
                  0   10   20   30   40   50   60
option_a       -112  -51  -14  -11  -11  -11  -10     <- trimmed
transition     -120  -63  -35  -16  -14  -10   -9     <- trimmed
question        -71  -84  -82  -72  -60  -31  -17     <- not trimmed
answer          -86  -81  -72  -74  -72  -78  -81     <- not trimmed
```

`option_a` goes from digital silence to full level in **30 ms**. No human speech onset
does that. The untrimmed segments rise over 60–90 ms and sound normal.

`add_audio` measures **after** `_trim`, so raising `TRIM_LEAD_PAD` is timeline-safe:
the duration is recomputed from the already-trimmed clip.

---

## 5. Order of work

1. Run the probe in §2 and report which of the three outcomes it is. **That only.**
2. With the answer in hand, fix Defect A.
3. Defects B and C after that, and only if A did not already change them.

Do not touch scripts, duration, new video types, or the renderer in this step.

## 6. What I am NOT proposing, and why

- **Not proposing a TTS model change.** The cross-tab is confounded, I have no
  evidence, and switching models changes the channel's entire voice.
- **Not proposing removing the silent countdown.** Those 4.5 s are by design; that is
  the owner's product decision, not a defect.
- **Not proposing crossfades.** They break `segment_times`.
