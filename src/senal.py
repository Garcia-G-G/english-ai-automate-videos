"""Señal: score each video against the typical curve of its format. Pure functions here."""
from datetime import date
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
SENAL_DIR = ROOT / "output" / "senal"

BREAKOUT_SCORE = 2.0
BREAKOUT_MIN_VIEWS = 300
COLD_SCORE = 0.5
WHY_RATIO = 1.5
DAYS = 14
COHORT_DAYS = 90
MIN_COHORT = 8
SECOND_WIND_MIN = 20  # a day-3+ rise under 20 views is noise


def typical(videos: list[dict], fmt: str, today: date, exclude: str | None = None):
    """(daily, cum) median curves for ages 0..DAYS; age = len(daily) - 1."""
    recent = [v for v in videos if v["id"] != exclude
              and (today - date.fromisoformat(v["published"])).days <= COHORT_DAYS]
    cohort = [v for v in recent if v["format"] == fmt]
    if len(cohort) < MIN_COHORT:
        cohort = recent
    daily, cum, total = [], [], 0.0
    for a in range(DAYS + 1):
        vals = [v["daily"][a] for v in cohort if len(v["daily"]) > a]
        m = median(vals) if vals else 0
        total += m
        daily.append(m)
        cum.append(total)
    return daily, cum


def score(daily: list[int], cum_typical: list[float]) -> float | None:
    typ = cum_typical[min(len(daily) - 1, len(cum_typical) - 1)]
    return sum(daily) / typ if typ else None


def state(daily: list[int], score: float | None, views: int) -> str:
    if score is not None and score >= BREAKOUT_SCORE and views >= BREAKOUT_MIN_VIEWS:
        return "breakout"
    old = len(daily) - 1 >= 3
    if old and daily[-1] >= SECOND_WIND_MIN and daily[-1] > daily[-2]:
        return "second_wind"
    if old and score is not None and score < COLD_SCORE:
        return "cold"
    return "normal"


def _ratio(value, base):
    if not value:
        return 0.0
    return value / base if base else float("inf")


def why(video: dict, medians: dict, channel_sources: dict) -> list[str]:
    views = video["views"]
    if not views:
        return []
    src = video["sources"]
    ratios = {
        "search": _ratio(src.get("YT_SEARCH", 0), channel_sources.get("YT_SEARCH", 0)),
        "external": _ratio(src.get("EXT", 0), channel_sources.get("EXT", 0)),
        "retention": _ratio(video["retention"], medians["retention"]),
        "shares": _ratio(video["shares"] * 1000 / views, medians["shares_per_1k"]),
        "subs": _ratio(video["subs"] * 1000 / views, medians["subs_per_1k"]),
    }
    return sorted((k for k, r in ratios.items() if r > WHY_RATIO), key=lambda k: -ratios[k])
