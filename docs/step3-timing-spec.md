# Step 3 timing — specification, from measurement

Written 2026-07-30 from the QA-gate baseline (`src/qa_gate.py`, 195 rendered
artifacts). This file is the *specification* for Step 3: it says what is
wrong, with numbers, and what "fixed" will look like when the same gate is
re-run.

**Nothing here has been fixed.** The gate is report-only. Fixing the timing now
would destroy the before/after that makes Step 3 provable.

---

## 1. THE SIGN CONFLICT — read this before touching anything

The measured defect is the **opposite sign** from the originally reported
symptom, and both are almost certainly real.

| | direction | evidence |
|---|---|---|
| **Reported symptom** | animations run *faster* than the voice — text advances early | user report |
| **Measured at segment level** | declared ends *overrun* actual speech by up to **1.29 s** — text lingers after the voice stops | drift table, below |

These are not in contradiction; they are two different mechanisms at two
different granularities, and Step 3 has to address **both**:

**Mechanism A — segment level (what the drift table measured).**
Trailing silence inside each ElevenLabs segment is counted as part of that
segment's duration. Declared segment *starts* are accurate to ~0.02 s while
declared *ends* overrun by 0.4–1.3 s, monotonically. The renderer therefore
holds each segment on screen past the end of its audio.

**Mechanism B — word level (finding 2 of the calibration).**
Word timings inside a segment are char-proportional estimates that were never
aligned to the waveform. They span the audio correctly
(`last_word_end / measured_duration` median 0.98) but distribute wrongly
inside it, so individual words drift both ways around the true position. A
word-level karaoke driven from these will run ahead in some places and behind
in others regardless of mechanism A.

Fixing A alone will make the lingering stop and leave the per-word jitter.
Fixing B needs forced alignment, i.e. ASR, which is deferred — so Step 3
should expect to fix A and *bound* B, not eliminate it.

---

## 2. Quiz option boundaries — invented arithmetic

`tts_elevenlabs.py:589-591` sets `transition_duration = 1.5` and
`per_option = options_duration / 4`. Neither is measured. The drift table
isolates the consequence exactly — on `quiz/cool_20260416_084217`, every
non-option boundary lands within 0.12 s and only the options drift:

```
segment        decl_start meas_start  d_start  decl_end  meas_end   d_end
  question           0.00       0.00    0.000      2.48      2.48   0.000
  transition         2.98       2.98    0.000      4.48      4.50   0.015
  option_a           4.48       4.99    0.507      6.72      6.93   0.203
  option_b           6.72       6.03   -0.696      8.97      9.05   0.079
  option_c           8.97       8.41   -0.562     11.21     11.34   0.121
  option_d          11.21      10.72   -0.498     13.46     13.46   0.000
  think             14.06      14.06    0.000     15.18     14.95  -0.234
  answer            22.18      22.27    0.090     26.18     26.16  -0.022
  explanation       26.58      26.70    0.117     36.42     36.41  -0.007
```

The option starts drift **+0.51, −0.70, −0.56, −0.50 s**. The sign flip
between `option_a` and the rest is the signature of a fixed `transition_duration`
that is too short, followed by an even division that then runs ahead.

**Target:** option-start drift within the same band as the other segments
(|delta| <= 0.12 s).

---

## 3. Educational segment ends — systematic overrun

`educational/work_out_20260116_193230`, and the pattern holds across the type:

```
segment          decl_start meas_start  d_start  decl_end  meas_end   d_end
  hook                 0.00       0.00    0.000      2.57      2.00  -0.566
  meaning              2.97       3.01    0.044      7.14      6.76  -0.384
  example1             7.54       7.59    0.045     13.28     12.25  -1.029
  example2            13.68      13.70    0.024     19.90     19.03  -0.864
  example3            20.30      20.31    0.017     24.71     24.05  -0.666
  tip                 25.11      25.12    0.006     32.62     31.34  -1.289
  cta                 33.02      33.01   -0.017     37.10     36.62  -0.487
```

Starts are essentially perfect. **Every end is negative** — measured speech
ends before the declared end, by 0.38 to 1.29 s. This is mechanism A.

**Target:** end drift symmetric around zero rather than systematically
negative.

---

## 4. Letter-to-word elision — the known-bad case, measured from audio

`tts_elevenlabs.py:562` builds `f"Opción {letter}, {word}."` and `:565` joins
all four options plus the transition into ONE utterance in a single TTS call,
so letter and word are separated only by a comma inside one breath.

Required: **>= 250 ms**. Measured:

```
quiz/fabric_20260116_201133   4 speech chunks for 4 options
   option_a  gap 0.000s   single chunk — letter fully elided
   option_b  gap 0.000s   single chunk — letter fully elided
   option_c  gap 0.000s   single chunk — letter fully elided
   option_d  gap 0.000s   single chunk — letter fully elided
   -> 4/4 FAIL, 4 fully elided

quiz/cool_20260416_084217     7 speech chunks for 4 options
   option_a  gap 0.171s
   option_b  gap 0.164s
   option_c  gap 0.216s
   option_d  gap 0.000s   single chunk — letter fully elided
   -> 4/4 FAIL, 1 fully elided
```

Across the corpus: **38 of 42** artifacts with per-option spans fail.

**Target:** every option gap >= 0.250 s. The likely fix is to stop joining the
options into one utterance, or to insert explicit silence between letter and
word — a TTS-construction change, not an arithmetic one.

---

## 5. Countdown silence is not silent

39% of artifacts carrying a countdown (26 of 67) have speech bleeding into the
span declared as digital silence — up to 0.54 s at up to **-0.9 dB**, which is
full speech level, inside a region the pipeline believes is `anullsrc`.

This was found by asserting against the declared silence map (trap a) rather
than counting regions. Cause not yet diagnosed; most likely the declared
countdown boundaries are computed from the same unmeasured arithmetic as the
options.

---

## 6. What "fixed" looks like

Re-run `python3 src/qa_gate.py` and compare against
`tests/baselines/qa_baseline_2026-07-30.json`:

| metric | baseline | target |
|---|---|---|
| quiz drift median / p90 | 0.173 / 0.505 | <= 0.120 / <= 0.200 |
| educational drift median / p90 | 0.330 / 0.690 | <= 0.120 / <= 0.250 |
| letter-to-word failing | 38 / 42 | 0 |
| declared-silence violations | 78 | 0 |
| span verdict ok | 86 / 93 | 93 / 93 |

The gate stays report-only until those move. `BLOCKING` in `src/qa_gate.py`
is the single flag that turns it into a gate.
