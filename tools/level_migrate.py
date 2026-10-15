#!/usr/bin/env python3
"""Move the level-family drafts into the queue (STEP 58, true_false_level STEP 61).

    python3 tools/level_migrate.py
    python3 tools/level_migrate.py --rederive   # queue files again, after a LEVEL_PLANS change

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

from tts_elevenlabs import LEVEL_PLANS, LEVEL_TIER_LINES, level_answer  # noqa: E402

TOPICS = {"level_test": "level_vocab", "say_it_level": "say_it", "true_false_level": "false_friends"}


def derive(script: dict) -> dict:
    """The derived fields, in the order the audio speaks them."""
    plan = LEVEL_PLANS[script["type"]]
    items = script["items"]
    spoken = [script["intro"]]
    for i, item in enumerate(items, start=1):
        if i in LEVEL_TIER_LINES:
            spoken.append(LEVEL_TIER_LINES[i])
        if plan["speak_prompt"]:
            spoken.append(item[plan["prompt"][0]])
        spoken.append(level_answer(item, plan["answer"][0]))
    spoken += [script["verdict"], script["outro"]]
    out = dict(script)
    if script["type"] == "true_false_level":
        # The English word of each statement, the one in «»; nothing is spoken in English.
        out["translations"] = {}
        out["english_phrases"] = [re.search(r"«([^»]+)»", it["statement"]).group(1) for it in items]
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


def main() -> int:
    if "--rederive" in sys.argv[1:]:
        return rederive()
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
