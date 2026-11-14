"""STEP 80: what each platform does with what we send, enforced before every upload.
Limits from the official pages (read 27 Oct 2026); see src/platform_rules.py."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import platform_rules as R  # noqa: E402


def test_youtube_counts_tags_as_youtube_does():
    assert R.tags_length(["Foo Baz"]) == 9 and R.tags_length(["Foo-Baz"]) == 7
    assert R.tags_length(["a", "b"]) == 3                                   # the comma counts


def test_the_title_loses_its_hashtags_and_is_cut_on_a_word():
    f = R.youtube("¿Cómo se dice CASA en inglés? 🏠 #Shorts", "D")
    assert f["title"] == "¿Cómo se dice CASA en inglés? 🏠" and f["changes"]
    long = "palabra " * 20
    assert R.youtube(long, "D")["title"] == ("palabra " * 12).strip()       # 95 chars, a whole word
    assert R.youtube("a" * 120, "D")["title"] == "a" * 100
    assert R.youtube("a <b> c", "D")["title"] == "a b c"


def test_the_description_fits_5000_bytes_not_characters():
    d = R.youtube("t", "ñandú " * 1000)["description"]                     # 6000 chars, 7000 bytes
    assert len(d.encode("utf-8")) <= 5000 and not d.endswith("ñan")


def test_each_hashtag_once_case_never_splits_it():
    f = R.youtube("t", "Texto\n\n#AprenderIngles #inglesfacil #aprenderinglés #InglesFacil")
    assert f["description"] == "Texto\n\n#AprenderIngles #inglesfacil"
    assert not [p for p in R.problems("youtube", "t", "#Shorts #shorts") if p["code"] == "hashtag_spellings"]
    assert [p for p in R.problems("youtube", "t", "#inglés #ingles") if p["code"] == "hashtag_spellings"]


def test_past_60_hashtags_the_last_ones_go():
    d = " ".join(f"#t{i}" for i in range(70))
    assert R.problems("youtube", "t", d)[0]["code"] == "yt_hashtags_60"
    assert len(R.hashtags_in(R.youtube("t", d)["description"])) == 60


def test_tags_stop_at_500_characters():
    tags = [f"etiqueta{i:03d}" for i in range(60)]
    out = R.youtube("t", "d", tags)["tags"]
    assert R.tags_length(out) <= 500 < R.tags_length(tags)


def test_instagram_caption_keeps_30_hashtags_and_2200_characters():
    c = "Hola " + " ".join(f"#h{i}" for i in range(40))
    assert len(R.hashtags_in(R.instagram(c)["caption"])) == 30
    assert len(R.instagram("x " * 2000)["caption"]) <= 2200


def test_facebook_reels_and_shorts_durations():
    assert R.problems("facebook", duration=92.0)[0]["code"] == "fb_reel_len"
    assert not R.problems("facebook", duration=89.9)
    assert R.problems("youtube", "t", "d", duration=200)[0]["code"] == "yt_short_len"
    assert not R.problems("youtube", "t", "d", duration=200, short=False)


def test_a_link_in_a_short_is_flagged_not_in_a_lesson():
    assert R.problems("youtube", "t", "Más en learningroutes.com")[0]["code"] == "yt_short_link"
    assert not R.problems("youtube", "t", "Más en learningroutes.com", short=False)


def test_the_ledger_records_what_was_actually_sent(tmp_path):
    import publication_log as PL
    from uploader import UploadResult
    ledger = tmp_path / "ledger.jsonl"
    r = UploadResult("youtube", True, upload_id="v1", url="https://youtube.com/shorts/v1",
                     sent={"title": "T", "description": "D", "hashtags": ["a"], "changes": ["x"]})
    PL.record_upload_result(artifact="a1", video_path=str(tmp_path / "a1.mp4"), video_type="quiz",
                            platform="youtube", result=r, sent_title="T #Shorts", sent_description="D D",
                            sent_hashtags=["a", "b"], ledger_path=ledger)
    row = json.loads(ledger.read_text().splitlines()[0])
    assert (row["published_title"], row["published_description"], row["hashtags"]) == ("T", "D", ["a"])


def test_the_upload_audit_reads_the_ledger_and_finds_nothing_blocking_in_a_clean_row(tmp_path):
    sys.path.insert(0, str(ROOT / "tools"))
    import upload_audit as A
    ledger = tmp_path / "l.jsonl"
    ledger.write_text(json.dumps({"platform": "youtube", "artifact": "x", "published_title": "T #Shorts",
                                  "published_description": "D #a", "hashtags": ["a"]}) + "\n")
    report = A.audit(ledger)
    assert report["blocking"] == 0 and report["by_code"]["yt_hashtag_in_title"] == 1
