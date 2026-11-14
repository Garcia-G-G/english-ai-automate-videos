"""STEP 81 §0: queue hygiene. Repeated words, seasons, title emoji, repeat renders."""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
import repetition as R  # noqa: E402
import season  # noqa: E402


def _s(name_words, vtype="how_do_you_say", **extra):
    return {"type": vtype, "items": [{"emoji": "🍎", "spanish": "x", "english": w} for w in name_words], **extra}


def _tree(tmp_path, published, queued):
    done, queue = tmp_path / "queue" / "_done", tmp_path / "queue" / "how_do_you_say"
    done.mkdir(parents=True), queue.mkdir(parents=True)
    for name, ws in published.items():
        (done / name).write_text(json.dumps(_s(ws)), encoding="utf-8")
    for name, ws in queued.items():
        (queue / name).write_text(json.dumps(_s(ws)), encoding="utf-8")
    return tmp_path / "queue", done, queue


def test_more_than_three_repeated_words_is_refused_case_insensitively(tmp_path):
    q, done, queue = _tree(tmp_path, {"a.json": ["Dog", "cat", "bird", "fish", "cow"]}, {})
    known = R.corpus("how_do_you_say", q, done)
    assert R.problem(_s(["dog", "CAT", "bird", "fish", "pig"]), known=known).startswith("REPEATS WORDS")
    assert R.problem(_s(["dog", "cat", "bird", "pig", "hen"]), known=known) is None      # 3 repeats: allowed


def test_of_two_queued_scripts_only_the_later_one_is_the_repeat(tmp_path):
    q, done, queue = _tree(tmp_path, {}, {"bv1.json": ["a", "b", "c", "d"], "bv2.json": ["a", "b", "c", "d"]})
    known = R.corpus("how_do_you_say", q, done)
    first, second = queue / "bv1.json", queue / "bv2.json"
    assert R.repeated(json.loads(first.read_text()), first, known) == []
    assert R.repeated(json.loads(second.read_text()), second, known) == ["a", "b", "c", "d"]


def test_other_types_and_the_rewrite_shelf_are_not_compared(tmp_path):
    q, done, queue = _tree(tmp_path, {}, {})
    (q / "_rewrite").mkdir()
    (q / "_rewrite" / "x.json").write_text(json.dumps(_s(["a", "b", "c", "d"])))
    assert R.corpus("how_do_you_say", q, done) == [] and R.words({"type": "quiz", "items": [{"english": "a"}]}) == set()


def test_bv090_repeats_all_ten_and_bv101_passes():
    bv090 = json.loads((ROOT / "content/queue/_rewrite/bv090_mas_comida.json").read_text(encoding="utf-8"))
    assert len(R.repeated(bv090)) == 10 and R.problem(bv090).startswith("REPEATS WORDS")
    p = ROOT / "content/queue/how_do_you_say/bv101_mas_animales.json"
    bv101 = json.loads(p.read_text(encoding="utf-8"))
    assert len(R.repeated(bv101, p)) <= 3 and R.problem(bv101, p) is None


def test_the_queue_guard_blocks_both_kinds_of_refusal_and_skips_the_rewrite_shelf(tmp_path, monkeypatch):
    import queue_guard
    assert queue_guard.blocks("REPEATS WORDS: 5 of its 10") and queue_guard.blocks("OUT OF SEASON: navidad")
    monkeypatch.setattr(queue_guard, "QUEUE_DIR", tmp_path)
    (tmp_path / "_rewrite").mkdir()
    (tmp_path / "quiz").mkdir()
    (tmp_path / "_rewrite" / "x.json").write_text("{}")
    (tmp_path / "quiz" / "y.json").write_text("{}")
    assert [p.name for p in queue_guard.queued_scripts()] == ["y.json"]


CAL = {"navidad": {"from": "12-01", "to": "12-20", "words": ["navidad"]},
       "halloween": {"from": "10-01", "to": "10-31", "words": ["halloween"]}}


@pytest.mark.parametrize("theme,day,late", [("la Navidad", date(2026, 11, 12), True), ("la Navidad", date(2026, 12, 5), False),
                                            ("Halloween", date(2026, 11, 12), True), ("Halloween", date(2026, 10, 31), False),
                                            ("la casa", date(2026, 11, 12), False)])
def test_seasonal_scripts_are_only_picked_inside_their_window(theme, day, late):
    assert bool(season.out_of_season({"theme": theme}, day, CAL)) is late


def test_the_real_calendar_has_both_seasons_and_halloween_waits_until_next_year():
    assert {"navidad", "halloween"} <= set(season.calendar())
    assert season.out_of_season({"theme": "Halloween"}, date(2026, 11, 12)).startswith("OUT OF SEASON")
    assert (ROOT / "content/queue/_skipped/bv049_halloween.json").exists()


def test_the_title_emoji_follows_meta_then_the_map_then_the_first_row():
    import metadata_generator as M
    row = [{"emoji": "🍎"}]
    assert M.title_emoji({"theme": "las profesiones", "items": row}) == "👷"              # not the first row's apple
    assert M.title_emoji({"theme": "las profesiones", "items": row, "_meta": {"title_emoji": "🎯"}}) == "🎯"
    assert M.title_emoji({"theme": "la comida", "items": row}) == "🍎"                    # last resort, and food fits
    assert M.title_emoji({"theme": "los saludos", "items": row, "video_title": "x 🍎"}) == "👋"


def test_a_fruit_emoji_is_refused_on_a_non_food_theme():
    import metadata_generator as M
    assert M._emoji_mismatch("🍎", "las profesiones", ["comida"]) is True
    assert M._emoji_mismatch("🍎", "la fruta", ["fruta"]) is False
    assert M._emoji_mismatch("🏠", "la casa", ["fruta"]) is False
    assert M.title_emoji({"theme": "tema raro", "items": [{"emoji": "🏠"}], "_meta": {"title_emoji": "🍌"}}) == "🏠"


def test_a_script_with_a_video_is_refused_unless_rerender_is_ticked(tmp_path, monkeypatch):
    import jobs
    monkeypatch.setattr(jobs, "PENDING_DIR", tmp_path / "pending")
    monkeypatch.setattr(jobs, "APPROVED_DIR", tmp_path / "approved")
    monkeypatch.setattr(jobs, "UPLOADED_DIR", tmp_path / "uploaded")
    script = {"type": "how_do_you_say", "_meta": {"topic_id": "bv010", "video_type": "how_do_you_say"}}
    side = tmp_path / "approved" / "how_do_you_say"
    side.mkdir(parents=True)
    (side / "a.json").write_text(json.dumps({"script_data": script}))
    jobs.refuse_repeat_render(script, False)                 # a sidecar without its MP4 is not a video
    (side / "a.mp4").write_bytes(b"x")
    with pytest.raises(jobs.AlreadyRendered) as err:
        jobs.refuse_repeat_render(script, False)
    assert "Volver a renderizar" in str(err.value) and isinstance(err.value, jobs.AlreadyRendering)
    jobs.refuse_repeat_render(script, True)                  # ticked: allowed
    jobs.refuse_repeat_render({"type": "how_do_you_say", "_meta": {"topic_id": "bv011"}}, False)   # another script


def test_generation_time_refuses_a_script_made_of_published_words(tmp_path, monkeypatch):
    import jobs
    bv090 = json.loads((ROOT / "content/queue/_rewrite/bv090_mas_comida.json").read_text(encoding="utf-8"))
    ledger = tmp_path / "generation_jobs.json"
    ledger.write_text(json.dumps({"active": [], "history": []}))
    monkeypatch.setattr(jobs, "JOBS_FILE", ledger)
    monkeypatch.setattr(jobs, "reset_tracker", lambda video_id=None: None)
    monkeypatch.setattr(jobs, "queue_pick", lambda video_type=None: None)
    monkeypatch.setattr(R, "QUEUE_DIR", ROOT / "content" / "queue")
    monkeypatch.setattr(R, "DONE_DIR", ROOT / "content" / "queue" / "_done")
    job = jobs.create_job("how_do_you_say")
    result = jobs.run_pipeline_with_tracking(job, "how_do_you_say", script_data=bv090, use_queue=False, dry_run=True)
    assert "REPEATS WORDS" in result["error"]
    again = jobs.run_pipeline_with_tracking(jobs.create_job("how_do_you_say"), "how_do_you_say",
                                            script_data=bv090, use_queue=False, dry_run=True, rerender=True)
    assert "REPEATS WORDS" not in (again.get("error") or "")


def test_the_repetition_corpus_parses_an_unchanged_file_once(tmp_path, monkeypatch):
    q, done, queue = _tree(tmp_path, {"a.json": ["x", "y"]}, {"b.json": ["z"]})
    calls = []
    real = R._read
    monkeypatch.setattr(R, "_read", lambda p: calls.append(p) or real(p))
    R._READ.clear()
    R.corpus("how_do_you_say", q, done)
    n = len(calls)
    R.corpus("how_do_you_say", q, done)
    assert n == 2 and len(calls) == n                        # second pass: no parse
    (queue / "b.json").write_text(json.dumps(_s(["z", "w"])), encoding="utf-8")
    assert {len(w) for _p, w, _pub in R.corpus("how_do_you_say", q, done) if _p.name == "b.json"} == {2}   # an edit is seen


def test_showing_the_next_best_does_not_run_a_fresh_audit_but_a_render_does():
    import inspect
    import jobs
    assert inspect.signature(jobs.queue_pick).parameters["fresh"].default is True
    src = inspect.getsource(jobs.next_best)
    assert "fresh=False" in src and "queue_pick(vtype)" not in src
