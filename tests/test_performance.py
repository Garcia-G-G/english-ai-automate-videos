"""STEP 80 §2: the channel's numbers, and the queue ordered by what works. No network: the YouTube
and Facebook readers are faked."""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import channel_stats as C  # noqa: E402
import queue_priority as Q  # noqa: E402


def _ledger(tmp_path):
    rows = [{"platform": "youtube", "upload_id": "a1", "video_type": "how_do_you_say", "published_at": "2026-10-01T10:00:00",
             "published_title": "¿Cómo se dice CASA en inglés? 🏠", "url": "u1"},
            {"platform": "youtube", "upload_id": "a2", "video_type": "choose_level", "published_at": "2026-10-20T10:00:00",
             "published_title": "Elige la correcta 🤔", "url": "u2"},
            {"platform": "youtube", "upload_id": "a3", "video_type": "how_do_you_say", "published_at": "2026-10-25T10:00:00",
             "published_title": "¿Cómo se dicen los ANIMALES en inglés? 🐶", "url": "u3"},
            {"platform": "facebook", "upload_id": "f1", "video_type": "how_do_you_say", "published_at": "2026-10-02"},
            {"platform": "youtube", "upload_id": "a1", "video_type": "how_do_you_say", "published_at": "2026-10-01"}]   # a duplicate row
    path = tmp_path / "ledger.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


class _Resp:
    def __init__(self, items):
        self.items = items

    def raise_for_status(self):
        pass

    def json(self):
        return {"items": self.items}


def _get(views):
    def get(url, params, headers, timeout):
        assert headers["Authorization"] == "Bearer tok" and "statistics" in params["part"]
        return _Resp([{"id": i, "statistics": {"viewCount": str(v)}, "snippet": {"title": f"t{i}"}}
                      for i, v in views.items() if i in params["id"].split(",")])
    return get


def test_youtube_rows_come_from_the_ledger_once_each(tmp_path):
    rows = C.youtube_rows(_ledger(tmp_path))
    assert [r["id"] for r in rows] == ["a1", "a2", "a3"]


def test_refresh_writes_the_days_snapshot_with_days_and_categories(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "LEDGER", _ledger(tmp_path))
    monkeypatch.setattr(C, "STATS_DIR", tmp_path / "stats")
    path = C.refresh(date(2026, 10, 26), get=_get({"a1": 1200, "a2": 140, "a3": 90}), token="tok",
                     facebook=lambda: {"views": {}, "note": "sin FB_PAGE_TOKEN"})
    snap = json.loads(path.read_text())
    assert path.name == "youtube_2026-10-26.json"
    by = {v["id"]: v for v in snap["videos"]}
    assert by["a1"]["days"] == 25 and by["a1"]["views"] == 1200
    assert C.category_word("¿Cómo se dicen los ANIMALES en inglés? 🐶", "how_do_you_say") == "ANIMALES"
    assert snap["facebook"]["note"] == "sin FB_PAGE_TOKEN"


def test_the_summary_judges_formats_on_videos_older_than_three_days():
    vids = [{"id": "1", "type": "how_do_you_say", "views": 1200, "days": 20, "title": "x", "category": "CASA"},
            {"id": "2", "type": "how_do_you_say", "views": 1000, "days": 10, "title": "x", "category": "FRUTA"},
            {"id": "3", "type": "how_do_you_say", "views": 20, "days": 1, "title": "x", "category": "MAR"},
            {"id": "4", "type": "choose_level", "views": 150, "days": 9, "title": "x", "category": "choose_level"}]
    s = C.summary(vids)
    f = {x["type"]: x for x in s["formats"]}
    assert f["how_do_you_say"]["mature_median"] == 1100 and f["how_do_you_say"]["count"] == 3
    assert s["formats"][0]["type"] == "how_do_you_say"
    assert [v["id"] for v in s["top"]][:2] == ["1", "2"] and s["bottom"][0]["id"] == "3"


def test_facebook_reads_video_insights_or_says_why_not(tmp_path, monkeypatch):
    ledger = _ledger(tmp_path)
    monkeypatch.delenv("FB_PAGE_TOKEN", raising=False)
    assert "sin FB_PAGE_TOKEN" in C.fetch_facebook(ledger)["note"]
    monkeypatch.setenv("FB_PAGE_TOKEN", "x")
    got = C.fetch_facebook(ledger, call=lambda vid: {"data": [{"values": [{"value": 77}]}]})
    assert got["views"] == {"f1": 77}

    def refuse(vid):
        raise RuntimeError("(#10) permission")
    assert "permission" in C.fetch_facebook(ledger, call=refuse)["note"]


# ── the queue's order ────────────────────────────────────────────────

CFG = {"prior_views": {"how_do_you_say": 1150, "choose_level": 150}, "a1": ["fruta", "casa"], "default_prior": 100.0}


def test_a_type_is_scored_by_its_measured_median_once_it_has_three_mature_videos():
    stats = {"videos": [{"type": "choose_level", "views": v, "days": 10} for v in (400, 500, 600)]
             + [{"type": "how_do_you_say", "views": 2000, "days": 1}]}
    scores = Q.type_scores(stats, CFG)
    assert scores["choose_level"] == {"score": 500.0, "source": "medida", "n": 3}
    assert scores["how_do_you_say"]["source"] == "previa"                   # 1 video, and too young


def test_an_a1_category_is_boosted_and_the_why_says_so():
    scores = Q.type_scores({}, CFG)
    p, why = Q.priority({"type": "how_do_you_say", "theme": "la fruta"}, scores, CFG)
    assert p == 1150 * Q.A1_BOOST and "categoría A1 «fruta»" in why
    p2, why2 = Q.priority({"type": "choose_level", "title": "Speak o talk"}, scores, CFG)
    assert p2 == 150 and "estimación previa" in why2


def test_ranked_puts_the_best_first_and_keeps_the_queue_order_on_ties(tmp_path):
    paths = []
    for name, data in [("g1", {"type": "choose_level"}), ("h1", {"type": "how_do_you_say", "theme": "el mar"}),
                       ("h2", {"type": "how_do_you_say", "theme": "la casa"}), ("h3", {"type": "how_do_you_say", "theme": "el mar"})]:
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(data))
        paths.append(p)
    order = [p.stem for p, _pr, _why in Q.ranked(paths, {}, CFG)]
    assert order == ["h2", "h1", "h3", "g1"]


def test_the_panel_picks_in_priority_order_and_inicio_offers_the_next_best():
    admin = (ROOT / "src" / "admin.py").read_text(encoding="utf-8")
    body = admin[admin.index("def queue_pick"):admin.index("def queue_pick") + 1500]
    assert "queue_order(queue_guard.queued_scripts())" in body
    assert "Producir el siguiente mejor" in admin and "next_best()" in admin
    assert '"Performance": ("Rendimiento"' in admin and "Actualizar estadísticas" in admin


def test_the_config_has_priors_for_every_panel_type_and_the_a1_list():
    import yaml
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["queue_priority"]
    assert cfg["prior_views"]["how_do_you_say"] > cfg["prior_views"]["phrases_level"] > cfg["prior_views"]["choose_level"]
    assert {"casa", "fruta", "animales", "colores", "verduras"} <= set(cfg["a1_categories"])


@pytest.mark.parametrize("page", ["Performance", "Dashboard"])
def test_the_pages_render_without_an_exception(page):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "src" / "admin.py"), default_timeout=180)
    at.session_state["current_page"] = page
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    if page == "Performance":
        assert any("Actualizar estadísticas" in b.label for b in at.button)
