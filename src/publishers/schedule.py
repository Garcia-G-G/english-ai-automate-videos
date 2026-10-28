"""The Meta publishing queue and its daily slots.

WHAT GOES IN. Only owner-approved videos: files in output/approved/ (or
already in output/uploaded/ after another platform took them). main.py's
OWNER_APPROVAL_REQUIRED policy still holds; this only times what was approved.
Approving in the dashboard enqueues when `meta_publish.auto_enqueue_on_approve`
is on; `tools/meta_publish.py enqueue` does it by hand.

WHAT COMES OUT. At each configured slot, one video goes to every platform it
is still queued for, through main.upload_video: the same guard, attempt log
and ledger as every other upload. So the status shown here is not stored
here; it is read back from the ledger and the attempt log.

The queue file sits next to the ledger (output/published/meta_queue.json).
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Dict, List, Optional

import publication_log as PL

logger = logging.getLogger(__name__)

DEFAULTS = {"platforms": ["instagram", "facebook"], "slots": ["10:00", "19:00"],
            "auto_enqueue_on_approve": False}


def settings(config: Optional[Dict] = None) -> Dict:
    if config is None:
        import yaml
        path = Path(__file__).resolve().parents[2] / "config.yaml"
        config = yaml.safe_load(path.read_text()) or {} if path.exists() else {}
    return {**DEFAULTS, **(config.get("meta_publish") or {})}


# Paths are derived from the ledger's at call time so the test fixture that
# redirects the ledger redirects these too.
def _output() -> Path:
    return Path(PL.LEDGER_DIR).parent


def queue_path() -> Path:
    return Path(PL.LEDGER_DIR) / "meta_queue.json"


def load_queue() -> List[Dict]:
    try:
        return json.loads(queue_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


def _save(entries: List[Dict]) -> None:
    path = queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def find_video(artifact: str, video_type: str) -> Optional[Path]:
    for stage in ("approved", "uploaded"):
        path = _output() / stage / video_type / f"{artifact}.mp4"
        if path.is_file():
            return path
    return None


def enqueue(video_path, now: Optional[datetime] = None) -> Dict:
    """Queue an approved video. Idempotent. Refuses anything not approved by the owner."""
    path = Path(video_path).resolve()
    stage = path.parent.parent
    if stage.name not in ("approved", "uploaded") or stage.parent != _output().resolve():
        raise ValueError(f"{path.name}: only videos in output/approved/ or output/uploaded/ "
                         f"can be queued (owner approval comes first)")
    if not path.is_file():
        raise ValueError(f"{path} does not exist")
    entries = load_queue()
    for entry in entries:
        if entry["artifact"] == path.stem:
            return entry
    entry = {"artifact": path.stem, "video_type": path.parent.name,
             "enqueued_at": (now or datetime.now()).isoformat(timespec="seconds")}
    _save(entries + [entry])
    logger.info("queued %s for Meta publishing", path.stem)
    return entry


def platform_status(artifact: str, platform: str, ledger=None, attempts=None) -> Dict:
    """queued | published | failed | holding, with the permalink or the reason."""
    ledger = PL.read_ledger() if ledger is None else ledger
    attempts = PL.read_attempts() if attempts is None else attempts
    rows = [r for r in ledger if r.get("artifact") == artifact and r.get("platform") == platform]
    if rows:
        return {"status": "published", "url": rows[-1].get("url"), "id": rows[-1].get("upload_id")}
    tried = [r for r in attempts if r.get("artifact") == artifact and r.get("platform") == platform]
    if not tried:
        return {"status": "queued"}
    last = tried[-1]
    if last.get("status") == PL.ATTEMPT_FAILED:
        return {"status": "failed", "detail": last.get("detail", "")}
    return {"status": "holding", "detail": f"attempt {last.get('status')}; the guard reconciles it"}


def status_rows(cfg: Optional[Dict] = None) -> List[Dict]:
    cfg = cfg or settings()
    ledger, attempts = PL.read_ledger(), PL.read_attempts()
    return [{**e, "path": find_video(e["artifact"], e["video_type"]),
             **{p: platform_status(e["artifact"], p, ledger, attempts) for p in cfg["platforms"]}}
            for e in load_queue()]


def _slot_times(slots: List[str], day: datetime) -> List[datetime]:
    out = []
    for s in slots:
        hh, mm = (int(x) for x in s.split(":"))
        out.append(datetime.combine(day.date(), dtime(hh, mm)))
    return sorted(out)


def due_slot(now: datetime, slots: List[str], platforms: List[str], attempts=None) -> Optional[datetime]:
    """Today's latest slot at or before `now`, unless an attempt already used it."""
    past = [t for t in _slot_times(slots, now) if t <= now]
    if not past:
        return None
    slot = past[-1]
    attempts = PL.read_attempts() if attempts is None else attempts
    for row in attempts:
        if row.get("platform") in platforms and row.get("status") == PL.ATTEMPT_STARTED:
            try:
                if datetime.fromisoformat(row["at"]) >= slot:
                    return None
            except (KeyError, ValueError):
                continue
    return slot


def next_item(cfg: Dict, artifact: Optional[str] = None) -> Optional[Dict]:
    """The oldest queued video with a platform still to do, or `artifact` (failed ones included)."""
    for row in status_rows(cfg):
        if artifact and row["artifact"] != artifact:
            continue
        wanted = ("queued", "failed") if artifact else ("queued",)
        todo = [p for p in cfg["platforms"] if row[p]["status"] in wanted]
        if todo and row["path"]:
            return {**row, "todo": todo}
    return None


def approved_item(cfg: Dict, artifact: str) -> Optional[Dict]:
    """An approved video that is not queued, shaped like next_item's row: for a dry run only,
    so checking one video does not put it in the slot queue (STEP 72 §5)."""
    found = sorted((_output() / "approved").glob(f"*/{artifact}.mp4"))
    if not found:
        return None
    path = found[0]
    status = {p: platform_status(artifact, p) for p in cfg["platforms"]}
    todo = [p for p in cfg["platforms"] if status[p]["status"] in ("queued", "failed")]
    return {"artifact": artifact, "video_type": path.parent.name, "path": path, **status,
            "todo": todo} if todo else None


def script_for(path: Path, video_type: str) -> Dict:
    """The script behind a video: its sidecar's, else the audio JSON (as admin.script_for_upload)."""
    for candidate, key in ((path.with_suffix(".json"), "script_data"),
                           (_output() / "audio" / video_type / f"{path.stem}.json", None)):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        data = data.get(key) if key else data
        if data:
            return data
    return {}


def dry_run(item: Dict) -> Dict:
    """What would be sent, checked against the specs and, if credentials exist, the live API.

    No side effects: nothing is sent and nothing is written, not even the cached
    Instagram id (only GETs, STEP 70 §2).
    """
    from publishers import get_publisher, validate_reel
    from upload_metadata import NO_OPERATOR_EDITS, resolve_upload_metadata

    script = script_for(item["path"], item["video_type"])
    report = {"artifact": item["artifact"], "path": str(item["path"]), "platforms": {}}
    for platform in item["todo"]:
        out = report["platforms"][platform] = {}
        try:
            validate_reel(str(item["path"]), platform)
            out["spec"] = "ok"
        except ValueError as exc:
            out["spec"] = str(exc)
        meta = resolve_upload_metadata(item["artifact"], script, platform, item["video_type"],
                                       (script.get("_meta") or {}).get("category", ""), NO_OPERATOR_EDITS)
        out["caption"] = meta["description"]
        publisher = get_publisher(platform)
        if not publisher.is_configured():
            out["api"] = "not configured (env vars missing)"
            continue
        try:
            out["api"] = publisher.check()
        except Exception as exc:                          # noqa: BLE001
            out["api"] = f"error: {exc}"
    return report


#: The platforms whose every publish takes publish_lock (panel button, now, tick, loop).
LOCKED_PLATFORMS = ("instagram", "facebook")
LOCKED = "publicando en la franja, espera"


@contextmanager
def publish_lock():
    """One Meta publish at a time across processes and threads. Yields False, at once, when
    another holds it: the caller must do nothing then."""
    path = queue_path().with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True


def publish(item: Dict) -> Dict:
    import main
    return main.upload_video(item["path"], item["video_type"], script_for(item["path"], item["video_type"]),
                             platforms=item["todo"], artifact=item["artifact"])


def tick(now: Optional[datetime] = None, *, dry: bool = False, force: bool = False,
         artifact: Optional[str] = None, cfg: Optional[Dict] = None) -> Dict:
    """Publish the next queued video if a slot is due (or `force`). Returns what happened."""
    cfg = cfg or settings()
    now = now or datetime.now()
    slot = due_slot(now, cfg["slots"], cfg["platforms"])
    if not (force or slot):
        return {"action": "wait", "reason": "no slot due", "slots": cfg["slots"]}
    item = next_item(cfg, artifact)
    if item is None and dry and artifact:
        item = approved_item(cfg, artifact)
    if item is None:
        return {"action": "idle", "reason": "nothing queued"}
    if dry:
        return {"action": "dry_run", "slot": slot and slot.isoformat(), **dry_run(item)}
    # One publisher at a time: cron tick, `loop`, `now` and the dashboard's Upload button.
    with publish_lock() as got:
        if not got:
            return {"action": "wait", "reason": "locked: another publish is running"}
        if next_item(cfg, artifact) != item:              # re-read under the lock
            return {"action": "wait", "reason": "queue changed; next tick"}
        return {"action": "published", "slot": slot and slot.isoformat(), "outcome": publish(item)}
