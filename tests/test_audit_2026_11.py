"""The 2026-11-02 audit: what reaches a viewer or the ledger when the happy path does not hold.
All HTTP is mocked. Nothing uploads or spends."""
import hashlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import ai_background as AB  # noqa: E402
import channel_stats as C  # noqa: E402
import cost_tracker  # noqa: E402
import llm  # noqa: E402
import metadata_generator as M  # noqa: E402
import queue_priority as Q  # noqa: E402
import script_generator  # noqa: E402
import upload_limits as L  # noqa: E402
import uploader  # noqa: E402
import video_metadata as V  # noqa: E402
import voice_lock  # noqa: E402

CFG = {"prior_views": {"how_do_you_say": 1150}, "a1": ["casa", "cara", "cocina", "fruta"], "default_prior": 100}


def _video(title, views, days=10, vtype="how_do_you_say", **more):
    return {"title": title, "views": views, "days": days, "type": vtype, "category": title, **more}


# ── spend ────────────────────────────────────────────────────────────

def test_a_new_tracker_saves_what_the_old_one_had_not(tmp_path, monkeypatch):
    monkeypatch.setattr(cost_tracker, "COSTS_DIR", tmp_path)
    cost_tracker.reset_tracker("click")._add_entry("openrouter_image", "m", 0.01, "illustration", {})
    cost_tracker.reset_tracker("next job")
    assert "illustration" in next(tmp_path.glob("costs_*.jsonl")).read_text()


def test_a_chat_call_outside_a_panel_click_is_refused_before_anything_is_sent(monkeypatch):
    monkeypatch.setattr(llm, "client", lambda: pytest.fail("reached the network"))
    with pytest.raises(voice_lock.VoiceLocked):
        llm.chat("scripts", [{"role": "user", "content": "hola"}])


def test_a_script_is_never_written_with_the_openrouter_key(monkeypatch):
    # The hole the first version of this guard had: the writer built a real client and passed it in.
    monkeypatch.setattr(llm, "client", lambda: pytest.fail("built a client before the refusal"))
    monkeypatch.setattr(voice_lock, "check", lambda *a: None)      # a panel click changes nothing
    with pytest.raises(llm.ScriptModelOff):
        script_generator.generate_script_from_prompt("grammar", {}, "quiz", "hola", "sistema")


def test_platform_metadata_outside_a_click_falls_back_without_a_call(monkeypatch):
    class Client:
        chat = property(lambda self: pytest.fail("reached the network"))
    monkeypatch.setattr(llm, "client", lambda: Client())
    out = M.regenerate_for_platform({"video_title": "¿Cómo se dice CASA en inglés? 🏠"}, "youtube", "how_do_you_say")
    assert out["title"]


def test_a_refused_retry_is_lifted_by_the_owners_check(monkeypatch):
    import publication_log as PL
    import upload_guard as G
    PL.record_attempt(artifact="v", platform="youtube", status=PL.ATTEMPT_UNKNOWN, video_path="v.mp4", detail="503")
    assert G.decide("v", "youtube").action == G.SKIP_HOLD
    PL.record_attempt(artifact="v", platform="youtube", status=PL.ATTEMPT_FAILED, video_path="v.mp4", detail="comprobado")
    assert G.decide("v", "youtube").should_upload


# ── publishing ───────────────────────────────────────────────────────

def test_a_limit_with_no_publish_behind_it_expires_after_the_window():
    failed = datetime(2026, 10, 1, 12)
    rows = [{"platform": "youtube", "status": "failed", "detail": f"400 {L.UPLOAD_LIMIT}", "at": failed.isoformat()}]
    assert L.limit_block(rows, failed + timedelta(hours=1))
    assert L.limit_block(rows, failed + L.WINDOW + timedelta(minutes=1)) is None


class _Resp:
    def __init__(self, status):
        self.status_code, self.headers, self.text = status, {}, "{}"

    def json(self):
        return {}


def _youtube(monkeypatch, tmp_path, put):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 16)
    init = _Resp(200)
    init.headers = {"Location": "https://upload/session"}
    monkeypatch.setattr(uploader.requests, "post", lambda url, **kw: init)
    monkeypatch.setattr(uploader.requests, "put", put)
    yt = uploader.YouTubeUploader()
    yt._token_data = {"access_token": "t"}
    return yt, str(video)


@pytest.mark.parametrize("status, doubt", [(503, True), (403, False)])
def test_a_youtube_chunk_answer_says_whether_the_video_may_exist(monkeypatch, tmp_path, status, doubt):
    yt, video = _youtube(monkeypatch, tmp_path, lambda *a, **k: _Resp(status))
    assert yt.upload_video(video, "Título", "Desc", ["Tag"]).in_doubt is doubt


def test_a_youtube_timeout_after_the_session_is_in_doubt_not_failed(monkeypatch, tmp_path):
    def timeout(*a, **k):
        raise uploader.requests.Timeout("no answer")
    yt, video = _youtube(monkeypatch, tmp_path, timeout)
    result = yt.upload_video(video, "Título", "Desc", ["Tag"])
    assert not result.success and result.in_doubt and result.session_uri


@pytest.mark.parametrize("status, state", [(503, "unknown"), (403, "failed")])
def test_a_session_query_5xx_is_unknown(monkeypatch, tmp_path, status, state):
    yt, _video_path = _youtube(monkeypatch, tmp_path, lambda *a, **k: _Resp(status))
    assert yt.query_session("https://upload/session", 16)["state"] == state


# ── the A/Bs ─────────────────────────────────────────────────────────

def test_the_background_group_does_not_move_with_the_length_turns():
    topics = [f"tema {k}" for k in range(200)]
    groups = [hashlib.sha256(f"background:{t}".encode()).digest()[0] % 2 for t in topics]
    together = sum(g == k % 2 for k, g in enumerate(groups))      # k % 2 is length_ab's turn for the k-th new topic
    assert 60 < together < 140


# ── metadata ─────────────────────────────────────────────────────────

SPEAK = {"type": "choose_level", "video_title": "SPEAK o TALK: ¿cuál va en cada frase? 💬", "theme": "speak o talk",
         "video_description": "Cuál va.", "items": [{"spanish": "Hablar", "english": "speak"}]}


def _llm(script, vtype):
    return {"titles": ["Elige la correcta en inglés: ¿cuál es? ✅"], "first_line": "", "list": "", "question": ""}


def test_a_title_written_for_the_topic_beats_the_llms_generic_one():
    m = V.build(SPEAK, "choose_level", llm=_llm, published=set())
    assert m["title"] == SPEAK["video_title"]
    assert m["alternatives"] == ["Elige la correcta en inglés: ¿cuál es? ✅"]


def test_a_title_already_published_goes_back_to_the_llm():
    m = V.build(SPEAK, "choose_level", llm=_llm, published={V._fold(SPEAK["video_title"]).strip()})
    assert m["title"] == "Elige la correcta en inglés: ¿cuál es? ✅"


@pytest.mark.parametrize("title", ["Completa: FOR, SINCE o AGO ⏳", "Un truco que casi nadie sabe de la casa 👶"])
def test_a_script_title_the_guards_would_refuse_goes_to_the_llm_not_the_template(title):
    good = "¿For, since o ago? Cómo se dice en inglés ⏳"
    llm_ = lambda s, t: {"titles": [good], "first_line": "", "list": "", "question": ""}
    assert V.build({**SPEAK, "video_title": title}, "fill_level", llm=llm_, published=set())["title"] == good


@pytest.mark.parametrize("script, vtype, tag", [
    ({"theme": "el hotel"}, "phrases_level", "#hoteleningles"),
    ({"theme": "hablar de tu familia"}, "say_it_level", "#fraseseningles"),
    ({"theme": "speak o talk"}, "choose_level", "#gramaticainglesa"),
    ({"theme": "RETO"}, "hecho_con_claude", "#erroreseningles"),
    ({"theme": "las partes de la casa"}, "how_do_you_say", "#partesdelacasaeningles"),
])
def test_the_first_hashtag_says_what_the_video_is(script, vtype, tag):
    assert V.topic_tag(script, vtype) == tag


def test_the_title_emoji_is_the_topics_not_the_first_rows():
    items = [{"emoji": "🍎"}]
    assert M.how_do_you_say_title({"theme": "el trabajo", "video_title": "¿Cómo se dice TRABAJO en inglés? 💼",
                                   "items": items}).endswith("💼")
    assert M.how_do_you_say_title({"theme": "el trabajo", "video_title": "Sin emoji en inglés?", "items": items}).endswith("🍎")


# ── what gets made next ──────────────────────────────────────────────

@pytest.mark.parametrize("theme, word", [("la cara", "cara"), ("defectos de carácter", None), ("las frutas", "fruta"),
                                         ("verbos de cocinar", None), ("la cocina", "cocina")])
def test_an_a1_category_is_a_whole_word(theme, word):
    assert Q.a1_word({"theme": theme}, CFG) == word


def test_a_topic_is_scored_by_the_videos_of_its_kind():
    videos = [_video(f"¿Cómo se dice CASA {k}?", 1000 + k) for k in range(3)] + [_video(f"Hotel {k}", 100 + k) for k in range(3)]
    scores = Q.type_scores({"videos": videos}, CFG)
    assert Q.priority({"type": "how_do_you_say", "theme": "la cocina"}, scores, CFG)[0] == 1001
    low, why = Q.priority({"type": "how_do_you_say", "theme": "Halloween"}, scores, CFG)
    assert low == 101 and "no son A1" in why


def test_with_too_few_of_a_kind_the_type_median_and_the_boost_stand():
    videos = [_video(f"Casa {k}", 1000) for k in range(3)] + [_video("Hotel", 100)]
    scores = Q.type_scores({"videos": videos}, CFG)
    assert Q.priority({"type": "how_do_you_say", "theme": "la cocina"}, scores, CFG)[0] == 1000 * Q.A1_BOOST


# ── the numbers ──────────────────────────────────────────────────────

def test_a_young_video_is_neither_a_winner_nor_a_loser():
    s = C.summary([_video("viejo", 100), _video("joven", 9000, days=2)])
    assert [v["title"] for v in s["top"]] == ["viejo"] and [v["title"] for v in s["bottom"]] == ["viejo"]
    assert {c["category"] for c in s["categories"]} == {"viejo"}


def test_hashtags_are_counted_once_per_video_and_only_with_enough_videos():
    videos = [_video(str(k), 100 * k, hashtags=["#Casa", "casa", "#Shorts"]) for k in range(1, 4)] + [_video("x", 5, hashtags=["#raro"])]
    assert C.hashtags(videos) == [{"hashtag": "#casa", "count": 3, "median": 200}]


def test_retention_carries_seconds_subscribers_and_shares():
    class R:
        def raise_for_status(self):
            pass

        def json(self):
            names = ["video", "views", "averageViewPercentage", "averageViewDuration", "subscribersGained", "shares"]
            return {"columnHeaders": [{"name": n} for n in names], "rows": [["a", 10, 120.44, 44, 2, 1]]}
    got = C.fetch_retention(["a"], "t", datetime(2026, 11, 2).date(), lambda *a, **k: R())
    assert got == {"a": {"avg_view_pct": 120.4, "avg_view_seconds": 44, "subs_gained": 2, "shares": 1}}


# ── the gate: a small miss warns and keeps the end card ──────────────

def test_a_small_miss_warns_and_a_large_one_refuses(monkeypatch):
    import deesser as D
    import loudness as Lo
    monkeypatch.setattr(Lo, "measure", lambda p: {"I": -15.5, "TP": -2.0})
    monkeypatch.setattr(Lo, "decode", lambda p: None)
    monkeypatch.setattr(Lo, "segment_levels", lambda *a: [])
    monkeypatch.setattr(Lo, "spread", lambda levels: 3.8)
    g = Lo.gate("v.mp4", [{}])
    assert g["flags"] == [] and g["warnings"] == ["loudness:-15.5LUFS", "segment_spread:3.8dB"]
    monkeypatch.setattr(Lo, "measure", lambda p: {"I": -17.0, "TP": -2.0})
    monkeypatch.setattr(Lo, "spread", lambda levels: 6.5)
    assert Lo.gate("v.mp4", [{}])["flags"] == ["loudness:-17.0LUFS", "segment_spread:6.5dB"]
    base = {"enabled": True, "other_hf_db": 0.2, "body_db": 0.0}
    assert D.flags({**base, "sibilant_hf_db": 4.5}) == [] and D.warnings({**base, "sibilant_hf_db": 4.5})
    assert D.flags({**base, "sibilant_hf_db": 3.5}) and not D.warnings({**base, "sibilant_hf_db": 3.5})


# ── scripts the model writes ─────────────────────────────────────────

@pytest.mark.parametrize("vtype, kept", [("phrases_level", 5), ("level_test", 5), ("how_do_you_say", 7)])
def test_the_formats_with_five_hashtags_keep_five(vtype, kept):
    tags = ["#CómoSeDice", "#a", "#b", "#c", "#d"]
    out = script_generator.validate_and_clean_script(
        {"type": vtype, "hashtags": tags, "video_title": "T 🏠 #Shorts", "full_script": "Hola.", "theme": "la casa", "intro": "Hola.",
         "items": [{"spanish": "Casa", "english": "house"}], "recap": "Todas.", "verdict": {"a": "b"}, "outro": "Adiós."}, vtype)
    assert len(out["hashtags"]) == kept and out["video_title"] == "T 🏠"
