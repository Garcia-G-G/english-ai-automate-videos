"""
Subtitle processor for word grouping and timing.

Handles:
- Word-level timestamp estimation from TTS segments
- Intelligent word grouping with sentence boundary respect
- English/Spanish word detection
- Overlap resolution and seamless transitions
"""

from typing import List, Dict, Optional


def clean_word_for_display(word: str) -> str:
    """
    Clean a word for display - remove stray quotes, fix spacing.

    Fixes: "'Pick" -> "Pick", "up'" -> "up", "ropa'." -> "ropa."
    Preserves: internal apostrophes "don't" -> "don't"
    """
    if not word:
        return word

    # Remove leading quotes
    while word and word[0] in "'\"`":
        word = word[1:]

    # Remove trailing quotes (preserve punctuation after)
    result = []
    i = 0
    while i < len(word):
        char = word[i]
        if char in "'\"`":
            remaining = word[i+1:]
            if not remaining or all(c in '.,!?;:' for c in remaining):
                i += 1
                continue
        result.append(char)
        i += 1

    return ''.join(result)


class SubtitleProcessor:
    """
    Processes TTS output into display-ready word groups.

    Handles segment boundaries, English word detection,
    intelligent grouping, and overlap resolution.
    """

    # Spanish connector words that shouldn't start a new group
    CONNECTORS = {'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del',
                  'en', 'con', 'por', 'para', 'que', 'se', 'no', 'es',
                  'muy', 'más', 'o', 'y', 'a', 'al', 'su', 'sus'}

    # Words that typically start a new phrase
    STARTERS = {'sabías', 'muchos', 'en', 'por', 'si', 'recuerda',
                'conocías', 'cuéntame'}

    def __init__(self, gap_threshold: float = 0.35, max_words_per_group: int = 5):
        self.gap_threshold = gap_threshold
        self.max_words = max_words_per_group

    def estimate_words_from_segments(
        self,
        segments: List[Dict],
        english_phrases: List[str] = None
    ) -> List[Dict]:
        """
        Estimate word-level timestamps from segment timestamps.

        Args:
            segments: List of segments with 'text', 'start', 'end'
            english_phrases: List of English words/phrases to detect

        Returns:
            List of word dicts with 'start', 'end', 'word', 'is_english', 'segment_id'
        """
        if not segments:
            return []

        # Build set of English words
        english_set = set()
        if english_phrases:
            for phrase in english_phrases:
                for word in phrase.lower().split():
                    cleaned = word.strip('.,!?¿¡:;\'"')
                    if cleaned:
                        english_set.add(cleaned)

        words = []

        for seg_idx, seg in enumerate(segments):
            text = seg.get('text', '')
            seg_start = seg.get('start', 0)
            seg_end = seg.get('end', seg_start + 1)
            seg_duration = seg_end - seg_start

            seg_words = text.split()
            if not seg_words:
                continue

            total_chars = sum(len(w) for w in seg_words)
            if total_chars == 0:
                total_chars = len(seg_words)

            current_time = seg_start

            for word_idx, raw_word in enumerate(seg_words):
                display_word = clean_word_for_display(raw_word)

                word_duration = seg_duration * (len(raw_word) / total_chars)
                word_duration = max(0.1, min(word_duration, 1.5))

                word_end = min(current_time + word_duration, seg_end)

                clean_for_lookup = display_word.lower().strip('.,!?¿¡:;')
                is_english = clean_for_lookup in english_set

                if not display_word.strip():
                    current_time = word_end
                    continue

                is_segment_end = (word_idx == len(seg_words) - 1)

                words.append({
                    'word': display_word,
                    'start': current_time,
                    'end': word_end,
                    'is_english': is_english,
                    'segment_id': seg_idx,
                    'segment_end': is_segment_end
                })

                current_time = word_end

        return words

    def group_words(self, words: List[Dict]) -> List[Dict]:
        """
        Group words into display phrases.

        CRITICAL: Never mix words from different segments (sentences).
        """
        if not words:
            return []

        groups = []
        current = []
        current_segment = None
        i = 0

        while i < len(words):
            w = words[i]
            text = w['word']
            lower = text.lower().strip('.,!?¿¡')
            is_en = w.get('is_english', False)
            word_segment = w.get('segment_id', 0)
            is_segment_end = w.get('segment_end', False)

            # CRITICAL: Check for segment boundary FIRST
            if current and current_segment is not None and word_segment != current_segment:
                groups.append(current)
                current = []
                current_segment = None

            if is_en:
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

            should_break = False

            if current:
                prev = current[-1]
                gap = w['start'] - prev['end']
                prev_text = prev['word']

                if gap > self.gap_threshold:
                    should_break = True
                if prev_text.rstrip().endswith(('.', '!', '?', ':')):
                    should_break = True
                if prev.get('segment_end', False):
                    should_break = True
                if text and text[0].isupper() and lower in self.STARTERS:
                    should_break = True
                if len(current) >= self.max_words and lower not in self.CONNECTORS:
                    should_break = True

            if should_break:
                groups.append(current)
                current = []

            current.append(w)
            current_segment = word_segment
            i += 1

        if current:
            groups.append(current)

        result = []
        for g in groups:
            if not g:
                continue

            start = g[0]['start']
            end = g[-1]['end']

            if end <= start:
                end = start + 0.033

            has_en = any(x.get('is_english', False) for x in g)

            cleaned_words = []
            for w in g:
                cleaned = clean_word_for_display(w['word'])
                if cleaned:
                    cleaned_words.append(cleaned)
                    w['word'] = cleaned

            text = ' '.join(cleaned_words)

            result.append({
                'words': g,
                'text': text,
                'start': start,
                'end': end,
                'english': has_en,
            })

        # Fix overlaps
        result.sort(key=lambda x: (x['start'], 0 if x['english'] else 1))

        filtered = []
        for i, g in enumerate(result):
            if i == 0:
                filtered.append(g)
                continue

            prev = filtered[-1]
            if g['start'] < prev['end'] - 0.01:
                if prev['english'] and not g['english']:
                    g['start'] = prev['end']
                    if g['end'] <= g['start']:
                        g['end'] = g['start'] + 0.5
                    filtered.append(g)
                elif g['english'] and not prev['english']:
                    filtered[-1] = g
                    prev['start'] = g['end']
                    if prev['end'] <= prev['start']:
                        prev['end'] = prev['start'] + 0.5
                    filtered.append(prev)
                else:
                    if g['end'] - g['start'] > prev['end'] - prev['start']:
                        filtered[-1] = g
                continue

            filtered.append(g)

        result = filtered

        # Fix end times for seamless transitions
        for i in range(len(result)):
            if i < len(result) - 1:
                next_start = result[i + 1]['start']
                if result[i]['end'] > next_start:
                    result[i]['end'] = next_start
                if result[i]['end'] <= result[i]['start']:
                    result[i]['end'] = result[i]['start'] + 0.033

        return result
