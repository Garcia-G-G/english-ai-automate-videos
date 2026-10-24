# STEP 78 §6 — comic

Proof: `_audit/stills/STEP78/s6/hc_c001.mp4` (gitignored; principiante · A1–A2), `hc_c001_sheet.png`,
`hc_c001_frame0.png`, `hc_c001_proof.json`.

| proof | level | duration | TTS $ | CPU s | LUFS | TP | colour |
|---|---|---|---|---|---|---|---|
| hc_c001 | principiante | 35.4 s | 0 (voiced in §2, ≈ $0.07) | 137.9 (load 4 → 16) | −14.1 | −2.4 | BT.709 |

- The references' look (fotograma_1..3): yellow ground with speed lines and a halftone, a progress
  bar, the level chip and «English Unlimited», white speech cards with an ink outline and hard
  shadow (the hook at frame 0, then `quiz.prompt`), option cards A/B/C popping in as the voice says
  each, the countdown ring 3-2-1 in the timeline's 3 s of room tone, «¡NO!» stamped on the wrong
  options and a green ring round the right one (a clap), `quiz.after` as a sticky, the challenge.
- Bubi reacts with the brand guide's expressions: surprised («wow», with a shake) until the
  reveal, then happy («¡lo lograste!», with a hop). The guide drew them but the repo had them only
  inside guia_de_marca.png; `tools/extract_bubi_expressions.py` cuts them out on transparent
  ground into `assets/branding/english-unlimited/expresiones/` (wow, lo_lograste, bien_hecho).
- Tests: the 27 comic scripts as for the other styles; the countdown sits in the timeline's 3 s;
  the stamps go on the wrong options only and the ring on the right one; Bubi's expressions.
