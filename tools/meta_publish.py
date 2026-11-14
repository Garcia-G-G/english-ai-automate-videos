#!/usr/bin/env python3
"""Publish approved videos to Instagram and Facebook Reels on a schedule.

    python3 tools/meta_publish.py enqueue output/approved/quiz/x.mp4   # or --approved
    python3 tools/meta_publish.py list                  # queued/published/failed + permalink
    python3 tools/meta_publish.py tick [--dry-run]      # publish if a slot is due (cron)
    python3 tools/meta_publish.py now [ARTIFACT] [--dry-run] [--platform facebook]   # ignore the slots
    python3 tools/meta_publish.py loop                  # tick every 5 minutes, forever
    python3 tools/meta_publish.py check                 # credentials + quota, read-only
    python3 tools/meta_publish.py setup-check           # what the Meta setup is missing; exit 0 = ready
    python3 tools/meta_publish.py refresh-token         # the Page token's type and expiry

Slots and platforms come from config.yaml `meta_publish`.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from env_setup import ensure_env_loaded  # noqa: E402

LOOP_SECONDS = 300


def _print(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    enq = sub.add_parser("enqueue")
    enq.add_argument("videos", nargs="*")
    enq.add_argument("--approved", action="store_true", help="queue everything in output/approved/")
    sub.add_parser("list")
    tick = sub.add_parser("tick")
    tick.add_argument("--dry-run", action="store_true")
    now = sub.add_parser("now")
    now.add_argument("artifact", nargs="?")
    now.add_argument("--dry-run", action="store_true")
    now.add_argument("--platform", choices=["instagram", "facebook"], help="only this platform")
    sub.add_parser("loop")
    sub.add_parser("check")
    sub.add_parser("refresh-token")
    sub.add_parser("setup-check")
    args = parser.parse_args(argv)

    ensure_env_loaded()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from publishers import MetaError, PUBLISHERS, get_publisher, schedule

    if args.cmd == "enqueue":
        videos = list(args.videos)
        if args.approved:
            videos += sorted(str(p) for p in (schedule._output() / "approved").glob("*/*.mp4"))
        for video in videos:
            try:
                print("queued", schedule.enqueue(video)["artifact"])
            except ValueError as exc:
                print("refused", exc)
        return 0
    if args.cmd == "list":
        cfg = schedule.settings()
        for row in schedule.status_rows(cfg):
            cells = "  ".join(f"{p}={row[p]['status']} {row[p].get('url') or row[p].get('detail') or ''}".strip()
                              for p in cfg["platforms"])
            print(f"{row['artifact']:40} {cells}")
        return 0
    if args.cmd in ("tick", "now"):
        cfg = schedule.settings()
        if getattr(args, "platform", None):
            cfg = {**cfg, "platforms": [args.platform]}
        _print(schedule.tick(dry=args.dry_run, force=args.cmd == "now",
                             artifact=getattr(args, "artifact", None), cfg=cfg))
        return 0
    if args.cmd == "loop":
        while True:
            _print(schedule.tick())
            time.sleep(LOOP_SECONDS)
    if args.cmd == "check":
        report = {}
        for name in PUBLISHERS:
            publisher = get_publisher(name)
            try:
                report[name] = publisher.check() if publisher.is_configured() else "not configured"
            except MetaError as exc:
                report[name] = f"error: {exc}"
        _print(report)
        return 0
    if args.cmd == "setup-check":
        from publishers.setup import report_lines, setup_report
        report = setup_report()
        print("\n".join(report_lines(report)))
        return 0 if not report["problems"] else 1
    if args.cmd == "refresh-token":
        # Nothing to refresh since STEP 72: Instagram rides on the Page token, which does not expire.
        import os
        from publishers.common import debug_token, expiry_text
        info = debug_token(os.getenv("FB_PAGE_TOKEN", ""))
        _print({"type": info.get("type"), "valid": info.get("is_valid"), "expires": expiry_text(info)})
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
