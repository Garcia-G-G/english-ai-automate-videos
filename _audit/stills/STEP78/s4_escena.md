# STEP 78 §4 — escena

Proof: `_audit/stills/STEP78/s4/hc_e011.mp4` (gitignored; medio · B1–B2), `hc_e011_sheet.png`,
`hc_e011_frame0.png`, `hc_e011_proof.json`.

| proof | level | duration | TTS $ | CPU s | LUFS | TP | colour |
|---|---|---|---|---|---|---|---|
| hc_e011 | medio | 35.1 s | 0.1008 | 289.3 (load 7 → 17) | −14.1 | −2.2 | BT.709 |

- The reference's layout: letterbox bars, a film frame with grain (four tiles cycled 12 times a
  second) and a vignette, the slate line (`hook_text`, frame 0) and a red timecode in the top bar,
  the level pill under it, a clapperboard (scene number, take, EN → ES). Inter, vendored with its
  OFL licence (`assets/fonts/OFL-Inter.txt`, added: the font was there without it).
- The clapper opens, then snaps shut with a clap (a new procedural sound) on «Toma uno», found
  among the beat's words; take 1 comes up as a yellow outlined subtitle on its English phrase.
- On «¡Corten!» a red marker strikes take 1 and «¡CORTEN!» punches in; «TOMA 2» on «Toma dos»;
  take 2 types in while the voice says it; the note under it; the challenge on the last beat.
- Below y 950 every line is at most 780 px wide, centred (x 150–930): off the button rail.
- A beat's word lookup is now exact for Spanish («Toma uno» is not «Toma dos»); English phrases
  keep their first-word fallback.
- Tests: the 27 escena scripts, as for mensajes.
