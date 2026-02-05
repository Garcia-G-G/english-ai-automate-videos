# FIX ALL VIDEO BUGS — Educational + Quiz/Test Videos

## Project
`~/Documents/english-ai-videos/`

## Read first
Before making any changes, read and understand:
```bash
cat src/video.py          # Main video rendering
cat src/tts_openai.py     # TTS and word timestamps
cat src/main.py           # Entry point, video types
```

---

# BUG GROUP A: Quiz/Test Videos

## Bug A1: Question text overlaps answer buttons
**Screenshot evidence:** "until next week" is cut off — the question text runs into the answer option buttons.

**Root cause:** The layout doesn't calculate total height of question text + buttons before positioning. The question text wraps to too many lines and collides with the button grid.

**Fix approach:**
1. Find the quiz/test frame rendering function (likely `create_frame_quiz()` or similar)
2. Calculate the question text height FIRST (measure wrapped text)
3. Position buttons BELOW the text with guaranteed gap (at least 40px)
4. If text is too long, reduce font size dynamically until it fits above buttons
5. The question area should occupy top 40% of screen, buttons middle 35%, countdown bottom 25%

```python
# Pseudocode for layout fix
SCREEN_W, SCREEN_H = 1080, 1920

# Question zone: top 40%
question_zone_bottom = int(SCREEN_H * 0.40)

# Buttons zone: 40% to 75%  
buttons_zone_top = int(SCREEN_H * 0.42)
buttons_zone_bottom = int(SCREEN_H * 0.72)

# Countdown zone: bottom 25%
countdown_zone_top = int(SCREEN_H * 0.75)

# Measure question text, shrink font if needed
font_size = 72
while True:
    wrapped = wrap_text(question, font_size, max_width=SCREEN_W - 100)
    text_height = len(wrapped) * (font_size * 1.3)
    if text_height < (question_zone_bottom - 80) or font_size <= 40:
        break
    font_size -= 4

# Draw question centered in question zone
# Draw 2x2 button grid in buttons zone
# Draw countdown in countdown zone
```

## Bug A2: Audio plays BEFORE animation
**Problem:** The TTS audio says the countdown number and question BEFORE the visual animation shows it. Audio leads video by ~0.5-1 second.

**Root cause:** The audio timestamps are not aligned with frame generation. Either:
- Audio is placed too early in the timeline
- Frame rendering doesn't account for audio onset timing
- The countdown timer audio plays at t=0 but animation starts at t=0.5

**Fix approach:**
1. Find where audio segments are placed on the timeline for quiz videos
2. Find where visual countdown/question animations are triggered
3. Make sure: `audio_start_time == animation_start_time`
4. If anything, visual should lead audio by ~50-100ms (feels more natural for video)

```python
# When placing countdown audio:
countdown_audio_start = question_end_time + pause_duration

# When rendering countdown frames:
countdown_visual_start = countdown_audio_start - 0.05  # Visual 50ms BEFORE audio

# NOT:
# countdown_visual_start = countdown_audio_start + 0.5  # This is the bug
```

5. Check if MoviePy's `set_start()` or audio composition is adding unintended offset
6. Test: Play the video and check that "3" appears on screen RIGHT WHEN audio says "three"

## Bug A3: TTS says wrong words
**Problem:** Sometimes the TTS mispronounces or says different words than what's on screen.

**Possible causes:**
1. Text sent to TTS doesn't match text displayed on screen
2. Special characters or formatting (underscores, brackets) confuse TTS
3. The question template has "___" (blank) which TTS might try to read

**Fix approach:**
1. Find where quiz text is sent to TTS
2. Clean the text before sending to TTS:
```python
def clean_for_tts(text: str) -> str:
    """Clean text for TTS - remove visual-only elements."""
    # Remove blanks (visual only)
    text = text.replace('___', '')
    text = text.replace('__', '')
    text = text.replace('_', ' ')
    
    # Remove multiple spaces
    text = ' '.join(text.split())
    
    # Remove formatting characters
    text = text.replace('*', '')
    text = text.replace('#', '')
    
    return text.strip()
```
3. Compare: print both `display_text` and `tts_text` to verify they make sense
4. For the question "In my opinion, we should ___ the meeting until next week":
   - Display: "In my opinion, we should ___ the meeting until next week"
   - TTS should say: "In my opinion, we should blank the meeting until next week" (or just skip the blank)

---

# BUG GROUP B: Educational Videos (Subtitle System)

## Bug B1: Mixed language groups
**Screenshot:** "Podrías decir I" — Spanish and English in same group

**Fix:** Rewrite `group_words()`:
```python
def group_words(words, max_words=4):
    """Group words. Rules: never mix sentences, never mix languages."""
    groups = []
    current = []
    
    for word in words:
        # Break after sentence-ending punctuation
        if current:
            prev = current[-1]['word'].rstrip()
            if prev.endswith(('.', '!', '?', ':')):
                groups.append(make_group(current))
                current = []
        
        # Break on language change
        if current:
            if current[-1].get('is_english', False) != word.get('is_english', False):
                groups.append(make_group(current))
                current = []
        
        # Break on max words
        if len(current) >= max_words:
            groups.append(make_group(current))
            current = []
        
        current.append(word)
    
    if current:
        groups.append(make_group(current))
    return groups

def make_group(words):
    return {
        'words': words,
        'text': ' '.join(w['word'] for w in words),
        'start': words[0]['start'],
        'end': words[-1]['end'],
        'english': any(w.get('is_english') for w in words),
    }
```

## Bug B2: Wrong words highlighted yellow
**Screenshot:** "with the" in yellow, "a problem" in blue

**Fix:** Only mark TEACHING words as English:
```python
# Build teaching word set from english_phrases
teaching_words = set()
for phrase in data.get('english_phrases', []):
    for w in phrase.lower().split():
        teaching_words.add(w.strip('.,!?"\\'()[]:;'))

# Mark words
for word in words:
    clean = word['word'].lower().strip('.,!?"\\'()[]:;')
    word['is_english'] = clean in teaching_words
```

## Bug B3: "WiFi" split into "Wi Fi"
**Fix:** Preserve compound words in tokenization:
```python
COMPOUNDS = {'WiFi', 'iPhone', 'YouTube', 'WhatsApp', 'Facebook', 'Instagram', 'TikTok'}

def preserve_compounds(text):
    for compound in COMPOUNDS:
        text = text.replace(compound, compound.replace(' ', '\x00'))
    words = text.split()
    return [w.replace('\x00', '') for w in words]
```

---

# EXECUTION ORDER

## Phase 1: Fix Quiz Videos (most visible bugs)
1. Fix layout — question text must NOT overlap buttons
2. Fix audio sync — visual and audio must be synchronized
3. Fix TTS text — clean blanks/special chars before sending to TTS
4. Generate test quiz video, verify all 3 fixes

## Phase 2: Fix Educational Videos
5. Rewrite `group_words()` with strict rules
6. Fix `is_english` marking to only flag teaching words
7. Fix compound word splitting
8. Generate test educational video, verify all 3 fixes

## Phase 3: Verify Both
9. Generate one quiz video and one educational video
10. Watch both completely
11. Confirm:
    - [ ] Quiz: text doesn't overlap buttons
    - [ ] Quiz: audio matches visual timing
    - [ ] Quiz: TTS says correct words
    - [ ] Educational: no mixed-language groups
    - [ ] Educational: only teaching words are yellow
    - [ ] Educational: compound words preserved

## Testing commands
```bash
cd ~/Documents/english-ai-videos

# Test quiz video
python src/main.py generate --type quiz --topic "business meetings"

# Test educational video  
python src/main.py generate --type educational --topic "WiFi connection problems"
```

## Rules
- REWRITE broken functions, don't add workarounds
- TEST after each fix
- ITERATE until all checkboxes pass
- If something doesn't work after 3 attempts, try a completely different approach
