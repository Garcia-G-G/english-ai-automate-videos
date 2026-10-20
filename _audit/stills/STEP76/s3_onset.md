# STEP 76 §3 — the onset gate calibrated by ear

`tools/onset_calibrate.py --on-disk DIR` (free, no TTS): the level of each stored clip's first
10 ms (dBFS), as a histogram, and a proposed threshold — the middle of the gap between the
highest clip under the band the owner hears as cut in (−20…−16 dBFS) and that band.

Over the 30 stored eleven_v3 English takes (`_audit/onset_eleven_v3/lv001`), full histogram in
`s3_histogram.txt`: the values run from −86 to −6 dBFS with no wide gap; the one under the band
sits between −21.7 and −19.0 dBFS, so the threshold is **−20.9 dBFS**
(`stitch.ONSET_FIRST_DBFS["eleven_v3"]`).

| rule on eleven_v3 | takes flagged of 30 |
|---|---|
| before: start-to-peak ≥ −6.5 dB | 3 (−4.1, −1.2, −0.4: hard cut-ins only) |
| now: first 10 ms ≥ −20.9 dBFS | 10 (every take from −19.0 dBFS up; −19…−16 had passed before) |

Fragment and doubled-onset checks are unchanged. Other models keep their start-to-peak limit
(−30 dB). The gate now also covers the Spanish clips of the level path (it gated English only).

Spanish clips on disk (assets/audio/standard, assets/audio/spanish, the level tier cache: 80)
cannot calibrate anything: 76 start in digital silence (pre-recorded with padding).

Cost in production: more retakes on v3 — on this sample a third of English takes would be
re-asked once (up to two retakes each), and Spanish clips are now gated as well. The
calibration rests on one script's takes; re-run it when the owner flags a word elsewhere.
No TTS in this section.
