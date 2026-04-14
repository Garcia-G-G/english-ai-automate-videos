# Animation Upgrade Prompts for Claude Code

## How to Use
Each section below is a **self-contained prompt** you can copy-paste into Claude Code.
Run them **in order** — Prompt 1 first (shared utilities), then any video type prompt after.

---

## PROMPT 1 — Shared Visual Utilities (Run First)

```
I need you to upgrade the visual utilities in my TikTok English-learning video generator project. These shared utilities will be used by all video types, so implement them first.

PROJECT CONTEXT:
- Canvas: 1080x1920 (TikTok vertical)
- Frame generator pattern: create_base_frame(t) → render → finalize_frame(frame, draw, t, duration)
- PIL/Pillow for rendering, numpy arrays for output
- Existing utilities in src/video/utils.py: font(), line_break(), draw_text_solid(), draw_text_with_glow(), draw_glass_button(), draw_gradient_rounded_rect(), fit_text_font(), create_base_frame(), finalize_frame()
- Existing constants in src/config/colors.py, src/config/typography.py, src/config/layout.py, src/config/timing.py
- Existing animations in src/animations/easing.py: tiktok_pop_scale(), spring_animation(), ease_out_back(), bounce_offset(), etc.

TASK — Add these new shared drawing utilities to src/video/utils.py:

1. draw_rounded_card(img, x, y, w, h, radius=30, fill=(255,255,255), alpha=240, shadow=True, shadow_offset=6, shadow_alpha=80):
   - Draw a solid rounded rectangle card with optional drop shadow
   - Shadow: dark semi-transparent offset below and right
   - Card: solid fill with rounded corners
   - Use PIL alpha compositing (paste with mask)
   - Return None (draws in-place on img)

2. draw_pill_badge(img, draw, text, center_x, center_y, font_size=28, bg_color=(76,175,80), text_color=(255,255,255), padding_x=24, padding_y=10):
   - Draw a pill-shaped badge (fully rounded rectangle) with text centered inside
   - Background: solid bg_color with fully rounded ends (radius = height/2)
   - Text: centered inside the pill
   - Return (width, height) of the pill

3. draw_circle_number(draw, number, center_x, center_y, radius=28, bg_color=(255,120,130), text_color=(255,255,255), font_size=32):
   - Draw a filled circle with a number centered inside
   - Used for quiz option letters (A, B, C, D) or numbered lists
   - Return None

4. draw_progress_timer_bar(draw, img, x, y, width, height, progress, bg_color=(60,60,80), fill_color=(76,175,80), radius=8):
   - Horizontal progress bar that depletes from right to left
   - progress: 1.0 = full, 0.0 = empty
   - Background: dark rounded rect, Fill: colored portion
   - Color should change: green (>0.5) → yellow (0.25-0.5) → red (<0.25)
   - Return None

5. draw_two_column_row(draw, img, left_text, right_text, y, row_height=90, left_font_size=44, right_font_size=44, left_color=(255,255,255), right_color=(255,215,0), highlight=False, highlight_color=(255,255,255,30), margin_x=80, divider_x=540):
   - Draw a two-column row for vocabulary list style
   - If highlight=True, draw a semi-transparent highlight rectangle behind the row
   - Left text right-aligned to divider_x, right text left-aligned from divider_x
   - A thin vertical divider line at divider_x
   - Return None

6. draw_difficulty_badge(draw, img, level, x, y):
   - level: "facil", "medio", "dificil", "experto"
   - Colors: facil=(76,175,80), medio=(255,193,7), dificil=(255,87,34), experto=(211,47,47)
   - Labels: "FÁCIL", "MEDIO", "DIFÍCIL", "EXPERTO"
   - Uses draw_pill_badge internally
   - Return (width, height)

Also add these constants to src/config/colors.py:

CARD_COLORS = {
    'white_card': (255, 255, 255),
    'cream_card': (255, 252, 245),
    'dark_card': (30, 30, 45),
    'shadow': (0, 0, 0),
    'divider': (200, 200, 210),
    'highlight_row': (255, 255, 255, 25),
}

DIFFICULTY_COLORS = {
    'facil': (76, 175, 80),
    'medio': (255, 193, 7),
    'dificil': (255, 87, 34),
    'experto': (211, 47, 47),
}

BADGE_COLORS = {
    'green': (76, 175, 80),
    'blue': (66, 133, 244),
    'orange': (255, 152, 0),
    'red': (244, 67, 54),
    'purple': (156, 39, 176),
}

And these to src/config/layout.py:

# Card dimensions
CARD_MARGIN_X = 60
CARD_PADDING = 40
CARD_RADIUS = 30
CARD_WIDTH = 1080 - 2 * CARD_MARGIN_X  # 960px

# Two-column vocabulary
VOCAB_ROW_HEIGHT = 90
VOCAB_DIVIDER_X = 500
VOCAB_START_Y = 350
VOCAB_MAX_ROWS = 12

# Timer bar
TIMER_BAR_WIDTH = 800
TIMER_BAR_HEIGHT = 12
TIMER_BAR_Y = 1750
TIMER_BAR_X = (1080 - 800) // 2  # centered

IMPORTANT:
- Do NOT modify any existing functions, only ADD new ones
- All new drawing functions must handle alpha compositing correctly using PIL Image.paste with mask
- Test that draw_rounded_card works by verifying the shadow renders behind the card
- Make sure draw_pill_badge text is properly centered using textbbox
- Import any new color constants at the top of utils.py where needed
```

---

## PROMPT 2 — Vocabulary List Style (Educational Enhancement)

```
I need you to create a new video renderer for vocabulary list style videos in my TikTok English-learning video generator. This shows a two-column Spanish/English vocabulary list with row-by-row highlight animation.

PROJECT CONTEXT:
- Canvas: 1080x1920 (TikTok vertical)
- Existing pattern: create_frame_TYPE(t, data, duration) → np.ndarray
- Uses create_base_frame(t) and finalize_frame(frame, draw, t, duration)
- PIL/Pillow rendering, numpy output
- Utilities available: font(), line_break(), draw_text_solid(), draw_text_centered(), draw_rounded_card(), draw_two_column_row(), draw_pill_badge(), fit_text_font()
- Animation functions: get_alpha(), tiktok_pop_scale(), ease_out_back(), spring_animation()
- Constants: VIDEO_WIDTH=1080, VIDEO_HEIGHT=1920, all layout/color/timing configs

REFERENCE STYLE (what I want):
- Title at top: "Vocabulario del día" or topic title in large yellow text
- Subtitle: topic description smaller below
- White/cream semi-transparent card (alpha ~220) centered on screen containing the vocabulary rows
- Two columns inside the card: ESPAÑOL | INGLÉS with a colored header row
- Each row shows one word pair, rows appear one by one synced to audio
- Current row gets highlighted with a colored background (semi-transparent blue or white glow)
- Previous rows stay visible but dimmer
- Small difficulty badge in corner (FÁCIL, MEDIO, etc.)
- Clean divider line between columns
- 8-12 word pairs per video

TASK — Create src/video/vocabulary.py:

1. Create function create_frame_vocabulary(t, data, duration) -> np.ndarray:

   Expected data structure:
   {
       "type": "vocabulary",
       "title": "Vocabulario: En el Restaurante",
       "difficulty": "medio",  // facil, medio, dificil, experto
       "pairs": [
           {"spanish": "La cuenta", "english": "The bill"},
           {"spanish": "El mesero", "english": "The waiter"},
           ...
       ],
       "segment_times": {
           "title": {"start": 0.0, "end": 2.0},
           "pair_0": {"start": 2.5, "end": 4.0},
           "pair_1": {"start": 4.5, "end": 6.0},
           ...
       }
   }

2. Animation timeline:
   - 0.0s: Title fades in with tiktok_pop_scale (yellow text, large font ~72px)
   - 0.3s: Difficulty badge slides in from right (ease_out_back)
   - 0.5s: White card fades in (draw_rounded_card, alpha 220, shadow)
   - 0.7s: Header row appears ("ESPAÑOL" | "INGLÉS" in bold, colored background strip)
   - Then each pair appears one by one synced to segment_times:
     - Row slides in from right (slide_in_x animation, 0.3s)
     - Spanish word on left, English word on right
     - Current row has a highlight background (semi-transparent colored strip)
     - When next row appears, previous row dims to ~70% alpha
   - All rows remain visible after appearing

3. Visual layout:
   - Title: Y=180, centered, yellow, font 72px, outline 5
   - Difficulty badge: top-right corner (X=900, Y=185)
   - Card: X=60, Y=300, W=960, H=depends on row count (VOCAB_ROW_HEIGHT * rows + header + padding)
   - Header row: inside card top, background colored strip (blue gradient), white text "ESPAÑOL" | "INGLÉS"
   - Data rows: VOCAB_ROW_HEIGHT=90px each, alternating very subtle background tint
   - Divider: thin vertical line at VOCAB_DIVIDER_X=500
   - Current highlighted row: semi-transparent blue/cyan background (0, 180, 220, 40)
   - Spanish text: white, font 42px
   - English text: yellow/gold (255, 215, 0), font 42px, slightly bold

4. Fallback for missing segment_times:
   - If no segment_times, distribute pairs evenly across duration
   - title_duration = 2.0s, then divide remaining time equally among pairs
   - Each pair gets at least 1.5s display time

5. Register the new type in src/video/__init__.py:
   - Import create_frame_vocabulary from .vocabulary
   - Add elif video_type == 'vocabulary' block in generate_video()
   - Parse segment_times if available

IMPORTANT:
- Follow the exact same pattern as other renderers (create_base_frame → draw → finalize_frame)
- Use the shared utility functions (draw_rounded_card, draw_two_column_row, etc.)
- Make sure text fits within columns using fit_text_font if words are long
- The card should be positioned so it doesn't overlap with the progress bar at the bottom
- Row highlight animation should be smooth (ease_in_out_sine for alpha transition)
```

---

## PROMPT 3 — Enhanced Quiz with Difficulty Levels

```
I need you to significantly upgrade the quiz video renderer in my TikTok English-learning video generator. The current quiz.py works but looks basic. I want a more professional, modern look inspired by popular TikTok quiz formats.

PROJECT CONTEXT:
- File to modify: src/video/quiz.py
- Current renderer: create_frame_quiz(t, data, duration) with gradient question box, pill options, countdown ring
- Available utilities: draw_rounded_card(), draw_pill_badge(), draw_circle_number(), draw_difficulty_badge(), draw_progress_timer_bar(), draw_gradient_rounded_rect(), draw_glass_button(), draw_sparkles()
- Animation functions: tiktok_pop_scale(), spring_animation(), ease_out_back(), slide_in_x(), get_alpha(), pulse_scale()
- Layout zones defined in config/layout.py: QUESTION_ZONE_TOP=288, OPTIONS_ZONE_TOP=806, etc.

CHANGES NEEDED:

1. ADD DIFFICULTY BADGE:
   - Read data.get('difficulty', 'medio') from the data dict
   - Draw difficulty badge in top-right area (X=880, Y=100) using draw_difficulty_badge()
   - Badge should pop in with tiktok_pop_scale at t=0.3s
   - Keep it visible throughout the video

2. ADD QUESTION NUMBER:
   - Read data.get('question_number', 1) from data dict
   - Show "Pregunta X" text above the question box in small font (32px)
   - White text with slight transparency (alpha 200)
   - Appears with the question

3. IMPROVE QUESTION BOX:
   - Replace the gradient rounded rect with draw_rounded_card (white card, alpha=235)
   - Question text should be dark (50, 45, 60) on the white card instead of white on gradient
   - Card: X=60, Y=QUESTION_ZONE_TOP, W=960, auto-height based on text
   - Add a thin colored accent bar (4px) at the top of the card using the difficulty color
   - Question text font: keep dynamic sizing but min 40px instead of 36px

4. IMPROVE OPTIONS:
   - Each option in its own rounded card (smaller, height ~85px)
   - Letter circle on the left (A, B, C, D) using draw_circle_number
   - Option text to the right of the circle
   - Cards stacked vertically with 15px gap
   - Stagger animation: each option slides in from right with 120ms delay between them
   - On answer reveal:
     - Correct option: card background turns green (100, 220, 160), white border glows
     - Wrong options: card fades to 40% alpha
     - Keep sparkle effect on correct answer
   - Remove the old cream background behind all options

5. ADD HORIZONTAL TIMER BAR:
   - Replace the circular countdown ring with a horizontal timer bar at the bottom
   - Use draw_progress_timer_bar() at TIMER_BAR_Y position
   - Timer depletes during countdown phase (3, 2, 1)
   - Color changes: green → yellow → red as time runs out
   - The countdown number (3, 2, 1) should still appear large and centered but WITHOUT the ring
   - Keep the pop animation and glow on the countdown numbers

6. ANSWER REVEAL IMPROVEMENTS:
   - When answer is revealed, the correct option card does a subtle pulse (pulse_scale, 1.0 → 1.03)
   - Show explanation text below options in a light card (alpha 200)
   - Explanation card slides up from bottom (slide animation, 0.4s)

IMPORTANT:
- Keep all existing timestamp parsing logic (parse_quiz_timestamps, resolve_quiz_timestamps) unchanged
- Keep the same create_frame_quiz(t, data, duration) signature
- Do NOT break the fallback logic for missing segment_times
- Maintain backward compatibility: if 'difficulty' is missing, default to 'medio'
- If 'question_number' is missing, don't show "Pregunta X"
- Test that the visual zones don't overlap (question card + options + timer bar)
- The VISUAL_ANTICIPATION timing constant (150ms) should still be respected
```

---

## PROMPT 4 — Phrase Card Style (Pronunciation Enhancement)

```
I need you to completely redesign the pronunciation video renderer in my TikTok English-learning video generator. Currently it shows plain text on a gradient background. I want a modern phrase-card style with a clean white card overlay.

PROJECT CONTEXT:
- File to modify: src/video/pronunciation.py
- Current function: create_frame_pronunciation(t, data, duration)
- Current layout: plain text at fixed Y positions, gradient background
- Available utilities: draw_rounded_card(), draw_pill_badge(), font(), draw_text_solid(), draw_text_centered(), fit_text_font(), get_alpha(), tiktok_pop_scale(), create_base_frame(), finalize_frame()
- Config: layout.py has PRON_TITLE_Y=250, etc. (can be updated)

REFERENCE STYLE (what I want):
- A large white rounded card centered on screen
- Inside the card, vertically stacked:
  1. Spanish word/phrase (large, dark text)
  2. A thin colored divider line
  3. English translation (medium, colored text - blue or teal)
  4. Phonetic pronunciation in simplified format (smaller, gray italic-style)
- Below the card: tip text
- The card should have a subtle shadow
- Clean, minimalist, modern look

TASK — Rewrite create_frame_pronunciation:

1. New animation timeline:
   Phase 1 (0% - 20% of duration): Card appears
   - White rounded card slides up from below with spring_animation
   - Card: centered, W=880, H=auto (depends on content), radius=35
   - Shadow beneath card

   Phase 2 (20% - 40%): Content fills in
   - Word appears inside card (tiktok_pop_scale), large font 80-120px (use _word_font_size)
   - Color: dark text (50, 45, 60) on white card
   - Thin horizontal divider line fades in below the word (color matches difficulty or cyan)

   Phase 3 (25% - 50%): "¿Cómo se pronuncia?" question
   - Question text appears below card, centered, white, font 48px
   - Fades in with get_alpha

   Phase 4 (40% - 60%): Common mistake
   - Red badge "Incorrecto" using draw_pill_badge with red background
   - Mistake text below badge in red, font 52px
   - Both inside the card (below the divider)
   - After 3 seconds, these fade out (alpha transition over 0.5s)

   Phase 5 (55% - 80%): Correct pronunciation
   - Green badge "Correcto" using draw_pill_badge with green background
   - Phonetic text below badge in green, font 56px
   - These replace the incorrect section inside the card
   - Pop-in animation (tiktok_pop_scale)

   Phase 6 (75% - 100%): Translation + Tip
   - Translation text appears inside card at bottom (teal/blue color, font 44px)
   - Format: "(traducción)" in parentheses
   - Tip text appears below the card, white, font 40px, fades in

2. Card layout (inside the card):
   - Padding: 50px top/bottom, 40px left/right
   - Word: centered horizontally, near top of card
   - Divider: 2px line, width=card_width - 80px, centered, color=(200, 210, 220)
   - Mistake/Correct section: below divider
   - Translation: bottom of card
   - The card height should be calculated dynamically based on what's currently showing

3. Fallback: if _word_font_size returns a size that still makes text overflow card width, use fit_text_font to shrink further (max_width = card_width - 80)

4. Update layout.py pronunciation constants to match the new card-based design:
   PRON_CARD_Y = 350  # top of card
   PRON_CARD_WIDTH = 880
   PRON_CARD_MIN_HEIGHT = 500
   PRON_CARD_RADIUS = 35
   PRON_CARD_PADDING = 50
   # Remove or keep old PRON_*_Y values for backward compat

IMPORTANT:
- Keep the same function signature: create_frame_pronunciation(t, data, duration)
- Keep _word_font_size() helper function (it works well)
- The card should NOT extend below Y=1700 to avoid progress bar overlap
- Use draw_rounded_card for the main card with shadow=True
- Use draw_pill_badge for "Incorrecto" and "Correcto" labels
- Text inside the card should be dark (not white) since it's on a white background
- Make sure the question "¿Cómo se pronuncia?" appears OUTSIDE and below the card (white text on gradient background)
```

---

## PROMPT 5 — Enhanced True/False with Card Layout

```
I need you to upgrade the true/false video renderer in my TikTok English-learning video generator to use a card-based layout matching the modern style of the other video types.

PROJECT CONTEXT:
- File to modify: src/video/true_false.py
- Current function: create_frame_true_false(t, data, duration)
- Current layout: plain text statement + gradient buttons (VERDADERO/FALSO)
- Available utilities: draw_rounded_card(), draw_pill_badge(), draw_gradient_rounded_rect(), draw_glass_button(), draw_sparkles(), draw_progress_timer_bar(), font(), draw_text_centered(), fit_text_font()
- Animation functions: tiktok_pop_scale(), spring_animation(), slide_in_x(), ease_out_back(), get_alpha(), pulse_scale()
- Timing: VISUAL_ANTICIPATION=150ms, TRUE_FALSE_SLIDE_DURATION=500ms

CHANGES NEEDED:

1. STATEMENT IN A WHITE CARD:
   - Replace plain text statement with a white rounded card (draw_rounded_card)
   - Card: centered, X=60, W=960, auto-height, alpha=235, radius=30
   - Statement text: dark (50, 45, 60) on white card, dynamic font sizing (fit_text_font, max 56px, min 36px)
   - Card pops in with spring_animation
   - Add a colored accent bar at top of card (4px, teal color)

2. IMPROVE BUTTONS:
   - Make the VERDADERO/FALSO buttons larger and more prominent
   - Each button: 420×130px (keep current size)
   - Add emoji/icon text: "✓ VERDADERO" and "✗ FALSO"
   - Buttons should have rounded corners (radius 30) and gradient fill
   - Keep the slide-in-from-sides animation (left/right)
   - On answer reveal:
     - Correct button: bright glow halo + pulse effect + sparkles
     - Wrong button: fades to 25% alpha, slides slightly away (10px outward)

3. ADD TIMER BAR:
   - Horizontal timer bar at TIMER_BAR_Y using draw_progress_timer_bar()
   - Depletes during countdown phase
   - Color transitions: green → yellow → red
   - Replace the countdown ring with just the large number + timer bar

4. EXPLANATION CARD:
   - When explanation appears, show it in a light card (alpha 200, slightly tinted)
   - Card slides up from bottom
   - Explanation text: white on slightly dark card OR dark on light card
   - Keep within bounds (don't overlap timer bar)

5. COUNTDOWN NUMBER:
   - Large number (font 180px) centered on screen
   - Pop animation with tiktok_pop_scale
   - No ring around it (cleaner look)
   - Subtle glow behind the number
   - Color: white with slight tint matching countdown phase (green→yellow→red)

IMPORTANT:
- Keep the same function signature: create_frame_true_false(t, data, duration)
- Keep all existing timestamp parsing (parse_true_false_timestamps, resolve_true_false_timestamps)
- Maintain the segment_times fallback logic
- Don't break backward compatibility with existing data format
- The card + buttons + timer should all fit without overlapping
```

---

## PROMPT 6 — Enhanced Fill-in-the-Blank with Card Layout

```
I need you to upgrade the fill-in-the-blank video renderer in my TikTok English-learning video generator to match the modern card-based visual style.

PROJECT CONTEXT:
- File to modify: src/video/fill_blank.py
- Current function: create_frame_fill_blank(t, data, duration)
- Current layout: plain text sentence + 2x2 glass button grid
- Available utilities: draw_rounded_card(), draw_pill_badge(), draw_circle_number(), draw_glass_button(), draw_sparkles(), draw_progress_timer_bar(), font(), draw_text_centered(), fit_text_font()
- Animation functions: tiktok_pop_scale(), slide_in_x(), ease_out_back(), get_alpha(), pulse_scale()

CHANGES NEEDED:

1. SENTENCE IN A WHITE CARD:
   - Show the sentence in a white rounded card at the top
   - Card: X=60, W=960, auto-height, alpha=235, radius=30
   - The blank (___) should be highlighted with a colored underline or a colored box
   - Before answer: blank shows as "______" with a pulsing underline (cyan color)
   - After answer: blank fills in with the correct word in green, with a pop animation
   - Sentence text: dark color (50, 45, 60) on white, font 48-56px

2. OPTIONS AS INDIVIDUAL CARDS:
   - Replace 2x2 glass button grid with 4 stacked option cards (vertical list)
   - Each option card: W=860, H=75px, radius=20, centered
   - Letter circle on left (A, B, C, D) using draw_circle_number, then option text
   - Gap between cards: 12px
   - Staggered slide-in animation: each card slides from right with 100ms delay
   - On answer reveal:
     - Correct card: green background (100, 220, 160), white text, sparkles
     - Wrong cards: fade to 40% alpha
     - Correct card does a subtle pulse

3. ADD TIMER BAR:
   - draw_progress_timer_bar at bottom area
   - Same behavior as quiz (depletes during countdown)

4. TRANSLATION:
   - Show translation in a small pill badge below the options
   - Uses draw_pill_badge with blue/teal background
   - Fades in 0.5s after answer is revealed

5. COUNTDOWN:
   - Large centered number (font 160px)
   - Pop animation, no ring
   - Subtle glow behind number
   - Timer bar depletes simultaneously

IMPORTANT:
- Keep same function signature: create_frame_fill_blank(t, data, duration)
- Keep existing timestamp parsing and fallback logic
- The blank highlighting is key — make it visually clear what word is missing
- Use pulsing underline animation for the blank (sine wave alpha, 0.5-1.0, 2Hz)
- After answer reveal, the blank word should pop in green with tiktok_pop_scale
```

---

## PROMPT 7 — Educational Video Visual Polish

```
I need you to fix and polish the educational video renderer in my TikTok English-learning video generator. The current educational.py has issues with text ghosting, empty space, and doesn't look as clean as it should.

PROJECT CONTEXT:
- File to modify: src/video/educational.py
- Current function: create_frame_educational(t, data, duration)
- Uses word-by-word karaoke sync with _groups
- Sub-renderers: _render_spanish_karaoke(), _render_english_hero(), _render_text_simple()
- Constants: SAFE_AREA_TOP, SAFE_AREA_BOTTOM, SIZE_MAIN_SPANISH=90, SIZE_ENGLISH_WORD=140
- Animations: tiktok_pop_scale, word_highlight_alpha, get_word_animation_state

PROBLEMS TO FIX:

1. TEXT GHOSTING / OVERLAP:
   - When groups transition, old text sometimes doesn't fully disappear
   - Fix: Ensure group_alpha reaches exactly 0 before stopping render
   - In _render_group_tiktok: if group_alpha <= 2, return (not just <= 0)
   - Make GROUP_TRANSITION faster: 0.2s instead of current value
   - Only render fade_out_group if it's within GROUP_TRANSITION time window

2. EMPTY SPACE:
   - Large gaps appear when text is short
   - Fix: Center text vertically within safe area more precisely
   - Calculate actual text block height (all lines + translation if English)
   - Center: base_y = SAFE_AREA_TOP + (safe_height - actual_height) / 2
   - Clamp: base_y should not go below SAFE_AREA_TOP or push text below SAFE_AREA_BOTTOM

3. SPANISH TEXT VISIBILITY:
   - Inactive (upcoming) Spanish words should be slightly visible (not hidden)
   - Change inactive color from (0, 170, 210) to (80, 120, 150) — more subtle, less bright
   - Active word: keep bright cyan (0, 212, 255)
   - Past words (already spoken): dim to (60, 90, 120)

4. ENGLISH WORD HERO SIZE:
   - English words appearing alone (hero mode) are too large at 140px
   - Reduce SIZE_ENGLISH_WORD usage in hero mode: cap at 100px for single words, 80px for phrases
   - In _render_english_hero: if len(text.split()) > 3, use 80px; elif len(text.split()) > 1, use 90px; else use 100px
   - Keep glow effect but reduce glow_radius from 10 to 6

5. TRANSLATION READABILITY:
   - Translation text (Spanish meaning of English phrase) should be more readable
   - Increase SIZE_TRANSLATION rendering from 56 to 48px (smaller but clearer)
   - Color: (200, 200, 220) → (220, 225, 240) — slightly brighter
   - Add a subtle dark text shadow behind translation (offset 2px, alpha 100)

6. OUTLINE REDUCTION:
   - Current outlines are too thick for modern look
   - _render_spanish_karaoke: reduce outline from 5 to 3 for normal words, keep 5 for English words only
   - _render_english_hero: reduce outline from 6 to 4
   - _render_text_simple: reduce outline from 5-6 to 3

IMPORTANT:
- Keep the same function signatures and data flow
- Do NOT modify add_sentence_boundaries() — it works correctly
- Do NOT change the word grouping logic — only the rendering
- The karaoke word-by-word sync must still work correctly
- Test that groups transition smoothly without ghost text
- Make sure text doesn't extend below SAFE_AREA_BOTTOM
```

---

## PROMPT 8 — Register Vocabulary Type in Pipeline

```
I need you to register the new "vocabulary" video type in the project pipeline so it can be generated from the admin dashboard and CLI.

PROJECT CONTEXT:
- New renderer: src/video/vocabulary.py with create_frame_vocabulary(t, data, duration)
- Pipeline entry: src/video/__init__.py (generate_video function)
- CLI: src/video/__init__.py (main function with argparse)
- Script generator: src/script_generator.py
- Admin dashboard: src/admin.py (Streamlit)
- TTS: src/tts_elevenlabs.py

TASK:

1. In src/video/__init__.py:
   - Add import: from .vocabulary import create_frame_vocabulary
   - Add to CLI choices: 'vocabulary' in the --type argument choices list
   - Add elif block in generate_video():
     ```
     elif video_type == 'vocabulary':
         # Resolve timing from segment_times or distribute evenly
         pairs = data.get('pairs', [])
         if not data.get('segment_times'):
             # Auto-distribute: 2s for title, rest split among pairs
             title_end = 2.0
             pair_duration = (duration - title_end) / max(len(pairs), 1)
             segment_times = {'title': {'start': 0.0, 'end': title_end}}
             for i in range(len(pairs)):
                 seg_start = title_end + i * pair_duration
                 seg_end = seg_start + pair_duration
                 segment_times[f'pair_{i}'] = {'start': seg_start, 'end': seg_end}
             data['segment_times'] = segment_times

         def frame_gen(t):
             return create_frame_vocabulary(t, data, duration)
     ```

2. In src/script_generator.py:
   - Add a vocabulary script generation template/function if there's a generate_script function
   - The vocabulary script should produce JSON with: type, title, difficulty, pairs[], full_script
   - full_script for TTS should read like: "Vocabulario en el restaurante. La cuenta, the bill. El mesero, the waiter. ..."
   - Each pair spoken as: "[spanish], [english]."

3. In src/tts_elevenlabs.py (if it has a generate_vocabulary_audio function or similar):
   - Add vocabulary support to the segment audio generation
   - Each pair should be a segment: speak Spanish word, pause, speak English word
   - Use existing generate_segment_audio() with appropriate pauses

IMPORTANT:
- Follow the exact same registration pattern as other video types in generate_video()
- Don't break any existing video types
- The vocabulary type should work with both ffmpeg and moviepy renderers
- If script_generator.py uses GPT/Claude for script generation, add vocabulary to the type options
```

---

## Usage Order

1. **Run Prompt 1 first** — adds shared utilities needed by all other prompts
2. **Run Prompt 7** — fixes educational videos (most used type, quickest win)
3. **Run Prompts 3, 4, 5, 6** in any order — enhances existing video types
4. **Run Prompt 2 then 8** — adds the new vocabulary list type

After each prompt, test by generating a sample video of that type to verify visuals.
