"""The lesson script — the one format the writer (human or model), the audio
generator and the Manim scene all agree on. Pure Python, no Manim, no network.

    lessons/<id>.json = {
      "id", "title", "kicker", "level", "language": "es", "target_minutes",
      "beats": [ { "id", "type", "narration", ...fields per type } ]
    }

Narration markup
  [[English text]]   an English span: spoken with language_code=en so the
                     accent is right; the brackets are never shown or spoken.
  Everything else is the narration language (Spanish).

Beat types and the fields the scene reads (limits enforced by validate()):
  title     kicker?                         big title card (lesson title or `text`)
  heading   text                            section card, clears the stage
  sentence  text, highlight?{word: color}, tags?{word: label}, fix?{from,to},
            gloss?, same?                   chips per word; `same` keeps the
                                            sentence already on stage and only
                                            applies the new highlight/tags/fix
  dialogue  lines[{speaker, en, es}]        two speakers, bubbles, ≤ 6 lines
  table     headers?, rows[[...]]           ≤ 6 rows × ≤ 3 cols; cells that
                                            match `emphasis` are green
  list      heading?, items[]               ≤ 6 items
  tip       text                            one callout
  quiz      question, options[], answer     ≤ 4 options; reveal on the answer
  recap     items[]                         ≤ 6 checked items
"""
import json
import re
from pathlib import Path

TYPES = {"title", "heading", "sentence", "dialogue", "table", "list", "tip", "quiz", "recap"}
COLORS = {"yellow", "blue", "green", "red"}
LIMITS = {"line": 90, "tip": 170, "cell": 28, "item": 110, "items": 6, "lines": 6, "rows": 6, "cols": 3,
          "options": 4, "narration": 420, "chips": 12}
EN_SPAN = re.compile(r"\[\[(.+?)\]\]", re.S)
PAUSE = re.compile(r"\{\{\s*pause\s*:\s*(\d+(?:\.\d+)?)\s*\}\}")   # {{pause:3}} — silence, in seconds
MAX_PAUSE = 6.0
_SENTINEL = "\x00"


# ── Narration helpers ──────────────────────────────────────────────────────────

def spoken_text(narration: str) -> str:
    """What the listener hears: brackets and pause markers removed, whitespace folded."""
    return " ".join(EN_SPAN.sub(r"\1", PAUSE.sub(" ", narration)).split())


def pauses(narration: str) -> list:
    """Pause lengths in seconds, in order of appearance."""
    return [min(MAX_PAUSE, float(m.group(1))) for m in PAUSE.finditer(narration)]


def segments(narration: str, base_lang: str = "es") -> list:
    """[{text, lang}] and [{pause: seconds}] in order — one TTS call per text segment,
    so every span gets its accent; a pause becomes silence in the stitched audio."""
    out, pos = [], 0
    events = sorted([(m.start(), m.end(), "en", m.group(1)) for m in EN_SPAN.finditer(narration)]
                    + [(m.start(), m.end(), "pause", m.group(1)) for m in PAUSE.finditer(narration)])
    for start, end, kind, value in events:
        before = narration[pos:start].strip()
        if before:
            out.append({"text": before, "lang": base_lang})
        if kind == "en":
            out.append({"text": " ".join(value.split()), "lang": "en"})
        else:
            out.append({"pause": min(MAX_PAUSE, float(value))})
        pos = end
    tail = narration[pos:].strip()
    if tail:
        out.append({"text": tail, "lang": base_lang})
    return out


def tokens(narration: str) -> list:
    """The spoken words with their language and their character offset in spoken_text():
    [{text, en, offset}]. English is what sat inside [[ ]]; offsets are what the word
    timings (voices.word_boundaries) are expressed in."""
    marked = EN_SPAN.sub(lambda m: "\x01" + m.group(1) + "\x02", PAUSE.sub(" ", narration))
    out, in_en, offset = [], False, 0
    for raw in marked.split():
        starts_en, ends_en = raw.startswith("\x01"), "\x02" in raw
        if starts_en:
            in_en = True
        clean = raw.replace("\x01", "").replace("\x02", "")
        if clean:
            out.append({"text": clean, "en": in_en, "offset": offset})
            offset += len(clean) + 1
        if ends_en:
            in_en = False
    return out


def cue_words(beat: dict) -> list:
    """The words a beat animates on, in the order the scene will use them."""
    kind, words = beat.get("type"), []
    if kind == "sentence":
        words += list((beat.get("highlight") or {}).keys())
        words += list((beat.get("tags") or {}).keys())
        if beat.get("fix"):
            words.append(beat["fix"]["to"])
    elif kind == "dialogue":
        words += [line["en"].split()[0] for line in beat.get("lines", []) if line.get("en")]
    elif kind == "table":
        words += [str(row[0]) for row in beat.get("rows", []) if row]
    elif kind in ("list", "recap"):
        words += [item.split()[0] for item in beat.get("items", []) if item.strip()]
    elif kind == "quiz":
        options = beat.get("options", [])
        if options and 0 <= beat.get("answer", -1) < len(options):
            words.append(options[beat["answer"]].split()[0])
    seen, unique = set(), []
    for w in words:
        w = w.strip().strip(".,;:!?¿¡\"'()→·-")
        if w and w not in seen:
            seen.add(w)
            unique.append(w)
    return unique


def _word_regex(word: str) -> re.Pattern:
    return re.compile(rf"(?<![\w])({re.escape(word)})(?![\w])", re.IGNORECASE)


def marked_narration(beat: dict) -> tuple:
    """Insert <bookmark mark='cN'/> before the first mention of each cue word, and
    <bookmark mark='pN'/> where each {{pause}} ends. Returns (text_with_bookmarks,
    {word_or_"pause:N": mark}) — words the narration never says get no mark and the
    scene falls back to proportional timing for them."""
    narration = beat.get("narration", "")
    # Pauses first: a sentinel survives the whitespace folding, then becomes a bookmark.
    text = " ".join(EN_SPAN.sub(r"\1", PAUSE.sub(f" {_SENTINEL} ", narration)).split())
    marks, n_pause = {}, 0
    while _SENTINEL in text:
        mark = f"p{n_pause}"
        text = text.replace(f"{_SENTINEL} ", f"<bookmark mark='{mark}'/>", 1) if f"{_SENTINEL} " in text \
            else text.replace(_SENTINEL, f"<bookmark mark='{mark}'/>", 1)
        marks[f"pause:{n_pause}"] = mark
        n_pause += 1
    for n, word in enumerate(cue_words(beat)):
        pattern = _word_regex(word)
        if pattern.search(text):
            mark = f"c{n}"
            text = pattern.sub(rf"<bookmark mark='{mark}'/>\1", text, count=1)
            marks[word] = mark
    return text, marks


def cued(beat: dict) -> list:
    """Cue words the narration actually says (what a test can assert on)."""
    return [k for k in marked_narration(beat)[1] if not k.startswith("pause:")]


# ── Loading and validation ─────────────────────────────────────────────────────

def load(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(lesson: dict, path) -> None:
    Path(path).write_text(json.dumps(lesson, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def estimate_minutes(lesson: dict, words_per_minute: int = 140) -> float:
    words = sum(len(spoken_text(b.get("narration", "")).split()) for b in lesson.get("beats", []))
    return round(words / words_per_minute + 0.04 * len(lesson.get("beats", [])), 1)


def character_count(lesson: dict) -> int:
    return sum(len(spoken_text(b.get("narration", ""))) for b in lesson.get("beats", []))


def validate(lesson: dict) -> list:
    """Every problem as one line; [] means the scene can render it."""
    problems = []
    for key in ("id", "title", "beats"):
        if not lesson.get(key):
            problems.append(f"lesson: missing {key}")
    if problems:
        return problems
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", lesson["id"]):
        problems.append("lesson: id must be a slug (a-z, 0-9, -)")
    ids = set()
    for i, beat in enumerate(lesson["beats"]):
        where = f"beat {i + 1} ({beat.get('id', '?')})"
        if not beat.get("id") or beat["id"] in ids:
            problems.append(f"{where}: missing or duplicate id")
        ids.add(beat.get("id"))
        kind = beat.get("type")
        if kind not in TYPES:
            problems.append(f"{where}: unknown type {kind!r}")
            continue
        narration = beat.get("narration", "")
        if not spoken_text(narration):
            problems.append(f"{where}: empty narration")
        elif len(spoken_text(narration)) > LIMITS["narration"]:
            problems.append(f"{where}: narration longer than {LIMITS['narration']} characters — split the beat")
        if narration.count("[[") != narration.count("]]"):
            problems.append(f"{where}: unbalanced [[ ]]")
        if "{{" in narration and len(PAUSE.findall(narration)) != narration.count("{{"):
            problems.append(f"{where}: a {{{{ }}}} marker is not {{{{pause:N}}}}")
        if any(p > MAX_PAUSE for p in (float(m.group(1)) for m in PAUSE.finditer(narration))):
            problems.append(f"{where}: a pause longer than {MAX_PAUSE:.0f} s")
        problems += _validate_fields(where, kind, beat)
    return problems


def warnings(lesson: dict) -> list:
    """Soft notes: the scene still renders, but a cue falls back to a guessed time."""
    notes = []
    for i, beat in enumerate(lesson.get("beats", [])):
        said = set(cued(beat))
        for word in cue_words(beat):
            if word not in said:
                notes.append(f"beat {i + 1} ({beat.get('id', '?')}): «{word}» is animated but never said — its timing is a guess")
    return notes


def _validate_fields(where: str, kind: str, beat: dict) -> list:
    p = []

    def need(field, typ):
        if field not in beat or not isinstance(beat[field], typ) or not beat[field]:
            p.append(f"{where}: {kind} needs {field}")
            return False
        return True

    def short(value, limit, what):
        if len(str(value)) > LIMITS[limit]:
            p.append(f"{where}: {what} longer than {LIMITS[limit]} characters")

    if kind == "heading":
        if need("text", str):
            short(beat["text"], "line", "text")
    elif kind == "tip":
        if need("text", str):
            short(beat["text"], "tip", "text")
    elif kind == "sentence":
        if beat.get("same"):
            pass
        elif need("text", str):
            short(beat["text"], "line", "text")
            if len(beat["text"].split()) > LIMITS["chips"]:
                p.append(f"{where}: sentence has more than {LIMITS['chips']} words")
        for color in (beat.get("highlight") or {}).values():
            if color not in COLORS:
                p.append(f"{where}: highlight color {color!r} not in {sorted(COLORS)}")
        fix = beat.get("fix")
        if fix and not (isinstance(fix, dict) and fix.get("from") and fix.get("to")):
            p.append(f"{where}: fix needs from and to")
    elif kind == "dialogue":
        if need("lines", list):
            if len(beat["lines"]) > LIMITS["lines"]:
                p.append(f"{where}: more than {LIMITS['lines']} lines")
            for line in beat["lines"]:
                if not isinstance(line, dict) or not line.get("en"):
                    p.append(f"{where}: every line needs en")
                else:
                    short(line["en"], "line", "line")
                    short(line.get("es", ""), "line", "gloss")
    elif kind == "table":
        if need("rows", list):
            if len(beat["rows"]) > LIMITS["rows"]:
                p.append(f"{where}: more than {LIMITS['rows']} rows")
            for row in beat["rows"]:
                if not isinstance(row, list) or not row or len(row) > LIMITS["cols"]:
                    p.append(f"{where}: rows need 1–{LIMITS['cols']} cells")
                else:
                    for cell in row:
                        short(cell, "cell", "cell")
    elif kind in ("list", "recap"):
        if need("items", list):
            if len(beat["items"]) > LIMITS["items"]:
                p.append(f"{where}: more than {LIMITS['items']} items")
            for item in beat["items"]:
                short(item, "item", "item")
    elif kind == "quiz":
        if need("question", str) and need("options", list):
            short(beat["question"], "line", "question")
            if not 2 <= len(beat["options"]) <= LIMITS["options"]:
                p.append(f"{where}: 2–{LIMITS['options']} options")
            if not isinstance(beat.get("answer"), int) or not 0 <= beat["answer"] < len(beat["options"]):
                p.append(f"{where}: answer must index an option")
            for option in beat["options"]:
                short(option, "item", "option")
    return p
