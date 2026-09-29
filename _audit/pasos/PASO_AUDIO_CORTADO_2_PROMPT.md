# Step 2: stop the code-switch truncation

## 0. The ONE-LINE version of what the owner asked for

> "estoy empezando a escuchar más los audios de los videos no sé porque se escucha
> como cortado antinatural"

Unchanged from Step 1. **Make the audio stop sounding like spliced tape.** Step 1
found out why. This step fixes it.

---

## 1. What Step 1 settled, and what it did not

**Settled.** The probe came back Outcome 1. Any clip containing a language
transition ends at the instant the voice stops; monolingual clips carry a 0.3–1.3 s
tail. Direction does not matter (EN→ES cuts like ES→EN), the ellipsis is not
required (`la carta the menu.` reproduces 2/3 with no `...`), and Spanish alone is
not the trigger (`la carta.` has a healthy ~1.2 s tail). The cut is in the bytes
ElevenLabs returns, before any concat, trim or re-encode. That closes the question
§2 of the previous brief left open, and it retires my "maybe it's our pipeline"
branch. Good work, and the two extra controls were the right call — my three texts
could not have separated "bilingual" from "Spanish present".

**Not settled, and it decides the fix.** `tail = 0.000` means *the file ends within
100 ms of the voice*. It does not by itself mean *a phoneme was lost*. Those are
different defects with different fixes:

- If nothing is lost, the clip merely ends on a waveform discontinuity — a click.
  Fade plus pad fixes it completely.
- If audio content is missing, fade plus pad makes the click go away while the word
  stays truncated, and we will have shipped a fix that hides its own failure.

§2 measures which. §3 applies the fix. Do both in this step.

---

## 2. First: is audio content actually lost?

Free, local, no API — reuse the clips the probe already wrote. If they are gone,
regenerate: 6 takes each of `"the menu."` and `"la carta... the menu."`, ~180
characters total.

Measure the acoustic span of the **English portion** in each condition:

- monolingual: `measure_speech_end(p) - measure_speech_start(p)`
- bilingual: run `silencedetect` to find the internal pause, then take the duration
  of the last speech region

Then corroborate with local Whisper (free, no API) on both sets and compare the
final word as transcribed.

**Read it like this:**

| result | meaning | what to do |
|---|---|---|
| English span within ~50 ms across conditions, Whisper agrees | envelope cut only, no content lost | §3 as written, and say so |
| bilingual span systematically shorter by >80 ms, or Whisper drops/clips the word | content is lost | **stop and report.** Do not apply §3 as the fix. Fade+pad would mask it |
| noisy, no clear pattern at n=6 | underpowered | raise to n=12 before concluding |

Report the two distributions, not a verdict on its own.

---

## 3. The fix: fade, then pad, at the clip level

Only if §2 says no content is lost.

**Why padding and not splitting the call at the language boundary.** Splitting is
the pattern `emit_split_options` already uses, and for vocabulary pairs it would
work, because `spanish` and `english` are separate fields. It does not generalise.
Real segments in the corpus:

```
[statement  ] 'Steal someone's thunder' significa tomar el crédito de otro?
[explanation] 'Their' significa 'su' (de ellos) y se usa para mostrar posesión...
[explanation] Your es posesivo. You're es you are. El apóstrofo no es decorativo.
```

The English is embedded at the start and in the middle of Spanish sentences. There
is no clean boundary to split on, and splitting these would destroy the prosody of
the sentence. Since EN→ES truncates too, every one of these clips is affected.
Padding after the call is the only fix that covers all of them, so that is the one
to build.

**Shape of it.** A helper in `tts_common.py`, applied to every clip right after
`generate_segment_audio` returns and **before** `add_audio` measures it:

```
if get_audio_duration(p) - measure_speech_end(p) < TAIL_MIN:      # TAIL_MIN ≈ 0.05
    afade=t=out:st=<dur - FADE>:d=<FADE>                          # FADE ≈ 0.020
    apad=pad_dur=<TAIL_PAD>                                       # TAIL_PAD ≈ 0.25
```

Three things about that, in order of how easy they are to get wrong:

1. **The fade is not optional.** Padding alone does not fix the click. The click is
   the waveform going from full amplitude to zero in one sample; appending zeros
   after it leaves that discontinuity exactly where it was. The fade is what removes
   it. The pad is what restores the pacing.
2. **Apply it before `add_audio`.** `add_audio` computes `running_time` from the
   clip's duration, so a clip padded first is accounted for correctly and the
   timeline stays consistent. Pad after and every segment start drifts.
3. **It lengthens videos.** Vocabulary has ~24 bilingual clips; at `TAIL_PAD = 0.25`
   that is +6 s. That is acceptable against the 50 s floor and the owner's "no
   ceiling, just not ten-minute videos", but it means `tools/duration_calibrate.py`
   has to be re-run afterwards or every prediction it makes is stale.

Pick the three constants from measurement, not from this brief — the numbers above
are starting points. `TAIL_PAD` should land near the 0.244 s median that healthy
monolingual clips actually show, not at a round number chosen for looking tidy.

---

## 4. Proof required before this is called done

1. `tools/audio_seams/corpus.py` before and after, both tables shown. The
   hard-cut counts must drop — state by how much, per type.
2. `tools/audio_seams/onset.py` on one regenerated vocabulary file, showing the
   10 ms tail profile now decays instead of dropping −20 → −120 in two frames.
3. One regenerated vocabulary video and one true_false video, produced end to end.
4. The §2 distributions.

"It sounds better now" is not a status report.

---

## 5. Out of scope for this step, on purpose

- **Defect B (`anullsrc` zeros in the gaps) is still live.** Step 1 found that
  29–38 % of quiz/fill_blank/true_false/vocabulary audio is exact digital zero
  against a −90 dB voice floor. The code-switch finding does not retire it. It is
  the next step, not this one, and the duration-neutrality constraint from the
  previous brief still applies: no crossfades, `segment_times` drives the renderer.
- **Defect C (`TRIM_LEAD_PAD = 0.02`, options entering at −11 dB in 30 ms)** — after
  B.
- **No TTS model change.** The model × type cross-tab is confounded; every type uses
  exactly one model. Still no evidence.

---

## 6. Recorded, not actioned: the shadowed API keys

Reported during Step 1, worth keeping, **not part of this step.**

`~/.bash_profile:11–12` exports `OPENAI_API_KEY` and `ELEVENLABS_API_KEY` from a
`security find-generic-password` substitution that is not being evaluated — the
exported value is the literal command text, 87 characters starting `securi`. It
shadows the working key.

Severity: **latent, warns.** Audio works today only because
`src/tts_elevenlabs.py:40` calls `load_dotenv(override=True)`. Any module that uses
plain `load_dotenv()` or reads `os.environ` directly gets the broken value and 401s
— which is exactly the failure `env_setup.py`'s docstring exists to warn about. It
is a machine-config defect, not a repo defect, so it belongs to the owner's shell,
not to a commit here.

The OpenAI key in `.env` is separately dead: it is the same revoked `sk-proj-…lT8A`
that 401'd earlier. That one needs a new key, not a config fix.
