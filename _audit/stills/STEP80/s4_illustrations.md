# STEP 80 §4 — an illustration for each item

- **On screen** (`how_do_you_say`): while a row is being taught (from its Spanish to the next row's),
  its word's illustration pops in (ease-out-back, 0.3 s) on a cream card ~30 % of the page wide
  (258 px), drawn on the page so it tilts and moves with it. It sits at the page's right, **below
  the active row whenever it fits** (over rows whose English is not written yet) and above it only for
  the last rows — never over the active row. No image for a word → no card. Nothing is drawn before
  the first row (the hook) or in the recap, so **frame 1 is identical with or without illustrations**
  (tested pixel for pixel).
- **The library** (`src/illustrations.py`): `assets/illustrations/<word>.png` (`Ice cream` →
  `ice_cream.png`); a word is drawn once, ever, then reused in every video.
- **Drawing them**: OpenRouter chat completions with `modalities: ["image", "text"]`, `meta/muse-image`
  ($0.01) with the style reference (`assets/illustrations/style_ref.png` when Claude provides it; the
  Bubi brand sheet until then), else `bytedance-seed/seedream-5-0-flash` ($0.018). Prompt: flat,
  thick ink outline, the brand palette, cream background, no text. Only from the panel: «Crear» with
  «Cómo se dice» shows «N ilustraciones nuevas · $X» for the next queued script and the button «Dibujar
  N ilustraciones»; each image goes through the OpenRouter caps and the voice lock first, and is
  logged (`openrouter_image`).
- **Not done**: no image was drawn (no paid call from Claude); the library is empty, so videos look
  as before until Garcia's first click. The style of the real images is not reviewed.

Seen while testing, not changed (outside §4): at t = 0.0 the page is still empty — the STEP 77
cascade writes the rows in from 0.2 to ~0.75 s, so «the full list on frame 1» holds from ~0.75 s,
not from the very first frame.
