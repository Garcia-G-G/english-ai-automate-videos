# STEP 75 §5 — loudness for Shorts

Same re-render as §4 (`rerender_short.py`, cached audio, $0), now with `src/loudness.py`
before the mux and the outros redrawn at −14 LUFS.

| | §0 baseline | §5 |
|---|---|---|
| integrated loudness | −15.5 LUFS | −14.1 LUFS |
| true peak | −0.4 dBTP | −1.9 dBTP |
| LRA | 4.7 LU | 5.7 LU |
| duration | 82.76 s | 82.76 s (narration sample count identical, asserted) |
| spread between the 23 spoken segments | 2.75 dB | 2.20 dB |
| loudnorm mode | — | linear |

The spread is gated RMS per segment (20 ms frames above −50 dBFS, «[silence]» segments
skipped) over the segment spans of the audio JSON. The audit's 4.5–5.7 LU was measured
differently (ungated short-term loudness of single words against sentences), so the two
numbers are not comparable with each other; the before/after above use the same method.

Outros after the redraw: aprende-ingles −13.7 LUFS / −2.0 dBTP, sigue-aprendiendo
−14.0 / −2.0, mas-lecciones −13.9 / −2.2 (before: −16.0, −16.1, −16.6). Stream parameters
unchanged, so the concat stays `-c copy`.

Render time: frames+encode 975.6 s at load average 30–47 (other projects running); not a
measurement, §6 times on a quiet machine.
