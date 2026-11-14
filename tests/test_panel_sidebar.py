"""STEP 83 §1: the sidebar. Groups, badges that vanish at 0, the meter's «sin dato», the brand."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from panel import sidebar as S  # noqa: E402


def test_the_three_groups_hold_every_page_exactly_once_in_the_mocks_order():
    assert [g for g, _ in S.GROUPS] == ["Producir", "Canal", "Ajustes"]
    flat = [p for _, pages in S.GROUPS for p in pages]
    assert flat == ["Dashboard", "Generate", "Queue", "Review", "Upload", "Manim", "Performance", "Comments", "Library",
                    "Topics", "Scheduler", "Settings", "Logs"]
    src = (ROOT / "src" / "admin.py").read_text(encoding="utf-8")
    labels = re.search(r"NAV_LABELS = \{(.*?)\n\}", src, re.S).group(1)
    assert set(re.findall(r'"(\w+)": \(', labels)) == set(flat)             # no page lost, none invented


def test_a_badge_is_hidden_at_zero_soft_for_the_queue_alert_for_the_rest():
    assert S.badge_css({"Queue": 0, "Review": 0, "Comments": 0}) == ""
    css = S.badge_css({"Queue": 12, "Review": 3, "Comments": 0})
    assert ".st-key-nav_Queue" in css and 'content: "12"' in css and "var(--line)" in css          # soft
    assert ".st-key-nav_Review" in css and 'content: "3"' in css and "var(--badge)" in css         # alert
    assert "nav_Comments" not in css and "nav_Dashboard" not in css


def test_the_meter_reads_the_real_numbers_or_says_sin_dato():
    html = S.meter_html(3.0, 15.0, 0.073, 0.25)
    assert "&#36;3.00 de &#36;15" in html and "width:20%" in html and "Por vídeo &#36;0.07 · tope &#36;0.25" in html
    nothing = S.meter_html(None, 15.0, None, None)
    assert nothing.count("sin dato") == 2 and "width:0%" in nothing and "tope" not in nothing
    assert "$" not in html.replace("&#36;", "")                                                    # never raw LaTeX dollars


def test_the_brand_carries_bubi_and_the_highlighted_name():
    html = S.brand_html("versión abc")
    assert html.count("data:image/png;base64,") == 1 and "English <mark>Unlimited</mark>" in html and "Estudio de vídeos" in html


def test_unanswered_comments_come_from_the_cached_list_without_an_api_call(tmp_path):
    import comments
    f = tmp_path / "t.json"
    assert comments.unanswered_count(f) == 0                                                       # never loaded
    comments.save_threads([{"id": "a", "replies": 0}, {"id": "b", "replies": 2}, {"id": "c", "replies": 0}], f)
    assert comments.unanswered_count(f) == 2
    f.write_text("not json")
    assert comments.unanswered_count(f) == 0


def test_the_sidebar_renders_with_all_pages_and_the_new_brand():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "src" / "admin.py"), default_timeout=180)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    keys = {b.key for b in at.sidebar.button}
    assert {f"nav_{p}" for _, pages in S.GROUPS for p in pages} <= keys
    text = " ".join(m.value for m in at.sidebar.markdown)
    assert "Estudio de vídeos" in text and "Producir" in text and "Canal" in text and "Ajustes" in text
