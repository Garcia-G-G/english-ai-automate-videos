"""STEP 80 §1b: title, description and hashtags generated at render time. The LLM is mocked."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import metadata_generator as M  # noqa: E402
import video_metadata as V  # noqa: E402

HDYS = {"type": "how_do_you_say", "theme": "la fruta", "video_description": "Diez frutas que comes cada día. 🍎",
        "items": [{"emoji": "🍎", "spanish": "Manzana", "english": "apple"},
                  {"emoji": "🍐", "spanish": "Pera", "english": "pear"}]}
CHOOSE = {"type": "choose_level", "video_title": "", "video_description": "Speak o talk: cuál va.",
          "items": [{"spanish": "Hablar", "english": "speak"}, {"spanish": "Charlar", "english": "talk"}]}


def _llm(titles=("¿Speak o talk? Cómo se dice en inglés 💬", "Speak vs talk: cómo decirlo en inglés 🗣️",
                 "Hablar en inglés: speak o talk 🤔"),
         first="Aprende cuándo usar speak y cuándo talk.", listed="Hablar = speak · Charlar = talk",
         question="¿Cuál usas más?"):
    return lambda script, vtype: {"titles": list(titles), "first_line": first, "list": listed, "question": question}


def test_the_how_do_you_say_title_is_never_touched_by_the_llm():
    m = V.build(HDYS, "how_do_you_say", llm=_llm(titles=["Otra cosa en inglés 🙃"]), published=set())
    assert m["title"] == M.how_do_you_say_title(HDYS) == "¿Cómo se dice FRUTA en inglés? 🍎"
    assert m["alternatives"] == []


def test_the_code_picks_a_title_by_its_rules_and_keeps_two_alternatives():
    titles = ["Solo el 10 % sabe esto en inglés 😱",                       # clickbait
              "¿Speak o talk? Cómo se dice en inglés 💬",
              "Speak vs talk 💬",                                             # no Spanish search phrase
              "Speak vs talk: cómo decirlo en inglés 🗣️"]
    m = V.build(CHOOSE, "choose_level", llm=_llm(titles=titles), published=set())
    assert m["title"] == "¿Speak o talk? Cómo se dice en inglés 💬"
    assert len(m["alternatives"]) == 2 and m["source"] == "llm"


@pytest.mark.parametrize("title, why", [("Di '' bien en inglés 😬", "empty quotes"),
                                        ("¿Cómo se dice {x} en inglés? 🤔", "unfilled"),
                                        ("¿Cómo se dice " + "x" * 80 + " en inglés? 🤔", "over 70"),
                                        ("Cómo se dice en inglés", "not one emoji"),
                                        ("How to say it in English 🤔", "no Spanish search phrase")])
def test_the_title_rules_refuse(title, why):
    assert any(why in p for p in V.title_ok(title)), V.title_ok(title)


def test_the_guard_refuses_empty_quotes_length_english_and_a_published_title():
    ok = {"title": "¿Cómo se dice FRUTA en inglés? 🍎", "description": "Hola."}
    assert V.guard(ok, set()) == []
    assert V.guard({**ok, "title": "Say '' right"}, set())
    assert any("English only" in p for p in V.guard({**ok, "title": "Learn fruit words 🍎"}, set()))
    assert any("already published" in p for p in V.guard(ok, {V._fold(ok["title"])}))
    assert V.guard({**ok, "description": "x" * 2300}, set())


def test_the_description_has_the_payoff_the_list_the_question_and_the_site():
    m = V.build(CHOOSE, "choose_level", llm=_llm(), published=set())
    d = m["description"]
    assert d.startswith("Aprende cuándo usar speak y cuándo talk.")
    assert "Hablar = speak · Charlar = talk" in d and "¿Cuál usas más?" in d
    assert d.rstrip().endswith(M.SITE_LINE)


def test_a_list_naming_a_word_not_in_the_script_is_replaced_by_the_scripts():
    m = V.build(CHOOSE, "choose_level", llm=_llm(listed="Hablar = speak · Decir = say"), published=set())
    assert "say" not in m["description"] and V.content_list(CHOOSE, "choose_level") in m["description"]
    assert m["checks"]["list_from_script"]


def test_with_the_llm_down_the_template_is_used():
    m = V.build(HDYS, "how_do_you_say", llm=lambda *a: None, published=set())
    assert m["source"] == "template"
    assert "Manzana = apple · Pera = pear" in m["description"]
    assert "¿Cuántas sabías?" in m["description"]
    m2 = V.build(CHOOSE, "choose_level", llm=lambda *a: None, published=set())
    assert m2["title"] and not M.metadata_problems(m2["title"])


def test_the_llm_is_never_asked_outside_the_panels_click(monkeypatch):
    import voice_lock
    called = []

    class Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    called.append(kw)
    assert voice_lock.locked()
    assert V.ask_llm(HDYS, "how_do_you_say", client=Client()) is None and called == []


def test_youtube_gets_three_to_five_ordered_tags_plus_shorts():
    tags = V.build(HDYS, "how_do_you_say", llm=lambda *a: None, published=set())["hashtags"]
    assert tags["youtube"] == ["#frutaeningles", "#aprenderingles", "#inglesfacil", "#inglesparahispanohablantes",
                               "#englishunlimited", "#Shorts"]
    assert all(4 <= len(tags[p]) <= 5 for p in ("tiktok", "instagram", "facebook"))


def test_the_upload_publishes_the_sidecars_metadata_with_its_tags_once():
    from upload_metadata import resolve_upload_metadata
    gen = V.build(HDYS, "how_do_you_say", llm=lambda *a: None, published=set())
    for platform in ("youtube", "tiktok"):
        r = resolve_upload_metadata("v", HDYS, platform, "how_do_you_say", "", {}, generated=gen)
        assert r["source"] == "sidecar" and r["title"] == gen["title"]
        first = r["hashtags"][0]
        assert r["description"].count(f"#{first.lstrip('#')}") == 1        # composed exactly once
        again = M.compose_description(r["description"], r["hashtags"])
        assert again == r["description"]


def test_a_render_writes_the_metadata_into_the_sidecar():
    admin = (ROOT / "src" / "admin.py").read_text(encoding="utf-8")
    engine = (ROOT / "src" / "jobs.py").read_text(encoding="utf-8")
    assert '"metadata": render_metadata(script_data, video_type, category)' in engine
    assert "review_metadata_editor(video)" in admin and "Usar alternativa" in admin
    assert '"metadata": video_metadata.build(script, "hecho_con_claude")' in (ROOT / "src" / "series.py").read_text(encoding="utf-8")


def test_a_plural_theme_gets_se_dicen_and_its_article():
    """Published 2026-10-27 as «¿Cómo se dice ANIMALES DEL MAR…»."""
    assert M.how_do_you_say_title({"theme": "los animales del mar", "items": [{"emoji": "🐙"}]}) \
        == "¿Cómo se dicen los ANIMALES DEL MAR en inglés? 🐙"
    assert M.how_do_you_say_title({"theme": "la cara", "items": [{"emoji": "👄"}]}) == "¿Cómo se dice CARA en inglés? 👄"
