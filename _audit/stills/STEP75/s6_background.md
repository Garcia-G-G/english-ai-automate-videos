# STEP 75 §6 — background band and speed (opaque-page types)

how_do_you_say and the level modes (`video_types.OPAQUE_PAGE_TYPES`) draw every word on an
opaque page, so the contrast band only darkened footage the page hides (strength 0.52 on
this Short). Now: no band, no per-clip band sampling; each clip is softened once
(quarter-res Gaussian blur, slight warm grade toward the sand paper, gentle vignette).

The watermark sits over footage below the page. Dropping the sampling outright took it
under 3:1 in 11 of 42 samples (worst 1.82:1), so its local scrim is still solved, over the
softened quarter-res clips: worst 3.07:1, 0 of 42 under 3:1 (old 3.16:1, 0 of 42).

`text_contrast.HEADLINE_COLOR` now imports `config.colors.ENGLISH_WORD_COLOR` instead of
holding a copy.

Full render, same narration, clips and encoder, in-process, back to back (`s6_ab.py`),
load average 7–14:

| | band (old) | softened (new) |
|---|---|---|
| render | 312.5 s | 281.7 s (−30.8 s) |
| background alone, 2481 frames + init | 87.3 s | 31.7 s |
| band / mark scrim | 0.520 / 0.210 | 0 / 0.230 |

Stills (old left, new right): `s6_pair_t4.png`, `s6_pair_t30.png`, `s6_pair_t70.png`.
