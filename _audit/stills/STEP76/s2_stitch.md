# STEP 76 §2 — one stitch rule

`src/stitch.py` holds the lessons' rule, shared instead of copied: the context rule (next_text
only at a language switch), the onset detector (was `probes/onset.py`, which re-exports it)
and the gate with retakes (was in `tts_elevenlabs`, which re-exports its names), the
punctuation gaps. `gen_audio` (lessons), `tts_elevenlabs` (levels) and `tts_bilingual`
(educational, pronunciation) use it. `tts_bilingual` now also trims each clip
(`trim_clip_silence`), levels the clips to their median (`loudness.level_clips`, ±6 dB, with
12/20 ms edge fades and a −1 dBFS ceiling) and joins WAVs, encoding once.

No other path sends previous/next text; the quiz/true_false/level generators request each clip
on its own and STEP 75 §5 levels every narration at the mux.

Proof: `give_up_20260113_185732` (no educational script with «m-make»/«d-do» is on record, so
the shortest one, 304 planned characters), re-synthesised on eleven_turbo_v2_5
(`s2_resynth.py`, output in `output/rendering/step76_s2/`).

| seam | languages | configured pause | silence between speech | clip edges out / in | largest step |
|---|---|---|---|---|---|
| 0 | es→en | 0.05 s | 0.062 s | −66.8 / −87.5 dBFS | −84.7 dBFS |
| 1 | en→es | 0.05 | 0.060 | −44.4 / −83.0 | −41.2 |
| 2 | es→en | 0.14 | 0.245 | −83.6 / −97.5 | −77.7 |
| 3 | en→es | 0.05 | 0.145 | −87.4 / −83.9 | −95.1 |
| 4 | es→en | 0.05 | 0.157 | −83.8 / −100.6 | −80.3 |
| 5 | en→es | 0.14 | 0.325 | −92.4 / −91.6 | −89.9 |
| 6 | es→en | 0.05 | 0.238 | −92.6 / −100.8 | −93.8 |
| 7 | en→es | 0.14 | 0.264 | −91.2 / −84.4 | −92.0 |

Silence between speech = configured pause + the trim pads (up to 80 ms each side) − the fades.
No call sends previous_text (all are language switches). Onset gate: 8 of 9 clips clean; «Don't
give up on your dreams,» had no clean take in 3 and the cleanest was kept; «give up» needed 2.
Gains −3.1 … +2.4 dB.

The first run, before the edge fades, had two clips ending at −14 and −17 dBFS (a click at the
join); the fades are why it is now ≤ −44.

Cost: three runs of ~370 characters (304 planned + retakes): $0.0414 and $0.0406 measured, the
middle one ≈ $0.041 (its report was overwritten). §2 total ≈ $0.123.
(Corrected in §5: these calls were logged; the tracker keeps rows in memory until the job
saves it, and this proof script never saved. The real pipeline does.)
