#!/usr/bin/env python3
"""The dashboard's background job engine: the job ledger, the script queue,
the batch queue and the render workers.

Moved out of admin.py so that editing a panel page no longer reloads the code
that runs renders, and so the engine can be tested without Streamlit. admin.py
re-exports every name it or its tests use. Process-wide state (locks, worker
list, audit cache) stays in dashboard_state, exactly as before.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from run_log import attach_run_log, detach_run_log  # noqa: E402
from script_generator import generate_script, get_random_topic, find_topic  # noqa: E402
import series  # noqa: E402
import voice_credits  # noqa: E402
import pipeline  # noqa: E402
from cost_tracker import reset_tracker  # noqa: E402

logger = logging.getLogger(__name__)


# Output directories
OUTPUT_DIR = ROOT / "output"
SCRIPTS_DIR = OUTPUT_DIR / "scripts"
AUDIO_DIR = OUTPUT_DIR / "audio"
VIDEO_DIR = OUTPUT_DIR / "video"
PENDING_DIR = OUTPUT_DIR / "pending"
# This video's own footage. The clip tier writes here and the renderer
# reads from here; --batch keeps its clips inside the artifact directory,
# and the dashboard has no artifact, so it gets one folder per video.
CLIPS_DIR = OUTPUT_DIR / "clips"
APPROVED_DIR = OUTPUT_DIR / "approved"
#: Where a render is written until it is whole (STEP 59 §6). No page lists it.
RENDERING_DIR = OUTPUT_DIR / "rendering"
#: Where a cut render goes: moved, never deleted, with a reason.txt.
CUT_DIR = OUTPUT_DIR / "rejected" / "_cut"
REJECTED_DIR = OUTPUT_DIR / "rejected"
UPLOADED_DIR = OUTPUT_DIR / "uploaded"

for d in [PENDING_DIR, APPROVED_DIR, REJECTED_DIR, UPLOADED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============== PERSISTENT PROGRESS TRACKING ==============
JOBS_FILE = OUTPUT_DIR / "generation_jobs.json"

# Guards the whole read-modify-write of JOBS_FILE. Generation runs in worker
# threads now, so create/update/complete interleave; without this a worker
# reading before another's write and saving after it silently drops that job.
# In dashboard_state, not here: this file is re-executed on every click, so a
# lock defined here was a new lock per click (see dashboard_state's docstring).
import dashboard_state as _ds
_JOBS_LOCK = _ds.JOBS_LOCK


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
    # A tmp name per writer: with one shared name, two writers that ever got
    # past the lock (2026-10-13, job ebe7bb3e) renamed each other's file away.
    tmp = JOBS_FILE.with_name(
        f"{JOBS_FILE.name}.{os.getpid()}.{threading.get_ident()}.tmp")
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
_OWNER_STARTED = _ds.once("owner_started", lambda: _proc_start(_OWNER_PID))


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


# ============== THE SCRIPT QUEUE ==============
#
# The queue: scripts written ahead of time, produced one at a time, no
# script-model call anywhere (born when the OpenAI account had no credits).
#
# THIS LIVES IN run_pipeline_with_tracking AND NOWHERE ELSE. Every door into
# the dashboard -- the Generate button, "5 of each type", the batch, the
# scheduler -- calls that one function, so putting the preference there gives
# it to all of them at once. Wiring it into each button is how this project
# has repeatedly fixed one door and left the others broken, most recently two
# packages ago, and the rule that earned is: the fix goes in the shared
# function.


def _queue_guard():
    """The guard module -- reloaded when its file changes.

    `sys.path.insert` used to run on every call of all three helpers below,
    and Streamlit calls them on every rerun — the list grew without bound
    for the lifetime of the process.

    RELOADED ON EDIT. tools/ is outside the folder Streamlit watches, so a
    dashboard left running kept whatever queue_guard it imported first, for
    days. A fix to the guard did not reach it until someone restarted it.
    """
    tools = str(ROOT / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import importlib
    import queue_guard
    try:
        mtime = (ROOT / "tools" / "queue_guard.py").stat().st_mtime_ns
    except OSError:
        return queue_guard
    seen = getattr(queue_guard, "_LOADED_MTIME", None)
    if seen is not None and seen != mtime:
        queue_guard = importlib.reload(queue_guard)
        _AUDIT_CACHE.update(at=0.0, bad=None)
    queue_guard._LOADED_MTIME = mtime
    return queue_guard


#: The last audit, and when it was taken. AN AUDIT IS NOT CHEAP: it reads
#: every queued script, validates it against the schema, measures every text
#: field with the real font through length_spec, and walks every script and
#: artifact on disk for topic_history. Streamlit reruns the whole page on
#: every widget interaction, so an uncached queue_status() put all of that in
#: front of every click on the Generate page.
_AUDIT_CACHE = _ds.AUDIT_CACHE
_AUDIT_TTL = 20.0


def _queue_bad(guard, fresh: bool = False) -> set:
    """Paths the guard refuses, from a short-lived cache.

    `fresh=True` for the decision that actually hands a script to a render —
    a stale audit there could produce a topic that was made 20 seconds ago.
    """
    now = time.time()
    if (not fresh and _AUDIT_CACHE["bad"] is not None
            and now - _AUDIT_CACHE["at"] < _AUDIT_TTL):
        return _AUDIT_CACHE["bad"]
    # ONLY WHAT BLOCKS. Severity is a property of the failure: a repeated
    # topic reaches the channel and cannot be taken back, while a short video
    # is a real video the owner can watch and judge. Refusing on duration
    # produced NOTHING, and pushed every quiz, true_false and fill_blank job
    # onto the GPT fallback -- which is how a dead OpenAI key ended up in the
    # owner's face on a route built to need no API at all.
    bad = {path for path, reason in guard.audit() if guard.blocks(reason)}
    _AUDIT_CACHE.update(at=now, bad=bad)
    return bad


class AlreadyRendering(RuntimeError):
    """A job for this script (topic_id + type) is already queued or running."""


def script_key(script: dict) -> Optional[str]:
    """topic_id:type, the identity of a script across jobs; None for a script without one."""
    meta = (script or {}).get("_meta") or {}
    vtype = (script or {}).get("type") or meta.get("video_type")
    return f"{meta['topic_id']}:{vtype}" if meta.get("topic_id") else None


def rendering_job_for(key: Optional[str], exclude: str = None) -> Optional[dict]:
    """The active job holding `key`. The ledger is shared, so this sees other dashboards too."""
    if not key:
        return None
    return next((j for j in get_active_jobs()
                 if j.get("script_key") == key and j.get("id") != exclude), None)


def move_to_cut(paths, reason: str, name: str) -> Optional[Path]:
    """Move whatever a cut render left to output/rejected/_cut/<name>/ with reason.txt. Never deletes."""
    present = [Path(p) for p in paths if p and Path(p).exists()]
    if not present:
        return None
    dest = CUT_DIR / name
    dest.mkdir(parents=True, exist_ok=True)
    for path in present:
        shutil.move(str(path), str(dest / path.name))
    (dest / "reason.txt").write_text(f"{datetime.now().isoformat()}\n{reason}\n", encoding="utf-8")
    logger.warning("cut render: moved %s to %s (%s)", [p.name for p in present], dest, reason[:200])
    return dest


def queue_order(paths: list) -> list:
    """The queued scripts in priority order (queue_priority); the file order when it cannot rank."""
    try:
        import queue_priority
        return [p for p, _score, _why in queue_priority.ranked(list(paths))]
    except Exception:                                       # noqa: BLE001 — never block the queue
        logger.warning("queue: priority unavailable, file order", exc_info=True)
        return list(paths)


def next_best() -> Optional[tuple]:
    """(path, script, why) — what «Producir el siguiente mejor» would make now, or None."""
    picked = queue_pick()
    if not picked:
        return None
    path, data = picked
    try:
        import channel_stats
        import queue_priority
        cfg = queue_priority.settings()
        _p, why = queue_priority.priority(data, queue_priority.type_scores(channel_stats.latest(), cfg), cfg)
    except Exception:                                       # noqa: BLE001
        why = "orden de la cola"
    return path, data, why


def queue_pick(video_type: str = None):
    """The next SAFE queued script for this type, or None.

    Safe means the guard raised no problem against it: not a topic already
    produced, not a duplicate of another queued script, and clean against the
    schema, the duration band and length_spec. A script with any problem is
    never handed out -- see tools/queue_guard.py.
    """
    try:
        queue_guard = _queue_guard()
    except Exception:                                       # noqa: BLE001
        logger.debug("queue: guard unavailable", exc_info=True)
        return None

    try:
        bad = _queue_bad(queue_guard, fresh=True)
        # STEP 80 §2: best first — the type's measured views, an A1 category boost
        for path in queue_order(queue_guard.queued_scripts()):
            if path.relative_to(ROOT) in bad:
                continue
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            if video_type and data.get("type") != video_type:
                continue
            if rendering_job_for(script_key(data)):
                continue                  # another job already holds it
            return path, data
    except Exception:                                       # noqa: BLE001
        logger.warning("queue: could not read the queue", exc_info=True)
    return None


def queue_status() -> dict:
    """What the Generate page shows: how many are ready, and per type."""
    try:
        queue_guard = _queue_guard()
        bad = _queue_bad(queue_guard)
        ready, by_type = 0, {}
        for path in queue_guard.queued_scripts():
            if path.relative_to(ROOT) in bad:
                continue
            ready += 1
            by_type[path.parent.name] = by_type.get(path.parent.name, 0) + 1
        return {"ready": ready, "blocked": len(bad), "by_type": by_type}
    except Exception:                                       # noqa: BLE001
        return {"ready": 0, "blocked": 0, "by_type": {}}


def queue_shelve(path) -> None:
    """Move a produced script to _done/. ONLY on success.

    Shelved, not deleted: the deletion would be the only evidence the script
    ever ran. Called after the video exists, so a failed job leaves the script
    in the queue and the next run picks it up again.
    """
    try:
        _queue_guard().main(["--done", str(path)])
        # The shelf moved a file the cached audit still describes.
        _AUDIT_CACHE.update(at=0.0, bad=None)
    except Exception:                                       # noqa: BLE001
        logger.warning("queue: could not shelve %s", path, exc_info=True)


# ============== THE BATCH QUEUE, ON DISK ==============
#
# It used to live in st.session_state and be drained in one loop:
#
#     while st.session_state.queue_items:
#         start_generation(st.session_state.queue_items.pop(0))
#
# which spawned a daemon thread per item. They serialise on _RENDER_LOCK, so
# one rendered and the rest waited -- and ANY restart of the Streamlit process
# killed every waiting thread at once while clearing the session that held the
# queue. The owner saw exactly that: the first one or two appear, the rest
# vanish. Five jobs sat "active" with their heartbeats frozen for six hours.
#
# So the queue outlives the process, the way the job ledger already does, and
# ONE item is in flight at a time. A restart loses the running render and
# nothing else; the rest are still on disk and resume.

BATCH_QUEUE_PATH = OUTPUT_DIR / "batch_queue.json"
_BATCH_LOCK = _ds.BATCH_LOCK


def batch_queue() -> list:
    """The items still waiting, oldest first."""
    with _BATCH_LOCK:
        try:
            with open(BATCH_QUEUE_PATH, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return []
    return data.get("items", []) if isinstance(data, dict) else []


def _write_batch_queue(items: list) -> None:
    with _BATCH_LOCK:
        BATCH_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BATCH_QUEUE_PATH, "w", encoding="utf-8") as handle:
            json.dump({"items": items}, handle, ensure_ascii=False, indent=2)


def batch_add(items: list) -> int:
    with _BATCH_LOCK:
        current = batch_queue() + list(items)
        _write_batch_queue(current)
        return len(current)


def batch_clear() -> None:
    _write_batch_queue([])


def batch_take():
    """Remove and return the next item, or None. Persisted immediately.

    Popped under the lock and written back before the job starts, so a crash
    between the two loses one item rather than replaying it forever.
    """
    with _BATCH_LOCK:
        items = batch_queue()
        if not items:
            return None
        nxt = items.pop(0)
        _write_batch_queue(items)
        return nxt


def batch_advance() -> str:
    """Start the next queued item if nothing is rendering. Returns its job id.

    Called when a job finishes AND from the Queue page, so the chain survives a
    restart: the page finds a non-empty queue with no active job and restarts
    it. One driver would have been enough until the process died.
    """
    if get_active_jobs():
        return ""
    nxt = batch_take()
    if not nxt:
        return ""
    logger.info("batch: starting %s (%d left)", nxt.get("type"),
                len(batch_queue()))
    return start_generation(nxt.get("type"), nxt.get("category"),
                            nxt.get("topic"))


def scheduler_batch(types: list, count: int) -> list:
    """The batch-queue items for «Generate Batch Now»: `count` videos cycling through `types`."""
    return [{"type": types[i % len(types)], "category": None, "topic": None} for i in range(count)]


def batch_estimate_usd(count: int, costs_dir: Path = None) -> Optional[float]:
    """count × the mean cost per video in output/costs, or None when nothing was recorded."""
    from cost_tracker import per_video_costs, video_cost_stats
    stats = video_cost_stats(per_video_costs(costs_dir or OUTPUT_DIR / "costs"))
    return round(count * stats["mean_usd"], 2) if stats["videos"] else None


def get_active_jobs() -> list:
    return load_jobs().get("active", [])



# ============== PIPELINE WITH PROGRESS TRACKING ==============

def run_pipeline_with_tracking(job_id: str, video_type: str, category: str = None,
                                topic_name: str = None, script_data: dict = None,
                                use_queue: bool = True,
                                background: str = None, dry_run: bool = False,
                                profile_name: str = None) -> dict:
    """Generate one video through the shared pipeline (src/pipeline.py).

    Same TTS dispatch, same merge and same renderer as main.py — only the
    output layout differs (videos land in output/pending/<type>/ for review).

    Args:
        script_data:  Use this script instead of generating one with the model (OpenRouter).
        background:   Preset name, or None to let the profile's resolver pick.
        dry_run:      Generate the script, resolve and log the TTS plan, then
                      stop. Skips the TTS call and the render. NOT free: the
                      script call (OpenRouter) happens before this takes effect.
        profile_name: Audience profile ("adults", "children"), or None for the
                      config default.

    THREE OF THESE FIVE WERE ALREADY HERE AND UNREACHABLE. `background` and
    `dry_run` were parameters no caller ever set, and resolve_profile has
    always taken a name that this function never passed — so `children` was
    configured, tested and impossible to select. The signature is the door;
    it was narrower than the engine behind it.
    """
    result = {"success": False, "video_path": None, "error": None}

    # Bound before the try so the failure paths can read them.
    queued_path = None
    script_path = None
    video_path = None
    # NOT video_path. video_path is the render TARGET and is bound before
    # render_video runs, so a killed or timed-out ffmpeg that left a partial
    # file behind made `video_path.exists()` true and the release below
    # decided a video had been produced. This is bound only once the render
    # returned, so "an mp4 survived the failure" means a finished mp4.
    rendered_video = None
    stage_path = None                 # the render while it is not whole yet
    stage_seconds = {}                # where the job's time went, per stage
    _t0 = time.monotonic()

    def _stage(name):
        nonlocal _t0
        now = time.monotonic()
        stage_seconds[name] = round(now - _t0, 1)
        _t0 = now

    def _cut_on_failure(error_msg):
        """Name the stage the time went to, and move an unfinished render to _cut/."""
        failed = next((n for n in ("script", "tts", "clips", "frames+encode", "gate+outro")
                       if n not in stage_seconds), "after gate")
        _stage(f"{failed} (failed)")
        logger.error("job %s stage seconds: %s", job_id, stage_seconds)
        if stage_path is not None:
            move_to_cut([stage_path], f"job {job_id}: {error_msg[:500]}\nstage seconds: {stage_seconds}",
                        stage_path.stem)

    # OPENED HERE, NOT WHEN THE VIDEO GETS ITS NAME. The script is paid for
    # before unique_name exists; a tracker reset after generate_script left
    # that cost on the previous video's already-saved tracker, and it was
    # never written. Named by job until the artifact name is known.
    tracker = reset_tracker(video_id=f"job_{job_id}")

    try:
        update_job(job_id, status="running", step_number=1,
                   current_step="Selecting topic...", progress=5)

        # Audience profile (voice, backgrounds, topics) — same resolution as the CLI
        profile = pipeline.resolve_profile(profile_name)
        update_job(job_id, profile=profile.get("name"))

        if script_data is not None:
            topic_name = topic_name or script_data.get("word") or script_data.get("topic") or "script"
        elif category and topic_name:
            # An explicit pick is still a pairing, and a bad pairing ships a
            # false lesson rather than an ugly one. Refusing is loud and
            # fixable; the video is not.
            from type_categories import resolve as _eligible_categories, NoEligibleCategory

            allowed = _eligible_categories(
                video_type, profile.get("content", {}).get("categories"))
            if category not in allowed:
                raise NoEligibleCategory(
                    f"a {video_type!r} video cannot be about a {category!r} "
                    f"topic. Allowed for this type and audience: "
                    f"{', '.join(allowed)}. Change the category, or widen the "
                    f"type's list in config.yaml under type_categories.")
            topic = find_topic(category, topic_name)
        else:
            # VIDEO TYPE AND TOPIC CATEGORY WERE INDEPENDENT DRAWS HERE.
            # type_categories.resolve was written for exactly this and had one
            # caller, studio/legacy_pipeline.py:136 — the --batch door. On this
            # door nothing constrained the pairing, and the result is on disk:
            # of the 19 pronunciation scripts under output/scripts/, ZERO drew
            # from content/topics/pronunciation.json. They drew from social,
            # false_friends, business, cultural... A `business` topic reaching
            # the pronunciation prompt is how "Job Interviews: Describing
            # experience" got a phonetic transcription whose "correct" answer
            # was the mistake the same script names.
            #
            # It intersects with the profile's own list rather than replacing
            # it: the profile says who the video is for, this says what the
            # type can teach. Both must hold. NoEligibleCategory is raised, not
            # defaulted — an unconstrained draw is the bug.
            from type_categories import resolve as _eligible_categories

            allowed = _eligible_categories(
                video_type, profile.get("content", {}).get("categories"))
            category, topic = get_random_topic(allowed_categories=allowed)
            topic_name = (topic.get("english") or topic.get("topic") or topic.get("wrong")
                         or topic.get("word") or topic.get("sentence") or str(topic))

        update_job(job_id, category=category, topic=topic_name,
                   current_step=f"Topic: '{topic_name}'", progress=10)

        # Step 2: the script -- from the queue if there is one, else the model (OpenRouter)
        if script_data is None and use_queue:
            picked = queue_pick(video_type)
            if picked:
                queued_path, script_data = picked
                topic_meta = script_data.get("_meta") or {}
                category = topic_meta.get("category") or category
                # video_title BEFORE the drawn topic_name. Only the
                # pronunciation queue carries `word` and only vocabulary
                # carries `title`, so educational / quiz / true_false /
                # fill_blank fell straight through to the topic the random
                # draw had picked a moment earlier — an unrelated subject
                # that then named the output file AND seeded the Pexels
                # footage query for a script about something else.
                topic_name = (script_data.get("word") or script_data.get("title")
                              or script_data.get("video_title")
                              or queued_path.stem)
                update_job(job_id, step_number=2, category=category,
                           topic=topic_name, script_source="queue",
                           current_step=f"Queued script: {queued_path.name}",
                           progress=15)

        if script_data is None and use_queue and queue_pick() is not None:
            # NO SILENT FALLBACK WHILE THE QUEUE HAS ANYTHING. The control
            # says "use a queued script"; quietly calling the script model instead
            # contradicts it, and with no working key it turned an empty type
            # into a 401 the owner had to decode on a route built to need no
            # API at all.
            #
            # The `queue_pick() is not None` guard is the honest edge: a queue
            # that is empty ALTOGETHER has no promise to keep, and the page
            # already unticks the box in that case. This only fires when other
            # types have scripts and THIS one has run out.
            raise RuntimeError(
                f"no queued script left for {video_type!r}, though the queue "
                f"still has others. Add more of this type, or turn off 'Use a "
                f"queued script' to write one with the model (OpenRouter).")

        if script_data is None:
            # script_source was "gpt" before 2026-10-27; nothing filters on it
            update_job(job_id, step_number=2, script_source="openrouter",
                       current_step="Escribiendo el guion con el modelo (OpenRouter)...", progress=15)
            script_data = generate_script(category, topic, video_type)

        # ONE JOB PER SCRIPT. Another dashboard (or a pick that raced this
        # one) may hold the same topic_id + type; two renders of bv010 is how
        # a second copy of a topic reached YouTube.
        key = script_key(script_data)
        if rendering_job_for(key, exclude=job_id):
            queued_path = None            # not ours to release or shelve
            raise AlreadyRendering(f"Ya se está renderizando {key.split(':')[0]}")
        if key:
            update_job(job_id, script_key=key)

        import re as _re
        output_name = _re.sub(r'[^\w\-]', '_', topic_name).strip('_').lower()
        output_name = _re.sub(r'_+', '_', output_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_name = f"{output_name}_{timestamp}"

        # Cost tracking for this video (TTS now runs in-process, so the
        # tracker survives long enough to be saved). Renamed, not reset: the
        # script model's call is already on it.
        if tracker is not None:
            tracker.rename(unique_name)

        # The short «¿Cómo se dice…?» A/B: every other new topic is voiced with 5 words, no recap
        length_ab_record = None
        if not dry_run:
            import length_ab
            length_ab_record = length_ab.assign(unique_name, script_data)
            if length_ab_record:
                script_data = length_ab.apply(script_data, length_ab_record["variant"])

        script_dir = SCRIPTS_DIR / video_type
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / f"{unique_name}.json"

        with open(script_path, 'w', encoding='utf-8') as f:
            json.dump(script_data, f, ensure_ascii=False, indent=2)

        update_job(job_id, current_step=f"Script generated", progress=30)
        _stage("script")

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
            # A DRY RUN PRODUCED NO VIDEO, so it must not leave the history
            # mark either. The output/scripts/ copy is written above, `_meta`
            # and all, and topic_history counts that copy — so a dry run of a
            # queued script made queue_guard refuse the original ALREADY
            # PRODUCED forever, while the script itself was never shelved.
            # Same release the failure paths do, for the same reason.
            _release_queued_script(queued_path, script_path)
            update_job(job_id, current_step="Dry run complete", progress=100)
            complete_job(job_id, success=True)
            result["success"] = True
            result["dry_run"] = True
            return result

        update_job(job_id, current_step="Audio generated", progress=55)
        _stage("tts")

        pipeline.merge_script_into_tts(script_data, json_path)

        # Step 4: Render video
        update_job(job_id, step_number=4,
                   current_step="Rendering video...", progress=60)

        video_path = PENDING_DIR / video_type / f"{unique_name}.mp4"
        # RENDERED ELSEWHERE, MOVED IN WHEN WHOLE (STEP 59 §6). A render killed
        # at its 1200 s limit left a 46 s bv010 in pending/ with no sidecar; it
        # was approved and uploaded. Only a finished, measured, gated file with
        # its sidecar beside it ever gets the pending/ name.
        stage_path = RENDERING_DIR / video_type / f"{unique_name}.mp4"
        update_job(job_id, stage_path=str(stage_path))

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

        # dest_dir AND duration, both of them.
        #
        # pipeline.py:194 guards the clip tier with `if topic and dest_dir`.
        # This call passed neither, so tier 3 was never evaluated on the
        # dashboard and every video fell to tier 4, the generated image. It is
        # not a preference that lost — it is a branch that was never reached.
        # Measured over output/generation_jobs.json: 50 jobs, 0 with clips,
        # $0.902 spent on stills the free tier would have replaced.
        #
        # duration decides how much footage to fetch. Without it the tier uses
        # a 30s default, which under-fetches for anything in the upper half of
        # the duration band and makes the playlist loop.
        clips_dir = CLIPS_DIR / unique_name
        tts_duration = None
        footage_themes = []
        artifact_theme = ""
        try:
            with open(json_path, encoding="utf-8") as _f:
                _artifact = json.load(_f)
            artifact_theme = str(_artifact.get("theme") or "")
            tts_duration = float(_artifact.get("duration") or 0) or None
            from topic_clips import footage_themes as _themes
            footage_themes = _themes(_artifact)            # STEP 77 §6: the theme before the category
        except Exception:                                       # noqa: BLE001
            # A missing duration costs a shorter playlist, never the video.
            logger.warning("background: could not read the duration from %s; "
                           "the clip tier will use its own default", json_path)

        # THE V2 SKIP AND THE MISSING RECORD BOTH MOVED INTO THE RESOLVER.
        #
        # This function used to hold both: it short-circuited v2 itself, and
        # it patched up the record when tier 1 returned without writing one.
        # Both fixes were in the CALLER, so studio/legacy_pipeline — which
        # never passes on_record at all — still had both defects. The
        # resolver now guarantees a record on every path, refuses rather
        # than substituting a flat preset, and skips the fetch for v2, so
        # every door gets it once.
        # STEP 80 §5: every other «Cómo se dice» gets the topic's AI clip behind the page (A/B)
        background_ab = None
        if not background and not dry_run:
            import ai_background
            background_ab = ai_background.assign(unique_name, video_type, artifact_theme or topic_name or category or "")
            background = background_ab["background"] or background
        resolved_background = pipeline.resolve_background(
            profile, background,
            topic=topic_name, category=category,
            dest_dir=clips_dir,
            duration=tts_duration,
            on_record=_record_background,
            themes=footage_themes,
        )
        update_job(job_id, current_step=f"Rendering video ({resolved_background})...")
        _stage("clips")

        pipeline.render_video(
            audio_path, json_path, stage_path,
            video_type=video_type,
            background=resolved_background,
            timeout=pipeline.render_timeout(video_type),
        )
        _stage("frames+encode")
        from qa_gate import probe_duration
        measured = probe_duration(str(stage_path))
        if tts_duration and (measured is None or abs(measured - tts_duration) > 0.5):
            raise pipeline.PipelineError(
                f"cut render: the video is {measured}s, the timeline {tts_duration:.2f}s")
        rendered_video = stage_path

        update_job(job_id, current_step="Video rendered", progress=90)

        # FINALISE: gate, then outro. Neither ran on this path before — the
        # gate was built in Step 2, flipped to BLOCKING in Step 3, and the
        # outro added in 4a, and finalize_video had zero callers, so the
        # dashboard published ungated video with no Learning Routes CTA too.
        # One function, both paths.
        fin = pipeline.finalize_video(stage_path, json_path,
                                      variant_seed=unique_name)
        _stage("gate+outro")
        result["gate"] = fin.get("gate")
        result["outro_appended"] = fin.get("outro_appended")
        result["blocking_flags"] = fin.get("blocking_flags", [])
        result["outro_variant"] = fin.get("outro_variant")
        if fin.get("video"):
            stage_path = Path(fin["video"])

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
            "deesser": fin.get("deesser"),              # STEP 80 §00: the voice's de-esser measure
        }
        update_job(job_id, current_step=f"Gate: {fin.get('gate')}", progress=95,
                   **verdict_record)

        if tracker and tracker.entries:
            tracker.save()

        # Save metadata
        video_path.parent.mkdir(parents=True, exist_ok=True)
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
                "background_ab": background_ab,             # STEP 80 §5: «ia» or «stock», and why
                "length_ab": length_ab_record,              # «short» or «long», and why (length_ab)
                # What this video cost, OpenAI vs ElevenLabs, as of the render.
                # The ledger in output/costs/ stays the authoritative record.
                "cost": tracker.summary() if tracker is not None else None,
                "script_data": script_data,
                # STEP 80 §1b: title, description and hashtags, generated at render time
                "metadata": render_metadata(script_data, video_type, category),
                "stage_seconds": stage_seconds,
                "created_at": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)

        # The sidecar exists, so now the video may have its pending/ name.
        os.replace(stage_path, video_path)
        rendered_video = video_path
        logger.info("job %s stage seconds: %s", job_id, stage_seconds)

        result["success"] = True
        result["video_path"] = str(video_path)
        complete_job(job_id, success=True, video_path=str(video_path))

        # AFTER the video exists, never before. A job that fails leaves its
        # script in the queue so the next run picks it up again; shelving at
        # pick time would burn a script on every crash.
        if queued_path is not None:
            queue_shelve(queued_path)

    except pipeline.PipelineError as e:
        # Already carries the renderer's own output — a Python traceback of the
        # subprocess wrapper would only bury it.
        error_msg = str(e)
        result["error"] = error_msg
        complete_job(job_id, success=False, error=error_msg[:2000])
        logger.error("[Pipeline ERROR]: %s", error_msg)
        _cut_on_failure(error_msg)
        _release_queued_script(queued_path, script_path, rendered_video)
    except AlreadyRendering as e:
        result["error"] = str(e)
        complete_job(job_id, success=False, error=str(e))
        logger.warning("job %s refused: %s", job_id, e)
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        result["error"] = error_msg
        complete_job(job_id, success=False, error=error_msg[:2000])
        logger.error("[Pipeline ERROR]: %s", error_msg)
        _cut_on_failure(str(e))
        _release_queued_script(queued_path, script_path, rendered_video)
    finally:
        # A failed run spent money too, and a ledger fed only by successes
        # under-counts exactly while iterating on a broken pipeline. save()
        # writes only what is not on disk yet, so the success path's own
        # save above cannot be doubled here.
        try:
            if tracker is not None:
                tracker.save()
        except Exception:                                   # noqa: BLE001
            logger.exception("could not persist the cost ledger")

    return result


def _release_queued_script(queued_path, script_path, video_path=None) -> None:
    """Undo the history mark a FAILED queued job left behind.

    The comment above the shelve promises that "a job that fails leaves its
    script in the queue so the next run picks it up again". It did not: the
    script is copied into output/scripts/ before TTS runs, `_meta` and all,
    and topic_history counts that copy as a produced video. On the next pick
    queue_guard flags the very same file ALREADY PRODUCED and refuses it
    forever — so one transient TTS or render failure permanently burned a
    hand-written script.

    Removing the copy on failure is what makes the promise true. Only for a
    queued script, and only on failure: a model-written script is the only
    record of what was generated and is kept either way.

    NOT WHEN AN MP4 SURVIVED THE FAILURE. render_video can succeed and the
    step after it still raise — finalize_video runs the gate and appends the
    outro through ffmpeg, and the metadata write follows it. topic_history
    counts SCRIPT json, never mp4s, so removing the copy while the video sits
    in output/pending/ un-marks a topic that HAS been produced, and the guard
    then re-offers the script and makes the same video twice. When the render
    got that far the mark is correct and stays; the script is burned, which a
    person can undo, whereas a duplicate reaches the channel.
    """
    if queued_path is None or script_path is None:
        return
    if video_path is not None and Path(video_path).exists():
        logger.info("queue: %s failed after its video was rendered — the "
                    "history mark stays, because %s is on disk",
                    queued_path.name, video_path)
        return
    try:
        Path(script_path).unlink(missing_ok=True)
        _AUDIT_CACHE.update(at=0.0, bad=None)
        logger.info("queue: %s failed — its output/scripts copy was removed "
                    "so the guard will offer it again", queued_path.name)
    except Exception:                                       # noqa: BLE001
        logger.warning("queue: could not un-mark %s after a failure",
                       queued_path, exc_info=True)


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
_RENDER_LOCK = _ds.RENDER_LOCK

_WORKERS: list = _ds.WORKERS

#: How often a running job stamps its row. Small enough that a dead worker is
#: obvious, large enough that it is not a write loop.
HEARTBEAT_SEC = 10


def start_series_generation(style: Optional[str] = None, level: Optional[str] = None) -> str:
    """STEP 78 §7: one «Hecho con Claude» Short in the background (series.render_one), tracked
    in the same job ledger as every other video."""
    job_id = create_job("hecho_con_claude", style, level)

    def _worker():
        log_path = attach_run_log(f"job-{job_id}")
        update_job(job_id, log_path=str(log_path))
        try:
            # STEP 79 §00: the series click may voice one script, within the plan.
            picked = series.pick(style, level)
            chars = voice_credits.script_chars(picked[1] if picked else None) or voice_credits.cap_chars()
            with voice_credits.panel_voice(chars):
                result = series.render_one(style, level, progress=lambda msg: update_job(job_id, current_step=msg))
            ok = result["gate"] == "PASS"
            complete_job(job_id, ok, result["video"],
                         None if ok else "quality gate: " + ", ".join(result["blocking_flags"]))
        except Exception as exc:                            # noqa: BLE001 — the job row says why
            logger.exception("series job %s failed", job_id)
            complete_job(job_id, False, None, str(exc))

    threading.Thread(target=_worker, daemon=True).start()
    return job_id


def start_generation(video_type: str, category: str = None, topic_name: str = None,
                     **kwargs) -> str:
    """Queue one video and return its job id immediately.

    The job appears in the ledger before this returns, so the very next page
    draw shows it as active. A script another job holds is refused with
    AlreadyRendering, before any job exists.
    """
    key = script_key(kwargs.get("script_data"))
    if rendering_job_for(key):
        raise AlreadyRendering(f"Ya se está renderizando {key.split(':')[0]}")
    job_id = create_job(video_type, category, topic_name)
    if key:
        update_job(job_id, script_key=key)

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
            # STEP 79 §00: this click is the only thing that may spend voice, within the plan.
            chars = voice_credits.script_chars(kwargs.get("script_data")) or voice_credits.cap_chars()
            with voice_credits.panel_voice(chars), _RENDER_LOCK:
                run_pipeline_with_tracking(job_id, video_type, category,
                                           topic_name, **kwargs)
        except voice_credits.VoiceRefused as refused:
            complete_job(job_id, success=False, error=str(refused))
        except Exception:                                   # noqa: BLE001
            # run_pipeline_with_tracking handles its own errors; this is the
            # last resort so a worker cannot die leaving the row active.
            logger.exception("Generation worker crashed (job %s)", job_id)
            complete_job(job_id, success=False,
                         error="Generation worker crashed — see dashboard logs")
        finally:
            stop_beating.set()
            detach_run_log(log_path)
            # THE CHAIN. One item in flight at a time: the next starts only
            # when this one finishes, so nothing sits in a thread waiting for
            # a lock where a restart can kill it.
            try:
                batch_advance()
            except Exception:                               # noqa: BLE001
                logger.exception("batch: could not start the next item")

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
    for job in orphans:
        if job.get("stage_path"):
            move_to_cut([job["stage_path"]], job["error"], Path(job["stage_path"]).stem)

    logger.info("Reaped %d orphaned job(s) from a previous dashboard process",
                len(orphans))
    return len(orphans)


def render_metadata(script: Optional[dict], video_type: str, category: str = "") -> Optional[dict]:
    """STEP 80 §1b: the video's metadata, built once at render time (never blocks the render)."""
    try:
        import video_metadata
        return video_metadata.build(script or {}, video_type, category or "")
    except Exception:                                       # noqa: BLE001 — a render must not fail on copy
        logger.exception("render metadata failed; the upload page builds it")
        return None
