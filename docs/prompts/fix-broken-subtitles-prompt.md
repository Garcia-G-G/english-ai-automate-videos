# URGENT FIX: Video Subtitle System is Completely Broken

## Project Location
`~/Documents/english-ai-videos/`

## The Problem (see attached screenshots)
The current video output is unusable. Here's what's happening:

**Screenshot evidence:**
1. "Podrías decir I" — Spanish and English mixed in same group (WRONG)
2. "have" — Single word isolated (looks choppy)
3. "a problem" — Shows in BLUE but it's English, should be YELLOW
4. "with the" — Shows in YELLOW but these aren't the teaching words
5. "Wi Fi" — Split into two words with space (should be "WiFi")

## Root Causes to Fix

### CAUSE 1: Word grouping is broken
The `group_words()` function in `video.py` (~line 2065) fails to respect sentence boundaries. It groups "Podrías decir" with "I" even though "I" starts a new English sentence.

**FIX:** Rewrite `group_words()` with this logic:
```
1. NEVER mix words from different sentences
2. If previous word ends with . ! ? → BREAK before next word
3. If current word is English and previous was Spanish → BREAK
4. If current word is Spanish and previous was English → BREAK
5. Max 4-5 words per group
```

### CAUSE 2: English word detection is wrong
Words like "a", "the", "with" are being marked as English (yellow) when they shouldn't be highlighted. Only the TEACHING words should be yellow.

The `english_phrases` list from the script should be the ONLY words highlighted in yellow. Common words like articles and prepositions should stay in the default color (cyan/blue).

**FIX:** In `create_frame_educational()`:
```python
# WRONG - currently marking ALL English words
is_english = word.get('is_english', False)

# RIGHT - only mark words that are in the explicit teaching list
teaching_words = set(w.lower() for phrase in data.get('english_phrases', []) for w in phrase.split())
is_teaching_word = word['word'].lower().strip('.,!?') in teaching_words
```

### CAUSE 3: Sentence boundary detection fails
The `add_sentence_boundaries()` function (~line 1918) uses fuzzy matching that breaks on common words. When Whisper transcribes slightly different from the script, the matching fails.

**FIX:** Don't rely on fuzzy matching. Use punctuation in the TTS output JSON directly:
```python
# The TTS already knows where sentences end - use that data
# Look for 'segment_times' or 'segments' in the JSON data
# Each segment = one sentence
```

### CAUSE 4: "WiFi" split into "Wi Fi"
The word tokenization is splitting compound words. 

**FIX:** In the text processing, preserve compound words:
```python
# Don't split on internal capitals or known compounds
compounds = {'WiFi', 'iPhone', 'YouTube', 'McDonald', ...}
```

## What I Need You To Do

### Step 1: Understand the data flow
Read these files and trace how words flow through the system:
- `src/tts_openai.py` — How does it generate word timestamps?
- `src/video.py` — `add_sentence_boundaries()`, `group_words()`, `create_frame_educational()`

### Step 2: Fix the word grouping (MOST IMPORTANT)
Rewrite `group_words()` to be simple and strict:
```python
def group_words(words, max_per_group=4):
    """
    Simple word grouping that NEVER crosses sentence boundaries.
    """
    groups = []
    current = []
    
    for word in words:
        # HARD BREAK: sentence ended
        if current and current[-1]['word'].rstrip().endswith(('.', '!', '?')):
            groups.append(current)
            current = []
        
        # HARD BREAK: language switch
        if current:
            prev_english = current[-1].get('is_english', False)
            curr_english = word.get('is_english', False)
            if prev_english != curr_english:
                groups.append(current)
                current = []
        
        # HARD BREAK: max words reached
        if len(current) >= max_per_group:
            groups.append(current)
            current = []
        
        current.append(word)
    
    if current:
        groups.append(current)
    
    return groups
```

### Step 3: Fix English word highlighting
Only highlight the TEACHING words, not every English word:
```python
# In create_frame_educational() or wherever colors are assigned
teaching_words = set()
for phrase in data.get('english_phrases', []):
    for w in phrase.lower().split():
        teaching_words.add(w.strip('.,!?"\\''))

# When rendering:
word_lower = word['word'].lower().strip('.,!?"\\'')
is_teaching_word = word_lower in teaching_words
color = YELLOW if is_teaching_word else CYAN
```

### Step 4: Test with this specific sentence
Use this test case to verify your fix works:
```
Script: "Podrías decir 'I have a problem with the WiFi' cuando tienes problemas de conexión."
English phrases: ["I have a problem with the WiFi"]

Expected groups:
1. "Podrías decir" (cyan)
2. "I have a problem" (yellow - teaching phrase)
3. "with the WiFi" (yellow - teaching phrase) 
4. "cuando tienes" (cyan)
5. "problemas de conexión." (cyan)

NOT:
- "Podrías decir I" ← WRONG, mixes languages
- "have" alone ← WRONG, too isolated
- "Wi Fi" ← WRONG, should be "WiFi"
```

### Step 5: Generate a test video and verify
```bash
cd ~/Documents/english-ai-videos
python src/main.py generate --type educational --topic "WiFi problems"
# Watch the video and check:
# - No mixed language groups
# - Teaching words in yellow
# - Common words in cyan
# - No split compound words
```

## Success Criteria
- [ ] "Podrías decir" and "I have..." are in SEPARATE groups
- [ ] Only "I have a problem with the WiFi" is yellow (the teaching phrase)
- [ ] "cuando tienes problemas de conexión" is cyan
- [ ] "WiFi" is one word, not "Wi Fi"
- [ ] Sentence boundaries are respected (no mixing sentences)

## DO NOT
- Do not just add more parameters to existing broken functions
- Do not try to "tune" the fuzzy matching
- Do not make the code more complex

## DO
- Rewrite the broken functions with simple, strict logic
- Test after each change
- Keep iterating until the test case works perfectly
