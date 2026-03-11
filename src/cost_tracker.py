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
    tracker.log_dalle(count=1)
    tracker.print_summary()
    tracker.save()
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
    # OpenAI DALL-E 3
    "dall-e-3-1024x1792-hd": {"per_image": 0.080},
    "dall-e-3-1024x1024-hd": {"per_image": 0.080},
    "dall-e-3-1024x1024-standard": {"per_image": 0.040},
    # ElevenLabs TTS (Starter plan ~$5/30k chars, Creator ~$22/100k chars)
    # Using Creator plan rate: $0.22 per 1k chars = $220 per 1M chars
    "eleven_v3": {"per_1m_chars": 220.00},
    "eleven_multilingual_v2": {"per_1m_chars": 220.00},
    "eleven_turbo_v2_5": {"per_1m_chars": 110.00},
}


class CostTracker:
    """Tracks API costs per video and across sessions."""

    def __init__(self, video_id: str = None):
        self.video_id = video_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.entries = []
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

    def log_dalle(self, count: int = 1, size: str = "1024x1792",
                  quality: str = "hd", label: str = "background_image"):
        """Log a DALL-E 3 image generation call."""
        key = f"dall-e-3-{size}-{quality}"
        pricing = PRICING.get(key, PRICING["dall-e-3-1024x1792-hd"])
        cost = count * pricing["per_image"]
        self._add_entry("dalle3", "dall-e-3", cost, label, {
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

    @property
    def total_cost(self) -> float:
        return sum(e["cost_usd"] for e in self.entries)

    @property
    def cost_by_provider(self) -> dict:
        costs = {}
        for e in self.entries:
            provider = "openai" if e["api_type"].startswith("openai") or e["api_type"] == "dalle3" else "elevenlabs"
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
        """Save cost entries to a JSON log file."""
        if not self.entries:
            return None

        today = date.today().isoformat()
        log_path = COSTS_DIR / f"costs_{today}.jsonl"

        with open(log_path, 'a', encoding='utf-8') as f:
            for entry in self.entries:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

        logger.info("Cost log saved: %s (%d entries, $%.4f)",
                     log_path.name, len(self.entries), self.total_cost)
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


if __name__ == "__main__":
    print_report()
