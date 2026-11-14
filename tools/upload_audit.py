"""STEP 80: what every published upload looks like to its platform — the problems that never fail
in the code but do on YouTube, Facebook or Instagram (src/platform_rules.py, official limits).

    python3 tools/upload_audit.py [LEDGER] [--md OUT.md]

Reads the publication ledger (what was sent). Prints each problem with how many uploads carry it
and examples; «bloquea» = the platform refuses or ignores it, «aviso» = it goes out, not as meant.
Free and offline: it reads no API. The long Manim lessons (not Shorts) are judged as long-form.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import platform_rules as R  # noqa: E402

LEDGER = ROOT / "output" / "published" / "ledger.jsonl"
LONG_FORM_TYPES = {"manim_lesson"}


def _is_short(row: Dict) -> bool:
    return row.get("video_type") not in LONG_FORM_TYPES and "english-teacher" not in str(row.get("artifact"))


def audit(ledger: Optional[Path] = None) -> Dict:
    ledger = Path(ledger or LEDGER)
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_code, examples, severity, message = Counter(), defaultdict(list), {}, {}
    for row in rows:
        found = R.problems(row.get("platform", ""), row.get("published_title") or "",
                           row.get("published_description") or "", row.get("hashtags") or [],
                           short=_is_short(row))
        for p in found:
            by_code[p["code"]] += 1
            severity[p["code"]] = p["severity"]
            message.setdefault(p["code"], p["message"])
            if len(examples[p["code"]]) < 5:
                examples[p["code"]].append(f'{row.get("platform")}:{row.get("artifact")}')
    blocking = sum(n for code, n in by_code.items() if severity[code] == "bloquea")
    return {"rows": len(rows), "by_code": dict(by_code), "severity": severity, "message": message,
            "examples": dict(examples), "blocking": blocking}


def markdown(report: Dict) -> str:
    lines = [f"# Upload audit — {report['rows']} publications", "",
             f"Blocking problems: **{report['blocking']}**.", "",
             "| problem | severity | uploads | example message | examples |", "|---|---|---|---|---|"]
    for code, n in sorted(report["by_code"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| `{code}` | {report['severity'][code]} | {n} | {report['message'][code][:120]} | "
                     f"{', '.join(report['examples'][code][:3])} |")
    return "\n".join(lines) + "\n"


def main(argv) -> int:
    md = None
    if "--md" in argv:
        md = Path(argv[argv.index("--md") + 1])
        argv = argv[:argv.index("--md")]
    report = audit(Path(argv[0]) if argv else None)
    text = markdown(report)
    print(text)
    if md:
        md.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
