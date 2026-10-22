# STEP 78b §1 — series polish

1. **mensajes**: every `[[English]]` phrase said after «Se dice» (other than the right form) gets its
   own card, entering on its word time: a green tick, or a red cross when it is the wrong form said
   again (hc_m001 «I have 25 years»). When the first one comes, «Se dice» and the rule move up over the
   dimmed chat, and the stack takes the lower half (7 slots in hc_m001, ≥ 3 in all 27, all above the
   bottom 22 %); past its slots the oldest fades and the rest move up. The input's cursor blinks.
2. **escena**: frame 0 shows take 1 as the yellow subtitle, the «¿Ves el error?» pill under it, and
   the clapper. Take 1 pops when the voice reads it; the pill goes at the strike.
3. **poster**: `poster.display_lines` breaks the display type: fewest lines, then breaks right after
   / → = ≠ —, then even lengths; never a separator at the start of a line, never a lone word of
   ≤ 3 letters. «DESPITE / IN SPITE OF» → «DESPITE /» «IN SPITE OF». Tested on big_wrong and big_right
   of all 27; the 54 blocks are in `s1_poster_blocks.png`. Paper grain (4 tiles, 8/s).
4. **comic**: frame 0 shows the hook card, the question and the three options, static; each pops
   from that state when the voice reaches it. Bubi breathes. The «¡NO!» stamp moved beside its
   option: with the narrower options it covered their last words.
5. **gate, stillness**: the longest run of frames with a mean absolute difference < 0.003 grey levels
   (x264 repeats a static frame at exactly 0; grain, a cursor or a breath are far above) must be
   ≤ 4.0 s. The STEP 78 proofs measured: hc_m001 4.0 s, hc_p019 6.0 s, hc_e011 1.37 s, hc_c001 1.97 s.

Also in the gate: the base whisper's temperature fallback gave different transcripts of the same
hc_c019 narration on two runs (one dropped the three options). A phrase now counts as heard in the
auto-language transcript or in a second one forced to English, and a word one letter off in a word of
≥ 3 letters matches («Ana» / «Anna»); «I am cold» still is not heard in «I have cold».

Levels: hc_m010, hc_e001 and hc_p002 are all principiante and hc_c019 is difícil, so medio was missing;
hc_p002 → hc_p011, the next medio poster.

| proof | style · level | duration | TTS | CPU s | LUFS | longest still | gate |
|---|---|---|---|---|---|---|---|
| hc_m001 | mensajes · principiante | 40.2 s | $0.0000 | 108.8 | -14.0 | 1.37 s @ 38.5 s | PASS |
| hc_p019 | poster · dificil | 34.0 s | $0.0000 | 233.3 | -14.3 | 1.37 s @ 32.33 s | PASS |
| hc_m010 | mensajes · principiante | 36.7 s | $0.0834 | 73.5 | -14.2 | 1.37 s @ 35.0 s | PASS |
| hc_e001 | escena · principiante | 37.0 s | $0.1065 | 283.5 | -14.1 | 1.37 s @ 35.33 s | PASS |
| hc_p011 | poster · medio | 34.1 s | $0.0768 | 182.1 | -14.0 | 1.37 s @ 32.37 s | PASS |
| hc_c019 | comic · dificil | 32.9 s | $0.0933 | 113.4 | -14.0 | 1.33 s @ 31.2 s | PASS |

TTS for §1: $0.36. Every longest still is the outro's last second and a half. CPU times were taken
with other work on the machine (load 5–24). Each render: `<id>.mp4`, `<id>_sheet.png` (5 frames),
`<id>_frame0.png`, `<id>_proof.json`, `<id>.json` (the sidecar with its timeline).
