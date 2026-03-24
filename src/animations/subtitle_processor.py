"""
Subtitle processor for word grouping and timing.

Handles:
- Word-level timestamp estimation from TTS segments
- Intelligent word grouping with sentence boundary respect
- English/Spanish word detection
- Overlap resolution and seamless transitions
- BBC-style subtitle formatting (max chars/lines)
"""

from typing import List, Dict, Optional

# Constants from TikTok subtitle guide
MIN_GAP_MS = 50              # Minimum gap between words (50ms)
MIN_SUBTITLE_GAP_MS = 250    # Minimum gap between subtitle changes (250ms)
MAX_CHARS_PER_LINE = 40      # BBC guideline
MAX_LINES = 2                # Maximum lines per subtitle


def fix_overlapping_timestamps(words: List[Dict], min_gap_ms: float = MIN_GAP_MS) -> List[Dict]:
    """
    Fix overlapping timestamps by adjusting end times.

    Prevents text overlap when AI-generated timestamps have conflicts.
    """
    if not words or len(words) < 2:
        return words

    for i in range(1, len(words)):
        gap = words[i]["start"] - words[i-1]["end"]
        if gap < min_gap_ms / 1000:
            # Adjust previous word's end time
            words[i-1]["end"] = words[i]["start"] - (min_gap_ms / 1000)
            # Ensure end > start
            if words[i-1]["end"] <= words[i-1]["start"]:
                words[i-1]["end"] = words[i-1]["start"] + 0.05
    return words


def validate_subtitle_text(text: str, max_chars: int = MAX_CHARS_PER_LINE,
                           max_lines: int = MAX_LINES) -> Dict:
    """
    Validate subtitle text against BBC guidelines.

    Returns dict with is_valid, suggested_splits, warnings.
    """
    result = {
        "is_valid": True,
        "warnings": [],
        "suggested_splits": []
    }

    lines = text.split('\n') if '\n' in text else [text]

    if len(lines) > max_lines:
        result["is_valid"] = False
        result["warnings"].append(f"Too many lines: {len(lines)} (max {max_lines})")

    for i, line in enumerate(lines):
        if len(line) > max_chars:
            result["is_valid"] = False
            result["warnings"].append(f"Line {i+1} too long: {len(line)} chars (max {max_chars})")

            # Suggest split point
            words = line.split()
            mid = len(words) // 2
            split1 = ' '.join(words[:mid])
            split2 = ' '.join(words[mid:])
            result["suggested_splits"].append((split1, split2))

    return result


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

    # Compound words that Whisper might split incorrectly
    COMPOUND_WORDS = {
        ('wi', 'fi'): 'WiFi',
        ('wai', 'fai'): 'WiFi',       # Phonetic variant from TTS
        ('why', 'fi'): 'WiFi',        # Whisper may hear it differently
        ('i', 'phone'): 'iPhone',
        ('you', 'tube'): 'YouTube',
        ('face', 'book'): 'Facebook',
        ('whats', 'app'): 'WhatsApp',
        ('tik', 'tok'): 'TikTok',
        ('snap', 'chat'): 'Snapchat',
        ('pay', 'pal'): 'PayPal',
        ('net', 'flix'): 'Netflix',
        ('e', 'mail'): 'email',
        ('blue', 'tooth'): 'Bluetooth',
    }

    def __init__(self, gap_threshold: float = 0.35, max_words_per_group: int = 8):
        self.gap_threshold = gap_threshold
        self.max_words = max_words_per_group

    def merge_compound_words(self, words: List[Dict]) -> List[Dict]:
        """
        Merge compound words that Whisper incorrectly split.

        E.g., "Wi" + "Fi" → "WiFi"
        """
        if not words or len(words) < 2:
            return words

        result = []
        i = 0

        while i < len(words):
            if i < len(words) - 1:
                w1 = words[i]['word'].lower().strip('.,!?')
                w2 = words[i + 1]['word'].lower().strip('.,!?')
                compound_key = (w1, w2)

                if compound_key in self.COMPOUND_WORDS:
                    # Merge the two words
                    merged = {
                        'word': self.COMPOUND_WORDS[compound_key],
                        'start': words[i]['start'],
                        'end': words[i + 1]['end'],
                        'is_english': words[i].get('is_english', False) or words[i + 1].get('is_english', False),
                        'segment_id': words[i].get('segment_id', 0),
                        'segment_end': words[i + 1].get('segment_end', False),
                    }
                    result.append(merged)
                    i += 2
                    continue

            result.append(words[i])
            i += 1

        return result

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
        # Filter: only short phrases (≤5 words) — longer ones are likely bad data
        # Exclude common Spanish words to prevent false positives
        SPANISH_COMMON = {
            'a', 'al', 'algo', 'alguien', 'ante', 'asi', 'así', 'bien', 'bueno',
            'cada', 'casa', 'casi', 'como', 'con', 'cual', 'cuando',
            'de', 'del', 'decir', 'donde', 'el', 'ella', 'en', 'era',
            'es', 'esa', 'ese', 'eso', 'esta', 'estar', 'este', 'esto',
            'forma', 'fue', 'hay', 'hoy', 'ir', 'la', 'las', 'le', 'les',
            'lo', 'los', 'mas', 'más', 'me', 'mi', 'muy', 'nada', 'ni', 'no',
            'nos', 'o', 'otra', 'otro', 'para', 'pero', 'por', 'puede',
            'que', 'qué', 'quien', 'se', 'ser', 'si', 'sin', 'sobre', 'son',
            'su', 'sus', 'tan', 'te', 'ti', 'tiene', 'todo', 'tu', 'tus',
            'un', 'una', 'uno', 'usar', 'usa', 'usan', 'va', 'vamos',
            'ver', 'vez', 'vida', 'y', 'ya', 'yo', 'palabra', 'ejemplo',
            'recuerda', 'cuando', 'veas', 'entonces', 'también', 'tambien', 'ahora',
            'aceptar', 'invitación', 'invitacion', 'divertida', 'casual',
            # Common Spanish words that GPT puts in english_phrases by mistake
            'gusta', 'gusto', 'increíble', 'increible', 'acuerdo', 'decir',
            'puedes', 'puedo', 'quiero', 'significa', 'sigues', 'cierto',
            'verdad', 'falso', 'correcto', 'incorrecto', 'ejemplo',
            'piensa', 'repite', 'respuesta', 'pregunta', 'opción', 'opcion',
            'frase', 'manera', 'lugar', 'momento', 'vez', 'cosa', 'cosas',
            'tipo', 'tipos', 'mundo', 'gente', 'personas', 'tiempo',
            'nuevo', 'nueva', 'mejor', 'peor', 'grande', 'pequeño',
            'buena', 'malo', 'mala', 'mismo', 'misma', 'otro', 'otra',
            'mucho', 'mucha', 'muchos', 'muchas', 'poco', 'poca',
            'siempre', 'nunca', 'solo', 'sólo', 'aquí', 'aqui', 'allí', 'alli',
            'este', 'estos', 'estas', 'ese', 'esos', 'esas',
            'estoy', 'estás', 'estas', 'está', 'estamos', 'están',
            'soy', 'eres', 'somos', 'tengo', 'tienes', 'tenemos', 'tienen',
            'hago', 'haces', 'hace', 'hacemos', 'hacen',
            'digo', 'dices', 'dice', 'dicen', 'decimos',
            'sé', 'sabes', 'sabe', 'sabemos', 'saben', 'sabías', 'sabias',
            'puedo', 'puedes', 'puede', 'podemos', 'pueden',
            'quiero', 'quieres', 'quiere', 'queremos', 'quieren',
            'necesito', 'necesitas', 'necesita', 'necesitamos',
            'creo', 'crees', 'cree', 'creemos',
            'outfit', 'tu',  # 'outfit' is borrowed but used in Spanish context
            'emocionante', 'respondido', 'escribir', 'leer', 'hablar',
            'escuchar', 'entender', 'aprender', 'enseñar', 'practicar',
        }
        english_set = set()
        if english_phrases:
            for phrase in english_phrases:
                phrase_words = phrase.lower().split()
                # Skip phrases with 4+ words — likely full Spanish sentences
                if len(phrase_words) > 3:
                    continue
                for word in phrase_words:
                    cleaned = word.strip('.,!?¿¡:;\'"🔥😱🤯')
                    if cleaned and cleaned not in SPANISH_COMMON and len(cleaned) > 1:
                        # Extra check: reject words with Spanish accents/ñ
                        if any(c in cleaned for c in 'áéíóúñü'):
                            continue
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

        # Fix any overlapping timestamps
        words = fix_overlapping_timestamps(words)

        return words

    def group_words(self, words: List[Dict]) -> List[Dict]:
        """
        Group words into display phrases.

        CRITICAL: Never mix words from different segments (sentences).
        """
        if not words:
            return []

        # Merge compound words first (e.g., "Wi Fi" → "WiFi")
        words = self.merge_compound_words(words)

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
                # Avoid orphan single-word groups before English phrases.
                # Pull last 1-2 Spanish words into the English group if:
                #   - current group has ≤2 words, OR
                #   - last word is a short connector
                prefix_words = []
                if current:
                    if len(current) <= 2:
                        # Small group — merge entirely with English
                        prefix_words = list(current)
                        current = []
                    else:
                        last_word = current[-1]
                        last_lower = last_word['word'].lower().strip('.,!?¿¡')
                        if last_lower in self.CONNECTORS or len(last_lower) <= 4:
                            prefix_words = [current.pop()]
                    if current:
                        groups.append(current)
                    current = []
                    current_segment = None

                en_group = prefix_words
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

        # Fix end times for seamless transitions with minimum gap
        min_gap = MIN_SUBTITLE_GAP_MS / 1000  # 250ms minimum gap

        for i in range(len(result)):
            if i < len(result) - 1:
                next_start = result[i + 1]['start']
                gap = next_start - result[i]['end']

                # If gap is too small, adjust for smooth transition
                if gap < min_gap and gap > 0:
                    # Split the difference - end current slightly early
                    result[i]['end'] = next_start - (min_gap / 2)

                # Fix overlap
                if result[i]['end'] > next_start:
                    result[i]['end'] = next_start - 0.033

                # Ensure valid timing
                if result[i]['end'] <= result[i]['start']:
                    result[i]['end'] = result[i]['start'] + 0.1

        return result
