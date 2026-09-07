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
from tts_common import SPANISH_FILTER  # canonical Spanish stoplist
import logging

logger = logging.getLogger(__name__)

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

    #: Clause boundaries a forced split may land on. A split anywhere else
    #: cuts mid-clause, which is the thing being removed.
    SPLIT_AFTER = (',', ';', ':')
    SPLIT_BEFORE = ('y', 'o', 'pero', 'porque', 'que', 'cuando', 'si',
                    'aunque', 'mientras', 'para')

    #: LINES, not words, and this is the unit that matters.
    #:
    #: A card is a wall because of how many LINES it occupies, not how many
    #: words it holds — "Supercalifragilistico" is one word and three lines.
    #: Lines are also what the reader experiences.
    #:
    #: A word ceiling could not see this at all. The card holds ten lines at
    #: 90px, so every sentence up to ten renders at full size and never
    #: appears in a font distribution: 78 declared sentences, 19% of the
    #: corpus, are six lines or more and shipped untouched — only six of
    #: them ever had to shrink. And the 40-word ceiling was unreachable,
    #: because the longest declared sentence in the corpus is 36 words, so
    #: _clause_split was built, tested and never executed on real content.
    #:
    #: 4 is measured rather than felt. Over 405 declared sentences:
    #:     2 lines splits 65%     3 lines splits 50%
    #:     4 lines splits 34%     5 lines splits 19%
    #: Below 4 the corpus re-fragments even though every cut is legal.
    MAX_LINES_PER_GROUP = 4

    def __init__(self, gap_threshold: float = 0.35, max_words_per_group: int = 40,
                 max_lines_per_group: int = None):
        """
        max_words_per_group is a LAST-RESORT CEILING, not the primary rule.

        It was 8, and it was the primary rule: an ordinary nine-word
        sentence — "Hoy vamos a aprender el phrasal verb show up." — was cut
        because nine is more than eight. Measured on one real timeline, 8 of
        26 groups (31%) either ended on a comma or cut mid-phrase.

        A group is a SENTENCE now, taken from the declared segment
        boundaries the timeline already carries. This number only decides
        what happens to a sentence with no internal boundary at all, and it
        is set from measurement rather than taste: across 405 declared
        sentences in the corpus the longest is 36 words, which fits the card
        at 80px over 12 lines. 40 leaves headroom above that and still bounds
        the pathological case.
        """
        self.gap_threshold = gap_threshold
        self.max_words = max_words_per_group
        self.max_lines = (self.MAX_LINES_PER_GROUP if max_lines_per_group is None
                          else max_lines_per_group)

    @staticmethod
    def _count_lines(text: str) -> int:
        """Lines this text occupies in the card, AT FULL SIZE.

        AT FULL SIZE IS THE WHOLE POINT. A long sentence that shrinks to
        80px fits more lines into the same card, so measuring after the fit
        would loosen the ceiling exactly where the text is longest — the
        gate would relax on the sentences it exists to catch. The fit's job
        is fitting; this decides whether the text should have been one card
        at all, and it decides once, before any fit runs.

        Imported lazily: video.utils imports animations.easing, which loads
        animations/__init__, which imports this module. A top-level import
        here would close that loop.
        """
        from config.layout import CARD_PADDING, CARD_WIDTH
        from video.constants import SIZE_MAIN_SPANISH
        from video.utils import font, line_break

        width = CARD_WIDTH - CARD_PADDING * 2 - 40
        return len(line_break(text, font(SIZE_MAIN_SPANISH), width))

    def _split_to_line_budget(self, words):
        """One declared sentence -> one or more cards of at most max_lines.

        Splits repeatedly, so a thirteen-line sentence becomes four cards
        rather than one oversized card and a remainder.
        """
        out, run = [], list(words)
        while run:
            text = " ".join(str(w.get("word", "")) for w in run)
            if self._count_lines(text) <= self.max_lines or len(run) < 2:
                out.append(run)
                break
            cut, kind = self._best_split(run)
            if cut is None or cut >= len(run):
                logger.warning(
                    "subtitle group occupies %d lines and has no clause "
                    "boundary to split on; left whole: %r",
                    self._count_lines(text), text[:80])
                out.append(run)
                break
            head, run = run[:cut], run[cut:]

            # THE CARD MUST NOT END ON A COMMA — on ANY split, not only a
            # comma split. A "before" split lands in front of a conjunction,
            # and the word before that conjunction very often already
            # carries a comma: "…count to five, que significa…" split before
            # "que" still left a card reading "Hoy aprenderemos a count to
            # five,". Checked in the output, not reasoned about.
            #
            # The mark stays in the narration and in the timing; it is only
            # not DRAWN at a card edge, where it carries no information the
            # break does not already carry. Garcia: "hay una coma cerrando
            # una oracion, eso deberia ser un punto".
            trimmed = str(head[-1].get("word", "")).rstrip()
            if trimmed.endswith((",", ";", ":")):
                last = dict(head[-1])
                last["word"] = trimmed.rstrip(",;:")
                head = head[:-1] + [last]
            out.append(head)
        return [r for r in out if r]

    def _best_split(self, words):
        """The latest boundary whose HEAD still fits the line budget.

        _clause_split returns the last boundary in the run, which makes the
        head as long as possible — and a head can be over budget while the
        tail is under it. Measured on the corpus, taking the last boundary
        blindly left 45 cards above four lines: the loop re-checked the tail
        it kept and never re-checked the head it had already emitted.

        So candidates are walked from latest to earliest and the first head
        that fits is taken. If none fits, the EARLIEST boundary is used —
        the smallest head — and the loop gets another go at what remains,
        which terminates because the run strictly shrinks.
        """
        candidates = []
        for index in range(len(words) - 1, 0, -1):
            token = str(words[index].get("word", "")).lower().strip(".,!?¿¡")
            if token in self.SPLIT_BEFORE:
                candidates.append((index, "before"))
        for index in range(len(words) - 1, 0, -1):
            previous = str(words[index - 1].get("word", "")).rstrip()
            if previous.endswith(self.SPLIT_AFTER):
                candidates.append((index, "after"))
        if not candidates:
            return None, "none"

        for index, kind in candidates:
            head = " ".join(str(w.get("word", "")) for w in words[:index])
            if self._count_lines(head) <= self.max_lines:
                return index, kind
        return min(candidates)[0], min(candidates)[1]

    def _clause_split(self, words):
        """Index to break at inside an over-long run, or None.

        Prefers the LAST clause boundary in the run, so the fragment that
        ships is as long as it can be while still reading as language. A run
        with no boundary returns None and is left whole — a mid-clause cut
        is worse than a card that is too full, and the caller reports it.
        """
        # A CONJUNCTION IS PREFERRED OVER A LATER COMMA. Scanning for the
        # first boundary of either kind put 50 of 136 cards on a comma;
        # preferring the conjunction moves that to 25, and rule 2 in
        # _split_to_line_budget takes the rest to zero. A card ending on a
        # whole word before 'y' or 'pero' reads as a continuation; one
        # ending on a comma reads as a cut.
        for index in range(len(words) - 1, 0, -1):
            token = str(words[index].get('word', '')).lower().strip('.,!?¿¡')
            if token in self.SPLIT_BEFORE:
                return index, 'before'
        for index in range(len(words) - 1, 0, -1):
            previous = str(words[index - 1].get('word', '')).rstrip()
            if previous.endswith(self.SPLIT_AFTER):
                return index, 'after'
        return None, 'none'

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
        # Was a local 220-word fork of the Spanish stoplist. All five
        # copies are now one canonical 275-word set in tts_common, whose
        # comment records why. ADD WORDS THERE, never here.
        SPANISH_COMMON = SPANISH_FILTER
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

        # DOES THIS TIMELINE DECLARE ITS SENTENCES?
        #
        # add_sentence_boundaries stamps segment_id on every word, and where
        # it has run the sentence is not a guess — it is recorded. A group
        # is then exactly one segment, and none of the heuristics below get
        # to cut inside it: not a 0.35s pause, not a capitalised starter,
        # not a word count, and not an English phrase in the middle of a
        # Spanish clause. That last one is what produced "Empezamos con
        # one," / "que significa uno." out of a single sentence.
        #
        # Older sidecars carry no segment_id — 28 of 51 in the corpus do —
        # and they keep the previous behaviour exactly, because inventing
        # sentence boundaries for a timeline that never declared any is how
        # this file got its heuristics in the first place.
        declares_sentences = any('segment_id' in w for w in words)

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
                # A completed sentence goes through the LINE budget: one
                # card if it fits, otherwise split at clause boundaries.
                groups.extend(self._split_to_line_budget(current)
                              if declares_sentences else [current])
                current = []
                current_segment = None

            if is_en and not declares_sentences:
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

                if declares_sentences:
                    # ONE GROUP PER DECLARED SENTENCE, and the sentence is
                    # segment_id — handled by the boundary check at the top
                    # of this loop, which is why nothing here breaks.
                    #
                    # NOT segment_end. The two disagree in older sidecars:
                    # pull_vs_pool sets segment_end at word 7 of a 10-word
                    # segment, so breaking on it split one declared sentence
                    # into two groups and produced a card reading 'y pool'.
                    # The id is the record; the flag is a hint that has
                    # drifted from it.
                    #
                    # NOTHING BREAKS HERE. The sentence is emitted whole at
                    # its segment boundary and the LINE budget decides how
                    # many cards it becomes — measured in the card, at full
                    # size, once. The old word ceiling of 40 survives only
                    # as a parameter for callers that ask for it; it never
                    # fired on real content, because the longest declared
                    # sentence in the corpus is 36 words.
                    pass
                else:
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
            groups.extend(self._split_to_line_budget(current)
                          if declares_sentences else [current])

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

            # NO CARD ENDS ON A COMMA. The split path already avoids
            # creating one, but a DECLARED sentence can itself end on a
            # comma — 11 do in the corpus, e.g. "Ahora es tu turno," — and
            # a card is a card whether the break was ours or the
            # segmenter's. The mark stays in the narration and in the
            # timing; it is only not drawn at a card edge.
            if text.rstrip().endswith((',', ';', ':')):
                text = text.rstrip().rstrip(',;:')

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

        # NOTE: this used to trim each group's `end` to make room for the next
        # one — `end = next_start - min_gap/2`, then `next_start - 0.033`.
        #
        # That mutation was removed, and it is a real cause of the reported
        # "animation runs ahead of the voice": it moved a group's end EARLIER
        # whenever two groups were close, so the text vanished while the audio
        # was still speaking its last word. Worse, it edited AUDIO timestamps
        # in order to solve a DISPLAY problem, which meant every later
        # consumer inherited a group whose `end` no longer described the
        # sound.
        #
        # Display windows are now owned by video/v2/timing_engine.py, which
        # derives display_start / display_end from these timestamps without
        # modifying them and enforces the golden rule (never leave the screen
        # before the last word ends + 350 ms). Overlapping or degenerate group
        # timings are handled there; that is why nothing replaces this block.
        return result
