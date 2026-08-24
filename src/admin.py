#!/usr/bin/env python3
"""
Admin Dashboard for English AI Videos
Web interface for generating, reviewing, uploading, and managing videos.

Run: streamlit run src/admin.py
Opens: http://localhost:8501
"""

import logging
import streamlit as st
import json
import os
import sys
import shutil
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Optional
import uuid

from run_log import attach_run_log, detach_run_log

# Streamlit installs no handler of its own, so without this every
# logger.* call in this module and in src/pipeline.py is discarded --
# including the render progress lines and the error path at the bottom of
# run_pipeline_with_tracking. Same format as main.py:setup_logging.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)

logger = logging.getLogger(__name__)

# Setup paths
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from script_generator import (
    generate_script,
    get_random_topic,
    find_topic,
    list_categories,
    load_topics,
    VIDEO_TYPES
)

# Shared pipeline — the SAME TTS dispatch, merge and renderer the CLI uses.
import pipeline
from cost_tracker import reset_tracker

# Output directories
OUTPUT_DIR = ROOT / "output"
SCRIPTS_DIR = OUTPUT_DIR / "scripts"
AUDIO_DIR = OUTPUT_DIR / "audio"
VIDEO_DIR = OUTPUT_DIR / "video"
PENDING_DIR = OUTPUT_DIR / "pending"
APPROVED_DIR = OUTPUT_DIR / "approved"
REJECTED_DIR = OUTPUT_DIR / "rejected"
UPLOADED_DIR = OUTPUT_DIR / "uploaded"

for d in [PENDING_DIR, APPROVED_DIR, REJECTED_DIR, UPLOADED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============== PERSISTENT PROGRESS TRACKING ==============
JOBS_FILE = OUTPUT_DIR / "generation_jobs.json"

# Guards the whole read-modify-write of JOBS_FILE. Generation runs in worker
# threads now, so create/update/complete interleave; without this a worker
# reading before another's write and saving after it silently drops that job.
_JOBS_LOCK = threading.RLock()


def load_jobs() -> dict:
    if JOBS_FILE.exists():
        try:
            with open(JOBS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"active": [], "history": []}


def save_jobs(jobs: dict):
    # Write-then-rename: a crash mid-write leaves the previous ledger intact
    # rather than a truncated file that load_jobs() silently reads as empty.
    tmp = JOBS_FILE.with_suffix(JOBS_FILE.suffix + ".tmp")
    with open(tmp, 'w') as f:
        json.dump(jobs, f, indent=2, default=str)
    os.replace(tmp, JOBS_FILE)


def _proc_start(pid: int) -> Optional[str]:
    """OS start time for `pid`, or None if no such process is running.

    Shelled out rather than taken from psutil, which is not a dependency
    here. The value is only ever compared for equality, so its format does
    not matter — only that the OS reports the same string for the same
    process and a different one for a recycled pid.
    """
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="],
                             capture_output=True, text=True, timeout=5)
    except Exception:                                       # noqa: BLE001
        return None
    return out.stdout.strip() or None


#: Identity of THIS process. Recomputed whenever Streamlit re-executes the
#: script, and that is the point: a process does not change its pid or its
#: start time when its source is reloaded, so both survive the reload that
#: wipes every in-memory registry.
_OWNER_PID = os.getpid()
_OWNER_STARTED = _proc_start(_OWNER_PID)


def _owner_alive(job: dict) -> bool:
    """Is the process that started this job still running?

    This is the whole liveness test, and it deliberately does NOT consult
    the heartbeat. A render stops stamping progress for minutes at a time
    during encoding — one real job went 3m47s between updates — so any
    staleness threshold either reaps live work or is too loose to catch
    anything. Process liveness has no such window.

    The previous version asked whether the job id was in an in-memory set.
    That set is module state, Streamlit re-executes the module on any source
    change, and the set comes back empty — so editing any watched file while
    a render was running marked that render failed. It had exactly that
    effect on 2026-08-17: job ab4ed292 was recorded as "Interrupted" at
    15:51:51 and went on to render, pass the gate and ship at 15:57.
    """
    pid = job.get("owner_pid")
    if not pid:
        # Written before owners were recorded, so nothing can vouch for it.
        return False
    if pid == _OWNER_PID:
        return True
    started = _proc_start(pid)
    if started is None:
        return False
    # A recycled pid is a different process wearing the same number.
    return not job.get("owner_started") or started == job["owner_started"]


def touch_heartbeat(job_id: str) -> None:
    """Stamp a running job so its row shows the worker is still there.

    Separate from update_job because `updated_at` means "progress changed"
    and is read as such by the UI. A heartbeat is not progress.
    """
    with _JOBS_LOCK:
        jobs = load_jobs()
        for job in jobs["active"]:
            if job["id"] == job_id:
                job["heartbeat"] = datetime.now().isoformat()
                save_jobs(jobs)
                return


def create_job(video_type: str, category: str = None, topic: str = None) -> str:
    job_id = str(uuid.uuid4())[:8]
    job = {
        "id": job_id,
        "owner_pid": _OWNER_PID,
        "owner_started": _OWNER_STARTED,
        "heartbeat": datetime.now().isoformat(),
        "video_type": video_type,
        "category": category,
        "topic": topic,
        "status": "pending",
        "progress": 0,
        "current_step": "Initializing...",
        "step_number": 0,
        "total_steps": 4,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "video_path": None,
        "error": None
    }
    with _JOBS_LOCK:
        jobs = load_jobs()
        jobs["active"].append(job)
        save_jobs(jobs)
    return job_id


def update_job(job_id: str, **kwargs):
    with _JOBS_LOCK:
        jobs = load_jobs()
        for job in jobs["active"]:
            if job["id"] == job_id:
                job.update(kwargs)
                job["updated_at"] = datetime.now().isoformat()
                break
        save_jobs(jobs)


def complete_job(job_id: str, success: bool, video_path: str = None, error: str = None):
    with _JOBS_LOCK:
        jobs = load_jobs()
        completed_job = None
        for i, job in enumerate(jobs["active"]):
            if job["id"] == job_id:
                completed_job = jobs["active"].pop(i)
                break
        if completed_job:
            completed_job["status"] = "completed" if success else "failed"
            completed_job["progress"] = 100 if success else completed_job.get("progress", 0)
            completed_job["video_path"] = video_path
            completed_job["error"] = error
            completed_job["completed_at"] = datetime.now().isoformat()
            jobs["history"].insert(0, completed_job)
            jobs["history"] = jobs["history"][:50]
        save_jobs(jobs)


def get_active_jobs() -> list:
    return load_jobs().get("active", [])


def get_job_history(limit: int = 5) -> list:
    return load_jobs().get("history", [])[:limit]


# ============== PIPELINE WITH PROGRESS TRACKING ==============

def run_pipeline_with_tracking(job_id: str, video_type: str, category: str = None,
                                topic_name: str = None, script_data: dict = None,
                                background: str = None, dry_run: bool = False) -> dict:
    """Generate one video through the shared pipeline (src/pipeline.py).

    Same TTS dispatch, same merge and same renderer as main.py — only the
    output layout differs (videos land in output/pending/<type>/ for review).

    Args:
        script_data: Use this script instead of generating one with GPT.
        dry_run:     Resolve and log the TTS plan only; no API calls, no render.
    """
    result = {"success": False, "video_path": None, "error": None}

    try:
        update_job(job_id, status="running", step_number=1,
                   current_step="Selecting topic...", progress=5)

        # Audience profile (voice, backgrounds, topics) — same resolution as the CLI
        profile = pipeline.resolve_profile()

        if script_data is not None:
            topic_name = topic_name or script_data.get("word") or script_data.get("topic") or "script"
        elif category and topic_name:
            topic = find_topic(category, topic_name)
        else:
            category, topic = get_random_topic(
                allowed_categories=profile.get("content", {}).get("categories"))
            topic_name = (topic.get("english") or topic.get("topic") or topic.get("wrong")
                         or topic.get("word") or topic.get("sentence") or str(topic))

        update_job(job_id, category=category, topic=topic_name,
                   current_step=f"Topic: '{topic_name}'", progress=10)

        # Step 2: Generate script
        if script_data is None:
            update_job(job_id, step_number=2,
                       current_step="Generating script with GPT...", progress=15)
            script_data = generate_script(category, topic, video_type)

        import re as _re
        output_name = _re.sub(r'[^\w\-]', '_', topic_name).strip('_').lower()
        output_name = _re.sub(r'_+', '_', output_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_name = f"{output_name}_{timestamp}"

        # Cost tracking for this video (TTS now runs in-process, so the
        # tracker survives long enough to be saved).
        tracker = reset_tracker(video_id=unique_name)

        script_dir = SCRIPTS_DIR / video_type
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / f"{unique_name}.json"

        with open(script_path, 'w', encoding='utf-8') as f:
            json.dump(script_data, f, ensure_ascii=False, indent=2)

        update_job(job_id, current_step=f"Script generated", progress=30)

        # Step 3: Generate TTS audio.
        # The TTS input is script_path (under output/scripts/); its output is
        # audio_path + audio_path.json.  Distinct files on purpose — the old
        # code passed a copy of the script at the audio JSON path, which the
        # TTS then overwrote with its own result.
        update_job(job_id, step_number=3,
                   current_step=f"Generating audio ({pipeline.resolve_provider_name()})...",
                   progress=35)

        audio_dir = AUDIO_DIR / video_type
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_path = audio_dir / f"{unique_name}.mp3"

        audio_path, json_path = pipeline.generate_tts(
            script_data, audio_path, script_path=script_path, dry_run=dry_run)

        if dry_run:
            update_job(job_id, current_step="Dry run complete", progress=100)
            complete_job(job_id, success=True)
            result["success"] = True
            result["dry_run"] = True
            return result

        update_job(job_id, current_step="Audio generated", progress=55)

        pipeline.merge_script_into_tts(script_data, json_path)

        # Step 4: Render video
        update_job(job_id, step_number=4,
                   current_step="Rendering video...", progress=60)

        video_path = PENDING_DIR / video_type / f"{unique_name}.mp4"

        # The same resolver --batch uses, with the topic and category this
        # job already has. Before this, the dashboard called it without them,
        # got None back and rendered a palette — so the per-video generated
        # backgrounds existed only on the --batch path.
        #
        # on_record puts the decision on the job, so the dashboard shows
        # which background a video got and whether the gate passed. It is a
        # callback rather than the batch `entry` dict because admin has no
        # such dict; the resolver takes either.
        # Captured locally as well as written to the job row, because the
        # job row is not durable: "Clear All History" wipes jobs["history"],
        # and a video sitting in pending/ would lose its record while the
        # artifact lived on. The artifact's json is the home; the row is a
        # copy for convenience.
        background_record = {}

        def _record_background(payload):
            background_record.update(payload)
            update_job(job_id, background=payload)

        resolved_background = pipeline.resolve_background(
            profile, background,
            topic=topic_name, category=category,
            on_record=_record_background,
        )
        update_job(job_id, current_step=f"Rendering video ({resolved_background})...")

        pipeline.render_video(
            audio_path, json_path, video_path,
            video_type=video_type,
            background=resolved_background,
            timeout=pipeline.RENDER_TIMEOUT_S,
        )

        update_job(job_id, current_step="Video rendered", progress=90)

        # FINALISE: gate, then outro. Neither ran on this path before — the
        # gate was built in Step 2, flipped to BLOCKING in Step 3, and the
        # outro added in 4a, and finalize_video had zero callers, so the
        # dashboard published ungated video with no Learning Routes CTA too.
        # One function, both paths.
        fin = pipeline.finalize_video(video_path, json_path,
                                      variant_seed=unique_name)
        result["gate"] = fin.get("gate")
        result["outro_appended"] = fin.get("outro_appended")
        result["blocking_flags"] = fin.get("blocking_flags", [])
        result["outro_variant"] = fin.get("outro_variant")
        if fin.get("video"):
            video_path = Path(fin["video"])

        # THE VERDICT, in three places on purpose.
        #
        # `result` alone is where it used to live, and _worker() calls this
        # function without capturing the return, so it died there — which is
        # how a gate REJECT reached output/pending/ with a green tick next to
        # the videos that passed.
        verdict_record = {
            "gate": fin.get("gate"),
            "blocking_flags": fin.get("blocking_flags", []),
            "outro_appended": bool(fin.get("outro_appended")),
            "outro_variant": fin.get("outro_variant"),
        }
        update_job(job_id, current_step=f"Gate: {fin.get('gate')}", progress=95,
                   **verdict_record)

        if tracker and tracker.entries:
            tracker.save()

        # Save metadata
        meta_path = video_path.with_suffix('.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump({
                "job_id": job_id,
                # The cost ledger's join key. Ledger rows carry
                # video_id == unique_name and the artifact is
                # <unique_name>.mp4, so no mapping needs inventing.
                "artifact": unique_name,
                "video_type": video_type,
                "category": category,
                "topic": topic_name,
                # The verdict lives with the artifact, so the two live or die
                # together. Clearing job history cannot orphan a video from
                # the reason it should not be published.
                **verdict_record,
                "background": background_record or None,
                "script_data": script_data,
                "created_at": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)

        result["success"] = True
        result["video_path"] = str(video_path)
        complete_job(job_id, success=True, video_path=str(video_path))

    except pipeline.PipelineError as e:
        # Already carries the renderer's own output — a Python traceback of the
        # subprocess wrapper would only bury it.
        error_msg = str(e)
        result["error"] = error_msg
        complete_job(job_id, success=False, error=error_msg[:2000])
        logger.error("[Pipeline ERROR]: %s", error_msg)
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        result["error"] = error_msg
        complete_job(job_id, success=False, error=error_msg[:2000])
        logger.error("[Pipeline ERROR]: %s", error_msg)

    return result


# ============== RUNNING GENERATION OFF THE SCRIPT THREAD ==============
#
# Streamlit draws the page on the same thread that would run the pipeline, so
# a synchronous call freezes the tab for the whole ~2-minute job and the
# ledger's own progress cannot be drawn while it advances. Workers write to
# the ledger; the page reads it.

# One render at a time. The renderer is CPU-bound (97% of its wall clock is
# frame generation), so two concurrent jobs do not finish sooner — measured
# 2026-08-14, two jobs 12s apart took ~4.5 min each against a 109s median.
# A second tab therefore queues instead of contending.
_RENDER_LOCK = threading.Lock()

_WORKERS: list = []

#: How often a running job stamps its row. Small enough that a dead worker is
#: obvious, large enough that it is not a write loop.
HEARTBEAT_SEC = 10


def start_generation(video_type: str, category: str = None, topic_name: str = None,
                     **kwargs) -> str:
    """Queue one video and return its job id immediately.

    The job appears in the ledger before this returns, so the very next page
    draw shows it as active.
    """
    job_id = create_job(video_type, category, topic_name)

    # The heartbeat is what a running job leaves behind, and it keeps
    # ticking through the long encode, when nothing else writes to the row.
    stop_beating = threading.Event()

    def _heartbeat():
        while not stop_beating.wait(HEARTBEAT_SEC):
            try:
                touch_heartbeat(job_id)
            except Exception:                               # noqa: BLE001
                logger.debug("heartbeat failed for job %s", job_id, exc_info=True)

    def _worker():
        # One file per job, recorded on the row so a 3am failure can be read
        # back from the ledger rather than from a console nobody kept.
        log_path = attach_run_log(f"job-{job_id}")
        update_job(job_id, log_path=str(log_path))
        try:
            with _RENDER_LOCK:
                run_pipeline_with_tracking(job_id, video_type, category,
                                           topic_name, **kwargs)
        except Exception:                                   # noqa: BLE001
            # run_pipeline_with_tracking handles its own errors; this is the
            # last resort so a worker cannot die leaving the row active.
            logger.exception("Generation worker crashed (job %s)", job_id)
            complete_job(job_id, success=False,
                         error="Generation worker crashed — see dashboard logs")
        finally:
            stop_beating.set()
            detach_run_log(log_path)

    threading.Thread(target=_heartbeat, name=f"heartbeat-{job_id}",
                     daemon=True).start()
    t = threading.Thread(target=_worker, name=f"generate-{job_id}", daemon=True)
    _WORKERS.append(t)
    t.start()
    return job_id


def wait_for_generations(timeout: float = None) -> bool:
    """Block until queued generations finish. For tests and shutdown."""
    deadline = time.monotonic() + timeout if timeout is not None else None
    for t in list(_WORKERS):
        remaining = None if deadline is None else max(0, deadline - time.monotonic())
        t.join(timeout=remaining)
        if t.is_alive():
            return False
    _WORKERS[:] = [t for t in _WORKERS if t.is_alive()]
    return True


def reap_orphaned_jobs() -> int:
    """Fail active rows that no live worker owns, and report how many.

    Workers are daemon threads: they die with the server, and the row they
    were updating stays "running" forever. Two such rows were sitting in the
    ledger with no process behind them.
    """
    with _JOBS_LOCK:
        jobs = load_jobs()
        orphans = [j for j in jobs["active"] if not _owner_alive(j)]
        if not orphans:
            return 0
        for job in orphans:
            jobs["active"].remove(job)
            job["status"] = "failed"
            job["error"] = (
                "Interrupted — the dashboard stopped while this job was at "
                f"'{job.get('current_step', 'unknown step')}'. Nothing was left running."
            )
            job["completed_at"] = datetime.now().isoformat()
            jobs["history"].insert(0, job)
        jobs["history"] = jobs["history"][:50]
        save_jobs(jobs)

    logger.info("Reaped %d orphaned job(s) from a previous dashboard process",
                len(orphans))
    return len(orphans)


# ============== HELPER FUNCTIONS ==============

def find_video_file(video_path_str: str) -> Optional[Path]:
    if not video_path_str:
        return None
    original = Path(video_path_str)
    if original.exists():
        return original
    filename = original.name
    for search_dir in [PENDING_DIR, APPROVED_DIR, REJECTED_DIR, VIDEO_DIR]:
        for match in search_dir.rglob(filename):
            if match.exists():
                return match
    return None


def get_pending_videos() -> list:
    videos = []
    if not PENDING_DIR.exists():
        return videos
    for type_dir in PENDING_DIR.iterdir():
        if type_dir.is_dir():
            for video_file in type_dir.glob("*.mp4"):
                meta_file = video_file.with_suffix('.json')
                meta = {}
                if meta_file.exists():
                    with open(meta_file, 'r') as f:
                        meta = json.load(f)
                videos.append({
                    "path": video_file,
                    "type": type_dir.name,
                    "name": video_file.stem,
                    "meta": meta,
                    "stage": "pending",
                    "created": datetime.fromtimestamp(video_file.stat().st_mtime)
                })
    return sorted(videos, key=lambda x: x["created"], reverse=True)


def get_approved_videos() -> list:
    """Videos awaiting upload, each annotated with what the ledger knows.

    THE SECOND DUPLICATE VECTOR. main.py never moves an uploaded file the way
    move_to_uploaded does for the dashboard, so an already-published video
    stays sitting in approved/ where this function lists it as ready to
    upload. The operator then uploads it again BY HAND — and a hand upload is
    exactly how hPdSoqjvu3E happened.

    Moving the file (main.py now does) is not sufficient on its own: a move
    can fail, a re-render puts the file back, and the operator can move it
    back. The ledger is the authority on what is published, so the list
    consults it. The two fixes cover different failure modes and both are
    applied — the move keeps disk state honest, this keeps the DECISION
    honest even when disk state is not.
    """
    from publication_log import find_by_artifact

    videos = []
    if not APPROVED_DIR.exists():
        return videos
    for type_dir in APPROVED_DIR.iterdir():
        if type_dir.is_dir():
            for video_file in type_dir.glob("*.mp4"):
                meta_file = video_file.with_suffix('.json')
                meta = {}
                if meta_file.exists():
                    with open(meta_file, 'r') as f:
                        meta = json.load(f)
                published = find_by_artifact(video_file.stem)
                videos.append({
                    "path": video_file,
                    "type": type_dir.name,
                    "name": video_file.stem,
                    "meta": meta,
                    "stage": "approved",
                    "published_to": sorted({r.get("platform") for r in published
                                            if r.get("platform")}),
                    "published_rows": published,
                    "created": datetime.fromtimestamp(video_file.stat().st_mtime)
                })
    return sorted(videos, key=lambda x: x["created"], reverse=True)


def get_library_videos() -> list:
    videos = []
    if not VIDEO_DIR.exists():
        return videos
    for type_dir in VIDEO_DIR.iterdir():
        if type_dir.is_dir():
            for video_file in type_dir.glob("*.mp4"):
                videos.append({
                    "path": video_file,
                    "type": type_dir.name,
                    "name": video_file.stem,
                    "size": video_file.stat().st_size,
                    # output/video/ is where `main.py --batch` stops. Until
                    # promote_to_review existed this was a dead end.
                    "stage": "batch",
                    "created": datetime.fromtimestamp(video_file.stat().st_mtime)
                })
    return sorted(videos, key=lambda x: x["created"], reverse=True)


def find_script_for(video_path: Path) -> Optional[Path]:
    """The script that produced this artifact, if it is still on disk.

    `main.py --batch` names the artifact after the script, so
    output/scripts/<type>/<stem>.json is the match. Dashboard renders append a
    timestamp to the stem, so a prefix search is the fallback, newest first.
    """
    type_dir = SCRIPTS_DIR / video_path.parent.name
    if not type_dir.is_dir():
        return None
    exact = type_dir / f"{video_path.stem}.json"
    if exact.exists():
        return exact
    matches = sorted(type_dir.glob(f"{video_path.stem}_*.json"), reverse=True)
    return matches[0] if matches else None


def promote_to_review(video_path: Path) -> dict:
    """Put a `--batch` artifact onto the reviewed-and-published route.

    output/video/ is where `main.py --batch` stops. Nothing in the dashboard
    could move an artifact any further from there: Library offered preview and
    download and that was the end of the road, so the six videos carrying the
    first Learning Routes CTA have been unpublishable from the UI since
    18 August.

    Promotion is a MOVE INTO output/pending/, not a shortcut to upload. From
    pending/ the artifact takes the identical route as anything the dashboard
    rendered itself — Review approves it into approved/, Upload consults the
    idempotency guard before a byte is sent. So this is a new DOOR into the
    existing flow, not a second flow. This repo has had three upload paths
    before and unifying them was Paso 5a.

    The publication ledger is consulted here as well as at upload. Not because
    the guard at the end is insufficient, but because an already-published
    artifact sitting in the "ready to upload" list is the exact shape of the
    mistake that published hPdSoqjvu3E twice, and the cheapest place to refuse
    is before it ever joins the queue.

    Returns a verdict dict rather than raising: this is called from a button.
    """
    from publication_log import find_by_artifact

    artifact = video_path.stem
    if not video_path.exists():
        return {"ok": False, "reason": f"{video_path} no longer exists"}

    published = find_by_artifact(artifact)
    if published:
        where = ", ".join(
            f"{r.get('platform')}={r.get('upload_id')}" for r in published)
        return {"ok": False, "artifact": artifact, "published_rows": published,
                "reason": f"already published ({where}) — promoting it would "
                          f"put a published video back in the upload queue"}

    video_type = video_path.parent.name
    dest_dir = PENDING_DIR / video_type
    dest = dest_dir / video_path.name
    if dest.exists():
        return {"ok": False, "artifact": artifact,
                "reason": f"{dest.relative_to(OUTPUT_DIR)} already exists; "
                          f"refusing to overwrite it"}

    script_path = find_script_for(video_path)
    script_data, category, topic = {}, "", artifact.replace("_", " ")
    if script_path:
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                script_data = json.load(f)
            meta = script_data.get("_meta", {}) or {}
            category = meta.get("category", "") or ""
            topic = meta.get("topic") or script_data.get("word") or topic
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("promote: could not read %s: %s", script_path, e)

    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(video_path), str(dest))

    # The same sidecar shape the dashboard writes, so Review and Upload cannot
    # tell a promoted artifact from a natively rendered one. Without
    # script_data the Upload page has no title to generate from and the
    # operator would be typing metadata by hand for every one.
    meta_path = dest.with_suffix(".json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "artifact": artifact,
            "video_type": video_type,
            "category": category,
            "topic": topic,
            "script_data": script_data,
            "promoted_from": "output/video",
            "promoted_at": datetime.now().isoformat(),
            "script_path": str(script_path) if script_path else None,
            "created_at": datetime.now().isoformat(),
        }, f, ensure_ascii=False, indent=2)

    logger.info("promote: %s -> %s (script=%s)", video_path, dest,
                script_path.name if script_path else "none")
    return {"ok": True, "artifact": artifact, "dest": dest,
            "meta_path": meta_path, "script_path": script_path,
            "video_type": video_type, "category": category, "topic": topic,
            "reason": "moved to pending; approve it in Review to upload"}


def approve_video(video_path: Path):
    video_type = video_path.parent.name
    dest_dir = APPROVED_DIR / video_type
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(video_path), str(dest_dir / video_path.name))
    meta_path = video_path.with_suffix('.json')
    if meta_path.exists():
        shutil.move(str(meta_path), str(dest_dir / meta_path.name))


def reject_video(video_path: Path):
    video_type = video_path.parent.name
    dest_dir = REJECTED_DIR / video_type
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(video_path), str(dest_dir / video_path.name))
    meta_path = video_path.with_suffix('.json')
    if meta_path.exists():
        shutil.move(str(meta_path), str(dest_dir / meta_path.name))


def unapprove_video(video_path: Path):
    video_type = video_path.parent.name
    dest_dir = PENDING_DIR / video_type
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(video_path), str(dest_dir / video_path.name))
    meta_path = video_path.with_suffix('.json')
    if meta_path.exists():
        shutil.move(str(meta_path), str(dest_dir / meta_path.name))


def _guard_decide(artifact: str, platform: str, manager=None):
    """Ask the idempotency guard before uploading. See upload_guard."""
    from upload_guard import decide
    return decide(artifact, platform, manager=manager)


def _guard_notice(st_module, artifact: str, platform_label: str, verdict) -> None:
    """Tell the operator why an upload did not happen.

    A guard that silently skips is indistinguishable from a broken button,
    and the operator's next move would be to upload by hand — which is the
    route that produced the duplicate in the first place.
    """
    from upload_guard import SKIP_DONE
    if verdict.action == SKIP_DONE:
        st_module.info(
            f"⏭️ {platform_label}: already published"
            + (f" (id={verdict.upload_id})" if verdict.upload_id else "")
            + f" — {verdict.reason}. Not uploading again."
        )
    else:
        st_module.warning(
            f"⏸️ {platform_label}: HELD — {verdict.reason}. This video may "
            f"already be live. Check the channel before forcing an upload."
        )


def _guarded_upload(manager, artifact: str, platform: str, video_path: str,
                    **kwargs):
    """manager.upload, with the attempt persisted before a byte is sent.

    The dashboard needs this for the same reason main.py does: the window
    between a live video and its ledger row is structural, not specific to
    the unattended path.
    """
    import os as _os

    from publication_log import (ATTEMPT_FAILED, ATTEMPT_PUBLISHED,
                                 ATTEMPT_SESSION, ATTEMPT_STARTED,
                                 record_attempt)

    try:
        size = _os.path.getsize(video_path)
    except OSError:
        size = 0

    record_attempt(artifact=artifact, platform=platform,
                   status=ATTEMPT_STARTED, video_path=video_path,
                   file_size=size, detail=str(kwargs.get("title", ""))[:120])

    def _session(uri, sz):
        record_attempt(artifact=artifact, platform=platform,
                       status=ATTEMPT_SESSION, video_path=video_path,
                       session_uri=uri, file_size=sz,
                       detail=str(kwargs.get("title", ""))[:120])

    result = manager.upload(platform, video_path, on_session=_session, **kwargs)

    ok = (result.get("success") if isinstance(result, dict)
          else getattr(result, "success", False))
    uri = (result.get("session_uri") if isinstance(result, dict)
           else getattr(result, "session_uri", None))
    vid = (result.get("upload_id") if isinstance(result, dict)
           else getattr(result, "upload_id", None))

    # On success the attempt is closed only AFTER _record_upload writes the
    # ledger row, so it is left open here deliberately. On failure it is
    # closed now, because the platform said nothing was created.
    if not ok:
        record_attempt(artifact=artifact, platform=platform,
                       status=ATTEMPT_FAILED, video_path=video_path,
                       session_uri=uri, file_size=size,
                       detail=str(result)[:200])
    return result


def _record_upload(st_module, video: dict, platform: str, result,
                   sent_title: str, sent_description: str,
                   sent_hashtags: list) -> None:
    """Persist the publication, and SHOUT if that fails.

    A video that is live but unrecorded is worse than a failed upload: a
    failure can be retried, an unrecorded success has to be found by hand on
    the platform. So a recording failure is surfaced in the UI rather than
    swallowed — the upload itself already succeeded and cannot be undone, but
    the operator has to know the id was lost.

    This is now only the UI half. The recording itself lives in
    publication_log.record_upload_result, so main.py's headless path uses the
    same recorder rather than a second one that could drift from it.
    """
    from publication_log import (ATTEMPT_PUBLISHED, ATTEMPT_SESSION,
                                 PublicationRecordError, record_attempt,
                                 record_upload_result)

    uri = (result.get("session_uri") if isinstance(result, dict)
           else getattr(result, "session_uri", None))
    vid = (result.get("upload_id") if isinstance(result, dict)
           else getattr(result, "upload_id", None))

    try:
        record_upload_result(
            artifact=video["name"],
            video_path=str(video["path"]),
            video_type=video.get("type", ""),
            platform=platform,
            result=result,
            sent_title=sent_title,
            sent_description=sent_description,
            sent_hashtags=sent_hashtags,
        )
        # Only now is the attempt closed: the video is live AND named.
        record_attempt(artifact=video["name"], platform=platform,
                       status=ATTEMPT_PUBLISHED, video_path=str(video["path"]),
                       session_uri=uri, upload_id=vid, detail="recorded")
    except PublicationRecordError as exc:
        logger.exception("publication record failed")
        # Leave the attempt OPEN, now carrying the id. That open row is what
        # stops the next run from publishing a second copy.
        record_attempt(artifact=video["name"], platform=platform,
                       status=ATTEMPT_SESSION, video_path=str(video["path"]),
                       session_uri=uri, upload_id=vid,
                       detail=f"published but record failed: {exc}")
        st_module.error(
            f"⚠️ Uploaded to {platform} but FAILED TO RECORD it: {exc}. "
            f"The video is live and this repo cannot name it — note the id now."
        )


def reconcile_platform_target(state: dict, platform_name: str,
                              enabled: bool) -> bool:
    """Decide what the upload-target checkbox should show, and store it.

    The checkbox mixes TWO kinds of state, which is why neither obvious fix
    is right on its own:

      derived  — whether the platform is configured/authenticated. Recomputed
                 from the environment on every rerun.
      user     — whether the operator wants to publish there this time.

    Dropping the `key` and letting `value=` win would destroy the user half:
    unticking YouTube would silently re-tick on the next rerun. Keeping the
    key alone destroys the derived half, which is the live bug — a keyed
    Streamlit widget IGNORES `value=` once session_state[key] exists, so the
    ticked state froze at whatever it was the FIRST time the widget rendered.
    Now that YouTube auth works, a session that rendered before auth succeeded
    keeps showing YouTube unavailable forever.

    The dangerous direction is the other one: a platform that WAS configured
    and no longer is stays ticked, and a disabled checkbox still returns its
    stored value — so the upload would be attempted against a platform with no
    credentials.

    Rules:
      * not available        -> forced off, always. Never target a platform we
                               cannot authenticate to.
      * became available     -> default on, because that is what the operator
                               almost certainly wants right after connecting.
      * still available      -> leave the operator's choice alone.
    """
    key = f"target_{platform_name}"
    seen_key = f"_target_seen_{platform_name}"
    want_key = f"_target_want_{platform_name}"

    # The widget key is not durable and the bookkeeping keys are. Streamlit
    # garbage-collects a widget's key on any run where that widget is not
    # rendered, and these checkboxes live inside `if approved:` — so an
    # operator with nothing awaiting upload, or just sitting on another tab,
    # loses `target_<platform>` while `_target_seen_<platform>` survives.
    # That desync is what crashed here: `previously == enabled`, so neither
    # branch below assigned, and the return read a key that was gone.
    #
    # So the operator's half is mirrored into a key Streamlit will not
    # collect, captured here while the widget key is still around to read.
    # Recovering by defaulting to on would have re-ticked a platform that was
    # deliberately turned off, which is the regression this whole function
    # exists to prevent.
    if key in state:
        state[want_key] = bool(state[key])

    previously = state.get(seen_key)
    want = bool(state.get(want_key, True))

    if not enabled:
        want = False
    elif previously != enabled:
        # Transitioned unavailable -> available (or first ever render).
        want = True

    # Assigned unconditionally: the caller renders a keyed widget straight
    # after this, and every path has to leave it something to render.
    state[key] = want
    state[want_key] = want
    state[seen_key] = enabled
    return want


# The resolver moved to upload_metadata.py so main.py's headless upload path
# can import it without pulling in streamlit and this module's import-time
# side effects. Re-exported here because both dashboard call sites below, and
# the tests, reach it as admin.resolve_upload_metadata.
from upload_metadata import (  # noqa: E402,F401
    NO_OPERATOR_EDITS, metadata_session_keys, resolve_upload_metadata,
)


def move_to_uploaded(video_path: Path, upload_info: dict = None):
    """Move video from approved to uploaded directory, saving upload metadata."""
    video_type = video_path.parent.name
    dest_dir = UPLOADED_DIR / video_type
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / video_path.name
    shutil.move(str(video_path), str(dest_path))
    meta_path = video_path.with_suffix('.json')
    dest_meta = dest_dir / meta_path.name
    if meta_path.exists():
        # Merge upload info into metadata
        meta = {}
        with open(meta_path, 'r') as f:
            meta = json.load(f)
        if upload_info:
            meta["upload_info"] = upload_info
        shutil.move(str(meta_path), str(dest_meta))
        with open(dest_meta, 'w') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)


def get_uploaded_videos() -> list:
    """Get all uploaded videos."""
    videos = []
    if not UPLOADED_DIR.exists():
        return videos
    for type_dir in UPLOADED_DIR.iterdir():
        if type_dir.is_dir():
            for video_file in type_dir.glob("*.mp4"):
                meta_file = video_file.with_suffix('.json')
                meta = {}
                if meta_file.exists():
                    with open(meta_file, 'r') as f:
                        meta = json.load(f)
                videos.append({
                    "path": video_file,
                    "type": type_dir.name,
                    "name": video_file.stem,
                    "meta": meta,
                    "stage": "uploaded",
                    "created": datetime.fromtimestamp(video_file.stat().st_mtime),
                    "upload_info": meta.get("upload_info", {}),
                })
    return sorted(videos, key=lambda x: x["created"], reverse=True)


def delete_video(video_path: Path):
    video_path.unlink(missing_ok=True)
    meta_path = video_path.with_suffix('.json')
    meta_path.unlink(missing_ok=True)


def mask_key(key: str) -> str:
    if not key or len(key) < 10:
        return "****"
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def get_api_status() -> dict:
    """Check which API keys are configured."""
    keys = {
        "OpenAI": ("OPENAI_API_KEY", True),
        "ElevenLabs": ("ELEVENLABS_API_KEY", False),
        "TikTok": ("TIKTOK_CLIENT_KEY", False),
        "YouTube": ("YOUTUBE_CLIENT_ID", False),
        "Instagram": ("INSTAGRAM_ACCESS_TOKEN", False),
    }
    status = {}
    for name, (env_var, required) in keys.items():
        val = os.getenv(env_var, "")
        status[name] = {
            "configured": bool(val and len(val) > 3),
            "required": required,
            "masked": mask_key(val) if val else "",
            "env_var": env_var,
        }
    return status


def save_env_key(key_name: str, value: str):
    """Update a key in the .env file."""
    env_path = ROOT / ".env"
    lines = []
    found = False

    if env_path.exists():
        with open(env_path, 'r') as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key_name}=") or stripped.startswith(f"# {key_name}="):
            new_lines.append(f"{key_name}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key_name}={value}\n")

    with open(env_path, 'w') as f:
        f.writelines(new_lines)

    # Also update current process environment
    os.environ[key_name] = value


# ============== STREAMLIT PAGE CONFIG ==============

st.set_page_config(
    page_title="English AI Videos",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)


@st.cache_resource
def _startup() -> dict:
    """Once per server process, before the first page is drawn.

    Guarded by cache_resource rather than run at import: importing this
    module (tests, tooling) must not rewrite the real ledger.
    """
    return {"reaped": reap_orphaned_jobs()}


_STARTUP = _startup()

# ============== CUSTOM THEME CSS ==============
st.markdown("""
<style>
    /* ── Global ── */
    .stApp {
        background: linear-gradient(180deg, #0a0a1a 0%, #111128 100%);
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d0d24 0%, #0a0a1a 100%);
        border-right: 1px solid rgba(99, 102, 241, 0.15);
    }
    section[data-testid="stSidebar"] .stButton button {
        border: 1px solid rgba(99, 102, 241, 0.2);
        border-radius: 10px;
        transition: all 0.2s;
        font-size: 0.9rem;
    }
    section[data-testid="stSidebar"] .stButton button:hover {
        border-color: rgba(99, 102, 241, 0.6);
        box-shadow: 0 0 15px rgba(99, 102, 241, 0.15);
    }

    /* ── Cards ── */
    .metric-card {
        background: linear-gradient(135deg, rgba(17, 17, 40, 0.9) 0%, rgba(26, 26, 58, 0.9) 100%);
        border: 1px solid rgba(99, 102, 241, 0.2);
        border-radius: 16px;
        padding: 24px;
        text-align: center;
        transition: all 0.3s;
    }
    .metric-card:hover {
        border-color: rgba(99, 102, 241, 0.5);
        transform: translateY(-2px);
        box-shadow: 0 8px 30px rgba(99, 102, 241, 0.1);
    }
    .metric-card .metric-value {
        font-size: 2.5rem;
        font-weight: 800;
        background: linear-gradient(135deg, #818cf8, #6366f1);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 8px 0;
    }
    .metric-card .metric-label {
        font-size: 0.85rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    /* ── Status indicators ── */
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    .status-connected {
        background: rgba(34, 197, 94, 0.15);
        color: #4ade80;
        border: 1px solid rgba(34, 197, 94, 0.3);
    }
    .status-disconnected {
        background: rgba(100, 116, 139, 0.15);
        color: #94a3b8;
        border: 1px solid rgba(100, 116, 139, 0.3);
    }
    .status-required {
        background: rgba(239, 68, 68, 0.15);
        color: #f87171;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }

    /* ── Platform cards ── */
    .platform-card {
        background: linear-gradient(135deg, rgba(17, 17, 40, 0.95) 0%, rgba(30, 30, 60, 0.95) 100%);
        border: 1px solid rgba(99, 102, 241, 0.15);
        border-radius: 16px;
        padding: 28px;
        text-align: center;
        min-height: 200px;
    }
    .platform-card .platform-icon {
        font-size: 2.5rem;
        margin-bottom: 12px;
    }
    .platform-card .platform-name {
        font-size: 1.2rem;
        font-weight: 700;
        margin-bottom: 8px;
    }

    /* ── Progress bar ── */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #6366f1, #818cf8, #a78bfa);
        border-radius: 10px;
    }

    /* ── Video cards ── */
    .video-card {
        background: rgba(17, 17, 40, 0.7);
        border: 1px solid rgba(99, 102, 241, 0.1);
        border-radius: 12px;
        padding: 16px;
        margin: 8px 0;
    }

    /* ── Section headers ── */
    .section-header {
        font-size: 1.1rem;
        font-weight: 700;
        color: #e2e8f0;
        padding: 12px 0 8px 0;
        border-bottom: 2px solid rgba(99, 102, 241, 0.2);
        margin-bottom: 16px;
    }

    /* ── Upload queue item ── */
    .upload-item {
        background: rgba(17, 17, 40, 0.8);
        border: 1px solid rgba(99, 102, 241, 0.15);
        border-radius: 12px;
        padding: 16px;
        margin: 8px 0;
        display: flex;
        align-items: center;
        gap: 16px;
    }

    /* ── Quick action buttons ── */
    div[data-testid="stHorizontalBlock"] .stButton button[kind="primary"] {
        background: linear-gradient(135deg, #6366f1, #4f46e5);
        border: none;
        border-radius: 12px;
        font-weight: 600;
    }

    /* ── Activity feed ── */
    .activity-item {
        padding: 10px 16px;
        border-left: 3px solid rgba(99, 102, 241, 0.3);
        margin: 6px 0;
        background: rgba(17, 17, 40, 0.5);
        border-radius: 0 8px 8px 0;
    }

    /* ── Key input ── */
    .key-status {
        padding: 8px 16px;
        border-radius: 10px;
        margin: 4px 0;
        font-family: monospace;
        font-size: 0.85rem;
    }
    .key-ok {
        background: rgba(34, 197, 94, 0.1);
        border: 1px solid rgba(34, 197, 94, 0.2);
        color: #4ade80;
    }
    .key-missing {
        background: rgba(100, 116, 139, 0.1);
        border: 1px solid rgba(100, 116, 139, 0.2);
        color: #64748b;
    }
    .key-error {
        background: rgba(239, 68, 68, 0.1);
        border: 1px solid rgba(239, 68, 68, 0.2);
        color: #f87171;
    }
</style>
""", unsafe_allow_html=True)


# ============== SIDEBAR NAVIGATION ==============

st.sidebar.markdown("### 🎬 English AI Videos")
st.sidebar.markdown("---")

if 'current_page' not in st.session_state:
    st.session_state.current_page = "Dashboard"

main_pages = {
    "Dashboard": "🏠",
    "Generate": "🎥",
    "Queue": "📋",
    "Review": "✅",
    "Upload": "📤",
    "Library": "📚",
}

tool_pages = {
    "Scheduler": "⏰",
    "Settings": "⚙️",
    "Logs": "📜",
}

st.sidebar.markdown("##### MAIN")
for name, icon in main_pages.items():
    label = f"{icon} {name}"
    is_active = st.session_state.current_page == name
    if st.sidebar.button(
        label, key=f"nav_{name}",
        use_container_width=True,
        type="primary" if is_active else "secondary"
    ):
        st.session_state.current_page = name
        st.rerun()

st.sidebar.markdown("##### TOOLS")
for name, icon in tool_pages.items():
    label = f"{icon} {name}"
    is_active = st.session_state.current_page == name
    if st.sidebar.button(
        label, key=f"nav_{name}",
        use_container_width=True,
        type="primary" if is_active else "secondary"
    ):
        st.session_state.current_page = name
        st.rerun()

# Sidebar stats
st.sidebar.markdown("---")
api_status = get_api_status()
configured_count = sum(1 for s in api_status.values() if s["configured"])
st.sidebar.markdown(f"**API Keys:** {configured_count}/{len(api_status)} configured")

pending_count = len(get_pending_videos())
approved_count = len(get_approved_videos())
st.sidebar.markdown(f"**Videos:** {pending_count} pending / {approved_count} approved")
st.sidebar.markdown("---")
st.sidebar.caption("v2.0 - English AI Videos")

page = st.session_state.current_page

# Session state init
if 'queue_items' not in st.session_state:
    st.session_state.queue_items = []
if 'scheduler_enabled' not in st.session_state:
    st.session_state.scheduler_enabled = False
if 'scheduler_config' not in st.session_state:
    st.session_state.scheduler_config = {
        "videos_per_batch": 5,
        "interval_minutes": 60,
        "types": ["quiz", "educational", "true_false", "vocabulary"]
    }
if 'upload_history' not in st.session_state:
    st.session_state.upload_history = []


# ============== DASHBOARD PAGE ==============
if page == "Dashboard":
    st.markdown("## 🏠 Dashboard")

    pending = get_pending_videos()
    approved = get_approved_videos()
    library = get_library_videos()
    uploaded = get_uploaded_videos()
    active_jobs = get_active_jobs()
    all_videos = pending + approved + library + uploaded

    # Metrics row
    cols = st.columns(6)
    metrics = [
        ("Total Videos", len(all_videos), "📹"),
        ("Pending", len(pending), "📝"),
        ("Approved", len(approved), "✅"),
        ("Uploaded", len(uploaded), "📤"),
        ("Active Jobs", len(active_jobs), "⚡"),
        ("Storage", f"{sum(v.get('size', 0) or (v['path'].stat().st_size if v['path'].exists() else 0) for v in all_videos) / (1024*1024):.1f} MB", "💾"),
    ]
    for col, (label, value, icon) in zip(cols, metrics):
        with col:
            st.markdown(f"""
            <div class="metric-card">
                <div style="font-size:1.5rem">{icon}</div>
                <div class="metric-value">{value}</div>
                <div class="metric-label">{label}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("")

    # Active jobs.
    #
    # A fragment, not a page-level rerun. The old version called st.rerun()
    # from inside this loop, which abandons the rest of the draw — harmless
    # while generation blocked the thread (nothing else could run anyway),
    # but now that jobs run in the background it would hide Quick Generate
    # and Recent Videos for as long as anything was rendering. run_every
    # repaints only this block, and only while there is something to show.
    @st.fragment(run_every="2s")
    def _render_active_jobs():
        jobs = get_active_jobs()
        if not jobs:
            return
        st.markdown('<div class="section-header">⚡ Currently Generating</div>',
                    unsafe_allow_html=True)
        for job in jobs:
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"**{job['video_type'].upper()}** — {job.get('topic', 'Selecting...')}")
                st.progress(job.get('progress', 0) / 100)
                st.caption(job.get('current_step', 'Initializing...'))
            with c2:
                st.code(job['id'])

    _render_active_jobs()

    # Quick Actions + Recent Videos
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown('<div class="section-header">⚡ Quick Generate</div>', unsafe_allow_html=True)
        action_cols = st.columns(4)

        quick_types = [
            ("Quiz", "quiz"),
            ("Educational", "educational"),
            ("True/False", "true_false"),
            ("Vocabulary", "vocabulary"),
        ]
        for col, (label, vtype) in zip(action_cols, quick_types):
            with col:
                if st.button(f"🎬 {label}", use_container_width=True, key=f"quick_{vtype}"):
                    job_id = start_generation(vtype)
                    st.toast(f"{label} queued (job {job_id})")
                    st.rerun()

        st.markdown("")
        st.markdown('<div class="section-header">📹 Recent Videos</div>', unsafe_allow_html=True)

        recent = get_pending_videos()[:6]
        if recent:
            vid_cols = st.columns(3)
            for idx, video in enumerate(recent):
                with vid_cols[idx % 3]:
                    name = video['name'][:18] + "..." if len(video['name']) > 18 else video['name']
                    st.caption(f"{video['type']} | {name}")
                    if video["path"].exists():
                        st.video(str(video["path"]))
        else:
            st.info("No videos yet. Use Quick Generate above!")

    with col_right:
        st.markdown('<div class="section-header">📊 By Type</div>', unsafe_allow_html=True)
        type_counts = {}
        for v in all_videos:
            vtype = v.get("type", "unknown")
            type_counts[vtype] = type_counts.get(vtype, 0) + 1

        if type_counts:
            for vtype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
                pct = (count / len(all_videos) * 100) if all_videos else 0
                st.write(f"**{vtype.replace('_', ' ').title()}**")
                st.progress(pct / 100)
                st.caption(f"{count} videos ({pct:.0f}%)")
        else:
            st.info("No videos yet")

        st.markdown("")
        st.markdown('<div class="section-header">🔗 Platforms</div>', unsafe_allow_html=True)
        for name, info in api_status.items():
            if name == "OpenAI":
                continue
            badge = "status-connected" if info["configured"] else "status-disconnected"
            label = "CONNECTED" if info["configured"] else "NOT SET"
            st.markdown(f'{name} <span class="status-badge {badge}">{label}</span>', unsafe_allow_html=True)

        st.markdown("")
        st.markdown('<div class="section-header">📊 Recent Activity</div>', unsafe_allow_html=True)
        history = get_job_history(5)
        if history:
            for job in history:
                icon = "✅" if job.get("status") == "completed" else "❌"
                topic = job.get('topic', 'Unknown')
                if len(topic) > 20:
                    topic = topic[:17] + "..."
                completed_time = ""
                if job.get("completed_at"):
                    completed_time = datetime.fromisoformat(job["completed_at"]).strftime("%H:%M")
                st.markdown(
                    f'<div class="activity-item">{icon} <strong>{topic}</strong>'
                    f' <span style="color:#64748b">| {job.get("video_type", "")} | {completed_time}</span></div>',
                    unsafe_allow_html=True
                )


# ============== GENERATE PAGE ==============
elif page == "Generate":
    st.markdown("## 🎥 Generate Video")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown('<div class="section-header">Configuration</div>', unsafe_allow_html=True)

        video_type = st.selectbox("Video Type", VIDEO_TYPES, index=0)

        selection_mode = st.radio(
            "Topic Selection",
            ["Random", "Select Category", "Specific Topic"],
            index=0
        )

        category = None
        topic_name = None

        if selection_mode == "Select Category":
            categories = list_categories()
            category = st.selectbox("Category", categories)
        elif selection_mode == "Specific Topic":
            categories = list_categories()
            category = st.selectbox("Category", categories)
            if category:
                topics = load_topics(category)
                topic_names = [t.get("english") or t.get("topic") or t.get("wrong") for t in topics]
                topic_name = st.selectbox("Topic", topic_names)

        generate_btn = st.button("🚀 Generate Video", type="primary", use_container_width=True)

    with col2:
        st.markdown('<div class="section-header">Generation Status</div>', unsafe_allow_html=True)

        # Same reason as the Dashboard panel: repaint this block, not the page.
        @st.fragment(run_every="2s")
        def _render_generation_status():
            jobs = get_active_jobs()
            if not jobs:
                return
            for job in jobs:
                st.markdown(f"**{job['video_type'].upper()}** — {job.get('topic', 'Selecting...')}")
                st.progress(job.get('progress', 0) / 100)
                st.caption(job.get('current_step', 'Initializing...'))
            st.markdown("---")

        _render_generation_status()

        st.markdown("**Recent (Last 5)**")
        history = get_job_history(5)
        if history:
            for i, job in enumerate(history):
                icon = "✅" if job["status"] == "completed" else "❌"
                video_file = find_video_file(job.get("video_path", ""))
                auto_expand = (i == 0 and video_file is not None)
                with st.expander(f"{icon} {job.get('topic', 'Unknown')} ({job['video_type']})", expanded=auto_expand):
                    st.write(f"**Status:** {job['status']}")
                    if job.get("error"):
                        st.error(job['error'][:300])
                    if video_file:
                        st.video(str(video_file))
        else:
            st.info("No videos generated yet.")

        if generate_btn:
            # Queued, not awaited: the outcome arrives in the job list above,
            # which this page already renders from the ledger.
            job_id = start_generation(video_type, category, topic_name)
            st.success(f"Generation started! Job: `{job_id}` — progress appears above.")
            st.rerun()


# ============== QUEUE PAGE ==============
elif page == "Queue":
    st.markdown("## 📋 Batch Queue")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown('<div class="section-header">Add to Queue</div>', unsafe_allow_html=True)

        st.write("**Quick Batch:**")
        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button("10 Random Quizzes", use_container_width=True):
                for _ in range(10):
                    st.session_state.queue_items.append({"type": "quiz", "category": None, "topic": None})
                st.success("Added 10 quizzes!")
                st.rerun()
        with bc2:
            if st.button("5 of Each Type", use_container_width=True):
                for vtype in ["quiz", "educational", "true_false"]:
                    for _ in range(5):
                        st.session_state.queue_items.append({"type": vtype, "category": None, "topic": None})
                st.success("Added 15 videos!")
                st.rerun()

        st.markdown("---")
        st.write("**Custom:**")
        q_type = st.selectbox("Type", VIDEO_TYPES, key="queue_type")
        q_count = st.number_input("Count", min_value=1, max_value=50, value=5)
        if st.button("Add to Queue", use_container_width=True):
            for _ in range(q_count):
                st.session_state.queue_items.append({"type": q_type, "category": None, "topic": None})
            st.success(f"Added {q_count} {q_type} videos!")
            st.rerun()

    with col2:
        st.markdown(f'<div class="section-header">Queue ({len(st.session_state.queue_items)} items)</div>', unsafe_allow_html=True)

        if st.session_state.queue_items:
            c1, c2 = st.columns(2)
            with c1:
                start_btn = st.button("▶️ Start Processing", type="primary", use_container_width=True)
            with c2:
                if st.button("Clear Queue", use_container_width=True):
                    st.session_state.queue_items = []
                    st.rerun()

            by_type = {}
            for item in st.session_state.queue_items:
                t = item["type"]
                by_type[t] = by_type.get(t, 0) + 1
            for t, count in by_type.items():
                st.write(f"**{t}**: {count} videos")

            if start_btn:
                # Queue them all at once. _RENDER_LOCK runs them one at a
                # time, so this is the same serial order the old loop had —
                # without holding the page open for the whole batch.
                total = len(st.session_state.queue_items)
                while st.session_state.queue_items:
                    item = st.session_state.queue_items.pop(0)
                    start_generation(item["type"])

                st.success(f"Queued {total} video(s). They run one at a time — "
                           "watch progress on the Generate page.")
                st.rerun()
        else:
            st.info("Queue is empty. Add videos above!")


# ============== REVIEW PAGE ==============
elif page == "Review":
    st.markdown("## ✅ Review Videos")

    pending = get_pending_videos()

    if not pending:
        st.info("No videos pending review. Generate some new videos!")
    else:
        st.write(f"**{len(pending)} videos pending review**")

        types_available = list(set(v["type"] for v in pending))
        filter_type = st.selectbox("Filter by type", ["All"] + types_available)
        if filter_type != "All":
            pending = [v for v in pending if v["type"] == filter_type]

        st.markdown("---")

        for idx, video in enumerate(pending):
            col1, col2 = st.columns([2, 1])
            with col1:
                st.subheader(f"{video['name']}")
                st.write(f"**Type:** {video['type']} | **Created:** {video['created'].strftime('%Y-%m-%d %H:%M')}")
                if video["meta"] and "script_data" in video["meta"]:
                    script = video["meta"]["script_data"]
                    with st.expander("Script Details"):
                        if video["type"] == "quiz":
                            st.write(f"**Question:** {script.get('question', 'N/A')}")
                            st.write(f"**Options:** {script.get('options', {})}")
                            st.write(f"**Correct:** {script.get('correct', 'N/A')}")
                        elif video["type"] == "educational":
                            st.write(f"**Hook:** {script.get('hook', 'N/A')}")
                        elif video["type"] == "true_false":
                            st.write(f"**Statement:** {script.get('statement', 'N/A')}")
                        st.write(f"**Script:** {script.get('full_script', 'N/A')[:200]}...")
                    # Show generated metadata preview
                    try:
                        from metadata_generator import generate_metadata
                        category = script.get("_meta", {}).get("category", "")
                        meta = generate_metadata(script, video["type"], category)
                        st.markdown("---")
                        st.markdown("**Generated Metadata:**")
                        st.markdown(f"📌 **Title:** {meta['title']}")
                        desc_preview = meta['description'].replace('\n', ' ')[:200]
                        st.markdown(f"📝 **Description:** {desc_preview}...")
                        st.markdown(f"🏷️ **Hashtags:** {' '.join(meta['hashtags'][:5])}")
                    except ImportError:
                        pass
                if video["path"].exists():
                    st.video(str(video["path"]))

            with col2:
                st.write("")
                st.write("")
                if st.button("✅ Approve", key=f"approve_{idx}", type="primary", use_container_width=True):
                    approve_video(video["path"])
                    st.success("Approved!")
                    st.rerun()
                if st.button("❌ Reject", key=f"reject_{idx}", use_container_width=True):
                    reject_video(video["path"])
                    st.rerun()

            st.markdown("---")

        st.markdown("**Bulk Actions**")
        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button("✅ Approve All", use_container_width=True):
                for v in pending:
                    approve_video(v["path"])
                st.success(f"Approved {len(pending)} videos!")
                st.rerun()
        with bc2:
            if st.button("❌ Reject All", use_container_width=True):
                for v in pending:
                    reject_video(v["path"])
                st.rerun()


# ============== UPLOAD PAGE ==============
elif page == "Upload":
    st.markdown("## 📤 Upload Center")

    approved = get_approved_videos()

    # Platform status cards
    st.markdown('<div class="section-header">Connected Platforms</div>', unsafe_allow_html=True)

    platform_cols = st.columns(3)

    platforms = [
        {
            "name": "TikTok",
            "icon": "🎵",
            "key": "TIKTOK_CLIENT_KEY",
            "desc": "Content Posting API",
            "color": "#ff0050",
        },
        {
            "name": "YouTube Shorts",
            "icon": "▶️",
            "key": "YOUTUBE_CLIENT_ID",
            "desc": "YouTube Data API v3",
            "color": "#ff0000",
        },
        {
            "name": "Instagram Reels",
            "icon": "📷",
            "key": "INSTAGRAM_ACCESS_TOKEN",
            "desc": "Graph API",
            "color": "#e1306c",
        },
    ]

    platform_status = {}
    for col, platform in zip(platform_cols, platforms):
        with col:
            is_configured = bool(os.getenv(platform["key"], ""))
            platform_status[platform["name"]] = is_configured
            badge_class = "status-connected" if is_configured else "status-disconnected"
            badge_text = "CONNECTED" if is_configured else "NOT CONFIGURED"

            st.markdown(f"""
            <div class="platform-card">
                <div class="platform-icon">{platform['icon']}</div>
                <div class="platform-name">{platform['name']}</div>
                <div style="color:#94a3b8;font-size:0.85rem;margin-bottom:12px">{platform['desc']}</div>
                <span class="status-badge {badge_class}">{badge_text}</span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("")

    # Upload section
    if not approved:
        st.warning("No approved videos ready for upload. Approve some videos in the Review tab first.")
    else:
        st.markdown(f'<div class="section-header">📹 Ready for Upload ({len(approved)} videos)</div>', unsafe_allow_html=True)

        # Platform selection
        any_platform = any(platform_status.values())

        if not any_platform:
            st.warning("No platforms configured. Add your API keys in **Settings** to enable uploads.")
            st.markdown("**Quick setup:**")
            st.markdown("1. Go to **Settings** > **API Keys & Security**")
            st.markdown("2. Add your TikTok, YouTube, or Instagram credentials")
            st.markdown("3. Come back here to upload")
            st.markdown("---")

        # Upload targets
        target_platforms = []
        tcols = st.columns(3)
        for col, platform in zip(tcols, platforms):
            with col:
                enabled = platform_status.get(platform["name"], False)
                # Reconcile the derived half (auth status) with the user half
                # (chosen targets) BEFORE rendering. No `value=` — a keyed
                # widget ignores it, which is the bug this replaces.
                reconcile_platform_target(
                    st.session_state, platform["name"], enabled)
                if st.checkbox(
                    f"{platform['icon']} {platform['name']}",
                    disabled=not enabled,
                    key=f"target_{platform['name']}"
                ):
                    target_platforms.append(platform["name"])

        st.markdown("---")

        # Video list with upload buttons
        for video in approved:
            with st.container():
                col1, col2 = st.columns([3, 2])

                with col1:
                    st.write(f"**{video['name']}**")
                    st.caption(f"{video['type']} | {video['created'].strftime('%Y-%m-%d %H:%M')}")
                    # A published video can still be sitting here (main.py did
                    # not move it, or a move failed). Say so before the
                    # operator presses upload — the manual route is how the
                    # first duplicate happened.
                    if video.get("published_to"):
                        ids = ", ".join(
                            f"{r.get('platform')}={r.get('upload_id')}"
                            for r in video.get("published_rows", [])
                            if r.get("upload_id"))
                        st.warning(
                            f"⚠️ ALREADY PUBLISHED to "
                            f"{', '.join(video['published_to'])}"
                            + (f" ({ids})" if ids else "")
                            + ". Uploading again would create a duplicate."
                        )
                    if video["path"].exists():
                        with st.expander("Preview Video"):
                            st.video(str(video["path"]))

                with col2:
                    # Generate metadata from script
                    script = {}
                    category = ""
                    if video.get("meta") and "script_data" in video["meta"]:
                        script = video["meta"]["script_data"]
                        category = script.get("_meta", {}).get("category", "")

                    try:
                        from metadata_generator import generate_metadata, adapt_for_platform, regenerate_for_platform
                        meta = generate_metadata(script, video.get("type", "educational"), category)
                    except ImportError:
                        meta = {
                            "title": script.get("hook", script.get("question", script.get("statement", ""))),
                            "description": "",
                            "hashtags": script.get("hashtags", ["#LearnEnglish"]),
                        }

                    # ONE key per field — the widget's key IS the storage.
                    #
                    # This used to use two keys per field: meta_title_<name>
                    # for storage and ti_<name> for the widget, written as
                    #
                    #   st.session_state[title_key] = st.text_input(
                    #       "Title", value=st.session_state[title_key],
                    #       key=f"ti_{name}")
                    #
                    # A Streamlit widget with a `key` keeps its value in
                    # st.session_state[key], and once that entry exists the
                    # `value=` argument is IGNORED on every rerun. So the
                    # regenerate button wrote the (paid-for) API result to the
                    # storage key, called st.rerun(), and the widget then
                    # returned its STALE text — which was assigned straight
                    # back over the new value on the very next line.
                    #
                    # Typing still worked, because that updates the widget key
                    # first; only writes originating outside the widget were
                    # lost. Hence the symptom: no error, no change, and a
                    # billed API call discarded every press.
                    #
                    # With a single key the button writes the same entry the
                    # widget reads, so there is nothing left to clobber.
                    title_key = f"meta_title_{video['name']}"
                    desc_key = f"meta_desc_{video['name']}"
                    tags_key = f"meta_tags_{video['name']}"
                    pending_key = f"_meta_pending_{video['name']}"

                    if title_key not in st.session_state:
                        st.session_state[title_key] = meta["title"]
                        st.session_state[desc_key] = meta["description"]
                        st.session_state[tags_key] = " ".join(meta["hashtags"])

                    # Apply a staged regeneration BEFORE the widgets exist.
                    #
                    # Streamlit forbids writing session_state[k] once the
                    # widget owning k has been instantiated this run, and the
                    # regenerate buttons render BELOW these fields — so the
                    # button handler cannot assign to them directly:
                    #
                    #   StreamlitAPIException: st.session_state.meta_title_x
                    #   cannot be modified after the widget with key
                    #   meta_title_x is instantiated
                    #
                    # So the handler stages its result under a separate key
                    # and reruns; the write lands here, at the top of the next
                    # run, while the widget keys are still free.
                    pending = st.session_state.pop(pending_key, None)
                    if pending:
                        st.session_state[title_key] = pending["title"]
                        st.session_state[desc_key] = pending["description"]
                        st.session_state[tags_key] = pending["hashtags"]

                    with st.expander("Edit Title & Description"):
                        # No `value=` and no assignment: the widget reads and
                        # writes session_state[key] itself.
                        st.text_input("Title", key=title_key)
                        st.text_area("Description", key=desc_key, height=80)
                        st.text_input("Hashtags", key=tags_key)

                        # Platform regeneration buttons
                        regen_cols = st.columns(3)
                        for i, (icon, pname, pkey) in enumerate([
                            ("🎵", "TikTok", "tiktok"),
                            ("▶️", "YouTube", "youtube"),
                            ("📸", "Instagram", "instagram"),
                        ]):
                            with regen_cols[i]:
                                if st.button(f"{icon} {pname}", key=f"regen_{pkey}_{video['name']}",
                                             use_container_width=True, help=f"Regenerate for {pname}"):
                                    try:
                                        with st.spinner(f"Generating for {pname}..."):
                                            result = regenerate_for_platform(
                                                script, pkey, video.get("type", "educational")
                                            )
                                            # Stage, do not assign: these
                                            # widgets already exist this run.
                                            tags = result.get("hashtags", [])
                                            st.session_state[pending_key] = {
                                                "title": result.get("title", ""),
                                                "description": result.get("description", ""),
                                                "hashtags": " ".join(
                                                    f"#{t.lstrip('#')}" for t in tags),
                                            }
                                            st.rerun()
                                    except Exception as e:
                                        st.error(f"Regeneration failed: {e}")

                # Upload button
                if target_platforms:
                    if st.button("📤 Upload", key=f"upload_{video['name']}", use_container_width=True):
                        try:
                            from uploader import get_upload_manager
                            manager = get_upload_manager()
                            # Same resolver as the bulk path, so the two
                            # cannot drift apart again.
                            _resolved = resolve_upload_metadata(
                                video["name"], script, "", 
                                video.get("type", "educational"), category,
                                st.session_state,
                            )
                            vid_title = _resolved["title"]
                            vid_desc = _resolved["description"]
                            vid_tags = _resolved["hashtags"]

                            platform_map = {
                                "TikTok": "tiktok",
                                "YouTube Shorts": "youtube",
                                "Instagram Reels": "instagram",
                            }
                            upload_success = False
                            upload_platforms = []
                            for platform_name in target_platforms:
                                platform_key = platform_map.get(platform_name, platform_name.lower())
                                # Build the EXACT strings once, then send and
                                # record the same variables. Composing the
                                # payload inside the call meant the record and
                                # the request could describe different text.
                                sent_title = vid_title[:100]
                                sent_desc = vid_desc
                                sent_tags = [t.lstrip("#") for t in vid_tags]
                                # IDEMPOTENCY. Same guard as the headless
                                # path; the manual route is how the first
                                # duplicate happened.
                                _v = _guard_decide(video["name"], platform_key,
                                                   manager=manager)
                                if not _v.should_upload:
                                    _guard_notice(st, video["name"], platform_name, _v)
                                    continue
                                with st.spinner(f"Uploading to {platform_name}..."):
                                    result = _guarded_upload(
                                        manager,
                                        video["name"],
                                        platform_key,
                                        str(video["path"]),
                                        title=sent_title,
                                        description=sent_desc,
                                        hashtags=sent_tags,
                                    )
                                    success = (isinstance(result, dict) and result.get("success")) or (hasattr(result, 'success') and result.success)
                                    if success:
                                        st.success(f"Uploaded to {platform_name}!")
                                        upload_success = True
                                        upload_platforms.append(platform_name)
                                        _record_upload(
                                            st, video, platform_key, result,
                                            sent_title, sent_desc, sent_tags)
                                        st.session_state.upload_history.append({
                                            "video": video["name"],
                                            "platform": platform_name,
                                            "time": datetime.now().isoformat(),
                                            "status": "success"
                                        })
                                    else:
                                        err = result.get("error", "Unknown") if isinstance(result, dict) else getattr(result, 'error', 'Unknown')
                                        st.error(f"Failed: {err}")

                            # Move to uploaded if at least one platform succeeded
                            if upload_success and video["path"].exists():
                                move_to_uploaded(video["path"], {
                                    "platforms": upload_platforms,
                                    "uploaded_at": datetime.now().isoformat(),
                                    "title": vid_title,
                                })
                                st.rerun()
                        except ImportError:
                            st.error("Upload module not available.")
                        except Exception as e:
                            st.error(f"Upload error: {str(e)}")
                else:
                    st.button("📤 Upload", key=f"upload_{video['name']}", disabled=True, use_container_width=True)

                btn_cols = st.columns(2)
                with btn_cols[0]:
                    if video["path"].exists():
                        with open(video["path"], "rb") as vf:
                            st.download_button(
                                "⬇️ Download",
                                data=vf,
                                file_name=video["path"].name,
                                mime="video/mp4",
                                key=f"dl_{video['name']}",
                                use_container_width=True,
                            )
                with btn_cols[1]:
                    if st.button("↩️", key=f"unapprove_{video['name']}", use_container_width=True,
                                 help="Move back to pending"):
                        unapprove_video(video['path'])
                        st.rerun()

                st.markdown("---")

        # Bulk upload
        if target_platforms and len(approved) > 1:
            st.markdown("---")
            st.markdown("**Bulk Upload**")
            if st.button(f"📤 Upload All {len(approved)} Videos to {', '.join(target_platforms)}", type="primary"):
                progress = st.progress(0)
                try:
                    from uploader import get_upload_manager
                    from metadata_generator import generate_metadata, adapt_for_platform
                    manager = get_upload_manager()

                    bulk_platform_map = {
                        "TikTok": "tiktok",
                        "YouTube Shorts": "youtube",
                        "Instagram Reels": "instagram",
                    }
                    uploaded_count = 0
                    for i, video in enumerate(approved):
                        script = {}
                        category = ""
                        if video.get("meta") and "script_data" in video["meta"]:
                            script = video["meta"]["script_data"]
                            category = script.get("_meta", {}).get("category", "")

                        any_success = False
                        platforms_done = []
                        for pname in target_platforms:
                            pkey = bulk_platform_map.get(pname, pname.lower())
                            # Was generate_metadata(script, ...) + adapt, which
                            # ignored session_state entirely and published text
                            # the operator never saw. One resolver now serves
                            # both upload paths.
                            adapted = resolve_upload_metadata(
                                video["name"], script, pkey,
                                video.get("type", "educational"), category,
                                st.session_state,
                            )
                            _v = _guard_decide(video["name"], pkey, manager=manager)
                            if not _v.should_upload:
                                _guard_notice(st, video["name"], pname, _v)
                                continue
                            result = _guarded_upload(
                                manager,
                                video["name"],
                                pkey,
                                str(video["path"]),
                                title=adapted["title"],
                                description=adapted["description"],
                                hashtags=adapted["hashtags"],
                            )
                            success = (isinstance(result, dict) and result.get("success")) or (hasattr(result, 'success') and result.success)
                            if success:
                                any_success = True
                                platforms_done.append(pname)
                                _record_upload(
                                    st, video, pkey, result,
                                    adapted["title"], adapted["description"],
                                    adapted["hashtags"])

                        if any_success and video["path"].exists():
                            move_to_uploaded(video["path"], {
                                "platforms": platforms_done,
                                "uploaded_at": datetime.now().isoformat(),
                                "title": meta["title"],
                            })
                            uploaded_count += 1

                        progress.progress((i + 1) / len(approved))

                    st.success(f"Uploaded {uploaded_count} videos!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Bulk upload error: {str(e)}")

    # Uploaded Videos section
    uploaded = get_uploaded_videos()
    if uploaded:
        st.markdown("---")
        st.markdown(f'<div class="section-header">✅ Uploaded Videos ({len(uploaded)})</div>', unsafe_allow_html=True)

        for video in uploaded:
            with st.container():
                col1, col2 = st.columns([3, 2])

                with col1:
                    st.write(f"**{video['name']}**")
                    upload_info = video.get("upload_info", {})
                    platforms_str = ", ".join(upload_info.get("platforms", ["Unknown"]))
                    uploaded_at = upload_info.get("uploaded_at", "")[:16]
                    st.caption(f"{video['type']} | Uploaded to: {platforms_str} | {uploaded_at}")

                    if video["path"].exists():
                        with st.expander("Preview Video"):
                            st.video(str(video["path"]))

                with col2:
                    upload_title = upload_info.get("title", "")
                    if upload_title:
                        st.caption(f"Title: {upload_title[:60]}...")
                    if video["path"].exists():
                        with open(video["path"], "rb") as vf:
                            st.download_button(
                                "⬇️ Download",
                                data=vf,
                                file_name=video["path"].name,
                                mime="video/mp4",
                                key=f"dl_uploaded_{video['name']}",
                                use_container_width=True,
                            )

                st.markdown("---")

    # Upload history (session)
    if st.session_state.upload_history:
        with st.expander("Recent Upload Log"):
            for entry in reversed(st.session_state.upload_history[-10:]):
                icon = "✅" if entry["status"] == "success" else "❌"
                st.write(f"{icon} **{entry['video']}** → {entry['platform']} ({entry['time'][:16]})")


# ============== LIBRARY PAGE ==============
elif page == "Library":
    st.markdown("## 📚 Video Library")

    library = get_library_videos()
    pending = get_pending_videos()
    approved = get_approved_videos()
    uploaded = get_uploaded_videos()
    all_videos = library + pending + approved + uploaded

    if not all_videos:
        st.info("Library is empty. Generate some videos!")
    else:
        cols = st.columns(3)
        with cols[0]:
            st.metric("Total Videos", len(all_videos))
        with cols[1]:
            total_size = sum(v.get("size", 0) or v["path"].stat().st_size for v in all_videos if v["path"].exists())
            st.metric("Total Size", f"{total_size / (1024*1024):.1f} MB")
        with cols[2]:
            st.metric("Video Types", len(set(v["type"] for v in all_videos)))

        stuck = [v for v in all_videos if v.get("stage") == "batch"]
        if stuck:
            st.info(
                f"{len(stuck)} artifact(s) from `main.py --batch` are sitting "
                f"in output/video/. Promote one to send it through Review and "
                f"the guarded upload flow.")

        st.markdown("---")

        fc1, fc2 = st.columns([1, 3])
        with fc1:
            types = ["All"] + list(set(v["type"] for v in all_videos))
            filter_type = st.selectbox("Filter", types, key="lib_filter")
        with fc2:
            search = st.text_input("Search", placeholder="Search by name...")

        filtered = all_videos
        if filter_type != "All":
            filtered = [v for v in filtered if v["type"] == filter_type]
        if search:
            filtered = [v for v in filtered if search.lower() in v["name"].lower()]

        st.write(f"Showing {len(filtered)} videos")
        st.markdown("---")

        rows = [filtered[i:i+3] for i in range(0, len(filtered), 3)]
        for row in rows:
            cols = st.columns(3)
            for idx, video in enumerate(row):
                with cols[idx]:
                    name = f"**{video['name'][:20]}...**" if len(video['name']) > 20 else f"**{video['name']}**"
                    st.write(name)
                    st.caption(f"{video['type']} | {video['created'].strftime('%m/%d %H:%M')}")
                    if video["path"].exists():
                        st.video(str(video["path"]))
                    # output/video/ artifacts had no road out of the library.
                    # Promotion moves them into pending/, where they take the
                    # same Review -> Approve -> guarded Upload route as
                    # everything else.
                    if video.get("stage") == "batch":
                        if st.button("⬆️ Promote to Review",
                                     key=f"promote_{video['path']}",
                                     use_container_width=True):
                            verdict = promote_to_review(video["path"])
                            if verdict["ok"]:
                                st.success(
                                    f"{verdict['artifact']} → pending/"
                                    f"{verdict['video_type']}/ — "
                                    f"{verdict['reason']}")
                                st.rerun()
                            else:
                                st.error(f"Not promoted: {verdict['reason']}")
                    if st.button("🗑️ Delete", key=f"del_{video['path']}", use_container_width=True):
                        delete_video(video["path"])
                        st.rerun()


# ============== SCHEDULER PAGE ==============
elif page == "Scheduler":
    st.markdown("## ⏰ Auto-Generation Scheduler")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown('<div class="section-header">Configuration</div>', unsafe_allow_html=True)

        videos_per_batch = st.number_input(
            "Videos per batch", min_value=1, max_value=20,
            value=st.session_state.scheduler_config["videos_per_batch"]
        )

        interval = st.selectbox(
            "Generation interval",
            options=[15, 30, 60, 120, 240],
            index=2,
            format_func=lambda x: f"{x} min" if x < 60 else f"{x//60}h"
        )

        st.write("**Video types:**")
        type_quiz = st.checkbox("Quiz", value="quiz" in st.session_state.scheduler_config["types"])
        type_edu = st.checkbox("Educational", value="educational" in st.session_state.scheduler_config["types"])
        type_tf = st.checkbox("True/False", value="true_false" in st.session_state.scheduler_config["types"])
        type_vocab = st.checkbox("Vocabulary", value="vocabulary" in st.session_state.scheduler_config["types"])

        selected_types = []
        if type_quiz: selected_types.append("quiz")
        if type_edu: selected_types.append("educational")
        if type_tf: selected_types.append("true_false")
        if type_vocab: selected_types.append("vocabulary")

        if st.button("💾 Save Config", use_container_width=True):
            st.session_state.scheduler_config = {
                "videos_per_batch": videos_per_batch,
                "interval_minutes": interval,
                "types": selected_types
            }
            st.success("Saved!")

    with col2:
        st.markdown('<div class="section-header">Control</div>', unsafe_allow_html=True)

        if st.session_state.scheduler_enabled:
            st.success("Scheduler is ACTIVE")
            if st.button("Stop Scheduler", use_container_width=True):
                st.session_state.scheduler_enabled = False
                st.rerun()
        else:
            st.warning("Scheduler is INACTIVE")
            if st.button("Start Scheduler", type="primary", use_container_width=True):
                st.session_state.scheduler_enabled = True
                st.rerun()

        st.markdown("---")
        if st.button("🚀 Generate Batch Now", use_container_width=True):
            if not selected_types:
                st.error("Select at least one type!")
            else:
                for i in range(videos_per_batch):
                    start_generation(selected_types[i % len(selected_types)])
                st.success(f"Queued {videos_per_batch} video(s). They run one at "
                           "a time — watch progress on the Generate page.")
                st.rerun()


# ============== SETTINGS PAGE ==============
elif page == "Settings":
    st.markdown("## ⚙️ Settings")

    tab1, tab2, tab3 = st.tabs(["🔑 API Keys & Security", "🎬 Video Config", "🔊 Audio Config"])

    # ── API Keys Tab ──
    with tab1:
        st.markdown('<div class="section-header">API Key Management</div>', unsafe_allow_html=True)
        st.caption("Keys are stored in `.env` and never exposed in logs or version control.")

        api_groups = {
            "Core (Required)": [
                ("OPENAI_API_KEY", "OpenAI", "GPT script generation + TTS fallback", True),
            ],
            "TTS Provider": [
                ("TTS_PROVIDER", "TTS Provider", "elevenlabs, openai, google, edge", False),
                ("ELEVENLABS_API_KEY", "ElevenLabs API Key", "High-quality voice synthesis", False),
                ("ELEVENLABS_VOICE_ID", "ElevenLabs Voice ID", "Voice character ID", False),
            ],
            "Social Media Uploads": [
                ("TIKTOK_CLIENT_KEY", "TikTok Client Key", "Content Posting API", False),
                ("TIKTOK_CLIENT_SECRET", "TikTok Client Secret", "Content Posting API", False),
                ("YOUTUBE_CLIENT_ID", "YouTube Client ID", "YouTube Data API v3", False),
                ("YOUTUBE_CLIENT_SECRET", "YouTube Client Secret", "YouTube Data API v3", False),
                ("INSTAGRAM_ACCESS_TOKEN", "Instagram Access Token", "Graph API", False),
                ("INSTAGRAM_BUSINESS_ACCOUNT_ID", "Instagram Business Account ID", "Graph API", False),
            ],
        }

        for group_name, keys in api_groups.items():
            st.markdown(f"**{group_name}**")

            for env_var, label, description, required in keys:
                current_value = os.getenv(env_var, "")
                is_set = bool(current_value and len(current_value) > 2)

                col1, col2, col3 = st.columns([2, 3, 1])

                with col1:
                    if required and not is_set:
                        css_class = "key-error"
                        status_text = "REQUIRED"
                    elif is_set:
                        css_class = "key-ok"
                        status_text = mask_key(current_value)
                    else:
                        css_class = "key-missing"
                        status_text = "Not set"

                    st.markdown(f"**{label}**")
                    st.markdown(f'<div class="key-status {css_class}">{status_text}</div>', unsafe_allow_html=True)
                    st.caption(description)

                with col2:
                    new_value = st.text_input(
                        f"Update {label}",
                        value="",
                        type="password" if "KEY" in env_var or "SECRET" in env_var or "TOKEN" in env_var else "default",
                        placeholder=f"Enter new {label}...",
                        key=f"input_{env_var}",
                        label_visibility="collapsed",
                    )

                with col3:
                    if st.button("Save", key=f"save_{env_var}", use_container_width=True):
                        if new_value:
                            save_env_key(env_var, new_value)
                            st.success(f"Saved!")
                            st.rerun()
                        else:
                            st.warning("Enter a value")

            st.markdown("---")

        # Security info
        st.markdown('<div class="section-header">Security Notes</div>', unsafe_allow_html=True)
        st.markdown("""
        - `.env` file is gitignored and never committed
        - OAuth tokens stored in `.tokens/` (also gitignored)
        - API keys are masked in the dashboard
        - Rotate keys immediately if you suspect exposure
        """)

    # ── Video Config Tab ──
    with tab2:
        import yaml

        CONFIG_PATH = ROOT / "config.yaml"

        def load_config():
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, 'r') as f:
                    return yaml.safe_load(f) or {}
            return {}

        def save_config(config):
            with open(CONFIG_PATH, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)

        config = load_config()

        col1, col2 = st.columns(2)

        with col1:
            try:
                from backgrounds import BACKGROUND_PRESETS, get_recommended_preset
                preset_options = list(BACKGROUND_PRESETS.keys())
                current_bg = config.get("video", {}).get("default_background", get_recommended_preset())
                default_background = st.selectbox(
                    "Default Background", options=preset_options,
                    index=preset_options.index(current_bg) if current_bg in preset_options else 0,
                )
            except ImportError:
                default_background = st.text_input(
                    "Default Background",
                    value=config.get("video", {}).get("default_background", "static_purple")
                )

            bg_mode = st.selectbox("Background Mode", ["random", "fixed"],
                                   index=0 if config.get("video", {}).get("background_mode") == "random" else 1)

            video_width = st.number_input("Width", value=config.get("video", {}).get("width", 1080),
                                          min_value=480, max_value=2160)

        with col2:
            video_height = st.number_input("Height", value=config.get("video", {}).get("height", 1920),
                                            min_value=854, max_value=3840)
            video_fps = st.number_input("FPS", value=config.get("video", {}).get("fps", 30),
                                        min_value=24, max_value=60)

            default_type = st.selectbox("Default Video Type", options=VIDEO_TYPES,
                                        index=VIDEO_TYPES.index(config.get("content", {}).get("default_type", "educational"))
                                        if config.get("content", {}).get("default_type", "educational") in VIDEO_TYPES else 0)

        if st.button("💾 Save Video Config", type="primary", use_container_width=True):
            new_config = {
                "video": {
                    "background_mode": bg_mode,
                    "default_background": default_background,
                    "enabled_backgrounds": config.get("video", {}).get("enabled_backgrounds", []),
                    "width": video_width,
                    "height": video_height,
                    "fps": video_fps,
                    "animation_style": config.get("video", {}).get("animation_style", "clean_pop"),
                },
                "audio": config.get("audio", {}),
                "output": config.get("output", {
                    "videos": "output/video",
                    "audio": "output/audio",
                    "frames": "output/frames"
                }),
                "content": {
                    "default_type": default_type,
                },
            }
            save_config(new_config)
            st.success("Video config saved!")

        with st.expander("Raw config.yaml"):
            st.code(yaml.dump(config, default_flow_style=False), language="yaml")

    # ── Audio Config Tab ──
    with tab3:
        import yaml

        CONFIG_PATH = ROOT / "config.yaml"
        config = {}
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'r') as f:
                config = yaml.safe_load(f) or {}

        audio_config = config.get("audio", {})

        col1, col2 = st.columns(2)
        with col1:
            provider = st.selectbox("TTS Provider",
                                    ["elevenlabs", "openai", "google", "edge"],
                                    index=["elevenlabs", "openai", "google", "edge"].index(
                                        audio_config.get("provider", "elevenlabs")))
            voice_id = st.text_input("Voice ID", value=audio_config.get("voice_id", "default"))
            model = st.selectbox("Model", ["eleven_v3", "eleven_multilingual_v2", "eleven_monolingual_v1"],
                                 index=0)

        with col2:
            global_speed = st.slider("Global Speed", 0.5, 2.0, audio_config.get("global_speed", 1.0), 0.05)
            stability = st.slider("Stability", 0.0, 1.0, audio_config.get("stability", 0.50), 0.05)
            similarity = st.slider("Similarity Boost", 0.0, 1.0, audio_config.get("similarity_boost", 0.80), 0.05)
            style = st.slider("Style", 0.0, 1.0, audio_config.get("style", 0.05), 0.05)

        if st.button("💾 Save Audio Config", type="primary", use_container_width=True):
            config["audio"] = {
                "provider": provider,
                "voice_id": voice_id,
                "model": model,
                "global_speed": global_speed,
                "stability": stability,
                "similarity_boost": similarity,
                "style": style,
                "speaker_boost": audio_config.get("speaker_boost", True),
                "humanize": audio_config.get("humanize", True),
            }
            with open(ROOT / "config.yaml", 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            st.success("Audio config saved!")


# ============== LOGS PAGE ==============
elif page == "Logs":
    st.markdown("## 📜 Generation Logs")

    jobs = load_jobs()
    all_jobs = jobs.get("active", []) + jobs.get("history", [])
    completed_jobs = [j for j in jobs.get("history", []) if j.get("status") == "completed"]
    failed_jobs = [j for j in jobs.get("history", []) if j.get("status") == "failed"]

    cols = st.columns(4)
    with cols[0]:
        st.metric("Total Jobs", len(all_jobs))
    with cols[1]:
        st.metric("Active", len(jobs.get("active", [])))
    with cols[2]:
        st.metric("Completed", len(completed_jobs))
    with cols[3]:
        st.metric("Failed", len(failed_jobs))

    st.markdown("---")

    log_filter = st.selectbox("Filter", ["All", "Active", "Completed", "Failed"])

    if log_filter == "Active":
        display_jobs = jobs.get("active", [])
    elif log_filter == "Completed":
        display_jobs = completed_jobs
    elif log_filter == "Failed":
        display_jobs = failed_jobs
    else:
        display_jobs = all_jobs

    display_jobs = sorted(display_jobs,
                          key=lambda x: x.get("updated_at", x.get("created_at", "")),
                          reverse=True)

    st.write(f"Showing {len(display_jobs)} jobs")
    st.markdown("---")

    for job in display_jobs[:50]:
        status = job.get("status", "unknown")
        icon = {"running": "🔄", "completed": "✅", "failed": "❌"}.get(status, "⏳")

        with st.expander(f"{icon} {job.get('topic', 'Unknown')} ({job.get('video_type', 'N/A')}) - {job.get('id', 'N/A')}"):
            c1, c2 = st.columns(2)
            with c1:
                st.write(f"**Job ID:** `{job.get('id', 'N/A')}`")
                st.write(f"**Type:** {job.get('video_type', 'N/A')}")
                st.write(f"**Category:** {job.get('category', 'N/A')}")
                st.write(f"**Progress:** {job.get('progress', 0)}%")
            with c2:
                st.write(f"**Created:** {job.get('created_at', 'N/A')}")
                if job.get("completed_at"):
                    st.write(f"**Completed:** {job['completed_at']}")
            if job.get("current_step"):
                st.info(f"Last step: {job['current_step']}")
            if job.get("error"):
                st.error(f"Error: {job['error'][:500]}")
            if job.get("video_path"):
                st.write(f"**Output:** `{job['video_path']}`")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Clear Failed Jobs", use_container_width=True):
            jobs["history"] = [j for j in jobs.get("history", []) if j.get("status") != "failed"]
            save_jobs(jobs)
            st.success("Cleared!")
            st.rerun()
    with c2:
        if st.button("Clear All History", use_container_width=True):
            jobs["history"] = []
            save_jobs(jobs)
            st.success("Cleared!")
            st.rerun()
