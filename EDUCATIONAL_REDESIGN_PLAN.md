# Educational Video Redesign — Card-Based Layout

## Current Problem

The educational video type shows raw text floating over the gradient background with no
visual structure. The other types (quiz, vocabulary, fill_blank, true_false) all use
rounded cards, glass buttons, and containers that look far more professional and organized.

## What Was Already Implemented (Prompts 1-3)

The following card-based features are already coded in `src/video/educational.py`:

- **Cream card** for Spanish karaoke groups (fill=cream_card, alpha=235, shadow)
- **Dark glassmorphism card** for English word highlights (fill=(20,20,40), accent bar)
- **Hero glassmorphism card** for 100% English groups (fill=(15,15,35), border, accent bar)
- **Spring bounce** entrance animation (ease_out_back, 0.45s)
- **Slide-in** for English card (slide_in_x, 0.15s delay)
- **Pop-scale** for hero card (tiktok_pop_scale)
- **Dynamic card sizing** based on content height
- **Vertical centering** within SAFE_AREA

## What Still Needs Work (Prompts 4-6)

---

### PROMPT 4: Card transition animations between groups

```
Read src/video/educational.py completely. Focus on _render_group_tiktok() and how
it handles is_fading_out.

Currently when a group fades out, only the alpha decreases. Improve the transitions:

1. When a group exits (is_fading_out=True):
   - Add a slide-out to the LEFT for the card. Calculate x_offset:
     fade_progress = min(1.0, (t - end) / GROUP_TRANSITION)
     x_offset = int(-200 * ease_in_out_sine(fade_progress))
   - Apply this x_offset to both the card position and all text inside it.
   - The alpha fade already exists — keep it as-is.

2. For the spring bounce entrance (already implemented):
   - Make sure the bounce only applies on the FIRST appearance, not on
     every frame. It should only trigger when elapsed < _BOUNCE_DURATION.
   - This is already correct in the code — just verify.

3. If there are 2 cards (main + English highlight card):
   - The English card already has a 0.15s delay via slide_in_x — this is fine.
   - On exit, the English card should slide out 0.1s BEFORE the main card
     (reverse stagger). Add this by checking if is_fading_out and adjusting
     the English card's alpha to fade faster.

4. Ensure two groups NEVER overlap visually:
   - The current GROUP_TRANSITION value controls how long the fade-out lasts.
   - If groups overlap in time, the fade-out should be faster.
   - Read the value from constants.py and verify it's short enough (should be
     0.15-0.25s max).

Files to modify: src/video/educational.py (only _render_group_tiktok and _render_english_card)
Files to read: src/config/timing.py (for GROUP_TRANSITION value)
```

### PROMPT 5: Visual polish — text colors inside cards

```
Read src/video/educational.py completely. The cards are already implemented but the
text colors need adjustment because the context changed (text is now on a card background,
not directly on a dark gradient).

1. Spanish text inside the CREAM card:
   - The cream card has a light background (255, 252, 245). Currently the Spanish
     words use these colors:
     - _SPANISH_ACTIVE = (0, 212, 255) — bright cyan (currently spoken)
     - _SPANISH_UPCOMING = (80, 120, 150) — muted grey-blue
     - _SPANISH_PAST = (60, 90, 120) — dim grey
   - These colors were designed for dark backgrounds. On a cream card:
     - Change _SPANISH_ACTIVE to (0, 120, 200) — darker blue that pops on cream
     - Change _SPANISH_UPCOMING to (60, 70, 90) — dark grey, readable on cream
     - Change _SPANISH_PAST to (130, 140, 160) — medium grey, subtle on cream
   - Reduce outline from 3px to 2px for Spanish words (the card provides contrast)
   - Keep outline at 4-5px for English words (yellow on cream needs contrast)

2. English words INSIDE the dark glassmorphism card:
   - ENGLISH_WORD_COLOR (yellow) on dark background is already good.
   - Reduce glow_radius from 6 to 4 (less exaggerated inside a card).

3. Translation text inside the dark card:
   - Change _TRANS_COLOR to (230, 235, 250) — slightly brighter since dark bg
   - Remove the shadow offset rendering (the dark card already provides contrast)
   - Keep outline at 2px.

4. Make sure fit_text_font() max_width matches the card interior:
   - Current: max_w = CARD_WIDTH - CARD_PADDING * 2 - 40 (already correct)
   - Verify this is used consistently in _render_spanish_karaoke() line_break call.

Files to modify: src/video/educational.py (color constants at top, outline values in
_render_spanish_karaoke, _render_english_card, _render_english_hero)
```

### PROMPT 6: Testing and final adjustments

```
Read src/video/educational.py (final version after prompts 4-5).

Create a test script at /tmp/test_educational_cards.py that generates test frames
for visual verification. The script should:

1. Import the necessary modules:
   import sys
   sys.path.insert(0, 'src')
   from video.educational import create_frame_educational
   from PIL import Image

2. Create test data for each scenario (mock groups with word timestamps):

   a) Spanish-only short group:
      - text: "Hola, vamos a aprender"
      - 4 words with timestamps 0.5s apart starting at 1.0s
      - No English words

   b) Spanish-only long group (should wrap to 2 lines):
      - text: "Cuando quieras expresar que algo está bien en inglés de manera casual"
      - 12 words with timestamps
      - No English words

   c) Mixed group (Spanish + English words):
      - text: "puedes usar la palabra cool para decir genial"
      - Mark "cool" as is_english=True
      - translations: {"cool": "genial/increíble"}

   d) English hero group:
      - text: "AWESOME"
      - english=True, all words is_english=True
      - translations: {"awesome": "increíble"}

   e) Transition frame (between two groups):
      - Two groups: first ends at 3.0s, second starts at 3.1s
      - Generate frame at t=3.05 (should show first fading out)

3. For each scenario, generate the frame at the appropriate time and save as PNG.

4. Verify visually that:
   - Text NEVER overflows outside the card boundaries
   - Cards NEVER overlap each other
   - Cards stay within SAFE_AREA_TOP and SAFE_AREA_BOTTOM
   - The spring bounce animation doesn't push cards off-screen
   - Word-by-word karaoke highlighting works correctly inside the card
   - The English highlight card appears below the main card with proper spacing
   - Translation appears in the English card, not floating
   - Hero card scales properly with pop-in animation

5. If anything looks wrong, adjust the layout constants and re-test.

Files to create: /tmp/test_educational_cards.py
Files to read: src/video/educational.py, src/video/utils.py
```

---

## Execution Order

1. **Prompt 4** → Slide-out transitions + reverse stagger
2. **Prompt 5** → Adjust text colors for card backgrounds
3. **Prompt 6** → Test all scenarios visually

Each prompt builds on the previous one. After prompt 6, the educational video should
have the same visual quality as quiz, vocabulary, and fill_blank.
