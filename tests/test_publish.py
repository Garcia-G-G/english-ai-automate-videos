#!/usr/bin/env python3
"""publish.py against a stub of the WP-38 API — the contract both sides are coded to.

The class of bug: the studio sends a part named `file` and the server expects `video`, or the
token travels as a query string, and the first real upload fails after a 7-minute render. The
stub records exactly what arrives and the tests assert the contract field by field.
"""
import json
import sys
import threading
from email import message_from_bytes
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

STUDIO = Path(__file__).resolve().parent.parent / "experiments" / "manim_voiceover_poc"
sys.path.insert(0, str(STUDIO))
import publish as P  # noqa: E402

TOKEN = "studio-token-0123456789abcdef"
SEEN = []


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _auth(self):
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self.send_response(401); self.end_headers(); self.wfile.write(b'{"error":"unauthorized"}')
            return False
        return True

    def do_GET(self):
        if not self._auth():
            return
        tree = [{"id": "r1", "title": "Inglés A2", "level": "A2", "modules": [
            {"id": "m1", "title": "Presente", "position": 1, "steps": [
                {"id": "s2", "position": 2, "title": "Simple vs continuo", "description": "Cuándo usar cada uno", "has_video": False},
                {"id": "s1", "position": 1, "title": "La ese de la tercera persona", "description": "", "has_video": True,
                 "video": {"title": "x", "duration_seconds": 477}}]}]}]
        body = json.dumps(tree).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        if not self._auth():
            return
        length = int(self.headers["Content-Length"])
        raw = self.rfile.read(length)
        msg = message_from_bytes(b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + raw, policy=HTTP)
        parts = {}
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            parts[name] = {"filename": part.get_filename(), "type": part.get_content_type(), "size": len(part.get_payload(decode=True)),
                           "value": part.get_payload(decode=True) if part.get_filename() is None else None}
        SEEN.append({"path": self.path, "parts": parts})
        body = json.dumps({"step_id": self.path.split("/")[4], "section_index": 0, "video_url": "/rails/active_storage/x.mp4",
                           "subtitles_url": "/rails/active_storage/x.srt"}).encode()
        self.send_response(201); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)

    def do_DELETE(self):
        if not self._auth():
            return
        SEEN.append({"path": self.path, "method": "DELETE"})
        self.send_response(204); self.end_headers()


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def fake_mp4(path: Path, size=4096):
    path.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * (size - 12))
    return path


def test_routes_tree_is_flattened_in_course_order(server):
    rows = P.flatten_steps(P.fetch_routes(server, TOKEN))
    assert [r["step_id"] for r in rows] == ["s1", "s2"]                 # sorted by position, not by arrival
    assert rows[0]["has_video"] and rows[0]["route"] == "Inglés A2" and rows[1]["description"] == "Cuándo usar cada uno"
    topic, extra = P.topic_for(rows[1])
    assert topic == "Simple vs continuo" and "Presente" in extra and "Cuándo usar cada uno" in extra


def test_publish_sends_the_exact_multipart_contract(server, tmp_path):
    video = fake_mp4(tmp_path / "lesson.mp4")
    (tmp_path / "lesson.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhola\n")
    SEEN.clear()
    result = P.publish(server, TOKEN, "s2", video, tmp_path / "lesson.srt", "Simple vs continuo", 417.86, "simple-vs-continuous", "matilda")
    assert result["status"] == 201 and result["video_url"].endswith(".mp4") and result["step_id"] == "s2"
    seen = SEEN[-1]
    assert seen["path"] == "/admin/api/steps/s2/video"
    parts = seen["parts"]
    assert set(parts) == {"video", "subtitles", "title", "duration_seconds", "lesson_id", "voice"}
    assert parts["video"]["type"] == "video/mp4" and parts["video"]["size"] == 4096 and parts["video"]["filename"] == "lesson.mp4"
    assert parts["subtitles"]["type"] == "application/x-subrip"
    assert parts["duration_seconds"]["value"] == b"418" and parts["lesson_id"]["value"] == b"simple-vs-continuous"
    assert parts["voice"]["value"] == b"matilda" and parts["title"]["value"].decode() == "Simple vs continuo"
    assert result["subtitles_sent"] is True


def test_publish_without_subtitles_omits_the_part(server, tmp_path):
    video = fake_mp4(tmp_path / "v.mp4")
    SEEN.clear()
    result = P.publish(server, TOKEN, "s1", video, tmp_path / "missing.srt", "t", 10, "x", "v")
    assert "subtitles" not in SEEN[-1]["parts"]
    # WP-38 rule: a film that arrives without captions CLEARS the captions of the film it
    # replaces (they were timed to the old film). The client must know it sent none, so
    # the page and the CLI can warn instead of silently un-captioning a step.
    assert result["subtitles_sent"] is False


def test_publish_refuses_a_file_that_is_not_an_mp4_before_uploading(server, tmp_path):
    png = tmp_path / "fake.mp4"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    SEEN.clear()
    with pytest.raises(P.PublishError, match="not an mp4"):
        P.publish(server, TOKEN, "s1", png, None, "t", 1, "x", "v")
    assert SEEN == []


def test_wrong_token_and_missing_token_give_a_readable_error(server, tmp_path):
    with pytest.raises(P.PublishError, match="401"):
        P.fetch_routes(server, "wrong-token-0123456789abcdef")
    with pytest.raises(P.PublishError, match="LR_STUDIO_TOKEN is missing"):
        P.fetch_routes(server, "")


def test_unpublish_deletes(server):
    SEEN.clear()
    assert P.unpublish(server, TOKEN, "s1") == 204
    assert SEEN[-1] == {"path": "/admin/api/steps/s1/video", "method": "DELETE"}


def test_unreachable_server_is_a_publish_error_not_a_traceback():
    with pytest.raises(P.PublishError, match="cannot reach"):
        P.fetch_routes("http://127.0.0.1:9", TOKEN)
