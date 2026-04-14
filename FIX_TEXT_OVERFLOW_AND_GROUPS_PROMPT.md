# FIX: Text Overflow, Font Size, Group Size, and Translations

## Prompt for Claude Code

```
CRITICAL VISUAL BUGS in educational videos. The text overflows the screen, groups are too long mixing Spanish and English in huge blocks, translations don't show, and the font is way too big. Here are the exact issues with measurements.

MEASUREMENTS (tested with actual Inter-Bold.ttf font on 1080x1920 canvas):
- Usable text width: 860px (1080 - 2*80 margins - 60 padding)
- At 90px font: "estás puedes decir I'm lost" (27 chars) = 1178px → OVERFLOW +318px
- At 70px font: same text = 916px → OVERFLOW +56px
- At 56px font: same text = 733px → FITS ✓
- At 90px font: "Y si dudas de tu ruta pregunta Am I going the right way" = 2401px → 3 lines
- At 56px font: same text = 1494px → 2 lines (much better)

REAL DATA: In 4 recent educational videos, 35 out of 135 groups (26%) have text that overflows at 90px font. The worst case has 55 characters requiring 3 lines at 90px.

FOUR FIXES NEEDED:

═══════════════════════════════════════════
FIX 1 — DYNAMIC FONT SIZE (most important)
═══════════════════════════════════════════
File: src/video/educational.py

Replace the static `base_size = SIZE_MAIN_SPANISH` (90px) with dynamic sizing based on group text length. The function fit_text_font() already exists in utils.py.

In _render_group_tiktok(), replace line 154:
```python
base_size = SIZE_MAIN_SPANISH
```

With:
```python
# Dynamic font size based on text length — max 2 lines
max_w = TEXT_AREA_WIDTH - 60
max_h = int((SAFE_AREA_BOTTOM - SAFE_AREA_TOP) * 0.4)  # Max 40% of safe area for text

from .utils import fit_text_font
_, base_size, _, _ = fit_text_font(text, SIZE_MAIN_SPANISH, 42, max_w, max_h)

# Ensure minimum readability
base_size = max(42, min(SIZE_MAIN_SPANISH, base_size))
```

This makes the font automatically shrink for longer groups (90px for short, down to 42px for very long text). The text should fit in max 2 lines.

Also, in _render_spanish_karaoke, the English words use `int(base_size * ENGLISH_WORD_SCALE)` (1.20x). When base_size is already 90, the English words render at 108px which makes them overflow even more. Add a cap:

At line 260, change:
```python
word_font_size = int(base_size * ENGLISH_WORD_SCALE)
```
To:
```python
word_font_size = min(int(base_size * ENGLISH_WORD_SCALE), base_size + 10)
```

This caps the English word size at base_size + 10px instead of 1.2x.

═══════════════════════════════════════════
FIX 2 — REDUCE MAX WORDS PER GROUP
═══════════════════════════════════════════
File: src/animations/subtitle_processor.py

The SubtitleProcessor defaults to max_words_per_group=5, but groups with 5 Spanish words + 3-4 English words end up with 8+ words that overflow. The real data shows groups like "Y si dudas de tu ruta pregunta Am I going the right way" (13 words!) because the English phrase gets absorbed into the Spanish group.

Change the max_words default:
```python
def __init__(self, gap_threshold: float = 0.35, max_words_per_group: int = 4):
```

This reduces from 5 to 4, creating shorter, more readable groups.

ALSO: In group_words() after line 310 where en_group is appended, add a post-processing step to split English groups that are too large. After `groups.append(en_group)`, the current code doesn't check if the combined Spanish+English text is too long.

The real fix is: when English words follow Spanish words, ALWAYS start a new group for the English phrase. Don't include trailing Spanish words with the English phrase. The current code at lines 289-295 includes orphaned single Spanish words WITH the English group. This creates monster groups like "sin paid vacation," or "ruta pregunta Am I going the right way".

Change lines 289-301 back to always separate:
```python
            if is_en:
                if current:
                    groups.append(current)
                    current = []
                    current_segment = None
                en_group = []
```

This ensures English phrases are ALWAYS their own group, separate from Spanish text. The "sin" single-word issue is less important than the overflow issue.

═══════════════════════════════════════════
FIX 3 — SHOW TRANSLATION FOR ALL ENGLISH GROUPS
═══════════════════════════════════════════
File: src/video/educational.py

The translation lookup in _render_spanish_karaoke (lines 321-342) only finds translations when the EXACT English phrase matches. But Whisper or the estimator often produces slightly different word forms.

Improve the lookup with fuzzy matching:

Replace lines 324-326:
```python
        en_words_text = ' '.join(w['word'] for w in words if w.get('is_english', False))
        en_clean = re.sub(r'[^\w\s-]', '', en_words_text).strip().lower()
        trans = translations.get(en_clean, "")
```

With:
```python
        en_words_text = ' '.join(w['word'] for w in words if w.get('is_english', False))
        en_clean = re.sub(r'[^\w\s-]', '', en_words_text).strip().lower()

        # Direct lookup first
        trans = translations.get(en_clean, "")

        # Fuzzy: try each translation key as substring
        if not trans:
            for key, value in (translations or {}).items():
                key_clean = key.lower().strip()
                if key_clean in en_clean or en_clean in key_clean:
                    trans = value
                    break

        # Fuzzy: try individual English words
        if not trans:
            for w in words:
                if w.get('is_english', False):
                    w_clean = re.sub(r'[^\w\s-]', '', w['word']).strip().lower()
                    if w_clean in (translations or {}):
                        trans = translations[w_clean]
                        break
```

Apply the same improved lookup in _render_english_hero (around line 372).

═══════════════════════════════════════════
FIX 4 — ENGLISH/SPANISH TEXT COLOR DISTINCTION
═══════════════════════════════════════════
File: src/video/educational.py

Currently ALL words in a group render in the same gold/yellow color (ENGLISH_WORD_COLOR) when they're English. But when Spanish and English words are in the same group, we need visual separation.

The current _render_spanish_karaoke already handles this — English words get ENGLISH_WORD_COLOR (gold) and Spanish words get _SPANISH_ACTIVE (cyan). This is correct. But the issue is that ALL words show as the same color when the group is all-English because is_english=True for all words.

No code change needed for this — just verify it works after fixes 1-3.

═══════════════════════════════════════════
SUMMARY OF CHANGES:
═══════════════════════════════════════════
1. educational.py: Dynamic font size using fit_text_font (90px→42px based on text length)
2. educational.py: Cap English word font at base_size + 10px
3. subtitle_processor.py: Reduce max_words from 5 to 4
4. subtitle_processor.py: Always separate English groups from Spanish (revert orphan merge)
5. educational.py: Fuzzy translation matching (substring + individual word lookup)

IMPORTANT:
- Do NOT change the SubtitleProcessor.group_words() segment boundary logic — it works
- Do NOT change line_break() — it works correctly for wrapping
- The fit_text_font function is already available in src/video/utils.py
- Test with "getting lost" video which has the worst overflow (55 char groups)
- After fix, text should always fit within the 860px area with max 2-3 lines
- Font sizes should range from 42px (long groups) to 90px (short groups)
```
