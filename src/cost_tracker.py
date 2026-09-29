#!/usr/bin/env python3
"""
API Cost Tracker for English AI Videos.

Tracks spending on OpenAI (GPT, TTS, Whisper, DALL-E) and ElevenLabs per video.
Logs to output/costs/ as JSON and provides session/daily/monthly summaries.

Usage:
    from cost_tracker import CostTracker
    tracker = CostTracker()
    tracker.log_openai_chat(prompt_tokens=2000, completion_tokens=500, model="gpt-4o-mini")
    tracker.log_elevenlabs_tts(characters=1500)
    tracker.log_openai_tts(characters=800)
    tracker.log_openai_whisper(duration_seconds=28.5)
    tracker.log_image(count=1)
    tracker.print_summary()
    tracker.save()

Reports:
    python3 src/cost_tracker.py               # daily, last 7 days
    python3 src/cost_tracker.py --videos 30   # per video, OpenAI vs ElevenLabs
"""

import json
import logging
import os
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
COSTS_DIR = ROOT / "output" / "costs"

# ============================================================
# PRICING (as of 2026 — update if rates change)
# ============================================================
PRICING = {
    # OpenAI Chat Completions
    "gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60},
    "gpt-4o": {"input_per_1m": 2.50, "output_per_1m": 10.00},
    "gpt-4": {"input_per_1m": 30.00, "output_per_1m": 60.00},
    # OpenAI TTS
    "tts-1": {"per_1m_chars": 15.00},
    "tts-1-hd": {"per_1m_chars": 30.00},
    # OpenAI Whisper
    "whisper-1": {"per_minute": 0.006},
    # OpenAI images — priced in image_gen.PER_IMAGE_USD, which is keyed by
    # (model, size, quality) and is the single source of truth. Nothing is
    # duplicated here; log_image() reads it directly. dall-e-3 entries are
    # gone with the model (retired from the API 2026-05-12), along with the
    # $0.080 figure that under-reported hd calls by a third.
    # ElevenLabs TTS (Starter plan ~$5/30k chars, Creator ~$22/100k chars)
    # Using Creator plan rate: $0.22 per 1k chars = $220 per 1M chars
    "eleven_v3": {"per_1m_chars": 220.00},
    "eleven_multilingual_v2": {"per_1m_chars": 220.00},
    "eleven_turbo_v2_5": {"per_1m_chars": 110.00},
}


def provider_of(api_type: str) -> str:
    """Which bill a ledger row lands on: "openai" or "elevenlabs".

    "dalle3" is retired but still appears in cost logs already on disk, so
    it stays here to keep those reading correctly.
    """
    api_type = api_type or ""
    if api_type.startswith("openai") or api_type == "dalle3":
        return "openai"
    if api_type.startswith("elevenlabs"):
        return "elevenlabs"
    return "other"


class CostTracker:
    """Tracks API costs per video and across sessions."""

    def __init__(self, video_id: str = None):
        self.video_id = video_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.entries = []
        # How many entries are already on disk. save() appends only the rest,
        # so a run that saves on success AND in its failure path cannot
        # write the same call twice.
        self._saved = 0
        self._start_time = time.time()
        COSTS_DIR.mkdir(parents=True, exist_ok=True)

    def log_openai_chat(self, prompt_tokens: int, completion_tokens: int,
                        model: str = "gpt-4o-mini", label: str = "script_generation"):
        """Log an OpenAI Chat Completion API call."""
        pricing = PRICING.get(model, PRICING["gpt-4o-mini"])
        cost = (prompt_tokens * pricing["input_per_1m"] / 1_000_000 +
                completion_tokens * pricing["output_per_1m"] / 1_000_000)
        self._add_entry("openai_chat", model, cost, label, {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        })
        return cost

    def log_openai_tts(self, characters: int, model: str = "tts-1", label: str = "tts"):
        """Log an OpenAI TTS API call."""
        pricing = PRICING.get(model, PRICING["tts-1"])
        cost = characters * pricing["per_1m_chars"] / 1_000_000
        self._add_entry("openai_tts", model, cost, label, {
            "characters": characters,
        })
        return cost

    def log_openai_whisper(self, duration_seconds: float, label: str = "timestamps"):
        """Log an OpenAI Whisper API call."""
        import math
        minutes = math.ceil(duration_seconds / 60)
        cost = minutes * PRICING["whisper-1"]["per_minute"]
        self._add_entry("openai_whisper", "whisper-1", cost, label, {
            "duration_seconds": round(duration_seconds, 2),
            "billed_minutes": minutes,
        })
        return cost

    def log_image(self, count: int = 1, size: str = "1024x1536",
                  quality: str = "medium", model: str = None,
                  label: str = "background_image"):
        """Log a gpt-image generation call."""
        from image_gen import IMAGE_MODEL, price_per_image
        model = model or IMAGE_MODEL
        per_image = price_per_image(quality, size, model)
        if per_image == 0.0:
            logger.warning("No price for %s %s %s — logging $0.00",
                           model, size, quality)
        cost = count * per_image
        self._add_entry("openai_image", model, cost, label, {
            "images": count,
            "size": size,
            "quality": quality,
        })
        return cost

    def log_elevenlabs_tts(self, characters: int, model: str = "eleven_v3",
                           label: str = "tts"):
        """Log an ElevenLabs TTS API call."""
        pricing = PRICING.get(model, PRICING["eleven_v3"])
        cost = characters * pricing["per_1m_chars"] / 1_000_000
        self._add_entry("elevenlabs_tts", model, cost, label, {
            "characters": characters,
        })
        return cost

    def _add_entry(self, api_type: str, model: str, cost: float,
                   label: str, details: dict):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "api_type": api_type,
            "model": model,
            "cost_usd": round(cost, 6),
            "label": label,
            "video_id": self.video_id,
            **details,
        }
        self.entries.append(entry)
        logger.info("[$%.4f] %s (%s) — %s", cost, api_type, model, label)

    def rename(self, video_id: str) -> None:
        """Give this run its final name, including the calls already logged.

        THE SCRIPT WAS PAID FOR BEFORE THE VIDEO HAD A NAME. The dashboard
        door calls GPT for the script, and only then builds the artifact
        name the ledger is keyed on. Resetting the tracker at that point left
        the script's cost on the PREVIOUS video's tracker -- usually one that
        had already been saved, so the cost was never written at all: 17
        openai_chat rows across 123 videos. Opening the tracker at job start
        and renaming it here keeps every call of the run under one id.
        """
        self.video_id = video_id
        for e in self.entries:
            e["video_id"] = video_id

    def summary(self) -> dict:
        """This run's spend, split the way the per-video report splits it."""
        by_provider = self.cost_by_provider
        return {
            "total_usd": round(self.total_cost, 6),
            "openai_usd": round(by_provider.get("openai", 0.0), 6),
            "elevenlabs_usd": round(by_provider.get("elevenlabs", 0.0), 6),
            "calls": len(self.entries),
        }

    @property
    def total_cost(self) -> float:
        return sum(e["cost_usd"] for e in self.entries)

    @property
    def cost_by_provider(self) -> dict:
        costs = {}
        for e in self.entries:
            provider = provider_of(e["api_type"])
            costs[provider] = costs.get(provider, 0) + e["cost_usd"]
        return costs

    @property
    def cost_by_type(self) -> dict:
        costs = {}
        for e in self.entries:
            costs[e["api_type"]] = costs.get(e["api_type"], 0) + e["cost_usd"]
        return costs

    def print_summary(self):
        """Print a cost summary to the console."""
        total = self.total_cost
        by_provider = self.cost_by_provider
        by_type = self.cost_by_type

        print(f"\n{'='*50}")
        print(f"  COST SUMMARY — {self.video_id}")
        print(f"{'='*50}")
        print(f"  Total: ${total:.4f}")
        print()
        print(f"  By Provider:")
        for provider, cost in sorted(by_provider.items()):
            print(f"    {provider:15s}: ${cost:.4f}")
        print()
        print(f"  By API Type:")
        for api_type, cost in sorted(by_type.items()):
            print(f"    {api_type:20s}: ${cost:.4f}")
        print(f"{'='*50}\n")

    def save(self) -> Path:
        """Append the entries not yet on disk to today's JSONL log.

        Safe to call more than once: only calls logged since the last save
        are written.
        """
        new = self.entries[self._saved:]
        if not new:
            return None

        today = date.today().isoformat()
        log_path = COSTS_DIR / f"costs_{today}.jsonl"

        with open(log_path, 'a', encoding='utf-8') as f:
            for entry in new:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        self._saved = len(self.entries)

        logger.info("Cost log saved: %s (%d entries, $%.4f)",
                     log_path.name, len(new), sum(e["cost_usd"] for e in new))
        return log_path


# ============================================================
# GLOBAL TRACKER (shared across pipeline)
# ============================================================
_current_tracker: Optional[CostTracker] = None


def get_tracker(video_id: str = None) -> CostTracker:
    """Get or create the current cost tracker."""
    global _current_tracker
    if _current_tracker is None or (video_id and _current_tracker.video_id != video_id):
        _current_tracker = CostTracker(video_id)
    return _current_tracker


def reset_tracker(video_id: str = None) -> CostTracker:
    """Create a fresh tracker for a new video."""
    global _current_tracker
    _current_tracker = CostTracker(video_id)
    return _current_tracker


# ============================================================
# REPORTING
# ============================================================

def get_daily_costs(days: int = 7) -> dict:
    """Get cost summaries for the last N days."""
    summaries = {}
    for log_file in sorted(COSTS_DIR.glob("costs_*.jsonl")):
        day = log_file.stem.replace("costs_", "")
        day_total = 0.0
        day_entries = 0
        by_type = {}

        with open(log_file, 'r') as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    day_total += entry.get("cost_usd", 0)
                    day_entries += 1
                    api_type = entry.get("api_type", "unknown")
                    by_type[api_type] = by_type.get(api_type, 0) + entry.get("cost_usd", 0)

        summaries[day] = {
            "total_usd": round(day_total, 4),
            "entries": day_entries,
            "by_type": {k: round(v, 4) for k, v in by_type.items()},
        }

    # Return last N days
    sorted_days = sorted(summaries.keys(), reverse=True)[:days]
    return {d: summaries[d] for d in sorted_days}


def get_monthly_total() -> float:
    """Get total cost for the current month."""
    current_month = date.today().strftime("%Y-%m")
    total = 0.0
    for log_file in COSTS_DIR.glob(f"costs_{current_month}*.jsonl"):
        with open(log_file, 'r') as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    total += entry.get("cost_usd", 0)
    return round(total, 4)


def print_report(days: int = 7):
    """Print a cost report for the last N days."""
    daily = get_daily_costs(days)
    monthly = get_monthly_total()

    print(f"\n{'='*55}")
    print(f"  API COST REPORT")
    print(f"{'='*55}")
    print(f"  Month total: ${monthly:.4f}")
    print()

    if daily:
        print(f"  Last {min(days, len(daily))} days:")
        for day, data in sorted(daily.items(), reverse=True):
            types = ", ".join(f"{k}=${v:.3f}" for k, v in data["by_type"].items())
            print(f"    {day}: ${data['total_usd']:.4f} ({data['entries']} calls) — {types}")
    else:
        print(f"  No cost data found in {COSTS_DIR}")

    print(f"{'='*55}\n")


# ============================================================
# PER VIDEO
# ============================================================

def per_video_costs(costs_dir: Path = None) -> list:
    """Every video in the ledger with what it cost, newest first.

    One row per `video_id`, which is the artifact name (admin writes it into
    the video's .json as `artifact`), split by provider because the two
    bills are paid separately and move for different reasons: OpenAI with
    scripts and images, ElevenLabs with narration length.

    `session_*` ids are calls made outside any video (a CLI session, a
    tracker nobody named). They are kept, not dropped, so the per-video
    total still reconciles with the daily one.
    """
    cdir = Path(costs_dir) if costs_dir else COSTS_DIR
    videos = {}
    if not cdir.is_dir():
        return []
    for log_file in sorted(cdir.glob("costs_*.jsonl")):
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    e = json.loads(line)
                    cost = float(e.get("cost_usd") or 0)
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                vid = e.get("video_id") or "unknown"
                row = videos.setdefault(vid, {
                    "video_id": vid, "openai_usd": 0.0, "elevenlabs_usd": 0.0,
                    "other_usd": 0.0, "total_usd": 0.0, "calls": 0,
                    "by_type": {}, "first_at": None, "last_at": None,
                })
                row[f"{provider_of(e.get('api_type'))}_usd"] += cost
                row["total_usd"] += cost
                row["calls"] += 1
                api_type = e.get("api_type", "unknown")
                row["by_type"][api_type] = row["by_type"].get(api_type, 0.0) + cost
                ts = e.get("timestamp")
                if ts:
                    row["first_at"] = min(filter(None, (row["first_at"], ts)))
                    row["last_at"] = max(filter(None, (row["last_at"], ts)))

    rows = list(videos.values())
    for row in rows:
        for key in ("openai_usd", "elevenlabs_usd", "other_usd", "total_usd"):
            row[key] = round(row[key], 6)
        row["by_type"] = {k: round(v, 6) for k, v in row["by_type"].items()}
    rows.sort(key=lambda r: r["last_at"] or "", reverse=True)
    return rows


def video_cost_stats(rows: list) -> dict:
    """Average and median per video, over real videos only.

    `session_*` rows are excluded here (not from per_video_costs): they are
    not videos, and one long CLI session would skew "what does a video cost".
    An outlier is a video over twice the median -- derived from the ledger,
    not a budget someone chose.
    """
    import statistics
    real = [r for r in rows if not r["video_id"].startswith("session_")]
    if not real:
        return {"videos": 0, "mean_usd": 0.0, "median_usd": 0.0,
                "openai_mean_usd": 0.0, "elevenlabs_mean_usd": 0.0,
                "outliers": []}
    totals = [r["total_usd"] for r in real]
    median = statistics.median(totals)
    return {
        "videos": len(real),
        "mean_usd": round(statistics.mean(totals), 4),
        "median_usd": round(median, 4),
        "openai_mean_usd": round(statistics.mean(r["openai_usd"] for r in real), 4),
        "elevenlabs_mean_usd": round(statistics.mean(r["elevenlabs_usd"] for r in real), 4),
        "outliers": [r["video_id"] for r in real
                     if median and r["total_usd"] > 2 * median],
    }


def print_video_report(limit: int = 20, costs_dir: Path = None):
    """Print what the last `limit` videos cost, split by provider."""
    rows = per_video_costs(costs_dir)
    stats = video_cost_stats(rows)
    outliers = set(stats["outliers"])

    print(f"\n{'='*86}")
    print(f"  COST PER VIDEO — last {min(limit, len(rows))} of {len(rows)}")
    print(f"{'='*86}")
    print(f"  {'video':44} {'OpenAI':>9} {'ElevenLabs':>11} {'total':>9} {'calls':>6}")
    for r in rows[:limit]:
        flag = " ⚠" if r["video_id"] in outliers else ""
        print(f"  {r['video_id'][:44]:44} ${r['openai_usd']:>8.4f} "
              f"${r['elevenlabs_usd']:>10.4f} ${r['total_usd']:>8.4f} "
              f"{r['calls']:>6}{flag}")
    print()
    print(f"  {stats['videos']} videos · mean ${stats['mean_usd']:.4f} "
          f"(OpenAI ${stats['openai_mean_usd']:.4f} + ElevenLabs "
          f"${stats['elevenlabs_mean_usd']:.4f}) · median ${stats['median_usd']:.4f}")
    if outliers:
        print(f"  ⚠ {len(outliers)} over twice the median")
    print(f"{'='*86}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="API cost reports")
    parser.add_argument("--videos", type=int, nargs="?", const=20, default=None,
                        metavar="N", help="cost per video, last N (default 20)")
    parser.add_argument("--days", type=int, default=7,
                        help="days in the daily report (default 7)")
    args = parser.parse_args()
    if args.videos is not None:
        print_video_report(args.videos)
    else:
        print_report(args.days)
