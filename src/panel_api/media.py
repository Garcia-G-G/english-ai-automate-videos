"""STEP 85 §2: GET /media/..., only files under output/. Path-checked like senal_server.resolve (no `..`, no
symlink out, no NUL); MP4s answer HTTP Range so a <video> can seek; thumbnails get long cache headers."""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response

ROOT = Path(__file__).resolve().parents[2]
MEDIA_ROOT = ROOT / "output"
CHUNK = 1 << 20
IMMUTABLE = "public, max-age=31536000, immutable"
mimetypes.add_type("image/webp", ".webp")
router = APIRouter()


def resolve(rel: str, root: Optional[Path] = None) -> Optional[Path]:
    """A URL path under /media → a file inside the media root; None for anything else."""
    rel = unquote(rel)
    if "\0" in rel or not rel:
        return None
    base = (root or MEDIA_ROOT).resolve()
    target = (base / rel.lstrip("/")).resolve()
    return target if base in target.parents and target.is_file() else None


def url_for(path: Path, root: Optional[Path] = None) -> Optional[str]:
    """The /media URL of a file under the media root, or None when it lies outside."""
    try:
        return "/media/" + quote(Path(path).resolve().relative_to((root or MEDIA_ROOT).resolve()).as_posix())
    except ValueError:
        return None


def _range(header: str, size: int):
    """«bytes=a-b» → (start, end) inclusive, or None when it cannot be satisfied."""
    try:
        unit, _, spec = header.partition("=")
        a, _, b = spec.split(",")[0].strip().partition("-")
        if unit.strip() != "bytes":
            return None
        start, end = (size - int(b), size - 1) if a == "" else (int(a), int(b) if b else size - 1)
    except ValueError:
        return None
    end = min(end, size - 1, start + 8 * CHUNK - 1)         # a shorter 206 is fine; never read a whole 40 MB file
    return (start, end) if 0 <= start <= end else None


@router.get("/media/{rel:path}")
def media(rel: str, request: Request):
    f = resolve(rel)
    if f is None:
        return Response(status_code=404)
    kind = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    cache = IMMUTABLE if f.suffix in (".webp", ".png", ".jpg") else "no-cache"
    size = f.stat().st_size
    rng = request.headers.get("range")
    if f.suffix == ".mp4" and rng:
        got = _range(rng, size)
        if got is None:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        start, end = got
        with open(f, "rb") as fh:
            fh.seek(start)
            body = fh.read(end - start + 1)
        return Response(body, status_code=206, media_type=kind,
                        headers={"Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes", "Cache-Control": cache})
    return FileResponse(f, media_type=kind, headers={"Accept-Ranges": "bytes", "Cache-Control": cache})
