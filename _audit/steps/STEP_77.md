# STEP 77 — Notebook kit and Shorts motion (audit wave 3)

Source: `_audit/AUDIT_2026-10-20.md` §B. Do this after STEP 76. Section by section: tests and one pushed commit per section; stop at the first failure. Cost: $0 — every proof re-renders existing artifacts from their cached audio; no new TTS, no new footage downloads beyond what the queries already fetch.

Process change (Garcia's request): no more listening/watching tests for Garcia inside STEPs. Each proof is measurements + stills that Claude reviews. Garcia only sees finished videos when he reviews them for upload.

## §0 Housekeeping
- Run the FULL suite first (STEP 76 ended without a final full run). Must be green before anything else.
- Commit the panel's queue moves now in the tree (bv027_sala, bv028_jardin, bv029, gr004 → `_done/`) if their artifacts exist.
- `costs.per_video_tts_usd: 0.30` (Garcia's per-Short budget; 0.25 would have stopped sy001 and gr004).
- `PRONUNCIATION_HINTS` stay off for eleven_v3 (decided; no ear test).
- Hide the legacy dashboard buttons that render the old neon brand (quiz antiguo, pronunciation, educational, vocabulary, fill_blank, true_false — every type whose renderer is not `how_do_you_say.py`) [audit 18]. The code stays until STEP 79.

## §1 `src/video/notebook/` — one kit, drawn properly [10, 20]
- Components: paper page, rings, pencil, tick, circle, highlighter, sticky note, title, Bubi sticker (`assets/branding/english-unlimited/simbolo_512.png`), small brand footer. Every static sprite is drawn at 4× and downsampled once with LANCZOS, then cached (per size/colour). One paper colour for page and outro card.
- `src/video/motion.py` is the only easing module: `ease_out_cubic`, `ease_in_out`, `ease_out_back(overshoot)`, `ease_out_expo`, `spring`, `stagger`. Delete the copies in `how_do_you_say.py`, `animations/easing.py` (keep what other live code imports, re-exported), `v2/motion.py` stays frozen.
- `how_do_you_say.py` (all 7 modes) draws only through the kit. Pixel test: a still of every mode renders; the anti-aliasing test from the audit (distinct values on an ellipse edge) passes for every sprite.

## §2 Speed [9, 18]
- No per-frame rotation: rotate the static page layers once into the cache; draw moving sprites unrotated at rotated coordinates (1° is invisible on a pencil or tick); composite at sub-pixel offsets (affine translate) so slow moves don't step.
- Memoise the page state (quantised: highlight alpha, reveal pixels, pencil position, pulse scale, dot fill); identical states reuse the frame.
- Render frames in a process pool over contiguous chunks, ordered into the ffmpeg pipe.
- Target: an 80 s Short renders in ≤ 60 s on the Mac (today ≈ 280 s). Report per-mode timings.

## §3 Motion [7, 8, 11, 16]
- Opening (0–1 s): the page rises from +120 px with `ease_out_back`, rows cascade in with a 50 ms stagger, and a Spanish sticky-note hook slaps on at −4° with the hard shadow (text from the script: `hook` if present, else built from the theme, e.g. «¿Sabes decir estas 10 cosas de tu cuarto?»; Fredoka 64–72 px).
- Writing: highlighter swipes left→right (`ease_out_expo`, 0.25 s) instead of fading; emoji pops with `ease_out_back` (1.15); ticks are stroke-drawn along their path; the pencil wobbles ±2 px while writing and lifts between rows; the reveal edge is a 12 px feather that follows the pencil tip.
- Recap (today 22 s frozen): the highlighter re-sweeps each row as the voice reaches it (use the segment times), a slow push 1.00→1.04 over the recap, and the CTA is a yellow sticky note «¿Cuántas sabías? __/10» popping with overshoot next to the Bubi sticker.
- Hand-off: the page slides away (0.3 s) into the outro; the outro card enters with `ease_out_back` and Bubi waves (two-frame arm swing). Re-render the 3 cached outros keeping their audio streams ($0).

## §4 Frame layer and safe areas [12, 13, 17]
- Remove the neon progress bar and the white Manrope watermark. Brand: Bubi mini + «learningroutes.com» in Fredoka inside the page footer.
- Safe areas for TikTok/Reels/Shorts: title moved down ~60 px (clear of TikTok's top tabs); nothing readable right of x 940 below y 950 (button rail) or below y 1450 on the left (caption zone).
- Level modes: nothing the viewer must read under 42 px (8 rows per page if 10 don't fit, or a two-column answer layout); tier labels ≥ 32 px; the pencil is 200 px long, has a soft shadow, and parks in the margin during think pauses so it never covers text.

## §5 Emoji [14]
- Keep Noto Color Emoji (its licence needs no on-screen credit) but present each emoji inside an ink-contour white sticker disc with the hard shadow, so it matches the brand.
- Fix the wrong picks (manta 🧣, alfombra 🧶, sábana/colchón sharing 🛏️): the script generator gets the rule «one distinct emoji per item, literal object, no near-synonyms», and `script_schema` rejects duplicates within a page. Re-pick for the 4 queued how_do_you_say scripts (no TTS needed; emoji are not spoken).

## §6 Footage [15]
- Queries include the script's theme (e.g. «bedroom interior», «cozy bedroom») before the category fallbacks.
- 0.5 s crossfades between clips; one grade for the whole set (the STEP 75 soft look).
- Frame index from timestamps, not `int(t*fps)`, so 29.97/59.94 fps clips don't drop or duplicate frames.

## §7 Sound design [19]
- Generate SFX procedurally like the lessons' `sfx.py` (no downloads, no licences): pencil scratch while writing, soft pop on emoji/tick, page swish on the entrance and the hand-off. Mixed −22 dB under the voice RMS, ducked another 6 dB when they land on a spoken word. No music bed.

## §8 Proof (Claude reviews it, not Garcia)
- Re-render from cached audio: the newest approved how_do_you_say and one level mode (choose_level or fill_level).
- For each: render time, and stills at 0.0, 0.3, 0.7, 1.0, 3.0 s, a writing moment, recap start, CTA, and two frames across the outro hand-off, saved to `_audit/stills/STEP77/`. Plus the STEP 75 measurement table (bitrate, keyframes, tags, LUFS, TP, duration) to prove nothing regressed.
- `git log --oneline -12`, `git status --short`. Stop.
