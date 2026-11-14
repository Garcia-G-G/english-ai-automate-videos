# STEP 50 — A voice that sounds less "AI made": one probe, then a decision

## 0. The ask and what it is not

The owner (2026-10-13): the voice still sounds AI-generated; he wants the small human
sounds people make when they talk. This is ONE probe that ends in an A/B file for his ear
(headphones), the same way as the Manim onset A/B — not a pipeline rewrite. Budget for the
probe: ≈ $1 of ElevenLabs. Constraints as always: OpenAI + ElevenLabs only, everything else
local and free, no MoviePy, no keys/voice IDs/home paths in commits.

The Manim onset A/B (`audio/_probe/variants/*_ab.mp3`, 6 variants) is still waiting for the
owner's ear. Fold it in: this probe adds the variants below to the same three items (b18,
b05, b08), so one listening session decides both questions.

## 1. What changed outside the repo (verified 2026-10-13 on elevenlabs.io)

- **Eleven v4 shipped on 2026-09-28**: `eleven_v4` and `eleven_v4_turbo`. ElevenLabs'
  models page lists `language_code` for both (and for `eleven_v3`); audio tags for v4
  Turbo; claims less accent drift and the same voice identity across languages.
- **API price per 1K characters**: v4 $0.08 (same as v3 and multilingual v2); **v4 Turbo
  $0.04 (same as the flash/turbo v2.5 we use now)**. So v4 Turbo on the bilingual path is
  cost-neutral; v4 is cost-neutral wherever we already use v3.
- `eleven_turbo_v2_5` is marked **deprecated** (= flash v2.5) on the models page. The
  Shorts bilingual path and the Manim lessons both use it.
- ElevenLabs' v3 prompting guide: "very short prompts are more likely to cause
  inconsistent outputs" (they suggest > 250 characters). Our segments are often one to
  three words ("Rojo.", "red. red.", "make the bed") — the most unstable shape there is,
  and the one where we hear the onset stutters.
- `src/profiles.py:94-104` says eleven_v3 does not accept language_code and forces turbo
  v2.5 on the bilingual path for that reason. Re-verify against the current API: if it is
  no longer true, that override is the thing keeping us on the deprecated model.

## 2. Variants to add (same items, same beeps-before-each format, 320 kbps)

| # | model | request shape | notes |
|---|---|---|---|
| 7 | eleven_v4_turbo | today's segmentation, explicit language_code per segment, no cross-language context | cost-neutral swap |
| 8 | eleven_v4 | ONE request per beat/item, both languages in it | timings from the with-timestamps alignment if v4 returns it, else local WhisperX (free); state which |
| 9 | #7 or #8 (whichever the detector likes) + the naturalness pack below | — | |

Naturalness pack (free, local, all measurable):
- Voice settings at v3/v4 "Natural" stability (not Robust); keep style low. Report the
  numbers you used.
- Do not trim the model's own inhale at a segment start (check the onset trimming code
  does not cut breaths; a breath is not a dirty onset — the detector must not flag it).
- A light mastering chain with ffmpeg only: high-pass ~80 Hz, `deesser`, gentle
  compression, `loudnorm` to the level we already target. No reverb unless it is
  inaudible as an effect. Measure loudness before/after.
- Script side, for this probe only: in the intro/outro text use one allowed non-verbal tag
  ([chuckles] or [exhales]) and one Spanish discourse marker ("Vale,", "Bueno,", "A ver…").
  Tell me which model honours the tag and which reads it aloud — I will write the content
  rules from that, not before.

## 3. What I need back

- The three A/B files with variants 1–9 (or 1–6 + 7–9 as a second file), full paths.
- Per variant: dirty onsets (the recalibrated detector), duration, characters, $ spent,
  and whether timing/alignment was available.
- The language_code answer for v3/v4 (§1, last bullet) with the request/response that
  proves it (no keys in the paste).
- Nothing becomes the default until the owner has listened.
