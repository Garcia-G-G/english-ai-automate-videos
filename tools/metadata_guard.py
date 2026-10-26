"""STEP 80 §0: no title or description with empty quotes ('' "" «») or a leftover {} / [[ ]].

    python3 tools/metadata_guard.py [REPORT.md]

1. Every queued script (the main queue and the series'): the metadata generate_metadata gives
   it now — which must pass — and its own video_title / video_description, which the guard now
   replaces when they fail.
2. Everything already published (output/published/ledger.jsonl): the titles and descriptions as
   they went out, for Garcia to edit by hand.

No LLM, no network: generate_metadata's template path only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import metadata_generator as M  # noqa: E402


def queued() -> list:
    import queue_guard
    import series
    return list(queue_guard.queued_scripts()) + sorted(series.QUEUE_DIR.glob("hc_*.json"))


def check_queue() -> dict:
    now_bad, own_bad = [], []
    for path in queued():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        vtype = data.get("type") or data.get("video_type") or path.parent.name
        meta = M.generate_metadata(data, vtype)
        for field in ("title", "description"):
            if M.metadata_problems(meta[field]):
                now_bad.append((path, field, meta[field]))
        for field in ("video_title", "video_description", "title", "caption"):
            if data.get(field) and M.metadata_problems(str(data[field])):
                own_bad.append((path, field, str(data[field])))
    return {"count": len(queued()), "now_bad": now_bad, "own_bad": own_bad}


def check_published() -> list:
    ledger = ROOT / "output" / "published" / "ledger.jsonl"
    out = []
    if not ledger.exists():
        return out
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        for field in ("published_title", "published_description"):
            text = row.get(field) or ""
            problems = M.metadata_problems(text)
            if problems:
                out.append({"platform": row.get("platform"), "url": row.get("url") or row.get("upload_id"),
                            "field": field.replace("published_", ""), "text": text[:120].replace("\n", " "),
                            "why": ", ".join(problems), "at": (row.get("published_at") or "")[:10]})
    return out


def report(q: dict, published: list) -> str:
    rel = lambda p: str(Path(p).relative_to(ROOT))
    lines = ["# Metadata guard (STEP 80 §0)", "",
             f"Queued scripts checked: {q['count']}.", "",
             f"**Metadata generated now that fails the guard: {len(q['now_bad'])}.**", ""]
    lines += [f"- `{rel(p)}` {f}: {t!r}" for p, f, t in q["now_bad"]]
    lines += ["", f"Scripts whose own field fails (the guard replaces it at render time): {len(q['own_bad'])}", ""]
    lines += [f"- `{rel(p)}` {f}: {t[:100]!r}" for p, f, t in q["own_bad"]]
    lines += ["", f"## Published with a problem: {len(published)} — edit by hand", "",
              "| date | platform | field | text | why | link |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['at']} | {r['platform']} | {r['field']} | {r['text']} | {r['why']} | {r['url']} |" for r in published]
    return "\n".join(lines) + "\n"


def main(argv: list) -> int:
    q, published = check_queue(), check_published()
    text = report(q, published)
    if argv:
        Path(argv[0]).write_text(text, encoding="utf-8")
    print(text)
    return 1 if q["now_bad"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
