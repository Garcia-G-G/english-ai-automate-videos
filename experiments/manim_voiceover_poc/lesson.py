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
  transform from, to, gloss?                one sentence morphs into another: shared
                                            words glide, words only in `from` fall away
                                            in red, words only in `to` drop in green
  timeline  events[{label, start, end?, kind}]  an axis from -10 to +10 with «ahora» at 0;
                                            kind point · span · repeat; ≤ 3 events
  sort      bins[], items[[text, bin]]      2–3 bins, ≤ 8 items that pop in and fly
                                            into their bin
  syllables word, parts[], stress, gloss?,  the word in syllable chips (the stressed one
            respelling?                     bigger, yellow); a dot hops across them while
                                            the word is said, then they close into the word

A lesson may name its look with "theme" (a key of brand.json → manim.themes); the
THEME environment variable overrides it, and manim.default_theme is the fallback.

`title` may come second or third, so a lesson can open on a hook (a `transform` that
shows the mistake in the first seconds).

The three motion types cue in order: each cue is looked for after the previous one,
inside the English ([[ ]]) of the narration only. A `transform` cues on the first word
of `to` that is new or has moved, looked for after the narration has said `from`; a
`timeline` event on the first word of its label; a `sort` item on the item itself; a
`syllables` beat on its word.
"""
import json
import re
from pathlib import Path

TYPES = {"title", "heading", "sentence", "dialogue", "table", "list", "tip", "quiz", "recap",
         "transform", "timeline", "sort", "syllables"}
ORDERED = {"transform", "timeline", "sort", "syllables"}       # cues searched in order, inside the English only
COLORS = {"yellow", "blue", "green", "red"}
LIMITS = {"line": 90, "tip": 170, "cell": 28, "item": 110, "items": 6, "lines": 6, "rows": 6, "cols": 3,
          "options": 4, "narration": 420, "chips": 12, "label": 40, "events": 3, "bins": 3,
          "bin": 14, "sort_items": 8, "sort_item": 24, "title_by": 3, "word": 30, "part": 12}
KINDS = {"point", "span", "repeat"}
AXIS = (-10, 10)
PUNCT = ".,;:!?¿¡\"'()→·-…"
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


def norm(word: str) -> str:
    """How two words are compared: case and punctuation do not count."""
    return word.strip(PUNCT).lower()


def transform_plan(source: str, target: str) -> dict:
    """How `source` becomes `target`, word by word (case and punctuation ignored).

    Words of both sentences are paired in order; the longest common subsequence of the
    pairs stays put relatively, the other shared words have *moved*. On a tie the LCS
    keeps the earlier `source` word, so in «You are tired» → «Are you tired» it is
    «Are» that jumps in front. Returns {from, to, pairs: [(i, j)], removed: [i],
    added: [j], moved: [j], cue: j} — `cue` is the first word of `to` that is new or has
    moved (the first word if nothing is)."""
    a, b = source.split(), target.split()
    na, nb = [norm(w) for w in a], [norm(w) for w in b]
    dp = [[0] * (len(nb) + 1) for _ in range(len(na) + 1)]
    for i in range(len(na) - 1, -1, -1):
        for j in range(len(nb) - 1, -1, -1):
            dp[i][j] = dp[i + 1][j + 1] + 1 if na[i] == nb[j] else max(dp[i + 1][j], dp[i][j + 1])
    stable, i, j = set(), 0, 0
    while i < len(na) and j < len(nb):
        if na[i] == nb[j]:
            stable.add((i, j))
            i, j = i + 1, j + 1
        elif dp[i][j + 1] >= dp[i + 1][j]:
            j += 1                           # tie: skip the `to` word, keep the `from` word in the LCS
        else:
            i += 1
    pairs = sorted(stable)
    used_a, used_b = {p[0] for p in pairs}, {p[1] for p in pairs}
    moved = []
    for j, w in enumerate(nb):               # shared words outside the LCS, paired in order
        if j in used_b:
            continue
        for i, v in enumerate(na):
            if i not in used_a and v == w:
                pairs.append((i, j))
                used_a.add(i)
                used_b.add(j)
                moved.append(j)
                break
    pairs.sort(key=lambda p: p[1])
    added = [j for j in range(len(nb)) if j not in used_b]
    removed = [i for i in range(len(na)) if i not in used_a]
    changed = sorted(set(added) | set(moved))
    return {"from": a, "to": b, "pairs": pairs, "removed": removed, "added": added,
            "moved": sorted(moved), "cue": changed[0] if changed else 0}


def cue_words(beat: dict) -> list:
    """The words a beat animates on, in the order the scene will use them. For the
    ORDERED types a word may repeat (two timeline labels that start with «I»): each
    occurrence is its own cue."""
    kind, words = beat.get("type"), []
    if kind in ORDERED:
        if kind == "transform" and beat.get("from") and beat.get("to"):
            plan = transform_plan(beat["from"], beat["to"])
            words = [plan["to"][plan["cue"]]] if plan["to"] else []
        elif kind == "timeline":
            words = [str(e.get("label", "")).split()[0] for e in beat.get("events", [])
                     if isinstance(e, dict) and str(e.get("label", "")).split()]
        elif kind == "sort":
            words = [str(item[0]) for item in beat.get("items", []) if isinstance(item, list) and item]
        elif kind == "syllables":
            words = [str(beat.get("word", ""))]
        return [w.strip(PUNCT) for w in words if w.strip(PUNCT)]
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


def cue_keys(beat: dict) -> list:
    """The key each cue word gets in marked_narration's marks, aligned with cue_words():
    the word itself, or "#n" for the ORDERED types (where a word may repeat)."""
    words = cue_words(beat)
    return [f"#{n}" for n in range(len(words))] if beat.get("type") in ORDERED else words


def marked_narration(beat: dict) -> tuple:
    """Insert <bookmark mark='cN'/> before the first mention of each cue word, and
    <bookmark mark='pN'/> where each {{pause}} ends. Returns (text_with_bookmarks,
    {word_or_"pause:N": mark}) — words the narration never says get no mark and the
    scene falls back to proportional timing for them. ORDERED types key their marks
    "#n" (see cue_keys) and look for each cue after the previous one, in English only."""
    narration = beat.get("narration", "")
    ordered = beat.get("type") in ORDERED
    if ordered:                              # \x01…\x02 fence the English; stripped at the end
        narration = EN_SPAN.sub(lambda m: f"[[\x01{m.group(1)}\x02]]", narration)
    # Pauses first: a sentinel survives the whitespace folding, then becomes a bookmark.
    text = " ".join(EN_SPAN.sub(r"\1", PAUSE.sub(f" {_SENTINEL} ", narration)).split())
    marks, n_pause = {}, 0
    while _SENTINEL in text:
        mark = f"p{n_pause}"
        text = text.replace(f"{_SENTINEL} ", f"<bookmark mark='{mark}'/>", 1) if f"{_SENTINEL} " in text \
            else text.replace(_SENTINEL, f"<bookmark mark='{mark}'/>", 1)
        marks[f"pause:{n_pause}"] = mark
        n_pause += 1
    if ordered:
        return _mark_in_order(beat, text, marks)
    for n, word in enumerate(cue_words(beat)):
        pattern = _word_regex(word)
        if pattern.search(text):
            mark = f"c{n}"
            text = pattern.sub(rf"<bookmark mark='{mark}'/>\1", text, count=1)
            marks[word] = mark
    return text, marks


def _english_spans(text: str) -> list:
    return [(m.start(), m.end()) for m in re.finditer(r"\x01[^\x02]*\x02", text)]


def _mark_in_order(beat: dict, text: str, marks: dict) -> tuple:
    pos = 0
    if beat.get("type") == "transform" and beat.get("from"):
        said = [re.escape(norm(w)) for w in beat["from"].split() if norm(w)]
        if said:                             # the cue comes after `from` has been said
            found = re.search(r"(?<![\w])" + r"[^\w]+".join(said) + r"(?![\w])", text, re.IGNORECASE)
            if found:
                pos = found.end()
    for n, word in enumerate(cue_words(beat)):
        for match in _word_regex(word).finditer(text, pos):
            if any(a < match.start() and match.end() < b for a, b in _english_spans(text)):
                mark = f"c{n}"
                text = text[:match.start()] + f"<bookmark mark='{mark}'/>" + text[match.start():]
                marks[f"#{n}"] = mark
                pos = match.end() + len(f"<bookmark mark='{mark}'/>")
                break
    return text.replace("\x01", "").replace("\x02", ""), marks


def cued(beat: dict) -> list:
    """Cue words the narration actually says (what a test can assert on)."""
    marks = marked_narration(beat)[1]
    return [w for k, w in zip(cue_keys(beat), cue_words(beat)) if k in marks]


# ── Loading and validation ─────────────────────────────────────────────────────

BRAND = Path(__file__).resolve().parent.parent.parent / "assets" / "branding" / "english-unlimited" / "brand.json"


def themes() -> dict:
    """brand.json → manim: {"default_theme", "themes": {name: tokens}}."""
    return json.loads(BRAND.read_text(encoding="utf-8"))["manim"]


def theme_name(lesson: dict, env: dict = None) -> str:
    """THEME in the environment, else the lesson's "theme", else the brand default."""
    import os
    env = os.environ if env is None else env
    return env.get("THEME") or lesson.get("theme") or themes()["default_theme"]


def load(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(lesson: dict, path) -> None:
    Path(path).write_text(json.dumps(lesson, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ── Duration: fitted on real renders ───────────────────────────────────────────
# A render lasts  words · s/word + beats · s/beat + the {{pause}} seconds + the end card
# + a 1 s hold. The defaults are the fit of the renders in renders/ledger.jsonl on
# 2026-10-13: n = 3 (third-person-s 425 s, morning-phrasal-verbs 424 s, used-to-soler
# 357 s), residuals within ±31 s. Three points cannot pin two rates — fitting both gave
# a negative cost per beat — so until MIN_FULL_FIT renders exist only the speaking rate
# is fitted and s/beat is the scene's own overhead (a 0.35 s fade out + a 0.35–0.6 s
# breath). The old "140 wpm + 0.04 min/beat" said 7.1 min for used-to-soler (5.95 real).
SECONDS_PER_WORD = 0.434          # ≈ 138 wpm, everything included
SECONDS_PER_BEAT = 0.75
END_SCREEN_S = 20.0
FINAL_HOLD_S = 1.0
MIN_FULL_FIT = 6


def features(lesson: dict) -> dict:
    """What the duration depends on — recorded in the ledger with every render."""
    beats = lesson.get("beats", [])
    return {"words": sum(len(spoken_text(b.get("narration", "")).split()) for b in beats),
            "beats": len(beats), "pause_s": round(sum(sum(pauses(b.get("narration", ""))) for b in beats), 2)}


def fit_duration(rows: list) -> dict:
    """Least squares on ledger rows that carry features: (duration − pauses − end card −
    hold) against words (and beats, once there are MIN_FULL_FIT renders). Duplicate rows
    of one render (same lesson, same bytes) count once."""
    seen, points = set(), []
    for r in rows:
        if not all(k in r for k in ("words", "beats", "pause_s")) or not r.get("duration_s"):
            continue
        key = (r.get("lesson"), r.get("bytes"), r.get("duration_s"))
        if key in seen:
            continue
        seen.add(key)
        rest = r["duration_s"] - r["pause_s"] - r.get("end_s", 0.0) - FINAL_HOLD_S
        points.append((r["words"], r["beats"], rest, r))
    fit = {"n": len(points), "seconds_per_word": SECONDS_PER_WORD, "seconds_per_beat": SECONDS_PER_BEAT,
           "fitted": "default"}
    if not points:
        return fit
    if len(points) >= MIN_FULL_FIT:
        sww = sum(w * w for w, *_ in points); swb = sum(w * b for w, b, *_ in points)
        sbb = sum(b * b for _, b, *_ in points)
        swy = sum(w * y for w, _, y, _ in points); sby = sum(b * y for _, b, y, _ in points)
        det = sww * sbb - swb * swb
        if det:
            a, k = (swy * sbb - sby * swb) / det, (sww * sby - swb * swy) / det
            if a > 0 and k >= 0:
                fit.update(seconds_per_word=a, seconds_per_beat=k, fitted="words+beats")
    if fit["fitted"] == "default":
        k = SECONDS_PER_BEAT
        a = sum((y - k * b) * w for w, b, y, _ in points) / sum(w * w for w, *_ in points)
        fit.update(seconds_per_word=a, fitted="words (s/beat fixed)")
    fit["residuals_s"] = [round(r["duration_s"] - (fit["seconds_per_word"] * w + fit["seconds_per_beat"] * b
                                                  + r["pause_s"] + r.get("end_s", 0.0) + FINAL_HOLD_S), 1)
                          for w, b, _, r in points]
    fit["wpm"] = round(60 / fit["seconds_per_word"], 1)
    return fit


def ledger_fit(path=None) -> dict:
    """fit_duration over renders/ledger.jsonl beside this file ({} when there is none)."""
    path = Path(path) if path else Path(__file__).resolve().parent / "renders" / "ledger.jsonl"
    if not path.exists():
        return {}
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return fit_duration(rows)


def estimate_seconds(lesson: dict, fit: dict = None, end_screen: bool = True) -> float:
    """fit=None reads the ledger, so the estimate improves with every render."""
    f = features(lesson)
    fit = ledger_fit() if fit is None else fit
    a = (fit or {}).get("seconds_per_word", SECONDS_PER_WORD)
    k = (fit or {}).get("seconds_per_beat", SECONDS_PER_BEAT)
    return a * f["words"] + k * f["beats"] + f["pause_s"] + FINAL_HOLD_S + (END_SCREEN_S if end_screen else 0.0)


def estimate_minutes(lesson: dict, fit: dict = None) -> float:
    return round(estimate_seconds(lesson, fit) / 60, 1)


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
    if lesson.get("theme") and lesson["theme"] not in themes()["themes"]:
        problems.append(f"lesson: theme {lesson['theme']!r} is not one of {sorted(themes()['themes'])}")
    titles = [i for i, b in enumerate(lesson["beats"]) if b.get("type") == "title"]
    if titles and titles[0] >= LIMITS["title_by"]:
        problems.append(f"lesson: the title card must be beat 1, 2 or 3 (it is beat {titles[0] + 1})")
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
        marks = marked_narration(beat)[1]
        for key, word in zip(cue_keys(beat), cue_words(beat)):
            if key not in marks:
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
    elif kind == "transform":
        if need("from", str) and need("to", str):
            for field in ("from", "to"):
                short(beat[field], "line", field)
                if len(beat[field].split()) > LIMITS["chips"]:
                    p.append(f"{where}: {field} has more than {LIMITS['chips']} words")
            if [norm(w) for w in beat["from"].split()] == [norm(w) for w in beat["to"].split()]:
                p.append(f"{where}: from and to are the same words — nothing would move")
        if beat.get("gloss"):
            short(beat["gloss"], "line", "gloss")
    elif kind == "timeline":
        if need("events", list):
            if len(beat["events"]) > LIMITS["events"]:
                p.append(f"{where}: more than {LIMITS['events']} events")
            for e in beat["events"]:
                if not isinstance(e, dict) or not str(e.get("label", "")).strip():
                    p.append(f"{where}: every event needs a label")
                    continue
                short(e["label"], "label", "event label")
                if e.get("kind") not in KINDS:
                    p.append(f"{where}: event kind must be one of {sorted(KINDS)}")
                start, end = e.get("start"), e.get("end", e.get("start"))
                if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (start, end)):
                    p.append(f"{where}: event start/end must be numbers")
                    continue
                if not (AXIS[0] <= start <= AXIS[1] and AXIS[0] <= end <= AXIS[1]):
                    p.append(f"{where}: event outside the axis {AXIS[0]}…{AXIS[1]}")
                if e.get("kind") in ("span", "repeat") and not end > start:
                    p.append(f"{where}: a {e.get('kind')} needs end > start")
    elif kind == "sort":
        if need("bins", list) and need("items", list):
            if not 2 <= len(beat["bins"]) <= LIMITS["bins"]:
                p.append(f"{where}: 2–{LIMITS['bins']} bins")
            for b in beat["bins"]:
                short(b, "bin", "bin")
            if len(beat["items"]) > LIMITS["sort_items"]:
                p.append(f"{where}: more than {LIMITS['sort_items']} items")
            for item in beat["items"]:
                if (not isinstance(item, list) or len(item) != 2 or not str(item[0]).strip()
                        or not isinstance(item[1], int) or not 0 <= item[1] < len(beat["bins"])):
                    p.append(f"{where}: every item is [text, bin index]")
                else:
                    short(item[0], "sort_item", "item")
    elif kind == "syllables":
        if need("word", str) and need("parts", list):
            short(beat["word"], "word", "word")
            parts = beat["parts"]
            if not 2 <= len(parts) <= 6:
                p.append(f"{where}: 2–6 parts")
            if not all(isinstance(x, str) and x.strip() for x in parts):
                p.append(f"{where}: every part is a non-empty string")
            else:
                for x in parts:
                    short(x, "part", "part")
                spelled = "".join(parts).lower()
                word = re.sub(r"[\s-]", "", beat["word"]).lower()
                if spelled != word and not beat.get("respelling"):
                    p.append(f"{where}: parts spell {spelled!r}, not {word!r} — or set \"respelling\": true")
            stress = beat.get("stress")
            if not isinstance(stress, int) or isinstance(stress, bool) or not 0 <= stress < len(parts):
                p.append(f"{where}: stress must index a part")
        if beat.get("gloss"):
            short(beat["gloss"], "line", "gloss")
    return p
