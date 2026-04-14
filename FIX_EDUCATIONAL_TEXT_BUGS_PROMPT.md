# FIX: Educational Video Text Bugs (Words Mixing Between Sentences)

## Prompt for Claude Code

```
CRITICAL BUG: Educational videos have text rendering bugs where words from different sentences overlap/mix together, and sometimes only one word appears on screen. I've diagnosed the exact root causes and need you to fix them.

ROOT CAUSE ANALYSIS:

Problem 1: estimate_word_timestamps() runs on TTS-processed text (after clean_for_tts + add_natural_pauses) which contains "..." pause markers. These become word tokens like "..." that pollute the word list and confuse grouping.

Problem 2: estimate_word_timestamps() does NOT add segment_id or segment_end fields to its word objects. Later, add_sentence_boundaries() in educational.py tries to match these words against the ORIGINAL full_script text — but the words came from the CLEANED text, so the matching fails. All words end up with segment_id=0, meaning group_words() treats the ENTIRE script as ONE sentence and never breaks at sentence boundaries.

Problem 3: The segment estimation in estimate_word_timestamps() distributes words across sentences by simple division (words_per_sent = len(words) // len(sentences)), which is mathematically wrong when sentences have different lengths.

FIXES NEEDED (3 changes in 1 file):

FILE: src/tts_elevenlabs.py

FIX 1 — Use the ORIGINAL full_script for word estimation, not the TTS-processed text.

In the CLI section (around lines 1337-1360), the current code does:
```python
text = clean_for_tts(text)          # removes ___,  markdown
# ... generates audio with text ...
est_words, est_segments = estimate_word_timestamps(text, duration, english_phrases)
```

The problem is that `text` at this point has been modified by clean_for_tts(). And generate_segment_audio() internally also calls add_natural_pauses() which adds "..." markers. But estimate_word_timestamps should use the ORIGINAL full_script text (before cleaning), because the video renderer will also use the original full_script for sentence boundary detection.

Change the code to:
```python
text = script_data.get('full_script', '')
if not text:
    print(f"Script missing 'full_script' for type '{video_type}'")
    import sys; sys.exit(1)
tts_text = clean_for_tts(text)  # cleaned version for TTS only
english_words = extract_english_words_from_script(script_data)
duration = generate_segment_audio(
    tts_text, args.output, voice_id=args.voice,
    segment_type='explanation', english_words=english_words,
)
english_phrases = script_data.get('english_phrases', [])
# Use the ORIGINAL text for word estimation (NOT tts_text)
est_words, est_segments = estimate_word_timestamps(text, duration, english_phrases)
```

FIX 2 — Rewrite estimate_word_timestamps() to properly create sentence-aware words.

Replace the entire function with this improved version:

```python
def estimate_word_timestamps(text: str, duration: float, english_phrases: list = None) -> tuple:
    """
    Estimate word-level timestamps from text and audio duration.

    Properly splits by sentences first, then distributes words proportionally
    within each sentence. Each word gets segment_id and segment_end fields
    that match what add_sentence_boundaries() would produce.
    """
    if not text or not text.strip():
        return [], []

    # Build english set for is_english detection
    english_set = set()
    if english_phrases:
        for phrase in english_phrases:
            for w in phrase.lower().split():
                english_set.add(re.sub(r'[^\w]', '', w))

    # Split text into sentences using punctuation
    # Keep the punctuation attached to the sentence
    sentence_pattern = r'(?<=[.!?])\s+|\s+(?=[¿¡])'
    sentences = [s.strip() for s in re.split(sentence_pattern, text.strip()) if s.strip()]

    if not sentences:
        sentences = [text.strip()]

    # Count total characters across all sentences for proportional timing
    sentence_word_lists = []
    total_chars = 0
    for sent in sentences:
        sent_words = sent.split()
        sentence_word_lists.append(sent_words)
        for w in sent_words:
            total_chars += len(w) + 1  # +1 for space

    if total_chars == 0:
        return [], []

    # Distribute time proportionally across sentences
    buffer = 0.15
    usable = max(0.5, duration - 2 * buffer)

    words = []
    segments = []
    current_time = buffer

    for sent_idx, (sentence, sent_words) in enumerate(zip(sentences, sentence_word_lists)):
        if not sent_words:
            continue

        # Calculate this sentence's share of total time
        sent_chars = sum(len(w) + 1 for w in sent_words)
        sent_duration = (sent_chars / total_chars) * usable

        # Distribute time within this sentence proportionally
        sent_char_total = sum(len(w) + 1 for w in sent_words)
        word_time = current_time
        sent_start = current_time

        for word_idx, raw_word in enumerate(sent_words):
            # Filter out "..." pause markers that might have leaked in
            stripped = raw_word.strip('.,!?¿¡:;\'"')
            if stripped == '...' or stripped == '..' or not stripped:
                continue

            word_dur = ((len(raw_word) + 1) / sent_char_total) * sent_duration
            word_dur = max(0.08, word_dur)  # minimum 80ms per word

            is_last_word = (word_idx == len(sent_words) - 1)
            word_clean = re.sub(r'[^\w]', '', raw_word).lower()

            words.append({
                'word': raw_word,
                'start': round(word_time, 3),
                'end': round(word_time + word_dur, 3),
                'is_english': word_clean in english_set,
                'segment_id': sent_idx,
                'segment_end': is_last_word,
            })
            word_time += word_dur

        sent_end = word_time
        segments.append({
            'start': round(sent_start, 3),
            'end': round(sent_end, 3),
            'text': sentence,
        })
        current_time = sent_end

    logger.info("Estimated %d word timestamps and %d segments from %.2fs audio",
                len(words), len(segments), duration)
    return words, segments
```

KEY DIFFERENCES from the old version:
1. Splits into sentences FIRST, then distributes words within each sentence
2. Each word gets proper segment_id (sentence index) and segment_end fields
3. Filters out "..." pause markers that shouldn't become word tokens
4. Proportional time allocation per sentence (longer sentences get more time)
5. Uses the same sentence splitting regex as add_sentence_boundaries()

FIX 3 — Make add_sentence_boundaries() handle pre-tagged words gracefully.

In src/video/educational.py, the function add_sentence_boundaries() (lines 38-91) already has a guard at line 43:
```python
if words[0].get('segment_id') is not None:
    return words
```

This should work — if estimate_word_timestamps now adds segment_id, this function will skip re-processing. But verify this guard exists and is correct.

ALSO verify in src/video/__init__.py that the data merge in admin.py (line 280-282) doesn't accidentally overwrite 'words' from TTS data with empty words from script_data. The current code:
```python
for key, value in script_data.items():
    if key not in tts_data or key != 'words':
        tts_data[key] = value
```

This logic has a subtle bug: `key not in tts_data or key != 'words'` is almost always True (it's True whenever key != 'words', regardless of whether key is in tts_data). This means script_data keys ALWAYS overwrite tts_data keys EXCEPT for 'words'. That's actually the intended behavior — protect 'words' from being overwritten. But it should also protect 'segments'. Fix the condition to:
```python
for key, value in script_data.items():
    if key not in ('words', 'segments', 'duration', 'segment_times'):
        tts_data[key] = value
```

This ensures TTS-generated timing data is never overwritten by the original script data.

TESTING:
After applying these fixes, generate an educational video from the dashboard. The video should:
1. Show text appearing sentence by sentence (not all at once)
2. Words within a sentence highlight one by one in sync with audio
3. When a sentence ends, it fades out before the next one appears
4. English words (in quotes in the script) should appear highlighted in gold/cyan
5. No ghost text from previous sentences should remain visible

IMPORTANT:
- Only modify estimate_word_timestamps() in tts_elevenlabs.py and the data merge in admin.py
- Do NOT change SubtitleProcessor.group_words() — it works correctly when given proper segment_id values
- Do NOT change the educational.py renderer — it works correctly when given proper groups
- Do NOT change quiz, true_false, fill_blank, pronunciation — they are not affected
```
