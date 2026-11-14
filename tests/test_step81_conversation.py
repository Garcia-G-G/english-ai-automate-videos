"""STEP 81 §3: the bonus question and the comments engine. HTTP and the model are faked."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import bonus as B  # noqa: E402
import comments as C  # noqa: E402


def _script(**kw):
    return {"type": "how_do_you_say", "theme": "la casa", "outro": "[excited] ¿Cuántas sabías?", "full_script": "x",
            "items": [{"spanish": "Casa", "english": "house"}], "_meta": {"topic_id": "bv002"}, **kw}


def test_the_bonus_line_is_appended_to_the_outro_with_a_word_not_in_the_list():
    out = B.apply(_script(), [], {"casa": "house", "puerta": "door"})
    assert out["outro"].endswith('Bonus: ¿cómo se dice "puerta"? Escríbelo en los comentarios.')
    assert out["_meta"]["bonus_used"] == {"es": "puerta", "en": "door"} and out["full_script"].endswith("comentarios.")


def test_meta_bonus_wins_then_the_next_queued_sequel_then_the_curated_list():
    assert B.pick(_script(_meta={"bonus": "ventana", "bonus_answer": "window"}), [], {"a": "b"}) == ("ventana", "window")
    sequel = {"_meta": {"sequel_of": "casa"}, "items": [{"spanish": "Techo", "english": "roof"}]}
    assert B.pick(_script(), [sequel], {"puerta": "door"}) == ("Techo", "roof")
    assert B.pick(_script(), [], {"puerta": "door"}) == ("puerta", "door")


def test_a_curated_word_already_in_the_list_is_never_asked_and_nothing_fitting_means_no_line():
    assert B.pick(_script(), [], {"casa": "house"}) is None
    s = _script()
    assert B.apply(s, [], {"casa": "house"}) is s


def test_other_types_and_a_second_pass_are_left_alone():
    quiz = {"type": "quiz", "outro": "x"}
    assert B.apply(quiz, [], {"a": "b"}) is quiz
    once = B.apply(_script(), [], {"puerta": "door"})
    assert B.apply(once, [], {"puerta": "door"}) is once


def test_the_real_config_has_curated_words():
    import queue_priority
    assert len(queue_priority._config().get("bonus_words") or {}) >= 10


# ── comments ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,ok", [("¡Muy bien! Sigue así.", True), ("mira https://x.com/a", False), ("escribe a a@b.co", False),
                                     ("llámame al +52 55 1234 5678", False), ("visita ejemplo.com", False), ("a" * 281, False),
                                     ("", False)])
def test_a_draft_is_safe_only_without_links_emails_phones_or_excess_length(text, ok):
    assert (C.clean_reply(text) is not None) is ok


def _reply(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def test_a_draft_is_made_once_validated_and_cached(tmp_path):
    cache, calls = tmp_path / "d.json", []

    def chat(task, messages, **kw):
        calls.append((task, messages[0]["content"]))
        return _reply("¡Correcto! «door» es la respuesta. 🙌")
    c = {"id": "c1", "author": "Ana", "text": "door!"}
    assert C.draft_reply(c, "door", chat, cache).startswith("¡Correcto!")
    assert C.draft_reply(c, "door", chat, cache).startswith("¡Correcto!") and len(calls) == 1
    assert calls[0][0] == "metadata" and "door" in calls[0][1]


def test_an_unsafe_draft_becomes_the_plain_thanks_and_a_failed_call_is_not_cached(tmp_path):
    cache = tmp_path / "d.json"
    assert C.draft_reply({"id": "c1", "text": "x"}, None, lambda *a, **k: _reply("visita http://spam.com"), cache) == C.FALLBACK

    def boom(*a, **k):
        raise RuntimeError("no key")
    assert C.draft_reply({"id": "c2", "text": "x"}, None, boom, cache) == C.FALLBACK
    assert "c2" not in json.loads(cache.read_text())                  # the next try can still draft


def test_threads_are_read_newest_first_through_the_channels_id():
    calls = []

    class R:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self.data

    def get(url, params=None, **kw):
        calls.append((url, params))
        if url == C.CHANNELS_URL:
            return R({"items": [{"id": "UC1"}]})
        return R({"items": [{"id": "t1", "snippet": {"videoId": "v1", "totalReplyCount": 0, "topLevelComment": {
            "snippet": {"authorDisplayName": "Ana", "textDisplay": "door", "publishedAt": "2026-11-12T10:00:00Z"}}}}]})
    got = C.fetch_threads("tok", get)
    assert got == [{"id": "t1", "video_id": "v1", "author": "Ana", "text": "door", "published": "2026-11-12T10:00:00Z", "replies": 0}]
    assert calls[1][1]["allThreadsRelatedToChannelId"] == "UC1" and calls[1][1]["order"] == "time"


def test_nothing_is_posted_unless_post_reply_is_called_and_it_refuses_unsafe_text():
    posted = []

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "new1"}

    def post(url, **kw):
        posted.append(kw["json"])
        return R()
    with pytest.raises(ValueError):
        C.post_reply("tok", "t1", "mira http://x.com", post)
    assert posted == []
    assert C.post_reply("tok", "t1", "¡Gracias!", post) == "new1"
    assert posted == [{"snippet": {"parentId": "t1", "textOriginal": "¡Gracias!"}}]


def test_the_bonus_answer_is_read_from_the_videos_sidecar(tmp_path):
    side = tmp_path / "how_do_you_say"
    side.mkdir()
    (side / "art1.json").write_text(json.dumps({"script_data": {"_meta": {"bonus_used": {"es": "puerta", "en": "door"}}}}))
    assert C.bonus_answers([{"artifact": "art1", "id": "v1"}, {"artifact": "art2", "id": "v2"}], [tmp_path]) == {"v1": "door"}


def test_the_comments_page_is_in_the_nav_and_renders_empty():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "src" / "admin.py"), default_timeout=180)
    at.session_state["current_page"] = "Comments"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Cargar comentarios" in b.label for b in at.button)
