#!/usr/bin/env python3
"""Bilingual TTS segmenter — splits a mixed ES/EN script into ordered
language-tagged segments so each one can be synthesized with the correct
accent (Spanish narration in native Latin-American Spanish, English
teaching words with an authentic English accent).

Why this exists
---------------
The old pipeline sent the WHOLE full_script (Spanish with embedded English
words) in a single ElevenLabs call.  The model picks ONE dominant language
/ accent for the whole utterance, so Spanish narration came out with a
gringo accent (or the English words came out hispanicized).  The fix is to
split the text into per-language segments and synthesize each with an
explicit ``language_code``.

Source of truth for what is English
-----------------------------------
1. Script metadata (``english_phrases``, ``translations`` keys, ``word``,
   ``pairs[].english``, quiz options for "cómo se dice") — these are the
   target teaching terms and always win.
2. Single-quoted spans in the text (the scripts consistently quote English
   material) classified with a conservative looks-English heuristic.
3. A light heuristic for stray unquoted English words.

Public API
----------
    collect_english_terms(script_data) -> List[str]
    segment_text(text, english_terms, narration_lang="es") -> List[dict]
    segment_script(script_data, narration_lang="es") -> List[dict]

Each segment is ``{"text": str, "lang": "es"|"en", "pause_after": float}``.
``pause_after`` is a stitching hint derived from trailing punctuation.
"""

import re
from dataclasses import dataclass
from typing import Dict, List
from tts_common import SPANISH_FILTER  # canonical Spanish stoplist

# Spanish words that AI-generated english_phrases sometimes contain by
# mistake — never treat these single words as English.
# Was a local 129-word fork of the Spanish stoplist. All five
# copies are now one canonical 275-word set in tts_common, whose
# comment records why. ADD WORDS THERE, never here.
_SPANISH_COMMON = SPANISH_FILTER

_SPANISH_CHARS = set('áéíóúñüÁÉÍÓÚÑÜ¿¡')

# High-signal English function words for the heuristic classifier.
_EN_HINTS = {
    'the', 'of', 'to', 'and', 'in', 'is', 'are', 'was', 'were', 'you',
    'your', 'my', 'i', 'it', 'this', 'that', 'do', 'does', 'did', "don't",
    'not', 'have', 'has', 'had', 'with', 'for', 'on', 'at', 'by', 'up',
    'out', 'off', 'we', 'they', 'he', 'she', 'him', 'her', 'me', 'a', 'an',
    'be', 'been', 'but', 'so', 'get', 'got', 'go', 'going', 'want',
    'wanted', 'can', "can't", 'will', 'would', 'should', 'could', 'let',
    "let's", 'am', 'what', 'how', 'when', 'where', 'why', 'who',
}

# Spanish function words that mark a token as clearly Spanish.
_ES_HINTS = _SPANISH_COMMON | {
    'hola', 'gracias', 'porque', 'aunque', 'después', 'antes', 'durante',
    'sabías', 'escucha', 'atención', 'inglés', 'español',
}

_EN_SUFFIXES = ('ing', 'ght', 'tion', 'ck', 'sh', ' th', 'oo', 'ee',
                'ould', 'ay', 'ey', 'ow', 'aw', "'s", "n't", 'ed')


@dataclass(frozen=True)
class LanguagePolicy:
    """One explicit native-narration and English-teaching language pair."""

    native_language: str
    narration_code: str
    english_code: str = "en"


LANGUAGE_POLICIES = {
    "es": LanguagePolicy("es", "es"),
    "zh-Hans": LanguagePolicy("zh-Hans", "zh"),
}


def _resolve_policy(narration_lang: str, language_policy) -> LanguagePolicy:
    if language_policy is not None:
        if not isinstance(language_policy, LanguagePolicy):
            raise ValueError("invalid language policy")
        return language_policy
    if narration_lang != "es":
        raise ValueError(
            "non-Spanish narration requires an explicit language policy"
        )
    return LANGUAGE_POLICIES["es"]


def looks_english(text: str) -> bool:
    """Conservative classifier: does this short span look like English?

    Used only for quoted spans / stray tokens NOT covered by script
    metadata.  Anything with Spanish orthography is immediately Spanish.
    """
    text = (text or "").strip()
    if not text:
        return False
    if any(c in _SPANISH_CHARS for c in text):
        return False

    tokens = [re.sub(r"[^\w']", '', t).lower() for t in text.split()]
    tokens = [t for t in tokens if t]
    if not tokens:
        return False

    score = 0.0
    for t in tokens:
        if t in _EN_HINTS:
            score += 2.0
            continue
        if t in _ES_HINTS:
            score -= 2.0
            continue
        if "'" in t:                       # don't, it's, let's
            score += 1.5
        if any(t.endswith(s) for s in _EN_SUFFIXES):
            score += 1.0
        if re.search(r'[kw]', t) and not re.search(r'^(kilo|watt)', t):
            score += 0.6                   # k/w are rare in Spanish
        if re.search(r'(ea|ou|au|gh|sh|th|ck|wh|ph)', t):
            score += 0.6
        if t.endswith(('ción', 'dad', 'mente', 'ar', 'er')) and len(t) > 4:
            score -= 0.8
    return score > 0


def _clean_term(term: str) -> str:
    return (term or "").strip().strip("'\"“”‘’").strip()


def collect_english_terms(script_data: Dict) -> List[str]:
    """Extract the canonical English teaching terms from script metadata.

    These are the ONLY spans forced to lang="en" regardless of heuristics.
    Returned longest-first so multi-word phrases match before their parts.
    """
    raw: List[str] = []

    for phrase in script_data.get('english_phrases') or []:
        if isinstance(phrase, str):
            raw.append(phrase)

    for key in (script_data.get('translations') or {}):
        raw.append(key)

    word = script_data.get('word')
    if isinstance(word, str):
        raw.append(word)

    for pair in script_data.get('pairs') or []:
        if isinstance(pair, dict) and pair.get('english'):
            raw.append(str(pair['english']))

    for ex in script_data.get('examples') or []:
        if isinstance(ex, str):
            raw.append(ex)
        elif isinstance(ex, dict):
            for k in ('en', 'english', 'sentence'):
                if ex.get(k):
                    raw.append(str(ex[k]))

    # Quiz "cómo se dice X" — the correct option is English.
    question = (script_data.get('question') or '').lower()
    if 'se dice' in question:
        options = script_data.get('options') or {}
        correct = script_data.get('correct')
        if isinstance(options, dict) and correct in options:
            raw.append(str(options[correct]))

    terms: List[str] = []
    seen = set()
    for term in raw:
        term = _clean_term(term)
        if not term or len(term) < 2:
            continue
        # Reject terms with Spanish orthography — bad AI metadata.
        if any(c in _SPANISH_CHARS for c in term):
            continue
        # Reject single common Spanish words that leaked into metadata.
        words = term.lower().split()
        if len(words) == 1 and words[0].strip(".,!?'-") in _SPANISH_COMMON:
            continue
        # Reject very long "phrases" only if they don't look English at all
        if len(words) > 8 and not looks_english(term):
            continue
        key = term.lower()
        if key not in seen:
            seen.add(key)
            terms.append(term)

    terms.sort(key=len, reverse=True)
    return terms


def _pause_for(chunk: str) -> float:
    """Stitching gap suggested by the trailing punctuation of a chunk."""
    tail = chunk.rstrip()[-1:] if chunk.rstrip() else ''
    if tail in '.!?':
        return 0.18
    if tail in ',;:':
        return 0.08
    return 0.03


def _term_pattern(term: str) -> str:
    """Regex for a term with non-letter boundaries (handles '-ed', "let's").

    Tokens are joined with a whitespace/quote class so metadata phrases
    still match when the script nests quotes inside them, e.g. the term
    "Let's hang out" matches the text "Let's 'hang out'".
    """
    tokens = [re.escape(t) for t in term.split()]
    body = r"[\s'’‘\"“”]+".join(tokens) if tokens else re.escape(term)
    return r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9])"


# Ambiguous tokens shared by both languages — never absorbed on their own.
_EN_SAFE_HINTS = _EN_HINTS - {'a', 'me', 'no', 'he', 'la'}
_MAX_ABSORB = 4


def _absorbable(tok: str, chained: bool) -> bool:
    """Can this unquoted token be pulled into a neighboring EN span?"""
    if any(c in _SPANISH_CHARS for c in tok):
        return False
    low = tok.lower()
    if low in _ES_HINTS:
        return False
    if low in _EN_SAFE_HINTS or looks_english(tok):
        return True
    # Chain rule: right after a confirmed English token, a plain ASCII
    # word that is not a known Spanish word keeps the phrase together
    # ("with friends", "this weekend").
    return chained and low.isascii() and low.isalpha()


def _extend_en_spans(text: str, spans: list) -> list:
    """Absorb adjacent English words into EN spans (nested-quote rescue).

    Scripts often wrap whole English example sentences in quotes but only
    the inner term is in the metadata ("como en 'I was 'hanging out' with
    friends'"). This pass walks outward from each EN span over unquoted
    tokens that clearly look English, so 'I was' / 'with friends' get the
    English accent too.
    """
    if not spans:
        return spans
    tokens = [(m.start(), m.end(), m.group(0))
              for m in re.finditer(r"[A-Za-z][A-Za-z'’]*", text)]
    spans = sorted(spans)
    out = []
    for idx, (s, e, lang) in enumerate(spans):
        if lang != 'en':
            out.append((s, e, lang))
            continue
        prev_end = out[-1][1] if out else 0
        next_start = spans[idx + 1][0] if idx + 1 < len(spans) else len(text)

        # Forward absorption
        after = [t for t in tokens if t[0] >= e and t[1] <= next_start]
        chained, taken = False, 0
        for ts, te, tok in after:
            gap = text[e:ts]
            if re.search(r"[.!?;:]", gap) or taken >= _MAX_ABSORB:
                break
            if not _absorbable(tok, chained):
                break
            e, chained, taken = te, True, taken + 1

        # Backward absorption
        before = [t for t in tokens if t[1] <= s and t[0] >= prev_end]
        chained, taken = False, 0
        for ts, te, tok in reversed(before):
            gap = text[te:s]
            if re.search(r"[.!?;:,]", gap) or taken >= _MAX_ABSORB:
                break
            if not _absorbable(tok, chained):
                break
            s, chained, taken = ts, True, taken + 1

        out.append((s, e, 'en'))

    # Merge overlapping/adjacent EN spans created by the extension.
    merged = []
    for span in sorted(out):
        if merged and span[2] == merged[-1][2] and span[0] <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], span[1]), span[2])
        else:
            merged.append(list(span))
    return [tuple(x) for x in merged]


def segment_text(text: str, english_terms: List[str],
                 narration_lang: str = "es", *,
                 language_policy: LanguagePolicy = None) -> List[Dict]:
    """Split ``text`` into ordered {text, lang, pause_after} segments.

    Priority: metadata terms > quoted spans (heuristic) > narration lang.
    English words embedded in a Spanish sentence become their own segment.
    """
    policy = _resolve_policy(narration_lang, language_policy)
    narration_lang = policy.narration_code
    text = (text or "").strip()
    if not text:
        return []

    # 1. Collect EN spans from metadata terms (longest-first, no overlaps).
    spans: List[tuple] = []   # (start, end, lang)

    def _overlaps(s: int, e: int) -> bool:
        return any(not (e <= a or s >= b) for a, b, _ in spans)

    for term in sorted(english_terms or [], key=len, reverse=True):
        try:
            pat = re.compile(_term_pattern(term), re.IGNORECASE)
        except re.error:
            continue
        for m in pat.finditer(text):
            if not _overlaps(m.start(), m.end()):
                spans.append((m.start(), m.end(), 'en'))

    # 2. Quoted spans not already covered — classify heuristically.
    for m in re.finditer(r"'([^']{1,80})'", text):
        s, e = m.start(1), m.end(1)
        if _overlaps(s, e):
            continue
        inner = m.group(1)
        lang = 'en' if looks_english(inner) else narration_lang
        if lang == 'en':
            spans.append((s, e, 'en'))

    spans.sort()
    spans = _extend_en_spans(text, spans)

    if language_policy is not None:
        return _policy_segments(text, spans, policy)

    # 3. Build the ordered segment list.
    segments: List[Dict] = []

    def _push(chunk: str, lang: str) -> None:
        stripped = chunk.strip()
        if not stripped:
            return
        # Punctuation-only chunk: attach to previous segment's text so the
        # voice keeps natural sentence prosody.
        if not re.search(r'\w', stripped):
            if segments:
                segments[-1]['text'] += stripped
                segments[-1]['pause_after'] = _pause_for(stripped)
            return
        # Strip wrapping quotes — they confuse TTS and are visual-only.
        stripped = stripped.strip("'\"“”‘’")
        if not stripped:
            return
        if segments and segments[-1]['lang'] == lang:
            segments[-1]['text'] += ' ' + stripped
            segments[-1]['pause_after'] = _pause_for(stripped)
        else:
            segments.append({'text': stripped, 'lang': lang,
                             'pause_after': _pause_for(stripped)})

    def _push_between(chunk: str) -> None:
        """Push an ES chunk, attaching its LEADING punctuation ("., '?")
        to the previous (usually EN) segment so prosody stays natural."""
        m = re.match(r"^[\s'\"“”‘’.,;:!?…)\]]+", chunk)
        if m and segments:
            lead = m.group(0).strip().strip("'\"“”‘’")
            if lead:
                segments[-1]['text'] += lead
                segments[-1]['pause_after'] = _pause_for(lead)
            chunk = chunk[m.end():]
        _push(chunk, narration_lang)

    cursor = 0
    for s, e, lang in spans:
        _push_between(text[cursor:s])
        _push(text[s:e], lang)
        cursor = e
    _push_between(text[cursor:])

    # 4. Punctuation right after a span boundary may have been split into
    # the following ES chunk (handled by _push).  Final cleanup: merge
    # adjacent same-lang segments (safety) and drop empties.
    merged: List[Dict] = []
    for seg in segments:
        # Drop stray quote marks (visual-only) but keep real apostrophes
        # between letters ("Let's", "don't").
        seg['text'] = re.sub(r"(?<![A-Za-z])['\"“”‘’]|['\"“”‘’](?![A-Za-z])",
                             '', seg['text'])
        seg['text'] = re.sub(r'\s+', ' ', seg['text']).strip()
        if not seg['text']:
            continue
        if merged and merged[-1]['lang'] == seg['lang']:
            merged[-1]['text'] += ' ' + seg['text']
            merged[-1]['pause_after'] = seg['pause_after']
        else:
            merged.append(seg)
    return merged


#: Marks that CLOSE a clause and therefore belong to the chunk they end.
#:
#: DELIBERATELY EXCLUDES ¿ AND ¡. Spanish opens a question or an
#: exclamation with them and they must stay at the head of their own chunk.
#: A fix that ate those would be worse than the bug it fixes, so they are
#: absent here and a test asserts it.
#:
#: Quote characters ARE included, and that took a measurement to settle.
#: The English spans are matched INSIDE their quotes, so the Spanish chunk
#: after one begins with the term's own CLOSING quote and only then the
#: full stop — "'. Este verbo…". Excluding quotes stopped the scan on that
#: first character and the period never moved. A leading quote on a
#: non-first chunk is always a closer, because an opening quote sits at the
#: END of the chunk before the span. Moving it is harmless either way:
#: wrapping quotes are stripped from the spoken text a few lines below.
_CLOSING_MARKS = ".,;:!?…)]»'\"“”’"


def _reclaim_closing_marks(text: str, pieces: list) -> list:
    """Move a chunk's LEADING closing punctuation back onto its predecessor.

    THE DEFECT. Chunks are cut at the boundaries of the English spans
    inside a sentence, so the Spanish chunk that follows an English term
    begins at the character right after it — which is the full stop that
    ENDED that sentence. The narration then carried chunks like
    ".Este verbo es muy útil", and because the mark led the chunk it also
    led the card the karaoke drew.

    Four of 92 segments in one render opened this way: '.Este verbo…',
    '.Por ejemplo…', '.Un tip para recordar…', '.Excelente,'.

    Fixed HERE rather than in the word timeline. Merging a leading mark
    backwards at timeline level would stretch the previous word's declared
    end across the gap between two TTS clips, which re-creates the timing
    defect that the declared-silence work removed. A chunk boundary has no
    such cost: nothing has been synthesised yet, so moving the character
    moves the audio with it.

    Boundaries stay CONTIGUOUS and lossless — every character of `text`
    still belongs to exactly one piece, so source_start/source_end remain a
    faithful map back onto the script.
    """
    adjusted = []
    for start, end, lang in pieces:
        while adjusted and start < end and (
                text[start] in _CLOSING_MARKS or text[start].isspace()):
            # Whitespace moves too, so the mark does not end up orphaned
            # from its sentence by a stray leading space.
            previous_start, _previous_end, previous_lang = adjusted[-1]
            adjusted[-1] = (previous_start, start + 1, previous_lang)
            start += 1
        if start < end:
            adjusted.append((start, end, lang))
    return adjusted


def _policy_segments(text: str, spans: list, policy: LanguagePolicy) -> List[Dict]:
    """Build a lossless source plan while keeping cleaned text for TTS."""
    pieces = []
    cursor = 0
    for start, end, _ in spans:
        if cursor < start:
            pieces.append((cursor, start, policy.narration_code))
        pieces.append((start, end, policy.english_code))
        cursor = end
    if cursor < len(text):
        pieces.append((cursor, len(text), policy.narration_code))

    merged = []
    for start, end, lang in pieces:
        if start == end:
            continue
        if merged and merged[-1][2] == lang and merged[-1][1] == start:
            merged[-1] = (merged[-1][0], end, lang)
        else:
            merged.append((start, end, lang))

    # A chunk must END with its own closing punctuation and must not BEGIN
    # with someone else's.
    merged = _reclaim_closing_marks(text, merged)

    result = []
    for index, (start, end, lang) in enumerate(merged):
        source = text[start:end]
        spoken = re.sub(r'\s+', ' ', source).strip().strip("'\"“”‘’")
        # Drop quote marks that are NOT between letters, so a closing quote
        # reclaimed from the next chunk does not reach the voice as
        # "show up'." while "didn't" and "Let's" keep their apostrophes.
        # Same expression the non-policy path has always used.
        spoken = re.sub(r"(?<![A-Za-z])['\"“”‘’]|['\"“”‘’](?![A-Za-z])",
                        '', spoken).strip()
        if not spoken:
            spoken = source
        result.append({
            "index": index,
            "text": spoken,
            "lang": lang,
            "pause_after": _pause_for(source),
            "source_text": source,
            "source_start": start,
            "source_end": end,
        })
    return result


def segment_script(script_data: Dict, narration_lang: str = "es", *,
                   language_policy: LanguagePolicy = None) -> List[Dict]:
    """Segment a script's ``full_script`` using its own metadata terms."""
    try:
        from tts_common import clean_for_tts
    except ImportError:          # standalone use
        clean_for_tts = lambda t: t  # noqa: E731
    text = clean_for_tts(script_data.get('full_script', '') or '')
    terms = collect_english_terms(script_data)
    return segment_text(
        text,
        terms,
        narration_lang,
        language_policy=language_policy,
    )


def describe_segments(segments: List[Dict]) -> str:
    """Human-readable table of segments (for logs / dry-run)."""
    lines = [f"{'#':>3}  {'lang':4}  {'pause':>5}  text"]
    for i, seg in enumerate(segments):
        lines.append(f"{i:>3}  {seg['lang']:4}  {seg['pause_after']:>5.2f}  "
                     f"{seg['text']}")
    return "\n".join(lines)
