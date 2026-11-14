"""market_research: most-viewed Shorts on a topic across YouTube, for the real audience, cached."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import market_research as M  # noqa: E402


class _Resp:
    def __init__(self, data): self.data = data
    def raise_for_status(self): pass
    def json(self): return self.data


def _video(vid, views, duration="PT30S", kids=False, lang="es"):
    return {"id": vid, "snippet": {"title": vid, "channelTitle": "c", "defaultAudioLanguage": lang},
            "statistics": {"viewCount": str(views)}, "contentDetails": {"duration": duration},
            "status": {"madeForKids": kids}}


def test_keeps_short_adult_spanish_videos_best_first_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "CACHE_DIR", tmp_path)
    calls = []

    def get(url, params, headers, timeout):
        calls.append(url)
        if url == M.SEARCH_URL:
            return _Resp({"items": [{"id": {"videoId": v}} for v in "abcde"]})
        return _Resp({"items": [_video("a", 10), _video("b", 900), _video("c", 5000, kids=True),
                                _video("d", 7000, lang="fr"), _video("e", 9000, duration="PT4M")]})
    got = M.search("cómo se dicen los números en inglés", token="t", get=get)
    assert [v["id"] for v in got] == ["b", "a"]                 # no kids, no French, no 4-minute video
    assert M.search("cómo se dicen los números en inglés", token="t", get=get) == got and len(calls) == 2


def test_the_topic_query_keeps_its_agreement():
    assert M.queries("how_do_you_say", "los números")[0] == "cómo se dicen los números en inglés"
    assert M.queries("how_do_you_say", "la cara")[0] == "cómo se dice la cara en inglés"
    assert M._seconds("PT1M5S") == 65


def test_no_network_under_pytest():
    assert M.top_videos("how_do_you_say", "la cara") == []
