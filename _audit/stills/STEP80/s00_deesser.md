# STEP 80 §00 — the de-esser

`src/deesser.py`, the chain Claude measured: `acrossover=split=5500:order=4th`, the high band through
`acompressor` (ratio 4, attack 1, release 60, knee 3), mixed back with `normalize=0`; threshold =
the narration's integrated LUFS − 12 dB. `config.yaml` → `audio.deesser: {enabled: true,
split_hz: 5500, below_lufs_db: 12, ratio: 4}`.

One function, `deesser.deess(src, dst)`, on the voice alone, before any SFX and before the final
loudnorm:
- **Shorts and series**: inside `loudness.prepare_narration` (both paths already call it), before
  the segment levelling and the two-pass loudnorm.
- **Lessons**: `voices.PrerecordedService` de-esses each beat on its way into the scene's cache (a
  wav, so no encoder padding moves a word time); the scene writes each beat's measure and their
  combination into its timeline. Stills mode skips it (no sound).
- **Cached audio too**: every re-render gets it for $0. The outro's voice is not in the STEP's list,
  and a redraw reuses the clip's own voice, so de-essing it there would stack on every redraw: left
  as it is.

**The measure** (`deesser.measure`, the gate's band math), taken on the voice before the mix:
- frames of 2048 samples; HF = 5–10 kHz, body = 100 Hz–4 kHz; voiced = within 50 dB of the
  loudest frame; sibilant = voiced with HF within 6 dB of its body or above.
- **sibilants**: energy-weighted, so it says how much the loud «s» comes down;
  **other frames**: the mean of each frame's reduction, so it says whether an ordinary frame is
  dulled. Summed instead, the few loud transitions into an «s» dominate the «other» number
  (1.06–1.2 dB on the series narrations, against Claude's 0.4).
- gate: sibilants 5–12 dB, other ≤ 1.0 dB, body ≤ 0.3 dB. In the Shorts gate
  (`pipeline.finalize_video`), the series gate and `renders.lesson_gate`; the numbers are in each
  sidecar (`deesser`) and in the lessons' timeline.

| narration | sibilants | other | body |
|---|---|---|---|
| hc_m001 (Claude's test file) | −7.00 dB | −0.49 dB | 0.00 dB |
| hc_e011 | −7.62 | −0.41 | 0.00 |
| hc_c001 | −8.10 | −0.27 | 0.00 |
| demo-motion lesson (9 beats) | −8.20 | −0.62 | 0.00 |

**The six approved series videos** were in `output/approved/hecho_con_claude/`, not `pending/`
(Garcia had approved them; none was published). Re-rendered there from cache, same file names,
same gate, voice locked, TTS $0 — all PASS:

| video | sibilants | other | body | LUFS |
|---|---|---|---|---|
| hc_c019 | −7.84 | −0.26 | 0.00 | −14.1 |
| hc_e001 | −7.93 | −0.41 | 0.00 | −14.1 |
| hc_m001 | −7.00 | −0.49 | 0.00 | −14.1 |
| hc_m010 | −7.02 | −0.40 | 0.00 | −14.2 |
| hc_p011 | −7.90 | −0.32 | 0.00 | −14.0 |
| hc_p019 | −8.30 | −0.30 | 0.00 | −14.4 |

Their sidecars keep the title, description and hashtags and now carry `deesser` and the new
`gate_checks`. They were rendered with today's code, so hc_e001 and hc_p019 also have the STEP 79
changes.

For Garcia's ear: `_audit/incoming/deesser_antes_y_despues.mp3` (hc_m001's voice: original, 1 s of
silence, de-essed; 73 s).
