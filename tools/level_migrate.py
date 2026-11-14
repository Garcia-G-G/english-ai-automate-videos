#!/usr/bin/env python3
"""Move the level-family drafts into the queue (STEP 58, true_false_level STEP 61).

    python3 tools/level_migrate.py
    python3 tools/level_migrate.py --rederive   # queue files again, after a LEVEL_PLANS change
    python3 tools/level_migrate.py --copy choose_level fill_level ...   # STEP 77 §9

--copy queues each draft of the named types the same way but LEAVES the draft where it is,
validates every script (validate_script and length_spec) before anything is written, and
skips a draft whose id is already queued, done or rendered.

Per draft: `translations`, `english_phrases` and `full_script` are derived the way
how_do_you_say's were, `_meta.draft` is dropped, the file goes to
content/queue/<type>/ and the draft is removed (moved, not copied). The topic file
goes to content/topics/. Refuses to overwrite anything already in the queue.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tts_elevenlabs import LEVEL_PLANS, level_answer, level_tier_lines  # noqa: E402

TOPICS = {"level_test": "level_vocab", "say_it_level": "say_it", "true_false_level": "false_friends",
          "fill_level": "grammar", "choose_level": "grammar", "phrases_level": "everyday_expressions"}


def derive(script: dict) -> dict:
    """The derived fields, in the order the audio speaks them."""
    plan = LEVEL_PLANS[script["type"]]
    items = script["items"]
    spoken = [script["intro"]]
    for i, item in enumerate(items, start=1):
        if i in level_tier_lines(plan):
            spoken.append(level_tier_lines(plan)[i])
        if plan["speak_prompt"]:
            spoken.append(item[plan["prompt"][0]])
        spoken.append(level_answer(item, plan["answer"][0]))
    spoken += [script["verdict"], script["outro"]] if "verdict" in script else [script["outro"]]
    out = dict(script)
    if script["type"] == "true_false_level":
        # The English word of each statement, the one in «»; nothing is spoken in English.
        out["translations"] = {}
        out["english_phrases"] = [re.search(r"«([^»]+)»", it["statement"]).group(1) for it in items]
    elif plan["answer"][0] == "filled":
        # The English spoken is the whole sentence with its blank filled (STEP 62).
        filled = [level_answer(it, "filled") for it in items]
        out["translations"] = {f: it["translation"] for f, it in zip(filled, items) if it.get("translation")}
        out["english_phrases"] = filled
    else:
        out["translations"] = {it["english"]: it["spanish"] for it in items}
        out["english_phrases"] = [it["english"] for it in items] + [it["alt"] for it in items if it.get("alt")]
    out["full_script"] = " ".join(spoken)
    out["_meta"] = {k: v for k, v in script["_meta"].items() if k != "draft"}
    return out


def rederive() -> int:
    """Rewrite the derived fields of every queued script from the current plan."""
    for vtype in TOPICS:
        paths = sorted((ROOT / "content" / "queue" / vtype).glob("*.json"))
        for p in paths:
            script = derive(json.loads(p.read_text(encoding="utf-8")))
            p.write_text(json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{vtype}: {len(paths)} queued scripts re-derived")
    return 0


def _taken(name: str, vtype: str, meta: dict) -> bool:
    """Queued, done, or already produced (the topic history the queue guard reads)."""
    if (ROOT / "content" / "queue" / vtype / name).exists() or (ROOT / "content" / "queue" / "_done" / name).exists():
        return True
    from topic_history import usage_counts
    return bool(usage_counts().get((str(meta.get("category")), str(meta.get("topic_id")))))


def add_topics(scripts) -> dict:
    """The topic entry each queued script names, appended to content/topics/<category>.json
    when it is not there yet: the queue guard refuses a script whose topic cannot be drawn."""
    added = {}
    for vtype, script in scripts:
        meta = script["_meta"]
        path = ROOT / "content" / "topics" / f"{meta['category']}.json"
        text = path.read_text(encoding="utf-8") if path.exists() else "[\n]\n"
        topics = json.loads(text)
        if any(str(t.get("id")) == str(meta["topic_id"]) for t in topics):
            continue
        entry = json.dumps({"id": meta["topic_id"], "topic": script["theme"], "spanish": script["theme"],
                            "theme": script["theme"], "category": meta["category"], "difficulty": "mixed",
                            "level": "A1-C2", "tags": [vtype, "level_family"]}, ensure_ascii=False)
        # Appended as text before the closing bracket: the file's own formatting stays as it is.
        end = text.rstrip().rfind("]")
        head = text[:end].rstrip()
        text = head + ("," if topics else "") + "\n  " + entry + "\n]\n"
        json.loads(text)                                     # still one valid list
        path.write_text(text, encoding="utf-8")
        added[meta["category"]] = added.get(meta["category"], 0) + 1
    return added


def copy(types) -> int:
    """STEP 77 §9: queue the drafts of `types`, keep the drafts; all-or-nothing per run."""
    import length_spec
    from script_schema import validate_script
    plan, problems = [], []
    for vtype in types:
        for p in sorted((ROOT / "content" / "drafts" / vtype).glob("*.json")):
            script = derive(json.loads(p.read_text(encoding="utf-8")))
            if _taken(p.name, vtype, script["_meta"]):
                print(f"{vtype}: {p.name} already queued, done or produced: skipped")
                continue
            try:
                validate_script(script, vtype, source=str(p))
            except Exception as exc:                     # noqa: BLE001
                problems.append(f"{p.name}: {exc}")
                continue
            over = length_spec.check_script(script)
            if over:
                problems.append(f"{p.name}: does not fit: {[(v['where'], v['field']) for v in over]}")
                continue
            plan.append((vtype, p.name, script))
    if problems:
        print("\n".join(problems))
        sys.exit(f"{len(problems)} drafts do not validate: nothing queued")
    print(f"topics added: {add_topics([(vtype, script) for vtype, _n, script in plan])}")
    counts = {}
    for vtype, name, script in plan:
        queue = ROOT / "content" / "queue" / vtype
        queue.mkdir(parents=True, exist_ok=True)
        (queue / name).write_text(json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        counts[vtype] = counts.get(vtype, 0) + 1
    for vtype in types:
        print(f"{vtype}: {counts.get(vtype, 0)} scripts queued (drafts kept)")
    return 0


def main() -> int:
    if "--rederive" in sys.argv[1:]:
        return rederive()
    if "--copy" in sys.argv[1:]:
        return copy([a for a in sys.argv[1:] if a != "--copy"])
    for vtype, category in TOPICS.items():
        drafts = sorted((ROOT / "content" / "drafts" / vtype).glob("*.json"))
        queue = ROOT / "content" / "queue" / vtype
        queue.mkdir(parents=True, exist_ok=True)
        clash = [p.name for p in drafts if (queue / p.name).exists()]
        if clash:
            sys.exit(f"{vtype}: already queued, refusing to overwrite: {clash[:5]}")
        for p in drafts:
            script = derive(json.loads(p.read_text(encoding="utf-8")))
            (queue / p.name).write_text(json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            p.unlink()
        topic = ROOT / "content" / "drafts" / "topics" / f"{category}.json"
        if topic.exists():
            topic.rename(ROOT / "content" / "topics" / topic.name)
        print(f"{vtype}: {len(drafts)} scripts queued, topics/{category}.json moved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
