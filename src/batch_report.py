"""One file per batch run, saying what happened — without reading logs.

WHY. R1 took fill_blank from one combined options TTS call to nine calls per
video, so there is more per-call failure surface and nobody is watching when
it fires. Everything downstream already refuses to abort a batch on one
failure, which is correct, but the consequence is that a failure becomes a
log line and the run still exits 0.

Two prior commits left specific things stranded in logs where, headless, they
might as well not exist:

  PROMPT 2 holds on a 404'd resumable session URI and logs CRITICAL. That is
  a video that may already be live and cannot be resolved automatically.

  PROMPT 1 leaves live-but-unrecorded at CRITICAL. The video IS live and the
  repo cannot name it.

Both are in NEEDS_HUMAN, at the top, in a section that is empty on a clean
run — so an operator reads one file and stops if it is empty.

SKIPPED IS ITS OWN CATEGORY, never folded into success. The idempotency guard
keys on (artifact, platform), and its documented hole is that re-rendering a
topic under the same name means the guard refuses to publish the new file,
forever, because a skip produces no signal. The key is right; the silence was
the problem. Every skip is recorded with its reason and the videoId the guard
believes is already live, so the hole is visible the morning it bites.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "output" / "batch_reports"

#: Where an artifact that FAILED goes — a pipeline failure, so it is findable
#: with a reason. Distinct from REJECTED_DIR below: a failure means a stage
#: broke, a rejection means the artifact was produced and judged unfit. The
#: remedies differ, so the trees differ.
FAILED_DIR = ROOT / "output" / "failed"

#: Where an artifact the QA GATE refused goes. This tree already means
#: exactly that (admin.py:61 REJECTED_DIR) and is the correct destination.
REJECTED_DIR = ROOT / "output" / "rejected"

SCHEMA_VERSION = 1

# Per-video outcome categories.
ATTEMPTED = "attempted"
PUBLISHED = "published"
SKIPPED = "skipped"
FAILED = "failed"
#: Counted independently of publishing, because publishing is optional and
#: producing a video is not. With --upload off every outcome bucket stayed at
#: zero, so a run that made six good videos and a run that made nothing
#: printed the same summary line. These two are what a scheduled run has to
#: be able to prove it did.
RENDERED = "rendered"
GATE_PASSED = "gate_passed"
#: The QA gate produced an artifact and refused it. NOT "failed": nothing
#: broke, and the remedy is to look at the blocking flags, not at a traceback.
REJECTED = "rejected"
NEEDS_HUMAN = "needs_human"


class BatchReport:
    """Accumulates one run's outcomes and writes them as one file.

    Every method is failure-tolerant on purpose. A reporting bug must never
    be the thing that takes down a batch — that would be the same defect this
    module exists to fix, one level up.
    """

    def __init__(self, run_id: str = None, kind: str = "batch",
                 report_dir: Path = None):
        self.started = datetime.now()
        self.run_id = run_id or self.started.strftime("%Y%m%d_%H%M%S")
        self.kind = kind
        self.report_dir = Path(report_dir) if report_dir else REPORT_DIR
        self.videos: List[Dict] = []

    # ── recording ────────────────────────────────────────────────────

    def start_video(self, name: str, video_type: str = "",
                    topic: str = "") -> Dict:
        entry = {"artifact": name, "type": video_type, "topic": topic,
                 "status": ATTEMPTED, "stage": "script", "reason": None,
                 "published": [], "skipped": [], "failed": [],
                 "needs_human": [], "artifact_path": None,
                 "started_at": datetime.now().isoformat()}
        self.videos.append(entry)
        return entry

    def reject(self, entry: Dict, blocking_flags, artifact_path=None) -> None:
        """The gate produced an artifact and refused it."""
        reject(entry, blocking_flags, artifact_path)

    def record_render(self, entry: Dict, video_path, gate: str = None) -> None:
        """A video rendered and cleared the gate. Independent of publishing."""
        record_render(entry, video_path, gate)

    def fail(self, entry: Dict, stage: str, reason: str,
             artifact_path=None) -> None:
        """A stage failed and the video did not publish."""
        if entry is None:
            return
        entry.update(status=FAILED, stage=stage, reason=str(reason)[:1000])
        if artifact_path:
            entry["artifact_path"] = str(artifact_path)

    def record_upload_outcome(self, entry: Dict, outcome: Dict) -> None:
        """Fold main.upload_video's outcome dict into this run's report."""
        record_upload_outcome(entry, outcome)


    # ── reading it back ──────────────────────────────────────────────

    @property
    def needs_human(self) -> List[Dict]:
        out = []
        for v in self.videos:
            for item in v["needs_human"]:
                out.append({"artifact": v["artifact"], **item})
        return out

    def counts(self) -> Dict[str, int]:
        # ATTEMPTED is the number of videos tried, taken from the list length
        # and NOT incremented in the loop below. It used to be both, so a
        # one-video run reported "2 attempted".
        c = {ATTEMPTED: len(self.videos), RENDERED: 0, GATE_PASSED: 0,
             PUBLISHED: 0, SKIPPED: 0, REJECTED: 0, FAILED: 0, NEEDS_HUMAN: 0}
        for v in self.videos:
            if v.get("artifact_path"):
                c[RENDERED] += 1
            if v.get("gate") == "PASS":
                c[GATE_PASSED] += 1
            status = v.get("status")
            if status != ATTEMPTED and status in c:
                c[status] += 1
        return c

    def to_dict(self) -> Dict:
        return {
            "schema": SCHEMA_VERSION,
            "run_id": self.run_id,
            "kind": self.kind,
            "started_at": self.started.isoformat(),
            "finished_at": datetime.now().isoformat(),
            # First key an operator should read. Empty on a clean run.
            "needs_human": self.needs_human,
            "counts": self.counts(),
            "videos": self.videos,
        }

    # ── writing ──────────────────────────────────────────────────────

    def write(self) -> Optional[Path]:
        """Write the run's report. Returns the path, or None if it could not
        be written — never raises, for the reason in the class docstring."""
        try:
            self.report_dir.mkdir(parents=True, exist_ok=True)
            path = self.report_dir / f"{self.run_id}.json"
            payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
        except Exception:                                 # noqa: BLE001
            logger.exception("could not write the batch report")
            return None

        (self.report_dir / "latest.json").write_text(payload, encoding="utf-8")
        self._log_summary(path)
        return path

    def _log_summary(self, path: Path) -> None:
        c = self.counts()
        logger.info("batch %s: %d attempted, %d rendered, %d passed the gate; "
                    "%d published, %d skipped, %d rejected, %d failed, "
                    "%d NEEDS A HUMAN -> %s",
                    self.run_id, c[ATTEMPTED], c[RENDERED], c[GATE_PASSED],
                    c[PUBLISHED], c[SKIPPED], c[REJECTED], c[FAILED],
                    c[NEEDS_HUMAN], path)
        for item in self.needs_human:
            logger.critical("NEEDS A HUMAN: %s/%s — %s. %s",
                            item["artifact"], item.get("platform"),
                            item.get("why"), item.get("check"))



def reject(entry: Dict, blocking_flags, artifact_path=None) -> None:
    """Mark one report entry as gate-rejected.

    Module-level for the same reason as record_upload_outcome: main.py folds
    a result in without holding a report object.
    """
    if entry is None:
        return
    entry.update(status=REJECTED, stage="gate",
                 reason="QA gate: " + ", ".join(blocking_flags or []),
                 blocking_flags=list(blocking_flags or []))
    if artifact_path:
        entry["artifact_path"] = str(artifact_path)


def record_render(entry: Dict, video_path, gate: str = None) -> None:
    """Record that a video was produced, before and regardless of upload.

    stage and artifact_path used to be written only inside the upload
    branch, so with --upload off a video that rendered, passed the gate and
    got its outro still reported stage="script" and artifact_path=None — the
    same shape as a run that died during script generation.

    Status is deliberately left alone. Publishing outcomes own that field;
    this records what the run PRODUCED, which is a different question.
    """
    if entry is None:
        return
    if video_path:
        entry["artifact_path"] = str(video_path)
    if gate:
        entry["gate"] = gate
    entry["stage"] = "gated" if gate == "PASS" else "rendered"


def record_upload_outcome(entry: Dict, outcome: Dict) -> None:
    """Fold main.upload_video's outcome dict into one report entry.

    Module-level so main.py can call it without constructing a report,
    and so a single video run gets the same categorisation a batch does.
    """
    if entry is None or not isinstance(outcome, dict):
        return

    entry["published"] = list(outcome.get("recorded") or [])
    entry["stage"] = "upload"
    
    for platform in outcome.get("skipped") or []:
        entry["skipped"].append({
            "platform": platform,
            "reason": _reason_for(outcome, platform, "guard")
                      or "already published (guard)",
            "believed_live_id": _believed_id(outcome, platform),
        })
    
    # Live but unrecorded: the video IS on the platform and this repo
    # cannot name it. PROMPT 1 could only log this at CRITICAL.
    for platform in outcome.get("unrecorded") or []:
        entry["needs_human"].append({
            "platform": platform,
            "why": "PUBLISHED BUT NOT RECORDED",
            "reason": _reason_for(outcome, platform, "record")
                      or "the ledger write failed after a successful upload",
            "check": "the video is LIVE. Find it on the channel and add "
                     "its id to output/published/ledger.jsonl by hand.",
        })
    
    # Held by the guard: state genuinely undetermined.
    for platform in outcome.get("held") or []:
        entry["needs_human"].append({
            "platform": platform,
            "why": "UPLOAD STATE UNDETERMINED",
            "reason": _reason_for(outcome, platform, "guard")
                      or "the resumable session could not be resolved",
            "check": "search the channel for this title. If it is there, "
                     "add it to the ledger; if not, delete the open "
                     "attempt row and re-run.",
        })
    
    for err in outcome.get("errors") or []:
        if err.get("stage") in ("upload", "import"):
            entry["failed"].append({"platform": err.get("platform"),
                                    "reason": err.get("error")})
    
    if entry["needs_human"]:
        entry["status"] = NEEDS_HUMAN
    elif entry["published"]:
        entry["status"] = PUBLISHED
    elif entry["skipped"] and not entry["failed"]:
        entry["status"] = SKIPPED
    elif entry["failed"]:
        entry["status"] = FAILED
        entry["reason"] = entry["failed"][0].get("reason")


def move_rejected(video_path, entry: Dict, report: Dict = None,
                  rejected_dir: Path = None) -> Optional[Path]:
    """Move a gate-rejected artifact to output/rejected/<type>/ with its report.

    output/rejected/ already means "the QA gate said no" and is the right
    destination. It is deliberately NOT output/failed/, which means a stage
    broke: a rejection has an artifact to look at and blocking flags to read,
    a failure has a traceback.
    """
    return _relocate(video_path, entry,
                     Path(rejected_dir) if rejected_dir else REJECTED_DIR,
                     ".rejection.json",
                     {"blocking_flags": entry.get("blocking_flags", []),
                      "gate_report": report or {}})


def quarantine(video_path, entry: Dict, failed_dir: Path = None) -> Optional[Path]:
    """Move a FAILED artifact somewhere findable, with a reason beside it.

    A stage broke. See move_rejected for the gate's verdict, which is a
    different class with a different remedy and its own tree.
    """
    return _relocate(video_path, entry,
                     Path(failed_dir) if failed_dir else FAILED_DIR,
                     ".failure.json", {"failed": entry.get("failed")})


def _relocate(video_path, entry: Dict, dest_root: Path, suffix: str,
              extra: Dict) -> Optional[Path]:
    """Move an artifact out of the render tree with a machine-readable reason.

    The reason is written as JSON next to the file: an operator should not
    have to correlate a filename against a log to find out what happened.

    Never raises — a bookkeeping failure must not be what takes a batch down.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        return None

    try:
        import shutil
        dest_dir = dest_root / (entry.get("type") or "unknown")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / video_path.name
        if dest.exists():
            dest = dest_dir / f"{video_path.stem}_{datetime.now():%H%M%S}{video_path.suffix}"
        shutil.move(str(video_path), str(dest))

        reason = {"artifact": entry.get("artifact"), "stage": entry.get("stage"),
                  "status": entry.get("status"), "reason": entry.get("reason"),
                  "at": datetime.now().isoformat()}
        reason.update(extra or {})
        dest.with_suffix(suffix).write_text(
            json.dumps(reason, indent=2, ensure_ascii=False), encoding="utf-8")

        # The sidecar travels with the artifact, or the reason is orphaned.
        side = video_path.with_suffix(".json")
        if side.exists():
            shutil.move(str(side), str(dest_dir / side.name))

        entry["artifact_path"] = str(dest)
        logger.warning("moved %s -> %s", video_path.name, dest)
        return dest
    except Exception:                                     # noqa: BLE001
        logger.exception("could not relocate %s", video_path)
        return None


def _reason_for(outcome: Dict, platform: str, stage: str) -> Optional[str]:
    for err in outcome.get("errors") or []:
        if err.get("platform") == platform and err.get("stage") == stage:
            return err.get("error")
    return None


def _believed_id(outcome: Dict, platform: str) -> Optional[str]:
    """The videoId the guard thinks is already live, for a skip."""
    for row in outcome.get("skip_details") or []:
        if row.get("platform") == platform:
            return row.get("upload_id")
    return None
