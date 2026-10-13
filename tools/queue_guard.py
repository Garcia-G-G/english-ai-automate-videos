#!/usr/bin/env python3
"""The queue guard — no topic is ever produced twice.

    python3 tools/queue_guard.py            # audit the queue, exit 1 on any problem
    python3 tools/queue_guard.py --next     # print the path of the next SAFE script
    python3 tools/queue_guard.py --done <p> # shelve a produced script

WHY THIS EXISTS. `topic_history` answers "has this topic been made?" and the
random draw uses it. The queue route does not draw at random: the scripts are
written ahead of time, by hand, and a hand can repeat itself in three ways the
draw never could.

    1. a queued script names a topic that was ALREADY produced
    2. two queued scripts name the SAME topic as each other
    3. a script is produced and then produced AGAIN, because nothing moved it

Only the first is something topic_history can see, and only since usage_counts
learned to read BOTH doors -- output/scripts/ AND output/artifacts/. The queue
route writes the script inside the artifact and nowhere else, so before that
change every queued video stayed "unused" forever and the memory would have
handed the same topic back. The other two failure modes arrive with the queue
itself, so the queue brings its own guard rather than trusting the discipline
of whoever fills it.

THE SHELF IS THE RECORD. A produced script moves to content/queue/_done/. It is
not deleted, because the deletion would be the only evidence it ever ran, and
this project has paid for unrecorded decisions before.

Exit codes: 0 clean - 1 a problem worth stopping for - 2 the queue is empty.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

QUEUE_DIR = ROOT / "content" / "queue"
DONE_DIR = QUEUE_DIR / "_done"


_REAL_TOPICS = None
_REAL_TOPICS_STAMP = None
TOPICS_DIR = ROOT / "content" / "topics"


def _topics_stamp():
    """(name, mtime, size) of every topic file: what the cache is valid for."""
    try:
        return tuple(sorted((f.name, f.stat().st_mtime_ns, f.stat().st_size)
                            for f in TOPICS_DIR.glob("*.json")))
    except OSError:
        return None


def _real_topics():
    """{category: {topic_id}} straight from content/topics/.

    RE-READ WHEN THE TOPIC FILES CHANGE. It used to be read once per process.
    The dashboard is a process that lives for days: one started on 2026-10-08
    kept a topic list without basic_vocab, so after how_do_you_say arrived on
    10-12 every one of its scripts was "NO SUCH TOPIC" in that process only --
    and the Generate page said "no queued script left for 'how_do_you_say'"
    while the CLI, a fresh process, listed seventeen.
    """
    global _REAL_TOPICS, _REAL_TOPICS_STAMP
    stamp = _topics_stamp()
    if _REAL_TOPICS is None or stamp != _REAL_TOPICS_STAMP:
        from script_generator import list_categories, load_topics
        topics = {}
        for category in list_categories():
            try:
                topics[category] = {str(t.get("id"))
                                    for t in load_topics(category)}
            except Exception:                               # noqa: BLE001
                topics[category] = set()
        _REAL_TOPICS, _REAL_TOPICS_STAMP = topics, stamp
    return _REAL_TOPICS


def _load(path: Path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:                                    # noqa: BLE001
        return exc


def queued_scripts():
    """Every queued script, name order, excluding the _done shelf."""
    if not QUEUE_DIR.exists():
        return []
    return sorted(p for p in QUEUE_DIR.rglob("*.json")
                  if DONE_DIR not in p.parents)


#: (fingerprint -> problems). The audit reads every queued script, validates
#: each against its schema and lays its text out with the real font, which
#: measures ten seconds on a hundred scripts. Streamlit re-runs the whole page
#: on every widget interaction and every job asks for the next safe script, so
#: an uncached audit put ten seconds in front of each of those. The fingerprint
#: is the queue's own (path, mtime, size) plus the produced-topic count, so any
#: edit or any finished video invalidates it and nothing goes stale.
#: WHAT ACTUALLY STOPS A SCRIPT FROM BEING PRODUCED.
#
# Severity is a property of the failure, not of the file. A repeated topic is
# unrecoverable -- the video reaches the channel and the audience sees the same
# lesson twice. A short video is a real video the owner can watch and judge.
# Refusing the second kind produced NOTHING, which is worse than producing
# something imperfect, and it pushed every quiz, true_false and fill_blank job
# onto the GPT fallback and a dead API key.
#
# So: correctness blocks, quality warns.
BLOCKING = ("ALREADY PRODUCED", "DUPLICATE", "NO SUCH TOPIC", "schema:",
            "UNKNOWN AUDIO TAG", "unreadable", "not a JSON object",
            "_meta.category", "no `type`")


def blocks(problem: str) -> bool:
    """Whether this problem means the script must not be handed out."""
    return any(problem.startswith(p) or p in problem[:40] for p in BLOCKING)


_AUDIT_CACHE = {}


def _fingerprint():
    try:
        files = tuple(sorted(
            (str(p), int(p.stat().st_mtime_ns), p.stat().st_size)
            for p in queued_scripts()))
    except OSError:
        return None
    try:
        from topic_history import usage_counts
        produced = sum(usage_counts().values())
    except Exception:                                       # noqa: BLE001
        produced = -1
    return (files, produced)


def audit(fresh: bool = False):
    """Every problem in the queue, as (path, problem) pairs.

    All of them rather than the first: a queue filled in one sitting tends to
    carry the same mistake several times, and fixing them one run at a time is
    how a batch of twenty becomes twenty conversations.
    """
    from topic_history import usage_counts
    from script_schema import validate_script
    import duration_spec
    import length_spec

    # NOT `key`. This function already binds `key` per script -- the
    # (category, topic_id) pair -- so the name was silently rebound inside the
    # loop and every store went in under the last script's topic. The cache
    # filled and never hit once.
    cache_key = None if fresh else _fingerprint()
    if cache_key is not None and cache_key in _AUDIT_CACHE:
        return list(_AUDIT_CACHE[cache_key])

    used = usage_counts()
    problems = []
    seen_in_queue = {}

    for path in queued_scripts():
        rel = path.relative_to(ROOT)
        data = _load(path)
        if isinstance(data, Exception):
            problems.append((rel, f"unreadable: {data}"))
            continue
        if not isinstance(data, dict):
            problems.append((rel, "not a JSON object"))
            continue

        meta = data.get("_meta") or {}
        category = meta.get("category")
        topic_id = meta.get("topic_id")
        vtype = data.get("type")

        # -- the three ways a queue repeats itself --
        if not category or not topic_id:
            problems.append((rel, "_meta.category / _meta.topic_id missing - "
                                  "topic_history cannot record this, so the "
                                  "topic would stay 'unused' forever"))
        else:
            # A TOPIC ID THAT DOES NOT EXIST is the quietest repeat of all: the
            # history records a topic nobody can draw, and the REAL topic stays
            # "unused" forever, free to be produced again later. Found by
            # checking a hand-written batch against the topic files -- one of
            # fifty ids was invented, and nothing else in the system would ever
            # have noticed.
            if category not in _real_topics() or str(topic_id) not in _real_topics()[category]:
                problems.append((rel, f"NO SUCH TOPIC: {category}/{topic_id} is "
                                      f"not in content/topics/ -- the history "
                                      f"would record a topic that cannot be drawn"))
            key = (str(category), str(topic_id))
            if used.get(key):
                problems.append((rel, f"ALREADY PRODUCED: {category}/{topic_id} "
                                      f"has {used[key]} video(s) on disk"))
            # BOTH members of a duplicate pair are flagged, not just the
            # second one. Flagging only the later file let --next hand out
            # the earlier one, so the operator produced a video from a script
            # whose twin was the thing that had been reviewed.
            if key in seen_in_queue:
                first = seen_in_queue[key]
                problems.append((rel, f"DUPLICATE of {first}: "
                                      f"both claim {category}/{topic_id}"))
                problems.append((first, f"DUPLICATE of {rel}: "
                                        f"both claim {category}/{topic_id}"))
            else:
                seen_in_queue[key] = rel

        # -- and the three gates the pipeline applies anyway --
        problems.extend((rel, problem) for problem in _content_problems_cached(path, data))

    if cache_key is not None:
        # One entry. The fingerprint changes on any edit, so keeping history
        # would only hold memory for a queue state that can never return.
        _AUDIT_CACHE.clear()
        _AUDIT_CACHE[cache_key] = list(problems)
    return problems



# ── Per-script content checks, cached on disk ──────────────────────────────
#
# WHY. The schema / tag / duration / length checks read nothing but the script
# itself (and the code and config that judge it), yet they were re-run for
# every queued script whenever ANYTHING in the queue changed -- one new file or
# one finished video meant ~11 s of text layout before the dashboard's Generate
# page could draw, on every first load and after every render. Measured
# 2026-10-13: queue_status 10.9 s of a 15.0 s first load.
#
# The topic checks (NO SUCH TOPIC, ALREADY PRODUCED, DUPLICATE) depend on the
# rest of the queue and on what has been produced, so they are NOT cached;
# they run every time, as before, and they are cheap.
#
# The cache key is the script's own (mtime, size) plus a signature of every
# file whose change could change a verdict: the schema, length_spec and
# duration modules, the renderers they measure against (src/video,
# src/config, src/animations), config.yaml and the fonts. Edit any of them and
# every entry is re-judged once.

CONTENT_CACHE = ROOT / "output" / ".cache" / "queue_content_checks.json"
_CONTENT_MEMO = {"sig": None, "entries": None}


def _code_signature() -> str:
    import hashlib
    h = hashlib.sha1()
    src = ROOT / "src"
    watched = [ROOT / "config.yaml", ROOT / "tools" / "duration_calibrate.py",
               ROOT / "tools" / "queue_guard.py"]
    watched += [src / n for n in ("script_schema.py", "length_spec.py",
                                  "duration_spec.py", "audio_tags.py",
                                  "emoji_font.py", "video_types.py")]
    # The renderers own the box sizes length_spec measures against.
    for folder in ("video", "config", "animations"):
        watched += sorted((src / folder).rglob("*.py"))
    watched += sorted((ROOT / "assets" / "fonts").glob("*"))
    for f in watched:
        try:
            st = f.stat()
        except OSError:
            continue
        h.update(f"{f.relative_to(ROOT)}|{st.st_mtime_ns}|{st.st_size}\n".encode())
    return h.hexdigest()


def _content_entries(sig: str) -> dict:
    if _CONTENT_MEMO["sig"] == sig and _CONTENT_MEMO["entries"] is not None:
        return _CONTENT_MEMO["entries"]
    entries = {}
    try:
        stored = json.loads(CONTENT_CACHE.read_text(encoding="utf-8"))
        if stored.get("sig") == sig:
            entries = stored.get("entries") or {}
    except (OSError, ValueError):
        pass
    _CONTENT_MEMO.update(sig=sig, entries=entries)
    return entries


def _save_content_entries(sig: str, entries: dict) -> None:
    try:
        CONTENT_CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CONTENT_CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"sig": sig, "entries": entries}), encoding="utf-8")
        tmp.replace(CONTENT_CACHE)
    except OSError:
        pass                      # a cache that cannot be written is only slower


def _content_problems_cached(path: Path, data: dict) -> list:
    try:
        st = path.stat()
    except OSError:
        return _content_problems(data, path)
    sig = _code_signature()
    entries = _content_entries(sig)
    key = str(path.relative_to(ROOT)) if ROOT in path.parents else str(path)
    stamp = f"{st.st_mtime_ns}|{st.st_size}"
    hit = entries.get(key)
    if hit and hit.get("stamp") == stamp:
        return list(hit["problems"])
    problems = _content_problems(data, key)
    entries[key] = {"stamp": stamp, "problems": problems}
    _save_content_entries(sig, entries)
    return problems


def _content_problems(data: dict, rel="<script>") -> list:
    """Schema, audio tags, duration band and layout for ONE script."""
    from script_schema import validate_script
    import duration_spec
    import length_spec
    out = []
    vtype = data.get("type")
    if not vtype:
        out.append(("no `type`"))
        return out
    try:
        validate_script(json.loads(json.dumps(data)),
                        video_type=vtype, source=str(rel))
    except Exception as exc:                                # noqa: BLE001
        out.append((f"schema: {exc}"))

    # MEASURED WITHOUT THE TAGS. An audio tag is a direction, not a
    # spoken word: counting "[excited]" toward the duration band would
    # make every number here fiction.
    script_text = data.get("full_script") or ""
    try:
        from audio_tags import strip_tags, unknown_tags
        for tag in unknown_tags(script_text):
            out.append((f"UNKNOWN AUDIO TAG {tag}: eleven_v3 does "
                                  f"not recognise it, so it gets READ ALOUD"))
        script_text = strip_tags(script_text)
    except ImportError:                                 # noqa: BLE001
        pass

    # AND MEASURED AGAINST THE TEXT THE GENERATOR ACTUALLY SPEAKS.
    # full_script is NOT the narration for quiz, true_false, fill_blank or
    # vocabulary: generate_<type>_audio_segmented builds the audio from the
    # structured fields and copies full_script into the metadata untouched.
    # Counting full_script for those four measured a string nobody says, so
    # a script sat inside the band and produced a 30-second video. Measured
    # on the corpus, not assumed -- see tools/duration_calibrate.py.
    try:
        if str(ROOT / "tools") not in sys.path:
            sys.path.insert(0, str(ROOT / "tools"))
        from duration_calibrate import spoken_words
        spoken = spoken_words(data)
    except Exception:                                   # noqa: BLE001
        spoken = len(script_text.split())
    try:
        band = duration_spec.word_range(vtype)
        if spoken and not (band["min"] <= spoken <= band["max"]):
            out.append((f"duration: {spoken} spoken words, band "
                                  f"is {band['min']}-{band['max']} "
                                  f"(target {band['target']})"))
    except Exception:                                       # noqa: BLE001
        pass

    try:
        measured = dict(data)
        measured["full_script"] = script_text
        for v in length_spec.check_script(measured) or []:
            out.append((f"length: {v['field']} at {v['where']} "
                                  f"needs {v['lines']} lines"))
    except Exception:                                       # noqa: BLE001
        pass

    return out


def main(argv):
    if "--done" in argv:
        src = Path(argv[argv.index("--done") + 1]).resolve()
        DONE_DIR.mkdir(parents=True, exist_ok=True)
        dest = DONE_DIR / src.name
        n = 1
        while dest.exists():
            dest = DONE_DIR / f"{src.stem}.{n}{src.suffix}"
            n += 1
        shutil.move(str(src), str(dest))
        # relative_to raises for a DONE_DIR outside the repo (a test that
        # redirects the queue does exactly that), and raising AFTER the move
        # made admin.queue_shelve log "could not shelve" for a script it had
        # just shelved. The report must not be able to undo the result.
        try:
            shown = dest.relative_to(ROOT)
        except ValueError:
            shown = dest
        print(f"shelved: {shown}")
        return 0

    problems = audit()
    bad = {p for p, reason in problems if blocks(reason)}
    warned = {p for p, reason in problems if not blocks(reason)}

    if "--next" in argv:
        # THE POINT OF THE WHOLE FILE. A script with any problem is never
        # handed out: a cron cannot read a warning, so the guard refuses
        # rather than printing a caveat next to the path.
        for path in queued_scripts():
            if path.relative_to(ROOT) not in bad:
                print(path)
                return 0
        if not queued_scripts():
            print("queue is empty - nothing to produce", file=sys.stderr)
            return 2
        print(f"every queued script has a problem ({len(bad)}); "
              f"run without --next to see them", file=sys.stderr)
        return 1

    total = len(queued_scripts())
    if not total:
        print("queue is empty")
        return 2
    if warned and not bad:
        print(f"{total} queued script(s), {len(warned)} with warnings, "
              f"none blocked. Next: {queued_scripts()[0].relative_to(ROOT)}\n")
        for path, problem in problems:
            print(f"  {path}\n      {problem}")
        return 0
    if not problems:
        print(f"{total} queued script(s), no problems. "
              f"Next: {queued_scripts()[0].relative_to(ROOT)}")
        return 0
    print(f"{total} queued script(s), {len(bad)} BLOCKED, "
          f"{len(warned)} with warnings:\n")
    for path, problem in problems:
        print(f"  {path}\n      {problem}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
