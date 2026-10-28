"""channel_insights.brief: the channel's own numbers, best first, and no network under pytest."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import channel_insights as C  # noqa: E402


def _v(title, views, vtype="how_do_you_say", days=10):
    return {"title": title, "views": views, "type": vtype, "days": days}


STATS = {"videos": [_v(f"T{i}", i * 100) for i in range(1, 11)]
         + [_v("Q", 50, "quiz"), _v("Q2", 60, "quiz"), _v("Q3", 70, "quiz"), _v("NEW", 99999, days=0)]}


def test_best_and_worst_titles_of_the_type_and_medians_by_type():
    text = C.brief("how_do_you_say", stats=STATS, top=3)
    best = text.index("1000 vistas — T10")
    assert best < text.index("900 vistas — T9") < text.index("800 vistas — T8")
    assert "Peores" in text and "100 vistas — T1" in text
    assert "NEW" not in text                                   # under MATURE_DAYS: not judged yet
    assert "how_do_you_say 550, quiz 60" in text
    assert "LO MÁS VISTO EN TODO YOUTUBE" not in text         # market research is off under pytest


def test_without_statistics_only_the_lessons_remain():
    text = C.brief("quiz", stats={"videos": []})
    assert text.count("\n- ") == len(C.LESSONS) and "Mejores" not in text


def test_importing_the_renderer_does_not_reseed_the_global_random():
    import random
    random.seed(7); expected = random.random()
    random.seed(7)
    import importlib, video.backgrounds as B
    importlib.reload(B)
    assert random.random() == expected
