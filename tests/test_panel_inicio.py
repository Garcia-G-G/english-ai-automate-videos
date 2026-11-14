"""STEP 83 §2: the data behind the new Inicio. Counts, colours, «sin dato», slot logic."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from panel import inicio as I  # noqa: E402

CR = ZoneInfo("America/Costa_Rica")


def _v(vtype="how_do_you_say", views=1000, days=3, title="t", vid="v"):
    return {"type": vtype, "views": views, "days": days, "title": title, "id": vid}


@pytest.mark.parametrize("hour,word", [(7, "Buenos días"), (11, "Buenos días"), (12, "Buenas tardes"), (18, "Buenas tardes"), (19, "Buenas noches"), (23, "Buenas noches")])
def test_the_greeting_follows_the_hour_in_costa_rica(hour, word):
    assert I.greeting(datetime(2026, 11, 13, hour, tzinfo=CR), "Garcia") == f"{word}, Garcia"


def test_the_greeting_uses_costa_rica_not_the_servers_zone():
    utc = datetime(2026, 11, 13, 13, 0, tzinfo=ZoneInfo("UTC"))            # 07:00 in Costa Rica
    assert I.greeting(utc, "G").startswith("Buenos días")


def test_the_date_line_is_in_spanish():
    assert I.date_line(datetime(2026, 11, 13, 9, tzinfo=CR)) == "Viernes 13 de noviembre"


def test_bar_colours_green_at_1_2x_red_under_half_only_after_a_day_else_blue():
    assert I.bar(_v(views=1300), 1000)["colour"] == "green"
    assert I.bar(_v(views=400, days=2), 1000)["colour"] == "red"
    assert I.bar(_v(views=400, days=0), 1000)["colour"] == "blue"          # too young to be red
    assert I.bar(_v(views=800), 1000)["colour"] == "blue"
    assert I.bar(_v(views=5000), 1000)["width"] == 100                      # the scale caps at 2× normal


def test_bar_labels_and_the_missing_normal_is_sin_dato_never_a_ratio():
    assert I.bar(_v(views=2000), 1000)["label"] == "2.0× lo normal"
    assert I.bar(_v(views=400, days=2), 1000)["label"] == "40 % · día 2"
    b = I.bar(_v(views=400), None)
    assert b["ratio"] is None and b["width"] == 0 and "sin dato" in b["label"]


def test_week_totals_and_the_five_most_recent():
    vids = [_v(views=100, days=d, vid=str(d)) for d in (0, 1, 2, 3, 4, 5, 6, 9)]
    t = I.week_totals(vids)
    assert t == {"views": 700, "videos": 7, "mean": 100}
    assert [v["days"] for v in I.recent(vids)] == [0, 1, 2, 3, 4]
    assert I.week_totals([]) == {"views": 0, "videos": 0, "mean": None}


def test_postit_weak_videos_first_then_a_winner_else_nothing():
    norm = {"how_do_you_say": 1000}
    weak = [_v(views=100, days=2, title="a"), _v(views=900, days=2), _v(views=50, days=0, title="young")]
    p = I.postit(weak, norm)
    assert p["kind"] == "weak" and [v["title"] for v in p["videos"]] == ["a"]       # the day-0 one is not judged
    win = I.postit([_v(views=2500, days=2, title="w"), _v(views=800, days=3)], norm)
    assert win["kind"] == "win" and win["videos"][0]["title"] == "w" and win["ratio"] == 2.5
    assert I.postit([_v(views=900, days=2)], norm) is None
    assert I.postit([_v(vtype="quiz", views=1, days=3)], norm) is None                 # no normal for that format


def test_postit_lists_at_most_three_weak_ones():
    vids = [_v(views=10 * k, days=2, title=str(k)) for k in range(1, 6)]
    assert len(I.postit(vids, {"how_do_you_say": 1000})["videos"]) == 3


def test_queue_days_at_four_a_day_and_the_stats_chip():
    assert [I.days_of_queue(n) for n in (0, 1, 4, 5, 491)] == [0, 1, 1, 2, 123]
    assert I.stats_chip(5) == ("Estadísticas al día · hace 5 h", "dot") and I.stats_chip(30)[1] == "dot amber"
    assert "sin dato" in I.stats_chip(None)[0]


def _slots(now):
    return [now.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in ((8, 30), (12, 0), (16, 0), (19, 30))]


def test_slot_states_published_scheduled_and_free():
    now = datetime(2026, 11, 13, 13, 0, tzinfo=CR)
    s = _slots(now)
    ledger = [
        {"platform": "youtube", "artifact": "a", "upload_id": "v1", "published_title": "Casa", "published_at": "2026-11-13T08:00:00", "extra": {"scheduled_for": s[0].isoformat()}},
        {"platform": "youtube", "artifact": "b", "upload_id": "v2", "published_title": "Cocina", "published_at": "2026-11-13T09:00:00", "extra": {"scheduled_for": s[2].isoformat()}},
        {"platform": "facebook", "artifact": "b", "published_at": "2026-11-13T09:01:00"},
    ]
    st = I.slot_states(now, s, ledger, [{"id": "v1", "views": 321}], {s[1]: "bv103", s[3]: "bv104"})
    assert [x["state"] for x in st] == ["published", "free", "scheduled", "free"]
    assert st[0]["views"] == 321 and st[2]["platforms"] == ["youtube", "facebook"] and st[1]["fills"] == "bv103"
    assert st[2].get("views") is None                                                      # not live yet: no views invented


def test_the_sentence_counts_free_slots_and_says_todo_listo_when_none():
    now = datetime(2026, 11, 13, 9, tzinfo=CR)
    s = _slots(now)
    full = [{"state": "published", "at": a} for a in s]
    assert I.slots_sentence(full) == "Hoy está todo listo."
    one = [{"state": "published", "at": s[0]}, {"state": "scheduled", "at": s[1]}, {"state": "scheduled", "at": s[2]}, {"state": "free", "at": s[3]}]
    assert I.slots_sentence(one) == "Hoy salen 4 vídeos y ya hay 3 en su sitio. Falta 1 para 19:30."
    gone = [{"state": "published", "at": s[0]}, {"state": "free", "at": s[1]}]
    assert I.slots_sentence(gone, datetime(2026, 11, 13, 20, tzinfo=CR)) == "Hoy está todo listo."         # a past gap is not missing


def test_flow_cells_name_the_page_and_the_real_counts():
    cells = I.flow_cells(2, datetime(2026, 11, 13, 16, tzinfo=CR), 3, 1, 491)
    assert [c["page"] for c in cells] == ["Generate", "Review", "Upload", "Queue"]
    assert cells[0]["hot"] and "16:00" in cells[0]["line"] and cells[3]["line"] == "para 123 días"
    assert not I.flow_cells(0, None, 0, 0, 0)[0]["hot"]


def test_render_time_is_the_median_of_the_last_ten_and_sin_dato_under_three():
    def job(sec, vt="how_do_you_say", status="completed"):
        a = datetime(2026, 11, 1)
        return {"video_type": vt, "status": status, "created_at": a.isoformat(), "completed_at": (a + timedelta(seconds=sec)).isoformat()}
    assert I.render_seconds([job(300), job(600), job(900)], "how_do_you_say") == 600
    assert I.render_seconds([job(300), job(600)], "how_do_you_say") is None
    assert I.render_seconds([job(300), job(600), job(900, status="failed"), job(100, "quiz")], "how_do_you_say") is None


def test_facts_show_sin_dato_in_grey_never_a_made_up_number():
    html = I.facts_html("how_do_you_say", None, None, None, 0)
    assert html.count("sin-dato") == 3 and "<b>0</b>" in html
    assert "~76 s" in I.facts_html("x", 76.0, 0.07, 600, 2) and "&#36;0.07" in I.facts_html("x", 76.0, 0.07, 600, 2)


def test_frame0_is_drawn_once_cached_at_270x480_and_other_types_get_none(tmp_path):
    import json
    script = json.loads((ROOT / "content/queue/_done/bv002_casa.json").read_text(encoding="utf-8"))
    p = I.frame0_png("bv002", script, 0.0, tmp_path)
    from PIL import Image
    assert Image.open(p).size == (270, 480)
    first = p.stat().st_mtime_ns
    assert I.frame0_png("bv002", script, 0.0, tmp_path) == p and p.stat().st_mtime_ns == first      # cached
    assert I.frame0_png("q", {"type": "quiz", "items": [1]}, 0.0, tmp_path) is None


def test_the_html_escapes_titles():
    out = I.agenda_html([{"at": datetime(2026, 11, 13, 8, 30, tzinfo=CR), "state": "published", "title": "<b>x</b>", "views": 5, "platforms": []}], 4, 0)
    assert "&lt;b&gt;x&lt;/b&gt;" in out and "5 vistas" in out


def test_a_past_free_slot_says_it_passed_and_the_topic_is_highlighted_once():
    now = datetime(2026, 11, 13, 13, 0, tzinfo=CR)
    st = I.slot_states(now, _slots(now), [], [], {})
    assert st[0]["past"] and not st[3]["past"]
    out = I.agenda_html(st, 4, 4)
    assert out.count("Pasó sin vídeo") == 2 and out.count("Hueco libre") == 2
    assert I.highlight_topic("¿Cómo se dicen las HERRAMIENTAS en inglés? 🔨") == "¿Cómo se dicen las <mark>HERRAMIENTAS</mark> en inglés? 🔨"


def test_a_video_dated_tomorrow_by_timezone_is_day_zero_not_day_minus_one():
    assert I.bar(_v(views=100, days=-1), 1000)["label"] == "10 % · día 0"
