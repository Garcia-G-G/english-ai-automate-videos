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

#: Where an artifact that failed goes, so it is findable with a reason.
#: output/rejected/ is the QA gate's; upload and render failures are a
#: different class and get their own tree rather than being mixed in.
FAILED_DIR = ROOT / "output" / "failed"

SCHEMA_VERSION = 1

# Per-video outcome categories.
ATTEMPTED = "attempted"
PUBLISHED = "published"
SKIPPED = "skipped"
FAILED = "failed"
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
        c = {ATTEMPTED: len(self.videos), PUBLISHED: 0, SKIPPED: 0,
             FAILED: 0, NEEDS_HUMAN: 0}
        for v in self.videos:
            if v["status"] in c:
                c[v["status"]] += 1
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
        logger.info("batch %s: %d attempted, %d published, %d skipped, "
                    "%d failed, %d NEEDS A HUMAN -> %s",
                    self.run_id, c[ATTEMPTED], c[PUBLISHED], c[SKIPPED],
                    c[FAILED], c[NEEDS_HUMAN], path)
        for item in self.needs_human:
            logger.critical("NEEDS A HUMAN: %s/%s — %s. %s",
                            item["artifact"], item.get("platform"),
                            item.get("why"), item.get("check"))



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


def quarantine(video_path, entry: Dict, failed_dir: Path = None) -> Optional[Path]:
    """Move a failed artifact somewhere findable, with a reason beside it.

    output/rejected/ belongs to the QA gate. An upload or render failure is a
    different class with a different remedy, so it gets output/failed/ rather
    than being mixed into a tree that means "the gate said no".

    The reason is written as JSON next to the file: an operator should not
    have to correlate a filename against a log to find out what happened.
    """
    failed_dir = Path(failed_dir) if failed_dir else FAILED_DIR
    video_path = Path(video_path)
    if not video_path.exists():
        return None

    try:
        import shutil
        dest_dir = failed_dir / (entry.get("type") or "unknown")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / video_path.name
        if dest.exists():
            dest = dest_dir / f"{video_path.stem}_{datetime.now():%H%M%S}{video_path.suffix}"
        shutil.move(str(video_path), str(dest))

        reason = {"artifact": entry.get("artifact"), "stage": entry.get("stage"),
                  "reason": entry.get("reason"), "failed": entry.get("failed"),
                  "at": datetime.now().isoformat()}
        dest.with_suffix(".failure.json").write_text(
            json.dumps(reason, indent=2, ensure_ascii=False), encoding="utf-8")
        entry["artifact_path"] = str(dest)
        logger.warning("quarantined %s -> %s", video_path.name, dest)
        return dest
    except Exception:                                     # noqa: BLE001
        logger.exception("could not quarantine %s", video_path)
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
