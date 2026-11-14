#!/usr/bin/env python3
"""Write _audit/STEP58_length_report.md: length_spec over every level script.

    python3 tools/level_length_report.py

Reads content/queue/<type>/, content/queue/_done/ and _skipped/ (a rendered script is
moved there, it still counts). Measured with the renderer's own fit.
"""
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import length_spec  # noqa: E402

TYPES = ("level_test", "say_it_level")
OUT = ROOT / "_audit" / "STEP58_length_report.md"


def scripts(vtype):
    queue = ROOT / "content" / "queue"
    found = list((queue / vtype).glob("*.json"))
    # _done: rendered; _skipped: set aside, topic already produced (STEP 78b §2). Both still written.
    for path in [*(queue / "_done").glob("*.json"), *(queue / "_skipped").glob("*.json")]:
        if json.loads(path.read_text(encoding="utf-8")).get("type") == vtype:
            found.append(path)
    return sorted(found, key=lambda p: p.name)


def main():
    out = [f"# STEP 58 — length_spec over the level scripts\n",
           f"Measured {datetime.date.today()} with the renderer's own fit (Fredoka Bold), "
           f"by `tools/level_length_report.py`, over content/queue/<type>/ and content/queue/_done/.\n"]
    for vtype in TYPES:
        paths = scripts(vtype)
        rows = []
        for path in paths:
            script = json.loads(path.read_text(encoding="utf-8"))
            for v in length_spec.check_script(script):
                rows.append((path.stem.split("_")[0], int(v["where"].split("[")[1].rstrip("]")) + 1,
                             v["field"], v["text"], v["over_width"], v["over_lines"]))
        out.append(f"## {vtype}: {len(paths)} scripts, {len(rows)} texts do not fit, "
                   f"in {len({r[0] for r in rows})} scripts\n")
        if rows:
            out.append("| script | item | field | text | over (px) | extra lines |\n|---|---|---|---|---|---|")
            out += [f"| {s} | {i} | {f} | {t} | {w} | {lines} |" for s, i, f, t, w, lines in rows]
            out.append("")
    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(line for line in out if line.startswith("## ")))


if __name__ == "__main__":
    main()
