#!/usr/bin/env python3
"""Push a rendered lesson into a Learning Routes step — the client side of WP-38.

    python3 publish.py routes                                   # the route → module → step tree
    python3 publish.py publish --step <STEP_ID> --lesson third-person-s --video renders/third-person-s/<file>.mp4
    python3 publish.py unpublish --step <STEP_ID>

Contract (PROMPT_29_WP38): bearer token in `Authorization`, JSON in and out,
  GET    /admin/api/routes
  POST   /admin/api/steps/:id/video   multipart: video, subtitles?, title, duration_seconds, lesson_id, voice
  DELETE /admin/api/steps/:id/video

LR_BASE_URL and LR_STUDIO_TOKEN come from english-ai-videos/.env or ./.env (the admin's Manim
page writes the latter). The token is never printed. Standard library only.
"""
import argparse
import json
import mimetypes
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gen_audio import read_env, DEFAULT_ENV  # noqa: E402
import lesson as L  # noqa: E402
import renders as R  # noqa: E402

DEFAULT_BASE = "http://localhost:3000"
MAX_VIDEO_BYTES = 300 * 1024 * 1024


class PublishError(RuntimeError):
    pass


# ── HTTP plumbing ─────────────────────────────────────────────────────────────

def encode_multipart(fields: dict, files: dict) -> tuple:
    """(body, content_type) — files = {part: (filename, bytes, mime)}."""
    boundary = "----studio" + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        if value is None:
            continue
        chunks += [f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                   str(value).encode("utf-8"), b"\r\n"]
    for name, (filename, data, mime) in files.items():
        chunks += [f"--{boundary}\r\n".encode(),
                   f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
                   f"Content-Type: {mime}\r\n\r\n".encode(), data, b"\r\n"]
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def request(base: str, token: str, method: str, path: str, body: bytes = None, content_type: str = None,
            timeout: int = 600) -> tuple:
    """(status, parsed json or None). Raises PublishError with a readable message on 4xx/5xx."""
    if len(token) < 16:
        raise PublishError("LR_STUDIO_TOKEN is missing (english-ai-videos/.env or ./.env).")
    req = urllib.request.Request(base.rstrip("/") + path, data=body, method=method,
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as error:
        detail = error.read()[:300].decode("utf-8", "replace")
        hints = {401: "the token was refused — is studio.api_token set in the Rails credentials and the same as LR_STUDIO_TOKEN?",
                 404: "no such step (or WP-38 is not deployed on this server)",
                 413: "the video is too large for the server", 422: "the server rejected the file"}
        raise PublishError(f"{method} {path} → {error.code}: {hints.get(error.code, '')} {detail}".strip()) from None
    except urllib.error.URLError as error:
        raise PublishError(f"cannot reach {base}: {error.reason}") from None


# ── API ───────────────────────────────────────────────────────────────────────

def fetch_routes(base: str, token: str) -> list:
    _, data = request(base, token, "GET", "/admin/api/routes")
    return data or []


def flatten_steps(tree: list) -> list:
    """[{route, module, step_id, step_title, description, has_video}] in course order."""
    rows = []
    for route in tree:
        for module in sorted(route.get("modules", []), key=lambda m: m.get("position", 0)):
            for step in sorted(module.get("steps", []), key=lambda s: s.get("position", 0)):
                rows.append({"route": route["title"], "route_id": route["id"], "level": route.get("level", ""),
                             "module": module["title"], "step_id": step["id"], "step_title": step["title"],
                             "description": step.get("description") or "", "has_video": bool(step.get("has_video")),
                             "video": step.get("video")})
    return rows


def topic_for(step: dict) -> tuple:
    """(topic, extra guidance) for gen_script.py, from a step's title, description and route level."""
    topic = step["step_title"].strip()
    extra = f"This lesson is step «{topic}» of the module «{step['module']}» in the course «{step['route']}»."
    if step.get("description"):
        extra += f" The course describes it as: {step['description'].strip()}"
    return topic, extra


def publish(base: str, token: str, step_id: str, video: Path, subtitles: Path, title: str, duration_seconds,
            lesson_id: str, voice: str) -> dict:
    data = Path(video).read_bytes()
    if data[4:8] != b"ftyp":
        raise PublishError(f"{video} is not an mp4 (no ftyp box)")
    if len(data) > MAX_VIDEO_BYTES:
        raise PublishError(f"{video} is {len(data) // 1024 // 1024} MB; the server takes at most 300 MB")
    files = {"video": (Path(video).name, data, "video/mp4")}
    # The server clears the captions of the film being replaced when no `subtitles` part
    # arrives (they were timed to the old film). So sending none is a decision, and the
    # caller is told about it in `subtitles_sent` — the page and the CLI warn on False.
    subtitles_sent = bool(subtitles and Path(subtitles).exists())
    if subtitles_sent:
        files["subtitles"] = (Path(subtitles).name, Path(subtitles).read_bytes(), "application/x-subrip")
    fields = {"title": title, "duration_seconds": int(round(duration_seconds or 0)), "lesson_id": lesson_id, "voice": voice}
    body, ctype = encode_multipart(fields, files)
    status, result = request(base, token, "POST", f"/admin/api/steps/{step_id}/video", body, ctype)
    return {"status": status, "subtitles_sent": subtitles_sent, **(result or {})}


def unpublish(base: str, token: str, step_id: str) -> int:
    status, _ = request(base, token, "DELETE", f"/admin/api/steps/{step_id}/video")
    return status


def latest_render(lesson_id: str, studio_dir: Path = HERE) -> dict:
    for row in R.ledger(studio_dir):
        if row.get("lesson") == lesson_id and (studio_dir / "renders" / row["file"]).exists():
            return row
    return {}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["routes", "publish", "unpublish"])
    parser.add_argument("--step")
    parser.add_argument("--lesson")
    parser.add_argument("--video", type=Path, help="default: the lesson's latest render in the ledger")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    args = parser.parse_args()
    env = read_env(args.env)
    base, token = env.get("LR_BASE_URL", DEFAULT_BASE), env.get("LR_STUDIO_TOKEN", "")
    try:
        if args.command == "routes":
            for row in flatten_steps(fetch_routes(base, token)):
                flag = "🎞" if row["has_video"] else "  "
                print(f"{flag} {row['step_id']}  {row['route']} › {row['module']} › {row['step_title']}")
            return 0
        if not args.step:
            sys.exit("--step is required")
        if args.command == "unpublish":
            print("unpublished:", unpublish(base, token, args.step))
            return 0
        if not args.lesson:
            sys.exit("--lesson is required")
        lesson = L.load(HERE / "lessons" / f"{args.lesson}.json")
        row = latest_render(args.lesson)
        video = args.video or (HERE / "renders" / row["file"] if row else None)
        if not video or not Path(video).exists():
            sys.exit("no render found for that lesson — render it first or pass --video")
        result = publish(base, token, args.step, video, Path(video).with_suffix(".srt"), lesson["title"],
                         row.get("duration_s") or R.probe_duration(Path(video)), lesson["id"], row.get("voice", ""))
        if not result["subtitles_sent"]:
            print(f"warning: no {Path(video).with_suffix('.srt').name} next to the render — the step was published "
                  "WITHOUT captions (and any captions it had were removed)", file=sys.stderr)
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    except PublishError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    sys.exit(main())
