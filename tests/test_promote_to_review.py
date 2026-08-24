#!/usr/bin/env python3
"""A --batch artifact must be able to reach the upload flow, once.

    python3 -m pytest tests/test_promote_to_review.py

output/video/ is where `main.py --batch` stops. The dashboard listed those
artifacts in Library, offered preview and download, and offered no way to
publish them — six videos carrying the first Learning Routes CTA sat there
from 18 August. The route did not exist.

The route that now exists is deliberately NOT an upload button. It is a move
into output/pending/, so a promoted artifact is indistinguishable from a
natively rendered one by the time Review and Upload see it, and there is still
exactly one upload path. Unifying those was Paso 5a and this must not undo it.

Both ends consult publication_log. The guard at upload is the one that stops a
duplicate mid-flight; the check here stops a published artifact from ever
appearing in the "ready to upload" list, which is the shape of the mistake
that published hPdSoqjvu3E twice.
"""

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture
def admin(tmp_path, monkeypatch):
    """admin.py with its output tree pointed at a scratch directory.

    Attribute patching only. An earlier version of this fixture popped "admin"
    out of sys.modules to force a clean import, which orphaned the module
    object test_reaper_survives_reload.py had already bound — importlib.reload
    then raised "module admin not in sys.modules" and the reaper test failed,
    but only when the two ran in the same session. The tests here need patched
    directories, not a fresh module.
    """
    monkeypatch.setattr("streamlit.set_page_config", lambda **k: None,
                        raising=False)
    admin = importlib.import_module("admin")
    out = tmp_path / "output"
    monkeypatch.setattr(admin, "OUTPUT_DIR", out)
    monkeypatch.setattr(admin, "VIDEO_DIR", out / "video")
    monkeypatch.setattr(admin, "PENDING_DIR", out / "pending")
    monkeypatch.setattr(admin, "APPROVED_DIR", out / "approved")
    monkeypatch.setattr(admin, "SCRIPTS_DIR", out / "scripts")
    return admin


def _batch_artifact(admin, name="break_the_ice", vtype="fill_blank",
                    with_script=True):
    vid = admin.VIDEO_DIR / vtype / f"{name}.mp4"
    vid.parent.mkdir(parents=True, exist_ok=True)
    vid.write_bytes(b"\x00mp4")
    if with_script:
        sp = admin.SCRIPTS_DIR / vtype / f"{name}.json"
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps({
            "type": vtype,
            "video_title": "Completa la frase",
            "hashtags": ["LearnEnglish"],
            "_meta": {"category": "idioms", "topic": "break the ice"},
        }, ensure_ascii=False), encoding="utf-8")
    return vid


def test_a_batch_artifact_lands_in_pending_not_approved(admin):
    """Promotion is a door into Review, not a shortcut past it."""
    vid = _batch_artifact(admin)

    verdict = admin.promote_to_review(vid)

    assert verdict["ok"], verdict["reason"]
    assert verdict["dest"] == admin.PENDING_DIR / "fill_blank" / "break_the_ice.mp4"
    assert verdict["dest"].exists()
    assert not vid.exists(), "the artifact was copied, not moved"
    assert not (admin.APPROVED_DIR / "fill_blank" / "break_the_ice.mp4").exists()


def test_the_sidecar_matches_what_the_dashboard_writes(admin):
    """Review and Upload must not be able to tell the two apart."""
    admin.promote_to_review(_batch_artifact(admin))

    meta = json.loads(
        (admin.PENDING_DIR / "fill_blank" / "break_the_ice.json").read_text())

    for key in ("artifact", "video_type", "category", "topic", "script_data",
                "created_at"):
        assert key in meta, f"the dashboard's sidecar has {key} and this does not"
    assert meta["video_type"] == "fill_blank"
    assert meta["category"] == "idioms"
    # Without script_data the Upload page has no title to generate from.
    assert meta["script_data"]["video_title"] == "Completa la frase"
    assert meta["promoted_from"] == "output/video"


def test_a_promoted_artifact_is_listed_for_review(admin):
    admin.promote_to_review(_batch_artifact(admin))

    names = [v["name"] for v in admin.get_pending_videos()]
    assert "break_the_ice" in names
    assert admin.get_library_videos() == [], "it should have left the library"


def test_an_already_published_artifact_is_refused(admin, monkeypatch):
    """The hPdSoqjvu3E shape: a published video back in the upload queue."""
    vid = _batch_artifact(admin)
    monkeypatch.setattr(
        "publication_log.find_by_artifact",
        lambda artifact, *a, **k: [{"platform": "youtube",
                                    "upload_id": "hPdSoqjvu3E"}])

    verdict = admin.promote_to_review(vid)

    assert not verdict["ok"]
    assert "already published" in verdict["reason"]
    assert "hPdSoqjvu3E" in verdict["reason"]
    assert vid.exists(), "a refused promotion must not move the file"


def test_promoting_twice_does_not_overwrite(admin):
    """The second press has nothing to move, and must not clobber the first."""
    admin.promote_to_review(_batch_artifact(admin))
    dest = admin.PENDING_DIR / "fill_blank" / "break_the_ice.mp4"
    dest.write_bytes(b"\x00the-one-under-review")

    again = admin.promote_to_review(_batch_artifact(admin))

    assert not again["ok"]
    assert "already exists" in again["reason"]
    assert dest.read_bytes() == b"\x00the-one-under-review"


def test_a_missing_script_still_promotes(admin):
    """A lost script costs metadata, not the route out of output/video/."""
    vid = _batch_artifact(admin, name="repro_fresh_20260817",
                          vtype="educational", with_script=False)

    verdict = admin.promote_to_review(vid)

    assert verdict["ok"]
    assert verdict["script_path"] is None
    meta = json.loads(verdict["meta_path"].read_text())
    assert meta["script_data"] == {}
    assert meta["topic"] == "repro fresh 20260817"


def test_a_timestamped_script_is_found_by_prefix(admin):
    vid = _batch_artifact(admin, name="my_bad", vtype="quiz",
                          with_script=False)
    sp = admin.SCRIPTS_DIR / "quiz" / "my_bad_20260817_101500.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps({"_meta": {"category": "slang"}}))

    assert admin.find_script_for(vid) == sp
    assert admin.promote_to_review(vid)["category"] == "slang"


def test_a_vanished_artifact_is_reported_not_raised(admin):
    """This is called from a button; it must not take the page down."""
    verdict = admin.promote_to_review(admin.VIDEO_DIR / "quiz" / "gone.mp4")

    assert not verdict["ok"]
    assert "no longer exists" in verdict["reason"]
