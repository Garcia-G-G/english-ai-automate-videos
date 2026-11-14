"""STEP 85b §6: «Miniaturas mejores para lo publicado». Lists the published videos whose chosen thumbnail is not what
we last sent to the platform, best performers first. NOTHING is sent until Garcia ticks videos and presses «Aplicar»;
at most 40 changes a day; YouTube only when the capability memo says yes."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from . import publish

ROOT = publish.ROOT
MAX_PER_DAY = 40
QUOTA_FILE = ROOT / "output" / "state" / "thumb_changes.json"
STAGES = ("uploaded", "approved", "pending", "video", "published")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _folder(artifact: str, root: Path) -> Optional[Path]:
    for stage in STAGES:
        for f in (root / "output" / stage).glob(f"*/{artifact}.thumb"):
            if (f / "thumb.jpg").exists():
                return f
    return None


def _sent_sha(folder: Path, platform: str) -> Optional[str]:
    try:
        meta = json.loads(folder.with_name(folder.name[:-len(".thumb")] + ".json").read_text(encoding="utf-8"))
        return ((meta.get("thumbnail") or {}).get("platforms") or {}).get(platform, {}).get("sha")
    except (OSError, ValueError):
        return None


def allowed(platform: str, vertical: bool, memo: Path = None) -> bool:
    """YouTube only when the memo says yes for that kind of video; Facebook always (its refusal is recorded)."""
    if platform == "youtube":
        return publish.capability(publish.SHORTS if vertical else publish.CHANNEL, memo)["state"] == "yes"
    return platform == "facebook"


def proposals(rows: Iterable[Dict], views: Optional[Dict[str, int]] = None, root: Path = None, memo: Path = None) -> List[Dict]:
    """One proposal per (artifact, platform) whose thumb.jpg differs from what we last sent; sorted by views, best first."""
    root, views, seen, out = root or ROOT, views or {}, set(), []
    for r in sorted(rows, key=lambda r: r.get("published_at") or "", reverse=True):
        key = (r.get("artifact"), r.get("platform"))
        if key in seen or not r.get("upload_id") or r.get("platform") not in ("youtube", "facebook"):
            continue
        seen.add(key)
        folder = _folder(r["artifact"], root)
        if folder is None:
            continue
        jpg = folder / "thumb.jpg"
        vertical = _is_vertical(jpg)
        if _sent_sha(folder, r["platform"]) == _sha(jpg) or not allowed(r["platform"], vertical, memo):
            continue
        out.append({"artifact": r["artifact"], "platform": r["platform"], "video_id": str(r["upload_id"]), "jpg": jpg, "vertical": vertical,
                    "views": int(views.get(str(r["upload_id"]), 0)), "title": r.get("published_title") or r["artifact"]})
    out.sort(key=lambda p: p["views"], reverse=True)
    return out


def _is_vertical(jpg: Path) -> bool:
    from PIL import Image
    w, h = Image.open(jpg).size
    return h > w


def used_today(today: Optional[date] = None, path: Path = None) -> int:
    try:
        data = json.loads((path or QUOTA_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    return int(data.get("count", 0)) if data.get("date") == (today or date.today()).isoformat() else 0


def apply(selected: List[Dict], token_yt: Callable[[], str], token_fb: Callable[[], str], get: Callable, post: Callable,
          today: Optional[date] = None, quota: Path = None, memo: Path = None, log: Path = None) -> List[Dict]:
    """Send ONLY the ticked proposals, at most MAX_PER_DAY changes a day (a proposal past the cap is returned as
    `deferred`, not sent). Every answer goes to the ledger and the sidecar; a failure never raises."""
    quota = quota or QUOTA_FILE
    n, results = used_today(today, quota), []
    for p in selected:
        if n >= MAX_PER_DAY:
            results.append({**_brief(p), "result": "deferred", "message": f"tope de {MAX_PER_DAY} cambios al día"})
            continue
        if not allowed(p["platform"], p["vertical"], memo):
            results.append({**_brief(p), "result": "skipped", "message": "YouTube aún no deja poner miniaturas propias"})
            continue
        try:
            if p["platform"] == "youtube":
                out = publish.youtube(p["video_id"], p["jpg"], p["vertical"], token_yt(), get, post, memo=memo)
            else:
                out = publish.facebook(p["video_id"], p["jpg"], token_fb(), post)
        except Exception as exc:                            # noqa: BLE001 — a thumbnail never touches a published video
            out = {"result": "error", "message": str(exc)[:200]}
        n += 1
        if out["result"] == "ok":
            out["sha"] = _sha(p["jpg"])
        publish._log_and_record(p["artifact"], p["platform"], p["video_id"], out, log)
        results.append({**_brief(p), **out})
    quota.parent.mkdir(parents=True, exist_ok=True)
    quota.write_text(json.dumps({"date": (today or date.today()).isoformat(), "count": n}), encoding="utf-8")
    return results


def _brief(p: Dict) -> Dict:
    return {"artifact": p["artifact"], "platform": p["platform"]}
