"""STEP 77 §9: the level drafts are queued by tools/level_migrate.py --copy, drafts kept."""
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import level_migrate  # noqa: E402

TYPES = ("choose_level", "fill_level", "true_false_level", "phrases_level")


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A copy of two drafts per type in a temporary root: the real queue is never written."""
    from collections import Counter
    import topic_history
    monkeypatch.setattr(topic_history, "usage_counts", lambda *a, **k: Counter())   # nothing produced yet
    (tmp_path / "content" / "topics").mkdir(parents=True)
    for vtype in TYPES:
        drafts = sorted((ROOT / "content" / "drafts" / vtype).glob("*.json"))[1:3]
        dest = tmp_path / "content" / "drafts" / vtype
        dest.mkdir(parents=True)
        for p in drafts:
            shutil.copy(p, dest / p.name)
    (tmp_path / "content" / "queue" / "_done").mkdir(parents=True)
    monkeypatch.setattr(level_migrate, "ROOT", tmp_path)
    return tmp_path


def test_copy_queues_every_draft_keeps_it_and_derives_without_rewording(tree):
    assert level_migrate.copy(TYPES) == 0
    for vtype in TYPES:
        for draft in (tree / "content" / "drafts" / vtype).glob("*.json"):
            queued = json.loads((tree / "content" / "queue" / vtype / draft.name).read_text(encoding="utf-8"))
            source = json.loads(draft.read_text(encoding="utf-8"))           # still there
            assert queued == level_migrate.derive(source)
            assert all(queued[k] == v for k, v in source.items() if k != "_meta")
            assert "draft" not in queued["_meta"] and queued["full_script"]
            topics = json.loads((tree / "content" / "topics" / f"{queued['_meta']['category']}.json").read_text())
            assert any(t["id"] == queued["_meta"]["topic_id"] for t in topics)       # the guard can draw it


def test_copy_skips_what_is_queued_or_done(tree, capsys):
    level_migrate.copy(TYPES)
    first = sorted((tree / "content" / "queue" / "choose_level").glob("*.json"))[0]
    first.rename(tree / "content" / "queue" / "_done" / first.name)
    level_migrate.copy(TYPES)
    out = capsys.readouterr().out
    assert f"{first.name} already queued, done or produced: skipped" in out
    assert not (tree / "content" / "queue" / "choose_level" / first.name).exists()


def test_the_real_queue_holds_forty_validated_scripts_per_new_type():
    import length_spec
    from script_schema import validate_script
    for vtype in TYPES:
        paths = sorted((ROOT / "content" / "queue" / vtype).glob("*.json"))
        done = [p for p in (ROOT / "content" / "queue" / "_done").glob("*.json")
                if json.loads(p.read_text(encoding="utf-8")).get("type") == vtype]
        assert len(paths) + len(done) >= 39, vtype                   # 002-040; the 001s were produced
        for p in paths:
            script = json.loads(p.read_text(encoding="utf-8"))
            validate_script(script, vtype, source=str(p))
            assert length_spec.check_script(script) == [], p.name
