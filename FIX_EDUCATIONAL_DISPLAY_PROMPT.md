# FIX: Educational Video Display — English Words Isolated, Missing Translations, Sync Issues

## Prompt for Claude Code

```
BUGS IN EDUCATIONAL VIDEO RENDERER: I have 5 specific bugs to fix in the educational video display. Here is the exact diagnosis with real data from generated videos.

PROJECT FILES:
- src/video/educational.py — frame renderer (main file to modify)
- src/animations/subtitle_processor.py — word grouping logic (needs one small fix)
- src/video/constants.py, src/config/typography.py — constants

REAL EXAMPLE DATA (video: "work-life balance expectations"):
The full_script contains Spanish text with English phrases in quotes like 'work-life balance' and 'paid vacation'.
The translations dict is: {"work-life balance": "equilibrio entre trabajo y vida personal", "paid vacation": "vacaciones pagadas"}

The SubtitleProcessor groups words into 34 groups. The problematic groups are:
- Group 3: text="work-life balance." english=True (shown as giant hero text ALONE)
- Group 6: text="work-life balance" english=True (shown as giant hero text ALONE)
- Group 11: text="sin" english=False (just the word "sin" alone — looks terrible)
- Group 12: text="paid vacation," english=True (shown as giant hero text ALONE)

BUG 1 — ENGLISH PHRASES SHOWN AS ISOLATED HERO TEXT
Currently, when a group is English (group['english']=True), _render_group_tiktok routes to _render_english_hero() which shows the English text in HUGE font (80-100px) centered on screen, with no Spanish context around it. This looks bad — the viewer sees "work-life balance." for 1.5 seconds with no context, then it disappears.

FIX: Instead of showing English phrases as isolated hero text, show them INLINE with the surrounding Spanish text. The English words should be highlighted (gold color, slightly larger, with glow) but within the context of their sentence.

In _render_group_tiktok (line 182-187), change the routing logic:

OLD:
```python
if words and not is_en:
    _render_spanish_karaoke(...)
elif is_en:
    _render_english_hero(...)
else:
    _render_text_simple(...)
```

NEW:
```python
if words:
    # Always use karaoke renderer — it handles English words inline via is_english flag
    _render_spanish_karaoke(t, words, start, end, group_alpha, draw, frame, cur_y, base_size, is_fading_out)
elif is_en:
    # Fallback for English groups without word-level data
    _render_english_hero(t, text, start, end, group_alpha, draw, frame, cur_y, translations, is_fading_out)
else:
    _render_text_simple(t, text, start, end, group_alpha, draw, frame, cur_y, base_size, is_en, is_fading_out)
```

BUT ALSO: modify _render_spanish_karaoke to show the translation below the text when the group contains English words. After the word rendering loop (after line 319 "cur_y += line_h"), add:

```python
# Show translation below if group contains English words
has_english = any(w.get('is_english', False) for w in words)
if has_english and translations:
    # Find the English phrase in this group
    en_words_text = ' '.join(w['word'] for w in words if w.get('is_english', False))
    # Strip punctuation for lookup
    import re
    en_clean = re.sub(r'[^\w\s-]', '', en_words_text).strip().lower()
    trans = translations.get(en_clean, "")
    if trans:
        cur_y += 20  # gap
        tf = font(_TRANS_SIZE)
        trans_text = f"({trans})"
        trans_lines = line_break(trans_text, tf, TEXT_AREA_WIDTH - 100)
        trans_line_h = int(_TRANS_SIZE * 1.3)
        for tline in trans_lines:
            bbox = draw.textbbox((0, 0), tline, font=tf)
            tw = bbox[2] - bbox[0]
            tx = (VIDEO_WIDTH - tw) // 2
            # Shadow for readability
            draw_text_solid(draw, tline, tx + 2, cur_y + 2, tf,
                            (0, 0, 0), int(group_alpha * 0.4), outline=0)
            draw_text_solid(draw, tline, tx, cur_y, tf,
                            _TRANS_COLOR, int(group_alpha * 0.9), outline=2)
            cur_y += trans_line_h
```

You'll need to add these imports at the top of _render_spanish_karaoke:
- Access to `translations` — add it as a parameter
- Access to `_TRANS_SIZE`, `_TRANS_COLOR`, `VIDEO_WIDTH`, `TEXT_AREA_WIDTH`

Update the function signature:
```python
def _render_spanish_karaoke(t, words, group_start, group_end, group_alpha, draw, frame, base_y, base_size, is_fading_out, translations=None):
```

And update the call in _render_group_tiktok to pass translations:
```python
_render_spanish_karaoke(t, words, start, end, group_alpha, draw, frame, cur_y, base_size, is_fading_out, translations=translations)
```

BUG 2 — TRANSLATION LOOKUP FAILS DUE TO PUNCTUATION
In _render_english_hero line 372, the translation lookup is:
```python
trans = translations.get(text.lower().strip(), "")
```

But the group text includes punctuation: "work-life balance." or "paid vacation," — so the lookup fails.

FIX: Strip punctuation before looking up:
```python
import re
lookup = re.sub(r'[^\w\s-]', '', text).strip().lower()
trans = translations.get(lookup, "")
```

Apply this same fix in _render_english_hero (line 372).

BUG 3 — SINGLE WORD "sin" SHOWN ALONE
The SubtitleProcessor.group_words() function breaks groups when it encounters English words (lines 289-305). This causes the Spanish word immediately before an English phrase to get orphaned as a tiny group. Example: "...a menudo sin 'paid vacation'" — "sin" ends up as its own group because the English words after it force a break.

FIX in src/animations/subtitle_processor.py:
In group_words(), at line 289 where English words cause a break, don't flush the current Spanish group if it only has 1 word. Instead, include the orphan word in the English group:

Replace the English isolation block (lines 289-305):
```python
if is_en:
    # Don't orphan single Spanish words before English phrases
    # Include trailing connectors in the English group
    if current and len(current) <= 1:
        # Single word like "sin" — include it with the English group
        en_group = list(current)
        current = []
        current_segment = None
    else:
        if current:
            groups.append(current)
            current = []
            current_segment = None
        en_group = []

    en_segment = word_segment
    while i < len(words) and words[i].get('is_english', False):
        if words[i].get('segment_id', 0) != en_segment:
            break
        en_group.append(words[i])
        if words[i].get('segment_end', False):
            i += 1
            break
        i += 1
    groups.append(en_group)
    continue
```

This way "sin paid vacation," becomes one group instead of "sin" alone + "paid vacation," alone.

BUG 4 — BASE FONT SIZE FOR ENGLISH GROUPS TOO LARGE
When _render_group_tiktok handles English groups, it sets base_size to _english_hero_size() which returns 80-100px. But for Spanish karaoke rendering (which we're now using for English groups too per Bug 1 fix), the base size should stay at SIZE_MAIN_SPANISH (90px) and only the English words within should be slightly larger.

FIX: In _render_group_tiktok, always use SIZE_MAIN_SPANISH as base_size. Remove the conditional:

OLD (line 154-157):
```python
if is_en:
    base_size = _english_hero_size(text)
else:
    base_size = SIZE_MAIN_SPANISH
```

NEW:
```python
base_size = SIZE_MAIN_SPANISH
```

The English words within the karaoke renderer already get ENGLISH_WORD_SCALE (1.20x) applied at line 257, so they'll be 108px (90*1.2) which is appropriately larger but not absurdly big.

BUG 5 — GROUP TEXT HEIGHT CALCULATION WRONG FOR MIXED GROUPS
When the group has both Spanish and English words, the total_h calculation (line 163) uses base_size for line height. But since English words have ENGLISH_WORD_SCALE applied, the actual rendered height can be taller. This causes the centering to be off.

FIX: After calculating total_h, add a buffer for mixed groups:
```python
total_h = len(lines) * line_h

# Add buffer for translation if group has English words
has_en_words = any(w.get('is_english', False) for w in words) if words else is_en
if has_en_words and translations:
    en_text = ' '.join(w['word'] for w in words if w.get('is_english', False)) if words else text
    import re
    en_clean = re.sub(r'[^\w\s-]', '', en_text).strip().lower()
    trans_text = translations.get(en_clean, "")
    if trans_text:
        tf = font(_TRANS_SIZE)
        trans_lines_count = len(line_break(f"({trans_text})", tf, TEXT_AREA_WIDTH - 100))
        total_h += trans_lines_count * int(_TRANS_SIZE * 1.3) + 20
```

SUMMARY OF CHANGES:
1. educational.py: Route ALL groups with words to _render_spanish_karaoke (not just non-English)
2. educational.py: Add translation display in _render_spanish_karaoke for groups with English words
3. educational.py: Fix translation lookup to strip punctuation before matching
4. educational.py: Always use SIZE_MAIN_SPANISH as base_size (remove hero size for English)
5. educational.py: Fix height calculation for mixed groups
6. subtitle_processor.py: Don't orphan single Spanish words before English phrases

IMPORTANT:
- Do NOT change the group_words logic for non-English word breaks (gap threshold, max words, connectors, starters) — those work correctly
- Do NOT change the _render_english_hero function itself — keep it as fallback for groups without word data
- Do NOT change any other video type renderer (quiz, true_false, fill_blank, pronunciation)
- The _render_spanish_karaoke function already handles English words inline (lines 254-301 in educational.py) — it renders them in ENGLISH_WORD_COLOR with glow. This is the correct behavior we want for ALL groups
- Test with the work-life balance video to verify: English phrases should appear inline with Spanish text, highlighted in gold with glow, and translations should appear below
```
