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


def _real_topics():
    """{category: {topic_id}} straight from content/topics/, read once."""
    global _REAL_TOPICS
    if _REAL_TOPICS is None:
        from script_generator import list_categories, load_topics
        _REAL_TOPICS = {}
        for category in list_categories():
            try:
                _REAL_TOPICS[category] = {str(t.get("id"))
                                          for t in load_topics(category)}
            except Exception:                               # noqa: BLE001
                _REAL_TOPICS[category] = set()
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


def audit():
    """Every problem in the queue, as (path, problem) pairs.

    All of them rather than the first: a queue filled in one sitting tends to
    carry the same mistake several times, and fixing them one run at a time is
    how a batch of twenty becomes twenty conversations.
    """
    from topic_history import usage_counts
    from script_schema import validate_script
    import duration_spec
    import length_spec

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
        if not vtype:
            problems.append((rel, "no `type`"))
            continue
        try:
            validate_script(json.loads(json.dumps(data)),
                            video_type=vtype, source=str(rel))
        except Exception as exc:                                # noqa: BLE001
            problems.append((rel, f"schema: {exc}"))

        # MEASURED WITHOUT THE TAGS. An audio tag is a direction, not a
        # spoken word: counting "[excited]" toward the duration band would
        # make every number here fiction, and a script could pass the band on
        # words nobody says.
        script_text = data.get("full_script") or ""
        try:
            from audio_tags import strip_tags, unknown_tags
            for tag in unknown_tags(script_text):
                problems.append((rel, f"UNKNOWN AUDIO TAG {tag}: eleven_v3 does "
                                      f"not recognise it, so it gets READ ALOUD"))
            script_text = strip_tags(script_text)
        except ImportError:                                 # noqa: BLE001
            pass
        spoken = len(script_text.split())
        try:
            band = duration_spec.word_range(vtype)
            if spoken and not (band["min"] <= spoken <= band["max"]):
                problems.append((rel, f"duration: {spoken} spoken words, band "
                                      f"is {band['min']}-{band['max']} "
                                      f"(target {band['target']})"))
        except Exception:                                       # noqa: BLE001
            pass

        try:
            measured = dict(data)
            measured["full_script"] = script_text
            for v in length_spec.check_script(measured) or []:
                problems.append((rel, f"length: {v['field']} at {v['where']} "
                                      f"needs {v['lines']} lines"))
        except Exception:                                       # noqa: BLE001
            pass

    return problems


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
    bad = {p for p, _ in problems}

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
    if not problems:
        print(f"{total} queued script(s), no problems. "
              f"Next: {queued_scripts()[0].relative_to(ROOT)}")
        return 0
    print(f"{total} queued script(s), {len(problems)} problem(s) "
          f"in {len(bad)} file(s):\n")
    for path, problem in problems:
        print(f"  {path}\n      {problem}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
