"""STEP 82 §3: figured pronunciation. The model call is faked; nothing is paid."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import pron  # noqa: E402
from video.tablero import kit  # noqa: E402


def _reply(obj):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(obj)))])


def _chat(obj, calls):
    def chat(task, messages, **kw):
        calls.append(task)
        return _reply(obj)
    return chat


def test_missing_words_get_one_cheap_draft_cached_and_marked_for_review(tmp_path):
    book, calls = tmp_path / "p.json", []
    items = [{"english": "house"}, {"english": "Kitchen"}]
    n = pron.fill_missing(items, book, _chat({"house": "jáus", "kitchen": "kíchen"}, calls))
    assert n == 2 and calls == ["metadata"]                # the cheap model, one call
    assert json.loads(book.read_text())["house"] == {"pron": "jáus", "review": True}
    assert items[0]["pron"] == "jáus" and items[1]["pron"] == "kíchen"


def test_a_cached_word_costs_nothing(tmp_path):
    book, calls = tmp_path / "p.json", []
    book.write_text(json.dumps({"house": {"pron": "jáus"}}))
    items = [{"english": "house"}]
    assert pron.fill_missing(items, book, _chat({}, calls)) == 0 and calls == [] and items[0]["pron"] == "jáus"


def test_invalid_drafts_are_dropped(tmp_path):
    items = [{"english": "house"}, {"english": "key"}, {"english": "door"}]
    pron.fill_missing(items, tmp_path / "p.json",
                      _chat({"house": "/haʊs/", "key": "k1", "door": "d" * 15}, []))
    assert all("pron" not in i for i in items)


def test_a_failing_model_leaves_the_english_alone(tmp_path):
    def boom(*a, **k):
        raise RuntimeError("no key")
    items = [{"english": "house"}]
    assert pron.fill_missing(items, tmp_path / "p.json", boom) == 0 and "pron" not in items[0]


def test_an_item_with_its_own_valid_pron_is_not_redrafted(tmp_path):
    calls = []
    pron.fill_missing([{"english": "house", "pron": "jáus"}], tmp_path / "p.json", _chat({}, calls))
    assert calls == []


def test_the_schema_accepts_a_valid_pron_and_refuses_ipa():
    from script_schema import HowDoYouSayItem
    assert HowDoYouSayItem(emoji="🏠", spanish="Casa", english="house", pron="jáus").pron == "jáus"
    with pytest.raises(ValueError):
        HowDoYouSayItem(emoji="🏠", spanish="Casa", english="house", pron="/haʊs/")
    assert HowDoYouSayItem(emoji="🏠", spanish="Casa", english="house").pron is None


def test_the_tile_reads_the_dictionary_when_the_item_has_no_pron(tmp_path, monkeypatch):
    p = tmp_path / "d.json"
    p.write_text(json.dumps({"house": {"pron": "jáus", "review": True}, "bed": "bed"}))
    monkeypatch.setattr(kit, "PRON_PATH", p)
    kit.pron_dictionary.cache_clear()
    try:
        assert kit.pron_for({"english": "House"}) == "jáus" and kit.pron_for({"english": "bed"}) == "bed"
        assert kit.pron_for({"english": "door"}) is None
    finally:
        kit.pron_dictionary.cache_clear()
