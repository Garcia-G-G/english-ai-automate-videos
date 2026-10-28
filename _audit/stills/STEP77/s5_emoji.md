# STEP 77 §5 — emoji

Still (gitignored): `s5_emoji_stickers.png` (bv026 dormitorio, the re-picked page).

- Noto Color Emoji stays (no on-screen credit needed); each emoji now sits in a white sticker
  disc with an ink outline and a hard ink shadow (`kit.emoji_sticker`), at 62 % of the disc so
  a square emoji's corners stay inside the circle.
- `script_schema` refuses the same emoji twice on a how_do_you_say page (VS16 ignored); the
  generator prompt asks for one distinct emoji per item, the literal object, no near-synonyms,
  and to change one of the words when two share the only emoji there is.
- Re-picks ($0, emoji are not spoken; JSON diffs are the emoji lines only):
  - bv026 dormitorio (rendered, `_done/`, and its cached artifact cómo_se_dice_20261019_163101):
    Manta 🧣→🟦, Sábana 🛌→⬜, Alfombra 🧶→🟫, Colchón keeps 🛏️. Unicode has no blanket,
    sheet or rug: fabric swatches, distinct from the bed.
  - queued: bv035 Bigote 👨→🥸, bv037 Ingeniero 🏗️→👷, bv039 Medusa 🌊→🪼, bv043 Flauta 🎶→🪈,
    bv047 Bajo 🐁→⬇️ (🐭 Pequeño was the same mouse), bv053 Levantarse 🛏️→🌅 (🛌 Acostarse).
- The STEP's «4 queued how_do_you_say scripts» were rendered before §5 ran; today 29 are queued,
  all reviewed: no duplicates. Left as they are, because Unicode has no literal emoji and the
  rule forbids ZWJ sequences: belt, earrings, harp, drill, glue, steering wheel, nurse/teacher/
  pilot/farmer (ZWJ only), «cinta adhesiva» 📼. Changing those words would change the audio.
