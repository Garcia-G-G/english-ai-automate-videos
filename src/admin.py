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
from datetime import datetime, timedelta
from typing import Optional

import video_types

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
    list_categories,
    load_topics,
)

# STEP 77 §0: what the panel offers — the notebook types only (the old neon renderers stay
# reachable from the CLI until STEP 79).
from video_types import PANEL_TYPES  # noqa: E402
import series  # noqa: E402
import voice_credits  # noqa: E402

import topic_history


# ============== WHAT THE DASHBOARD IS ALLOWED TO OFFER ==============
#
# UNA CAPACIDAD SIN PUERTA ES UNA CAPACIDAD QUE NO EXISTE.
#
# Every list below is READ from the place the engine reads it, never restated
# here. That is not tidiness, it is the actual defect being fixed: the
# scheduler offered four of the six video types because the UI wrote the list
# out by hand, and fill_blank and pronunciation could not be produced from the
# unattended batch at all. A second hand-written list under "5 of Each Type"
# queued three types and reported fifteen videos.
#
# A hand-written copy in the UI cannot be caught by a test of the engine,
# because the engine is correct. So the copies are gone, and
# test_dashboard_doors asserts by AST that none comes back.


#: Display names for the video types. NOT a gate on what may be offered —
#: unknown types get a readable label from their own name, so adding a
#: seventh type to VIDEO_TYPES makes it appear on every screen with no edit
#: here. A dict that had to be extended per type would be the same defect one
#: layer down.
_TYPE_LABELS = {
    "true_false": "True/False",
}


def type_label(video_type: str) -> str:
    """Human label for a video type, for checkboxes and selectboxes: the type's own panel name
    («Elige la correcta», STEP 80 §3), else the label map, else the key made readable."""
    import video_types
    if video_type == series.PANEL_LABEL:                  # the series is offered under its own name
        return video_type
    own = (video_types.TYPES.get(video_type) or {}).get("dashboard")
    return own or _TYPE_LABELS.get(video_type, str(video_type).replace("_", " ").title())


def scheduler_default_types() -> list:
    """Types the unattended batch offers: the panel's (notebook) types, from the one list."""
    from video_types import PANEL_TYPES
    return list(PANEL_TYPES)


def _declared_profiles() -> list:
    """Every audience profile named in config.yaml, resolvable or not."""
    from profiles import load_profiles

    # load_profiles returns {"default": <name>, "profiles": {...}} — the
    # names are one level down, and the default is guaranteed to be among
    # them even when config.yaml declares no profiles section at all.
    loaded = load_profiles()
    names = set((loaded.get("profiles") or {}).keys())
    names.add(loaded.get("default") or "adults")
    return sorted(names)


def _profile_status() -> tuple:
    """(available, {name: why not}) — resolved by actually resolving them.

    A SELECTBOX IN FRONT OF A BROKEN PATH IS WORSE THAN NO SELECTBOX, and
    `children` is exactly that today: it is declared in config.yaml with its
    own audio settings and its own topic categories, and it CANNOT BE
    RESOLVED, because its voice_id is the literal "default" and
    audiences._validated_voice rejects that. Offering it would raise
    InvalidAudienceProfile after the operator had already picked a topic.
    Set CHILDREN_ELEVENLABS_VOICE_ID (or a real voice_id under
    profiles.children.audio in config.yaml) and it appears here by itself.
    """
    # get_active_profile, NOT pipeline.resolve_profile: the latter calls
    # apply_profile_env and pins os.environ["VIDEO_PROFILE"], so probing
    # every declared profile with it would leave the process configured as
    # whichever one happened to be tried last. A probe must not change the
    # thing it is probing.
    from profiles import get_active_profile

    available, blocked = [], {}
    for name in _declared_profiles():
        try:
            get_active_profile(name)
        except Exception as exc:                                # noqa: BLE001
            blocked[name] = str(exc)
        else:
            available.append(name)
    return available, blocked


def available_profiles() -> list:
    """Audience profiles that actually resolve — what the UI may offer.

    pipeline.resolve_profile(name) has always taken a name; admin called it
    with none, so no profile but the config default was ever selectable.
    """
    return _profile_status()[0]


def unavailable_profiles() -> dict:
    """{name: reason} for declared profiles that cannot be resolved.

    Shown on the page rather than swallowed: "children unavailable" with no
    reason is the same dead end as no control at all.
    """
    return _profile_status()[1]


def topic_memory_report(allowed_categories=None) -> dict:
    """What topic_history already computes, shaped for a screen.

    coverage() was written for exactly this and its only caller was its own
    test — the memory was computed and never rendered. `percent_used` is
    derived here rather than stored so the screen cannot go stale, and the
    repeats list arrives worst-first because it is the part that answers
    "why do I keep seeing the same video".
    """
    report = dict(topic_history.coverage(allowed_categories))
    total = report.get("total") or 0
    report["percent_used"] = (100.0 * report.get("used", 0) / total) if total else 0.0
    return report


# The job engine lives in src/jobs.py so a page edit does not reload a running
# render's code. Re-exported because the pages and the tests reach it as admin.X.
import dashboard_state as _ds  # noqa: E402
from jobs import (  # noqa: E402,F401
    OUTPUT_DIR, SCRIPTS_DIR, AUDIO_DIR, VIDEO_DIR, PENDING_DIR, CLIPS_DIR, APPROVED_DIR,
    RENDERING_DIR, CUT_DIR, REJECTED_DIR, UPLOADED_DIR, JOBS_FILE, _JOBS_LOCK,
    load_jobs, save_jobs, _proc_start, _OWNER_PID, _OWNER_STARTED, _owner_alive,
    touch_heartbeat, create_job, update_job, complete_job, _queue_guard, _AUDIT_CACHE,
    _AUDIT_TTL, _queue_bad, AlreadyRendering, script_key, rendering_job_for,
    move_to_cut, queue_order, next_best, queue_pick, queue_status, queue_shelve,
    BATCH_QUEUE_PATH, _BATCH_LOCK, batch_queue, _write_batch_queue, batch_add,
    batch_clear, batch_take, batch_advance, scheduler_batch, batch_estimate_usd,
    get_active_jobs, run_pipeline_with_tracking, _release_queued_script, _RENDER_LOCK,
    _WORKERS, HEARTBEAT_SEC, start_series_generation, start_generation,
    wait_for_generations, reap_orphaned_jobs, render_metadata,
)


# ============== HELPER FUNCTIONS ==============


#: What a page shows for a sidecar that is not valid JSON (STEP 75 §3).
DAMAGED = "archivo dañado"


def read_sidecar(meta_file: Path):
    """(meta, problem): problem is None, or «archivo dañado: name (why)» instead of a crash."""
    try:
        meta = json.loads(Path(meta_file).read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            raise ValueError("not an object")
        return meta, None
    except (OSError, ValueError) as e:
        logger.warning("sidecar %s unreadable: %s", meta_file, e)
        return {}, f"{DAMAGED}: {Path(meta_file).name} ({type(e).__name__})"


def get_pending_videos() -> list:
    videos = []
    if not PENDING_DIR.exists():
        return videos
    for type_dir in PENDING_DIR.iterdir():
        if type_dir.is_dir():
            for video_file in type_dir.glob("*.mp4"):
                meta_file = video_file.with_suffix('.json')
                if not meta_file.exists():
                    # STEP 59 §6: no sidecar means the job never finished it.
                    logger.warning("review: %s has no sidecar; not shown", video_file.name)
                    continue
                meta, damaged = read_sidecar(meta_file)
                videos.append({
                    "path": video_file,
                    "type": type_dir.name,
                    "name": video_file.stem,
                    "meta": meta,
                    "damaged": damaged,
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
                meta, damaged = read_sidecar(meta_file) if meta_file.exists() else ({}, None)
                published = find_by_artifact(video_file.stem)
                videos.append({
                    "path": video_file,
                    "type": type_dir.name,
                    "name": video_file.stem,
                    "meta": meta,
                    "damaged": damaged,
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


def render_meta_queue(st_module) -> None:
    """The Instagram/Facebook queue: status per platform, permalink or reason."""
    from publishers import schedule
    try:
        cfg = schedule.settings()
        rows = schedule.status_rows(cfg)
    except (OSError, ValueError) as e:
        st_module.error(f"Cola Instagram/Facebook ilegible: {e}")
        return
    with st_module.expander(f"📅 Cola Instagram/Facebook ({len(rows)}) · franjas {', '.join(cfg['slots'])}",
                            expanded=False):
        # The same report as `meta_publish.py setup-check`, on demand: it calls Meta.
        if st_module.button("Comprobar configuración de Meta", key="meta_setup_check"):
            from publishers.setup import report_lines, setup_report
            try:
                st_module.session_state["meta_setup"] = report_lines(setup_report())
            except Exception as exc:                      # noqa: BLE001
                st_module.session_state["meta_setup"] = [f"✗ setup-check falló: {exc}"]
        for line in st_module.session_state.get("meta_setup", []):
            (st_module.error if line.startswith("✗") else st_module.write)(line)
        if not rows:
            st_module.caption("Vacía. Encola con `python3 tools/meta_publish.py enqueue --approved` "
                              "o activa `meta_publish.auto_enqueue_on_approve`.")
            return
        st_module.dataframe(
            [{"vídeo": r["artifact"], **{p: r[p]["status"] for p in cfg["platforms"]},
              **{f"{p} enlace / motivo": r[p].get("url") or r[p].get("detail") or "" for p in cfg["platforms"]}}
             for r in rows],
            width="stretch", hide_index=True)


def approve_video(video_path: Path):
    video_type = video_path.parent.name
    dest_dir = APPROVED_DIR / video_type
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(video_path), str(dest_dir / video_path.name))
    meta_path = video_path.with_suffix('.json')
    if meta_path.exists():
        shutil.move(str(meta_path), str(dest_dir / meta_path.name))
    from publishers import schedule
    if schedule.settings()["auto_enqueue_on_approve"]:
        try:
            schedule.enqueue(dest_dir / video_path.name)
        except (OSError, ValueError):
            logger.exception("could not queue %s for Meta publishing", video_path.name)


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


def _guard_decide(artifact: str, platform: str, manager=None, **content):
    """Ask the idempotency guard before uploading. See upload_guard."""
    from upload_guard import decide
    return decide(artifact, platform, manager=manager, **content)


def save_sidecar_metadata(video: dict, metadata: dict) -> None:
    """Write the edited metadata into the video's sidecar, so «Subir» publishes what was reviewed."""
    path = Path(video["path"]).with_suffix(".json")
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data["metadata"] = metadata
    tmp = path.with_suffix(".json.part")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    (video.setdefault("meta", {}) or {})["metadata"] = metadata


def review_metadata_editor(video: dict) -> None:
    """«Revisar» (STEP 80 §1b): title, description and hashtags already filled in by the render,
    editable, with «Usar alternativa», «Regenerar» and «Guardar en el vídeo»."""
    meta = (video.get("meta") or {}).get("metadata")
    script = script_for_upload(video)
    if not meta:
        meta = render_metadata(script, video["type"], (script.get("_meta") or {}).get("category", "")) or {}
    if not meta.get("title"):
        return
    name = video["name"]
    keys = {k: f"rv_{k}_{name}" for k in ("title", "desc", "tags")}
    staged = st.session_state.pop(f"rv_pending_{name}", None)
    if keys["title"] not in st.session_state or staged:
        src = staged or {"title": meta["title"], "desc": meta.get("description", ""),
                         "tags": " ".join((meta.get("hashtags") or {}).get("youtube") or [])}
        for k in keys:
            st.session_state[keys[k]] = src[k]
    with st.expander("📝 Título, descripción y hashtags", expanded=False):
        st.caption("Generados al renderizar" + (" con IA" if meta.get("source") == "llm" else " (plantilla)"))
        st.text_input("Título", key=keys["title"])
        st.text_area("Descripción", key=keys["desc"], height=160)
        st.text_input("Hashtags (YouTube)", key=keys["tags"])
        for k, alt in enumerate(meta.get("alternatives") or []):
            if st.button(f"Usar alternativa: {alt}", key=f"rv_alt_{k}_{name}"):
                st.session_state[f"rv_pending_{name}"] = {"title": alt, "desc": st.session_state[keys["desc"]],
                                                          "tags": st.session_state[keys["tags"]]}
                st.rerun()
        c1, c2 = st.columns(2)
        if c1.button("🔁 Regenerar", key=f"rv_regen_{name}", help="Una llamada a la IA para YouTube"):
            try:
                from metadata_generator import regenerate_for_platform
                r = regenerate_for_platform(script, "youtube", video["type"])
                st.session_state[f"rv_pending_{name}"] = {
                    "title": r.get("title", ""), "desc": r.get("description", ""),
                    "tags": " ".join(f"#{t.lstrip('#')}" for t in r.get("hashtags", []))}
                st.rerun()
            except Exception as e:                          # noqa: BLE001 — shown, not raised
                st.error(f"No se pudo regenerar: {e}")
        if c2.button("💾 Guardar en el vídeo", key=f"rv_save_{name}"):
            from metadata_generator import metadata_problems
            title, desc = st.session_state[keys["title"]].strip(), st.session_state[keys["desc"]].strip()
            problems = metadata_problems(title) + metadata_problems(desc)
            if problems:
                st.error("No se guardó: " + ", ".join(problems))
            else:
                tags = st.session_state[keys["tags"]].split()
                hashtags = dict(meta.get("hashtags") or {})
                hashtags["youtube"] = tags
                save_sidecar_metadata(video, {**meta, "title": title, "description": desc, "hashtags": hashtags,
                                              "source": "edited"})
                st.success("Guardado: «Subir» publicará esto.")


def illustrations_panel() -> None:
    """«N ilustraciones nuevas · $X» for the next queued «Cómo se dice», and the click that draws
    them (OpenRouter, under the caps; every word is drawn once and reused in every video)."""
    import illustrations
    picked = queue_pick("how_do_you_say")
    if not picked:
        return
    path, script = picked
    words = illustrations.words_of(script)
    need = illustrations.missing(words)
    if not need:
        st.caption(f"🖼️ Las {len(words)} ilustraciones de `{path.name}` ya están en la biblioteca.")
        return
    cost = illustrations.estimate_usd(len(need))
    st.caption(f"🖼️ {len(need)} ilustraciones nuevas · \\${cost:.2f} para `{path.name}` "
               f"({', '.join(need[:6])}{'…' if len(need) > 6 else ''})")
    if st.button(f"Dibujar {len(need)} ilustraciones", key="illustrations_draw"):
        import voice_lock
        try:
            with st.spinner("Dibujando…"), voice_lock.panel_grant():
                done = illustrations.generate(need)
            from cost_tracker import get_tracker
            get_tracker().save()
            ok = [w for w, how in done.items() if not how.startswith("error")]
            st.success(f"{len(ok)} de {len(need)} dibujadas.")
            for w, how in done.items():
                if how.startswith("error"):
                    st.warning(f"{w}: {how}")
        except Exception as e:                              # noqa: BLE001 — a cap or the lock: shown
            st.error(str(e))


def ai_background_panel() -> None:
    """«Fondo IA para «tema» · $0.12» for the next queued «Cómo se dice», and the click that draws
    it (veo-3.1-lite through OpenRouter, under the caps; cached per topic)."""
    import ai_background
    picked = queue_pick("how_do_you_say")
    if not picked:
        return
    topic = picked[1].get("theme") or picked[1].get("category") or ""
    if not topic:
        return
    if ai_background.cached(topic):
        st.caption(f"🎞️ «{topic}» ya tiene fondo IA (se usa en uno de cada dos vídeos: A/B).")
        return
    st.caption(f"🎞️ Fondo IA para «{topic}» · \\${ai_background.estimate_usd():.2f} "
               f"({ai_background.SECONDS} s, 9:16, sin audio; uno de cada dos vídeos lo usa)")
    if st.button("Generar fondo IA", key="ai_background_draw"):
        import voice_lock
        try:
            with st.spinner("Generando el clip (1-3 min)…"), voice_lock.panel_grant():
                ai_background.generate(topic)
            from cost_tracker import get_tracker
            get_tracker().save()
            st.success(f"Fondo de «{topic}» guardado.")
        except Exception as e:                              # noqa: BLE001 — a cap, the lock or the API: shown
            st.error(str(e))



def script_for_upload(video: dict) -> dict:
    """The script behind an approved video: its sidecar's, else the audio JSON, else output/scripts.

    STEP 65: bv010 reached approved/ with no sidecar (its render timed out
    after writing the mp4) and went up as «¿Cómo se dice  en inglés?» because
    this was `{}`. The audio JSON beside it carried the script all along.
    """
    script = (video.get("meta") or {}).get("script_data")
    if script:
        return script
    # STEP 80 §0: a series video's sidecar names its script; without it the upload saw {} and
    # hc_c010 went out as «¿Sabías que '' NO significa lo que crees?»
    script_id = (video.get("meta") or {}).get("script_id")
    if video.get("type") == "hecho_con_claude" and script_id:
        try:
            return series.load(series.DRAFTS_DIR / f"{script_id}.json")
        except (OSError, ValueError):
            logger.warning("script_for_upload: no series script %s", script_id)
    for path in (AUDIO_DIR / video["type"] / f"{video['name']}.json", find_script_for(video["path"])):
        try:
            if path and Path(path).is_file():
                return json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("script_for_upload: unreadable %s", path)
    return {}


def upload_content(video: dict, script: dict, title: str, description: str,
                   allow_duplicate: bool = False) -> dict:
    """What upload_guard.content_refusal checks for one approved video."""
    return {"title": title, "description": description,
            "gate": (video.get("meta") or {}).get("gate"),
            "topic_id": (script.get("_meta") or {}).get("topic_id"),
            "topic_name": script.get("theme") or (script.get("_meta") or {}).get("topic"),
            "allow_duplicate": allow_duplicate}


def _guard_notice(st_module, artifact: str, platform_label: str, verdict) -> None:
    """Tell the operator why an upload did not happen.

    A guard that silently skips is indistinguishable from a broken button,
    and the operator's next move would be to upload by hand — which is the
    route that produced the duplicate in the first place.
    """
    from upload_guard import REFUSE, SKIP_DONE
    if verdict.action == REFUSE:
        st_module.error(f"⛔ {platform_label}: no se sube — {verdict.reason}")
    elif verdict.action == SKIP_DONE:
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
    """_guarded_upload_unlocked, under the Meta publish lock for Instagram and Facebook
    (STEP 70 §3): a click while the slot tick publishes does nothing, and a video the tick
    has just published is not sent again."""
    from publishers import schedule
    if platform not in schedule.LOCKED_PLATFORMS:
        return _guarded_upload_unlocked(manager, artifact, platform, video_path, **kwargs)
    with schedule.publish_lock() as got:
        if not got:
            return {"success": False, "error": schedule.LOCKED, "locked": True}
        state = schedule.platform_status(artifact, platform)["status"]
        if state in ("published", "holding"):           # re-read under the lock
            return {"success": False, "error": f"ya publicado o en curso en {platform}", "locked": True}
        return _guarded_upload_unlocked(manager, artifact, platform, video_path, **kwargs)


SETUP_PENDING = "configuración pendiente"


def note_setup_failure(pending: set, platform: str, result) -> Optional[str]:
    """STEP 72 §3: a Meta platform that failed for its setup (token, permissions, Instagram
    link) is added to `pending` and the batch skips its other videos. Returns the one
    message to show, or None."""
    from publishers import schedule
    from publishers.setup import is_setup_error
    error = (result.get("error") if isinstance(result, dict) else getattr(result, "error", None)) or ""
    ok = result.get("success") if isinstance(result, dict) else getattr(result, "success", False)
    if ok or platform not in schedule.LOCKED_PLATFORMS or platform in pending or not is_setup_error(error):
        return None
    pending.add(platform)
    return (f"{platform}: {SETUP_PENDING} ({error[:200]}). Se omiten sus demás vídeos de este lote; "
            f"ejecuta `python3 tools/meta_publish.py setup-check`.")


def _cleanup_module():
    """tools/cleanup.py, the same code `make clean` runs (STEP 74 §3)."""
    tools = str(ROOT / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import cleanup
    return cleanup


def cleanup_blockers(studio_jobs: Optional[Path] = None) -> list:
    """Jobs still running: the cleanup deletes intermediates a live render reads."""
    busy = [f"vídeo {j.get('id', '?')}" for j in load_jobs().get("active", []) if _owner_alive(j)]
    live = {t.name for t in threading.enumerate()}
    folder = studio_jobs or ROOT / "experiments" / "manim_voiceover_poc" / "renders" / "jobs"
    for status in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            state = json.loads(status.read_text(encoding="utf-8")).get("state")
        except (OSError, ValueError):
            continue
        if state == "running" and status.stem in live:
            busy.append(f"Manim {status.stem}")
    return busy


def _upload_platforms() -> list:
    """config.yaml upload.platforms, as main.py reads it."""
    import yaml
    try:
        with open(ROOT / "config.yaml", encoding="utf-8") as f:
            return (yaml.safe_load(f) or {}).get("upload", {}).get("platforms", []) or []
    except (OSError, yaml.YAMLError):
        return []


def tiktok_caption(title: str, description: str, hashtags) -> str:
    """STEP 73 §4: the text Garcia pastes in the TikTok app, ≤ 2200 characters."""
    from publishers.common import compose_caption
    return compose_caption("\n\n".join(p for p in (title, description) if p), hashtags, limit=2200)


def prepare_for_tiktok(video_path, caption: str, run=subprocess.run) -> None:
    """Reveal the MP4 in Finder and put the caption on the clipboard (macOS)."""
    run(["open", "-R", str(video_path)], check=True)
    run(["pbcopy"], input=caption, text=True, check=True)


def record_manual_tiktok(artifact: str, video_path, caption: str) -> dict:
    """A TikTok upload done by hand, recorded so the queue and the stats count it."""
    from publication_log import ATTEMPT_MANUAL, record_attempt
    return record_attempt(artifact=artifact, platform="tiktok", status=ATTEMPT_MANUAL,
                          video_path=str(video_path), detail=caption)


def manual_tiktok_row(artifact: str, attempts) -> Optional[dict]:
    """The latest manual TikTok record for this artifact, or None."""
    from publication_log import ATTEMPT_MANUAL
    rows = [r for r in attempts if r.get("artifact") == artifact and r.get("platform") == "tiktok"
            and r.get("status") == ATTEMPT_MANUAL]
    return rows[-1] if rows else None


def _guarded_upload_unlocked(manager, artifact: str, platform: str, video_path: str,
                             **kwargs):
    """manager.upload, with the attempt persisted before a byte is sent.

    The dashboard needs this for the same reason main.py does: the window
    between a live video and its ledger row is structural, not specific to
    the unattended path.
    """
    import os as _os

    from publication_log import (ATTEMPT_FAILED, ATTEMPT_PUBLISHED,
                                 ATTEMPT_SESSION, ATTEMPT_STARTED,
                                 ATTEMPT_UNKNOWN, record_attempt)

    from upload_limits import claim, release

    # STEP 67: a second press while this video is uploading does nothing, and logs nothing.
    if not claim(artifact, platform):
        return {"success": False, "error": "ya se está subiendo este vídeo", "in_flight": True}
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

    try:
        result = manager.upload(platform, video_path, on_session=_session, **kwargs)
    finally:
        release(artifact, platform)

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
        err = (result.get("error") if isinstance(result, dict)
               else getattr(result, "error", None))
        doubt = (result.get("in_doubt") if isinstance(result, dict)
                 else getattr(result, "in_doubt", False))
        record_attempt(artifact=artifact, platform=platform,
                       status=ATTEMPT_UNKNOWN if doubt else ATTEMPT_FAILED,
                       video_path=video_path,
                       session_uri=uri, file_size=size,
                       detail=str(err or result)[:300])
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
      * became available     -> OFF. A destination the operator did not choose
                               must not be armed.
      * still available      -> leave the operator's choice alone.

    That middle rule used to default ON — "what the operator almost certainly
    wants right after connecting". It is the wrong trade on a page whose
    button publishes irreversibly. Every connected platform armed itself on
    first render, so a distracted press published to a destination nobody
    picked; during the E1 proof TikTok had to be unticked twice to keep a
    demonstration upload off it. The cost of defaulting off is one extra
    click. The cost of defaulting on is a video the operator cannot unpublish.
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
    # Unseen means unchosen. The operator opts in per press.
    want = bool(state.get(want_key, False))

    if not enabled:
        want = False
    elif previously != enabled:
        # Transitioned unavailable -> available (or first ever render).
        want = False

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

# Privacy is decided in exactly one place, uploader.PLATFORM_PRIVACY, and the
# dashboard only reads it. Imported under a clearer name because at this call
# site the question is "what does the page show", not "what does the API get".
from uploader import privacy_label as platform_privacy_label  # noqa: E402,F401


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
        meta, _ = read_sidecar(meta_path)
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
                meta, damaged = read_sidecar(meta_file) if meta_file.exists() else ({}, None)
                videos.append({
                    "path": video_file,
                    "type": type_dir.name,
                    "name": video_file.stem,
                    "meta": meta,
                    "damaged": damaged,
                    "stage": "uploaded",
                    "created": datetime.fromtimestamp(video_file.stat().st_mtime),
                    "upload_info": meta.get("upload_info", {}),
                })
    return sorted(videos, key=lambda x: x["created"], reverse=True)


# ============== WHAT INICIO IS ALLOWED TO SAY ==============
#
# Inicio used to open with Total Videos, Storage MB and "By Type 40%". Every
# one of those is an aggregate ABOUT the system, and there is no move an
# operator can make in response to any of them. The rule for that page is now:
# a block either names specific artifacts and the one action that moves each
# forward, or it does not appear.
#
# The helpers below exist so the page can obey that rule without doing its own
# arithmetic inline, and so the arithmetic can be tested without Streamlit.

#: What a video with no gate verdict on file says. NOT a tick, and not a
#: silence. Seven of the artifacts on disk predate the commit that started
#: writing the verdict into the sidecar; rendering them as unmarked would be
#: indistinguishable from rendering them as passed, which is the exact defect
#: that put a gate REJECT into pending/ with a green tick next to the videos
#: that passed. Absence has to be visible or it reads as approval.
GATE_MISSING_LABEL = "sin registro"

#: Verdict -> (label, tone). Tone is for the page to colour with; the strings
#: are the vocabulary the operator sees.
GATE_LABELS = {
    "PASS": ("PASS", "pass"),
    "REJECT": ("REJECT", "reject"),
    "NO_REPORT": ("sin informe", "unknown"),
}


def gate_record(meta: Optional[dict]) -> dict:
    """What the artifact's own sidecar says about the QA gate.

    Three states, deliberately, and the third is not the first:
      recorded PASS      the gate ran and accepted it
      recorded REJECT    the gate ran and refused it
      no record at all   nobody knows, and the page must say so

    A missing sidecar, a sidecar without the key, and a null value all mean
    the same thing — no verdict was ever written — and all produce
    GATE_MISSING_LABEL.
    """
    verdict = (meta or {}).get("gate")
    if not verdict:
        return {"verdict": None, "known": False,
                "label": GATE_MISSING_LABEL, "tone": "unknown", "flags": []}
    label, tone = GATE_LABELS.get(verdict, (str(verdict), "unknown"))
    flags = (meta or {}).get("blocking_flags") or []
    return {"verdict": verdict, "known": True,
            "label": label, "tone": tone, "flags": list(flags)}


def independent_disk_census(output_dir: Path = None) -> dict:
    """Count the same artifacts again, by a route that shares no code.

    This is the proof obligation, not a convenience. get_pending_videos and
    friends walk iterdir() and glob per type directory and each attaches its
    own metadata; if one of them silently skipped a directory, the page would
    under-report and look perfectly healthy doing it. So the numbers Inicio
    prints are checked against a plain recursive walk that knows nothing about
    types, sidecars or the ledger reader, and the page shows BOTH.

    A disagreement is a bug in one of the two, and the page says so rather
    than picking a winner.
    """
    base = Path(output_dir) if output_dir else OUTPUT_DIR

    def walk(name: str) -> int:
        d = base / name
        return sum(1 for f in d.rglob("*.mp4") if f.is_file()) if d.is_dir() else 0

    # The gate split, recomputed from the sidecars directly rather than from
    # anything get_pending_videos attached.
    pending_dir = base / "pending"
    gate_pass = gate_none = gate_other = 0
    def _gate_of(sidecar_path):
        return json.loads(Path(sidecar_path).read_text(encoding="utf-8")).get("gate")

    if pending_dir.is_dir():
        for mp4 in pending_dir.rglob("*.mp4"):
            sidecar = mp4.with_suffix(".json")
            verdict = None
            if sidecar.is_file():
                try:
                    # Re-read only when the sidecar changes, not every click.
                    verdict = _ds.per_file(sidecar, _gate_of)
                except (json.JSONDecodeError, OSError, AttributeError):
                    verdict = None
            if verdict == "PASS":
                gate_pass += 1
            elif verdict is None:
                gate_none += 1
            else:
                gate_other += 1

    ledger_path = base / "published" / "ledger.jsonl"
    ledger_rows = 0
    if ledger_path.is_file():
        with open(ledger_path, "r", encoding="utf-8") as f:
            ledger_rows = sum(1 for line in f if line.strip())

    return {
        "batch": walk("video"),
        "pending": walk("pending"),
        "approved": walk("approved"),
        "uploaded": walk("uploaded"),
        "rejected": walk("rejected"),
        "pending_gate_pass": gate_pass,
        "pending_gate_missing": gate_none,
        "pending_gate_other": gate_other,
        "ledger_rows": ledger_rows,
    }


def get_ledger_rows(limit: int = None) -> list:
    """Published rows, newest first, straight from the publication ledger."""
    from publication_log import read_ledger
    try:
        rows = read_ledger()
    except (OSError, ValueError) as e:
        logger.warning("inicio: could not read the ledger: %s", e)
        return []
    rows.sort(key=lambda r: r.get("published_at") or "", reverse=True)
    return rows[:limit] if limit else rows


def get_failed_jobs(limit: int = None) -> list:
    """Jobs that crashed, newest first.

    A gate REJECT is NOT here. "failed" means the pipeline raised; a refused
    video is a successful render of a bad artifact and carries its verdict on
    the artifact instead. Merging the two would corrupt both counts.
    """
    failed = [j for j in load_jobs().get("history", [])
              if j.get("status") == "failed"]
    failed.sort(key=lambda j: j.get("completed_at") or j.get("updated_at") or "",
                reverse=True)
    return failed[:limit] if limit else failed



def lazy_video(path, key: str, open_now: bool = False) -> None:
    """A video player that costs nothing until someone asks for it.

    WHY. st.video(path) reads the WHOLE file into Streamlit's media store and
    ships it to the browser on EVERY rerun -- and Streamlit reruns the page on
    every click. An expander does not help: its body runs while closed. The
    Upload page drew 27 players (758 MB) and the Library 28, so every click
    there re-read ~0.8 GB before the page could answer, and the browser held
    dozens of <video> elements. Measured 2026-10-13: that is the "se tilda".

    Now a button stands in for the player; one click loads that one video and
    keeps it open for the session. `open_now` is for the single video a page
    exists to show (the newest render, the first one waiting for review).
    """
    state_key = f"_lazy_video_{key}"
    if open_now or st.session_state.get(state_key):
        st.video(str(path))
        return
    if st.button("▶️ Ver vídeo", key=f"_lazy_btn_{key}"):
        st.session_state[state_key] = True
        st.video(str(path))


def lazy_download(path, key: str) -> None:
    """A download button that reads the file only when asked.

    st.download_button(data=<file>) reads the whole video into memory on
    every rerun, whether or not anyone downloads it: 27 of them on the Upload
    page was 0.36 s and ~0.8 GB per click. The first press prepares this one
    file; the second press downloads it.
    """
    state_key = f"_lazy_dl_{key}"
    if not st.session_state.get(state_key):
        if st.button("⬇️ Download", key=f"_lazy_dl_btn_{key}",
                     width="stretch"):
            st.session_state[state_key] = True
            st.rerun()
        return
    with open(path, "rb") as handle:
        st.download_button("⬇️ Guardar archivo", data=handle,
                           file_name=Path(path).name, mime="video/mp4",
                           key=f"_lazy_dl_real_{key}", width="stretch")

def focus_first(videos: list, artifact: Optional[str]) -> list:
    """Put the artifact the operator pressed on at the top of the list.

    Inicio's "Revisar" and "Subir" buttons are per-artifact; without this they
    would land the operator at the top of a page listing every video, which
    for the seventh row in the queue is a worse position than they started
    from. Order only — nothing is filtered out, because the operator may well
    want to keep going down the list once they are there.
    """
    if not artifact:
        return videos
    hit = [v for v in videos if v.get("name") == artifact]
    if not hit:
        return videos
    return hit + [v for v in videos if v.get("name") != artifact]


def cost_snapshot(config_path: Path = None, costs_dir: Path = None,
                  today: str = None) -> dict:
    """One line's worth of money: today, the month, and the ceiling.

    Not the Costes panel — that is a later step. This answers only "did I
    spend anything today, and how close is the month to the limit", which is
    the one cost question that changes what the operator does next.

    The ceiling comes from config.yaml `costs.monthly_ceiling_usd`. If it is
    absent the line says so instead of inventing one, because a made-up
    ceiling that nobody set is worse than a visible gap.
    """
    import yaml

    cdir = Path(costs_dir) if costs_dir else (OUTPUT_DIR / "costs")
    day = today or datetime.now().strftime("%Y-%m-%d")
    month = day[:7]

    def file_total(path) -> float:
        acc = 0.0
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    acc += float(json.loads(line).get("cost_usd") or 0)
                except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
                    continue
        return acc

    def total(pattern: str) -> float:
        acc = 0.0
        if not cdir.is_dir():
            return acc
        for f in sorted(cdir.glob(pattern)):
            try:
                # Each day's file is summed once per change, not per click.
                acc += _ds.per_file(f, file_total)
            except OSError:
                continue
        return acc

    ceiling = None
    cfg_file = Path(config_path) if config_path else (ROOT / "config.yaml")
    try:
        from yaml_cache import load_yaml
        cfg = load_yaml(cfg_file) or {}
        raw = (cfg.get("costs") or {}).get("monthly_ceiling_usd")
        ceiling = float(raw) if raw is not None else None
    except (OSError, yaml.YAMLError, TypeError, ValueError):
        ceiling = None

    month_usd = round(total(f"costs_{month}*.jsonl"), 4)
    return {
        "day": day,
        "month": month,
        "today_usd": round(total(f"costs_{day}.jsonl"), 4),
        "month_usd": month_usd,
        "ceiling_usd": ceiling,
        "pct_of_ceiling": (month_usd / ceiling * 100) if ceiling else None,
    }


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
        "OpenRouter": ("OPENROUTER_API_KEY", True),
        "TikTok": ("TIKTOK_CLIENT_KEY", False),
        "YouTube": ("YOUTUBE_CLIENT_ID", False),
        "Instagram": ("FB_PAGE_TOKEN", False),
        "Facebook": ("FB_PAGE_TOKEN", False),
    }
    status = {}
    for name, (env_var, required) in keys.items():
        val = os.getenv(env_var, "")
        if env_var == "OPENROUTER_API_KEY":
            import secret_store
            val = secret_store.get(env_var) or ""   # the env first, then the Keychain
        status[name] = {
            "configured": bool(val and len(val) > 3),
            "required": required,
            "masked": mask_key(val) if val else "",
            "env_var": env_var,
        }
    return status


def save_env_key(key_name: str, value: str):
    """Update a key in .env: validated, no line breaks, temp file + rename (config/secrets)."""
    from config.secrets import save_env_key as _save
    _save(key_name, value)


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
    /* ── English Unlimited · panel ──────────────────────────────────────────
       Brand v2 «pegatina» on paper: sand background, white cards, ink text,
       English blue for actions, yellow only as a highlighter (never text).
       The palette itself lives in .streamlit/config.toml (theme), so Streamlit's
       own widgets, the sidebar and both OS themes agree with these rules; this
       block only styles the markup the panel writes by hand. Before 2026-10-14
       a hard-coded navy gradient sat on top of Streamlit's light theme, and on
       a Mac in light mode every label was dark grey on navy (contrast ~1.3:1). */
    @import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600&family=Manrope:wght@400;500;600;700&display=swap');
    :root {
        --eu-sand: #F3EEE4; --eu-card: #FFFFFF; --eu-card2: #EAE3D6;
        --eu-ink: #1C1812; --eu-muted: #6D665B; --eu-line: #D9D0C0;
        --eu-blue: #1B6FA8; --eu-blue-soft: #DCEAF4; --eu-yellow: #F2D66B;
        --eu-green: #2F8F5B; --eu-green-soft: #DDEFE3;
        --eu-red: #C0453A; --eu-red-soft: #F6DEDB; --eu-amber-soft: #F8EBC0;
    }
    html, body, .stApp, [data-testid="stSidebar"], .stMarkdown, button, input, textarea, select {
        font-family: "Manrope", system-ui, -apple-system, "Segoe UI", sans-serif;
    }
    h1, h2, h3, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        font-family: "Fredoka", "Manrope", system-ui, sans-serif !important;
        font-weight: 600 !important; letter-spacing: 0; color: var(--eu-ink);
    }
    [data-testid="stHeader"] { background: transparent; }
    .block-container { padding-top: 2.2rem; max-width: 1200px; }

    /* ── Sidebar: brand, then one quiet list of pages ── */
    section[data-testid="stSidebar"] { border-right: 1px solid var(--eu-line); }
    section[data-testid="stSidebar"] .stButton button {
        justify-content: flex-start; border-radius: 10px; font-weight: 600;
        border: 1px solid transparent; box-shadow: none; padding: 0.35rem 0.8rem;
        min-height: 2.3rem;
    }
    section[data-testid="stSidebar"] .stButton button[kind="secondary"] { background: transparent; color: var(--eu-ink); }
    section[data-testid="stSidebar"] .stButton button[kind="secondary"]:hover { background: var(--eu-card); border-color: var(--eu-line); }
    section[data-testid="stSidebar"] .stButton button > div { justify-content: flex-start; width: 100%; }
    .eu-brand { font-family: "Fredoka", system-ui, sans-serif; font-weight: 600; font-size: 1.35rem; line-height: 1.15; color: var(--eu-ink); }
    .eu-brand mark { background: linear-gradient(transparent 58%, var(--eu-yellow) 58%, var(--eu-yellow) 92%, transparent 92%); color: inherit; padding: 0 2px; }
    .eu-navlabel { font-size: 0.7rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: var(--eu-muted); padding-top: 0.9rem; }
    .eu-ver { font-size: 0.75rem; color: var(--eu-muted); margin-top: 0.3rem; }

    /* ── Cards ── */
    .metric-card, .platform-card, .video-card, .upload-item {
        background: var(--eu-card); border: 1px solid var(--eu-line); border-radius: 14px;
        padding: 20px; color: var(--eu-ink);
    }
    .metric-card { text-align: center; }
    .metric-card .metric-value { font-family: "Fredoka", sans-serif; font-size: 2.3rem; font-weight: 600; color: var(--eu-blue); margin: 6px 0; font-variant-numeric: tabular-nums; }
    .metric-card .metric-label { font-size: 0.78rem; color: var(--eu-muted); text-transform: uppercase; letter-spacing: .08em; }
    .platform-card { text-align: center; min-height: 190px; }
    .platform-card .platform-icon { font-size: 2.2rem; margin-bottom: 10px; }
    .platform-card .platform-name { font-family: "Fredoka", sans-serif; font-size: 1.15rem; font-weight: 600; margin-bottom: 6px; color: var(--eu-ink); }
    .upload-item { display: flex; align-items: center; gap: 16px; padding: 14px; margin: 8px 0; }
    .video-card { padding: 14px; margin: 8px 0; }

    /* ── Status ── */
    .status-badge, .gate-badge {
        display: inline-block; padding: 3px 10px; border-radius: 999px;
        font-size: 0.72rem; font-weight: 700; letter-spacing: .04em;
    }
    .status-connected, .gate-pass, .key-ok { background: var(--eu-green-soft); color: var(--eu-green); border: 1px solid transparent; }
    .status-disconnected, .key-missing { background: var(--eu-card2); color: var(--eu-muted); border: 1px solid transparent; }
    .status-required, .gate-reject, .key-error { background: var(--eu-red-soft); color: var(--eu-red); border: 1px solid transparent; }
    /* "sin registro" stays outlined and amber: a video nobody gated is a
       decision the operator still owes, not a neutral fact. */
    .gate-unknown { background: var(--eu-amber-soft); color: #7A5A00; border: 1px dashed #C9A227; }
    .key-status { padding: 8px 14px; border-radius: 10px; margin: 4px 0; font-size: 0.85rem; }

    .stProgress > div > div > div > div { background: var(--eu-blue); border-radius: 10px; }

    .section-header {
        font-family: "Fredoka", sans-serif; font-size: 1.15rem; font-weight: 600; color: var(--eu-ink);
        padding: 10px 0 8px; border-bottom: 2px solid var(--eu-line); margin-bottom: 14px;
    }
    .activity-item, .ledger-row {
        padding: 8px 14px; border-left: 3px solid var(--eu-blue); margin: 6px 0;
        background: var(--eu-card); border-radius: 0 10px 10px 0; font-size: 0.85rem; color: var(--eu-ink);
    }
    .ledger-row a { color: var(--eu-blue); text-decoration: none; }
    .ledger-row a:hover { text-decoration: underline; }

    /* ── Work queue (Inicio) ── */
    .queue-head { display: flex; align-items: baseline; gap: 12px; padding: 14px 0 6px; border-bottom: 2px solid var(--eu-line); margin-bottom: 10px; }
    .queue-head .queue-count { font-family: "Fredoka", sans-serif; font-size: 1.6rem; font-weight: 600; color: var(--eu-blue); font-variant-numeric: tabular-nums; }
    .queue-head .queue-title { font-size: 1.05rem; font-weight: 700; color: var(--eu-ink); }
    .queue-head .queue-action { margin-left: auto; font-size: 0.78rem; color: var(--eu-muted); }
    .artifact-name { font-size: 0.92rem; font-weight: 600; color: var(--eu-ink); word-break: break-word; }
    .artifact-meta { font-size: 0.78rem; color: var(--eu-muted); }
    .census-ok { font-size: 0.75rem; color: var(--eu-muted); }
    .census-mismatch { font-size: 0.78rem; color: var(--eu-red); font-weight: 700; }
    .cost-line {
        padding: 10px 16px; border-radius: 12px; background: var(--eu-card); border: 1px solid var(--eu-line);
        font-size: 0.88rem; color: var(--eu-ink); font-variant-numeric: tabular-nums;
    }
    /* One artifact, one line: thumbnail and text in one flex row, so a
       21-item queue is not five screens of scrolling. */
    .art-row { display: flex; align-items: center; gap: 14px; padding: 8px 12px; background: var(--eu-card); border: 1px solid var(--eu-line); border-radius: 12px; }
    .art-thumb { height: 80px; width: 45px; object-fit: cover; border-radius: 6px; flex: 0 0 auto; background: var(--eu-card2); }
    .art-thumb-empty { height: 80px; width: 45px; flex: 0 0 auto; border-radius: 6px; border: 1px dashed var(--eu-line); display: flex; align-items: center; justify-content: center; text-align: center; font-size: 0.55rem; line-height: 1.1; color: var(--eu-muted); }
    .art-body { min-width: 0; }
    .art-body .artifact-name { margin-bottom: 2px; }
    .art-note { font-size: 0.75rem; color: #7A5A00; margin-top: 3px; }
    .inicio-row div[data-testid="stVerticalBlock"] { gap: 0; }

    /* Inline code in captions read as random green pills on the cost line. */
    [data-testid="stMarkdownContainer"] code, .stMarkdown code, [data-testid="stCaptionContainer"] code {
        background: var(--eu-card2) !important; color: var(--eu-ink) !important; border-radius: 6px; padding: 1px 6px; font-size: 0.85em;
    }
</style>
""", unsafe_allow_html=True)


# ============== SIDEBAR NAVIGATION ==============

def _running_version() -> str:
    """The commit this PROCESS is running, not the one on disk.

    Read once at import, so it freezes at whatever was current when the
    process started. That is the whole point: three separate times the owner
    was told a bug was fixed while his dashboard was still executing the old
    module, and nothing on screen could have told him. A background worker
    holds the old functions even after Streamlit re-runs the page, so
    refreshing the browser is not a restart.
    """
    import subprocess
    try:
        sha = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:                                       # noqa: BLE001
        sha = "?"
    return sha or "?"


_RUNNING_VERSION = _ds.once("running_version", _running_version)
_STARTED_AT = _ds.once("started_at", lambda: datetime.now().strftime("%H:%M"))

st.sidebar.markdown('<div class="eu-brand">English <mark>Unlimited</mark></div>'
                    f'<div class="eu-ver">versión {_RUNNING_VERSION} · abierto a las {_STARTED_AT}</div>',
                    unsafe_allow_html=True)
# STEP 80 §1: OpenRouter's spend this month against its cap (from output/costs/), the one
# balance that decides whether a render may voice.
def _openrouter_spent():
    try:
        import tts_openrouter
        return tts_openrouter.month_spend(), tts_openrouter._settings()["monthly_usd"]
    except Exception:                                       # noqa: BLE001 — the header must draw
        return None, 15.0


_or_spent, _or_cap = _openrouter_spent()
for _line in voice_credits.header_lines(_or_spent, _or_cap):
    st.sidebar.markdown(f'<div class="eu-ver">{_line}</div>', unsafe_allow_html=True)

#: Page key -> (label on screen, Material icon). Keys are what ?page= and the
#: code use; only the label is translated.
NAV_LABELS = {
    "Dashboard": ("Inicio", ":material/home:"),
    "Generate": ("Crear", ":material/movie:"),
    "Queue": ("Cola", ":material/queue:"),
    "Review": ("Revisar", ":material/task_alt:"),
    "Upload": ("Subir", ":material/upload:"),
    "Library": ("Biblioteca", ":material/video_library:"),
    "Performance": ("Rendimiento", ":material/insights:"),
    "Topics": ("Temas", ":material/psychology:"),
    "Manim": ("Lecciones", ":material/school:"),
    "Scheduler": ("Programar", ":material/schedule:"),
    "Settings": ("Ajustes", ":material/settings:"),
    "Logs": ("Registros", ":material/receipt_long:"),
}


def _nav_button(name: str, is_active: bool) -> bool:
    label, icon = NAV_LABELS.get(name, (name, None))
    kwargs = dict(key=f"nav_{name}", width="stretch",
                  type="primary" if is_active else "secondary")
    try:
        return st.sidebar.button(label, icon=icon, **kwargs)
    except TypeError:                       # a Streamlit without `icon=`
        return st.sidebar.button(label, **kwargs)


main_pages = {
    "Dashboard": "🏠",
    "Generate": "🎥",
    "Queue": "📋",
    "Review": "✅",
    "Upload": "📤",
    "Library": "📚",
    "Performance": "📈",
}

tool_pages = {
    "Topics": "🧠",
    "Manim": "🎞️",
    "Scheduler": "⏰",
    "Settings": "⚙️",
    "Logs": "📜",
}

if 'current_page' not in st.session_state:
    # Direct links open a page: http://localhost:8501/?page=Manim
    wanted = getattr(st, "query_params", {}).get("page", "Dashboard")
    st.session_state.current_page = wanted if wanted in {**main_pages, **tool_pages} else "Dashboard"

st.sidebar.markdown('<div class="eu-navlabel">Producción</div>', unsafe_allow_html=True)
for name, icon in main_pages.items():
    is_active = st.session_state.current_page == name
    if _nav_button(name, is_active):
        st.session_state.current_page = name
        st.rerun()

st.sidebar.markdown('<div class="eu-navlabel">Herramientas</div>', unsafe_allow_html=True)
for name, icon in tool_pages.items():
    is_active = st.session_state.current_page == name
    if _nav_button(name, is_active):
        st.session_state.current_page = name
        st.rerun()

# Sidebar stats
st.sidebar.markdown("---")
api_status = get_api_status()
configured_count = sum(1 for s in api_status.values() if s["configured"])
st.sidebar.caption(f"Claves API: {configured_count} de {len(api_status)} configuradas")

pending_count = len(get_pending_videos())
approved_count = len(get_approved_videos())
st.sidebar.caption(f"Videos: {pending_count} por revisar · {approved_count} aprobados")
st.sidebar.markdown("---")

page = st.session_state.current_page

# Session state init
if 'scheduler_config' not in st.session_state:
    st.session_state.scheduler_config = {
        "videos_per_batch": 5,
        # All six, from the one list. Four were written out here by hand,
        # which is how fill_blank and pronunciation became unproducible.
        "types": scheduler_default_types(),
    }
if 'upload_history' not in st.session_state:
    st.session_state.upload_history = []


# ============== INICIO PAGE ==============
#
# THE RULE THIS PAGE OBEYS: every block names artifacts and the one action
# that moves each of them forward. If a block cannot say "these N specific
# videos, and here is what to do with them", it is not on this page.
#
# What that removed, and why each had to go rather than be shrunk:
#
#   Total Videos      an aggregate. 35 is not a thing to do.
#   Storage MB        an aggregate, and one nobody has ever acted on. Disk
#                     pressure is a machine problem, not a queue.
#   By Type / %       "Quiz 40%" describes the archive. The operator does not
#                     choose the next video by rebalancing a pie.
#   Platform badges   system state, not artifact state, and already shown on
#                     Upload where a press actually depends on it.
#   Recent Activity   a feed of successes. Every one of those successes is
#                     already sitting in the pending queue below, named, with
#                     its button. The feed was a second, worse copy.
#
# What stayed or arrived: the four real queues, anything in flight, anything
# that failed (with its reason and its log), and one line of money.
if page == "Dashboard":
    st.markdown("## Inicio")
    st.caption("Lo que toca hoy, en orden: producir, revisar, subir.")

    import thumbnails
    from thumbnails import ensure_thumbnail

    batch = get_library_videos()
    pending = get_pending_videos()
    approved = get_approved_videos()
    published = get_ledger_rows()
    census = independent_disk_census()

    # ── Hoy: four numbers that say what is waiting (STEP 80, Garcia: «velocity without losing quality»)
    _week_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
    _week = len({r.get("artifact") for r in published                # videos, not one row per platform
                 if (r.get("published_at") or "")[:10] >= _week_ago and r.get("artifact")})
    _hoy = st.columns(4)
    with _hoy[0]:
        st.metric("Por revisar", len(pending), border=True)
    with _hoy[1]:
        st.metric("Por subir", len(approved), border=True)
    with _hoy[2]:
        st.metric("Vídeos publicados · 7 días", _week, border=True)
    with _hoy[3]:
        st.metric(f"OpenRouter este mes · tope \\${_or_cap:.0f}", "$" + f"{(_or_spent or 0):.2f}", border=True)   # a metric's value is plain text

    # STEP 80 §2: the main action — the best queued script, in words, and why it is next
    _best = next_best()
    with st.container(border=True):
        if _best:
            _bp, _bd, _why = _best
            _what = _bd.get("theme") or _bd.get("title") or _bd.get("topic") or _bp.stem
            st.caption("SIGUIENTE VÍDEO")
            st.markdown(f"#### {type_label(_bd.get('type') or '')} · {_what}")
            st.caption("Por qué este: " + _why.split(": ", 1)[-1])   # the type is already in the title
            if st.button("▶ Producir ahora", type="primary", key="produce_next_best"):
                try:
                    st.session_state.last_job = start_generation(_bd.get("type"), use_queue=True)
                    st.success(f"En marcha: {_what}")
                except AlreadyRendering as busy:
                    st.warning(str(busy))
        else:
            st.markdown("**La cola está vacía.** Añade guiones en «Temas» o crea uno en «Crear».")

    def _census_line(listed: int, counted: int, what: str) -> None:
        """Print both counts. Never just the one the page happens to like.

        The list and the census are two different walks of the same disk. If
        they agree, the number on the page is worth something. If they do not,
        the page says which two numbers disagree and stops pretending.
        """
        if listed == counted:
            st.markdown(
                f'<span class="census-ok">{listed} en la lista · {counted} en disco ✓</span>',
                unsafe_allow_html=True)
        else:
            st.markdown(
                f'<span class="census-mismatch">⚠ No cuadra en «{what}»: {listed} en la lista, '
                f'{counted} en disco. Uno de los dos recuentos está mal.</span>',
                unsafe_allow_html=True)

    def _queue_head(count, title: str, source: str, action: str) -> None:
        num = (f'<span class="queue-count">{count}</span>'
               if count is not None else '')
        st.markdown(
            f'<div class="queue-head">{num}'
            f'<span class="queue-title">{title}</span>'
            f'<span class="artifact-meta">{source}</span>'
            f'<span class="queue-action">→ {action}</span>'
            f'</div>', unsafe_allow_html=True)

    def _esc(value) -> str:
        """Everything below builds HTML by concatenation, and every value in
        it comes off disk: artifact names are filenames, the failure reasons
        are exception strings, the URLs are ledger rows. An `&` in a topic or
        a `<` in a traceback would otherwise silently mangle the row it is in.
        """
        import html as _html
        return _html.escape(str(value), quote=True)

    def _gate_html(meta: Optional[dict]) -> str:
        g = gate_record(meta)
        return f'<span class="gate-badge gate-{g["tone"]}">{_esc(g["label"])}</span>'

    @st.cache_data(show_spinner=False)
    def _thumb_uri(path: str, mtime: float) -> str:
        """The still, inlined. Keyed on mtime so a re-render busts the cache.

        Inlined rather than served through st.image because the picture has to
        sit INSIDE the flex row with the name; two Streamlit elements stacked
        in a column cannot be made to share a line."""
        import base64
        return ("data:image/jpeg;base64,"
                + base64.b64encode(Path(path).read_bytes()).decode("ascii"))

    def _thumb_html(video_path: Path) -> str:
        thumb = ensure_thumbnail(video_path)
        if not thumb:
            return '<div class="art-thumb-empty">sin<br>imagen</div>'
        try:
            uri = _thumb_uri(thumb, Path(thumb).stat().st_mtime)
        except OSError:
            return '<div class="art-thumb-empty">sin<br>imagen</div>'
        return f'<img class="art-thumb" src="{uri}" alt="">'

    def _artifact_row(video: dict, meta_line: str, badge: str = "",
                      note: str = "") -> str:
        note_html = f'<div class="art-note">{_esc(note)}</div>' if note else ""
        return (f'<div class="art-row">{_thumb_html(video["path"])}'
                f'<div class="art-body">'
                f'<div class="artifact-name">{_esc(video["name"])}</div>'
                f'<div class="artifact-meta">{_esc(meta_line)}</div>'
                f'{badge}{note_html}</div></div>')

    def _go(page_name: str, artifact: str) -> None:
        """Hand the operator to the page where the decision is made, with the
        artifact they pressed on moved to the top of it. Without the second
        half, pressing "Revisar" on the seventh video drops you at the first."""
        st.session_state.focus_artifact = artifact
        st.session_state.current_page = page_name
        st.rerun()

    # One pass over every artifact the page is about to draw, so the operator
    # waits once with a spinner instead of watching rows appear one ffmpeg
    # call at a time. After the first visit this loop is all cache hits.
    to_warm = [v["path"] for v in (batch + pending + approved)]
    uncached = [v for v in to_warm
                if not thumbnails.thumbnail_path(v).exists()]
    if uncached:
        with st.spinner(f"Extrayendo {len(uncached)} miniaturas (una vez por artefacto)..."):
            for v in uncached:
                ensure_thumbnail(v)

    def _month_name(ym: str) -> str:
        names = ("enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre "
                 "diciembre").split()
        try:
            return names[int(ym[5:7]) - 1]
        except (ValueError, IndexError):
            return ym

    # ── Money, one line ──────────────────────────────────────────────────
    cost = cost_snapshot()
    if cost["ceiling_usd"]:
        ceiling_txt = (f'de un techo de &#36;{cost["ceiling_usd"]:.2f} '
                       f'({cost["pct_of_ceiling"]:.0f}%)')
    else:
        ceiling_txt = "sin techo configurado en config.yaml (costs.monthly_ceiling_usd)"
    st.markdown(
        # STEP 80 §0: «$» as an entity — two of them on a line rendered as LaTeX math
        f'<div class="cost-line">💸 Gasto total: hoy <strong>&#36;{cost["today_usd"]:.2f}</strong>'
        f' · {_month_name(cost["month"])} <strong>&#36;{cost["month_usd"]:.2f}</strong>'
        f' {ceiling_txt}</div>', unsafe_allow_html=True)

    # ── Money, per video ─────────────────────────────────────────────────
    # Collapsed: the line above is the question that changes what the
    # operator does next; this is where they go when it looks wrong.
    from cost_tracker import per_video_costs, video_cost_stats
    _video_costs = per_video_costs(OUTPUT_DIR / "costs")
    if _video_costs:
        _stats = video_cost_stats(_video_costs)
        _outliers = set(_stats["outliers"])
        with st.expander(
                f"💸 Coste por vídeo: media \\${_stats['mean_usd']:.3f} · mediana "
                f"\\${_stats['median_usd']:.3f} · {_stats['videos']} vídeos"):
            st.dataframe(
                [{"video": r["video_id"],
                  "fecha": (r["last_at"] or "")[:16].replace("T", " "),
                  "OpenRouter $": round(r.get("openrouter_usd", 0.0), 4),
                  # historical: rows from before OpenRouter was the only paid AI (2026-10-27)
                  "OpenAI $ (antiguo)": round(r["openai_usd"], 4),
                  "ElevenLabs $ (antiguo)": round(r["elevenlabs_usd"], 4),
                  "total $": round(r["total_usd"], 4),
                  "llamadas": r["calls"],
                  "⚠": "> 2× mediana" if r["video_id"] in _outliers else ""}
                 for r in _video_costs[:50]],
                width="stretch", hide_index=True)
            st.caption("Últimos 50. Detalle completo: "
                       "`python3 src/cost_tracker.py --videos 100`")
    st.markdown("")

    # ── In flight ────────────────────────────────────────────────────────
    #
    # A fragment, not a page-level rerun. The old version called st.rerun()
    # from inside this loop, which abandons the rest of the draw — harmless
    # while generation blocked the thread (nothing else could run anyway),
    # but now that jobs run in the background it would hide every queue below
    # for as long as anything was rendering. run_every repaints only this
    # block, and only while there is something to show.
    @st.fragment(run_every="2s")
    def _render_active_jobs():
        jobs = get_active_jobs()
        if not jobs:
            return
        _queue_head(len(jobs), "En marcha", "", "se actualiza solo")
        for job in jobs:
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"**{type_label(job['video_type'])}** — {job.get('topic') or 'eligiendo tema…'}")
                st.progress(job.get('progress', 0) / 100)
                st.caption(job.get('current_step') or 'empezando…')
            with c2:
                st.code(job['id'])

    _render_active_jobs()

    # ── 1. Rendered by --batch, never promoted ───────────────────────────
    if batch or census["batch"]:                        # rare (a --batch render): no block when empty
        _queue_head(len(batch), "Hechos por lote, sin revisar", "", "pasar a revisión")
        _census_line(len(batch), census["batch"], "hechos por lote")
    for idx, v in enumerate(batch):
        c1, c2 = st.columns([6, 1.6], vertical_alignment="center")
        with c1:
            st.markdown(_artifact_row(
                v, f'{v["type"]} · {v["created"].strftime("%Y-%m-%d %H:%M")} · '
                   f'{v["size"] / (1024*1024):.1f} MB'),
                unsafe_allow_html=True)
        with c2:
            if st.button("⬆️ A revisión", key=f"inicio_promote_{idx}",
                         width="stretch"):
                verdict = promote_to_review(v["path"])
                if verdict["ok"]:
                    st.success(f"{verdict['artifact']} pasó a «Por revisar». {verdict['reason']}")
                    st.rerun()
                else:
                    st.error(verdict["reason"])
    st.markdown("")

    # ── 2. Awaiting review ───────────────────────────────────────────────
    _queue_head(len(pending), "Por revisar", "", "revisar")
    _census_line(len(pending), census["pending"], "por revisar")

    # The gate split, counted twice as well. This is the number that must not
    # be allowed to drift: an artifact with no verdict rendering as one that
    # passed is precisely the failure D0 was written to end.
    listed_gate = {"pass": 0, "missing": 0, "other": 0}
    for v in pending:
        g = gate_record(v.get("meta"))
        if not g["known"]:
            listed_gate["missing"] += 1
        elif g["verdict"] == "PASS":
            listed_gate["pass"] += 1
        else:
            listed_gate["other"] += 1
    gate_ok = (listed_gate["pass"] == census["pending_gate_pass"]
               and listed_gate["missing"] == census["pending_gate_missing"]
               and listed_gate["other"] == census["pending_gate_other"])
    gate_txt = (f'{listed_gate["pass"]} con PASS · '
                f'{listed_gate["missing"]} {GATE_MISSING_LABEL}'
                + (f' · {listed_gate["other"]} otro veredicto' if listed_gate["other"] else ''))
    if gate_ok and not pending:
        pass                                            # nothing listed, nothing on disk: no line
    elif gate_ok:
        st.markdown(f'<span class="census-ok">{gate_txt} — '
                    f'({census["pending_gate_pass"]}/{census["pending_gate_missing"]}'
                    + (f'/{census["pending_gate_other"]}' if listed_gate["other"] else '')
                    + ') en disco ✓</span>',
                    unsafe_allow_html=True)
    else:
        st.markdown(f'<span class="census-mismatch">⚠ Los veredictos no cuadran: '
                    f'{gate_txt} vs {census["pending_gate_pass"]}/'
                    f'{census["pending_gate_missing"]}/{census["pending_gate_other"]} '
                    f'en disco.</span>', unsafe_allow_html=True)
    if listed_gate["missing"]:
        st.caption(
            f'{listed_gate["missing"]} no tienen veredicto del control de calidad. '
            f'«{GATE_MISSING_LABEL}» no quiere decir que pasaran: nadie lo comprobó '
            f'(son anteriores a que el veredicto se guardara con el vídeo).')

    if not pending:
        st.caption("Nada por revisar. Produce el siguiente vídeo arriba.")
    for idx, v in enumerate(pending):
        c1, c2 = st.columns([6, 1.6], vertical_alignment="center")
        with c1:
            flags = gate_record(v.get("meta"))["flags"]
            st.markdown(_artifact_row(
                v, f'{v["type"]} · {v["created"].strftime("%Y-%m-%d %H:%M")}',
                badge=_gate_html(v.get("meta")),
                note=("⚠ " + ", ".join(str(f) for f in flags)) if flags else ""),
                unsafe_allow_html=True)
        with c2:
            if st.button("👀 Revisar", key=f"inicio_review_{idx}",
                         width="stretch"):
                _go("Review", v["name"])
    st.markdown("")

    # ── 3. Approved, not uploaded ────────────────────────────────────────
    _queue_head(len(approved), "Por subir", "", "subir")
    _census_line(len(approved), census["approved"], "por subir")
    if not approved:
        st.caption("Nada por subir. Lo que apruebes en «Revisar» aparece aquí.")
    for idx, v in enumerate(approved):
        c1, c2 = st.columns([6, 1.6], vertical_alignment="center")
        with c1:
            # The ledger is the authority on what is published, and a video
            # already live sitting in the "ready to upload" list is the exact
            # shape of the mistake that published hPdSoqjvu3E twice.
            note = ("⚠ el registro ya lo da por publicado en: "
                    + ", ".join(v["published_to"])) if v.get("published_to") else ""
            st.markdown(_artifact_row(
                v, f'{v["type"]} · {v["created"].strftime("%Y-%m-%d %H:%M")}',
                badge=_gate_html(v.get("meta")), note=note),
                unsafe_allow_html=True)
        with c2:
            if st.button("📤 Subir", key=f"inicio_upload_{idx}",
                         width="stretch"):
                _go("Upload", v["name"])
    st.markdown("")

    # ── 4. Published ─────────────────────────────────────────────────────
    _queue_head(len(published), "Publicados", "", "abrir en la plataforma")
    _census_line(len(published), census["ledger_rows"], "publicados")

    def _ledger_row(r: dict) -> str:
        artifact = r.get("artifact") or "(sin artefacto)"
        when = (r.get("published_at") or "")[:10]
        url = r.get("url") or ""
        plat = r.get("platform") or "?"
        # The href is escaped AND scheme-checked: a ledger row is data, and a
        # javascript: value reaching an anchor would be a click away from
        # running in the operator's dashboard.
        safe = url if url.startswith(("http://", "https://")) else ""
        link = (f'<a href="{_esc(safe)}" target="_blank" rel="noopener noreferrer">'
                f'▶ abrir</a>' if safe
                else '<span class="artifact-meta">sin URL</span>')
        # UNMATCHED:: rows were backfilled from the platform API and have no
        # local file; saying so is the point of keeping them in the list.
        note = (' <span class="artifact-meta">· sin fichero local</span>'
                if artifact.startswith("UNMATCHED::") else '')
        return (f'<div class="ledger-row">{link} · '
                f'<span class="artifact-name">{_esc(artifact)}</span>'
                f'<span class="artifact-meta"> · {_esc(plat)} · {_esc(when)}</span>'
                f'{note}</div>')

    LEDGER_SHOWN = 6
    for r in published[:LEDGER_SHOWN]:
        st.markdown(_ledger_row(r), unsafe_allow_html=True)
    if len(published) > LEDGER_SHOWN:
        with st.expander(f"Ver las otras {len(published) - LEDGER_SHOWN} publicaciones"):
            for r in published[LEDGER_SHOWN:]:
                st.markdown(_ledger_row(r), unsafe_allow_html=True)
    st.markdown("")

    # ── Failures ─────────────────────────────────────────────────────────
    #
    # BELOW the queues, deliberately. This block was drawn first and the
    # top of Inicio became five stale crashes — the newest nine days old,
    # four of them the same ImportError from a bug fixed weeks ago — with
    # every actionable queue pushed under the fold. A three-week-old
    # traceback is not the next thing to do, so it does not get the
    # position that says it is.
    #
    # A gate REJECT is deliberately NOT here: "failed" means the pipeline
    # raised, a refused video is a successful render of a bad artifact and
    # carries its verdict on the artifact instead. These are crashes, and the
    # only thing to do with a crash is read its log — so the log is the row.
    failed = get_failed_jobs()
    if failed:
        SHOWN = 3
        _queue_head(len(failed), "Fallos recientes", "", "leer el log")
        for job in failed[:SHOWN]:
            when = (job.get("completed_at") or job.get("updated_at") or "")[:16].replace("T", " ")
            topic = job.get("topic") or "(sin tema)"
            reason = (job.get("error") or "sin motivo registrado").strip().splitlines()[0][:180]
            log_path = job.get("log_path")
            st.markdown(
                f'<div class="activity-item">❌ <strong>{_esc(topic)}</strong> '
                f'<span class="artifact-meta">· {_esc(job.get("video_type",""))} '
                f'· {_esc(when)} · job {_esc(job.get("id",""))}</span><br>'
                f'<span style="color:var(--eu-red);font-size:0.8rem">{_esc(reason)}</span></div>',
                unsafe_allow_html=True)
            if log_path:
                exists = Path(log_path).exists()
                st.caption(f'📜 `{log_path}`' + ("" if exists else "  — el archivo ya no está"))
            else:
                st.caption("📜 sin log_path en el registro del job")
        if len(failed) > SHOWN:
            with st.expander(f"Ver los otros {len(failed) - SHOWN} fallos"):
                for job in failed[SHOWN:]:
                    when = (job.get("completed_at") or "")[:16].replace("T", " ")
                    reason = (job.get("error") or "sin motivo").strip().splitlines()[0][:140]
                    st.markdown(f"- **{job.get('topic') or '(sin tema)'}** · {when} — {reason}")
                    if job.get("log_path"):
                        st.caption(f"  📜 `{job['log_path']}`")
        st.markdown("")

    # ── How new artifacts enter the queues above ─────────────────────────
    _queue_head(None, "Crear rápido", "", "un vídeo del tipo que elijas, de la cola")
    # DERIVED, and that is a bug fix, not tidying. This row was written by
    # hand with four of the six types, so fill_blank and pronunciation had no
    # Generate button -- the exact defect admin.py:2264 documents having fixed
    # in the scheduler, regrown in a different list in the same file.
    _buttons = video_types.DASHBOARD_BUTTONS
    action_cols = st.columns(len(_buttons))
    for col, (label, vtype) in zip(action_cols, _buttons):
        with col:
            if st.button(f"🎬 {label}", width="stretch", key=f"quick_{vtype}"):
                job_id = start_generation(vtype)
                st.toast(f"{label}: en marcha (job {job_id})")
                st.rerun()


# ============== GENERATE PAGE ==============
elif page == "Generate":
    st.markdown("## Crear video")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown('<div class="section-header">Configuración</div>', unsafe_allow_html=True)

        # STEP 80 §3: Spanish labels, and the type's own name instead of its key
        video_type = st.selectbox("Tipo de vídeo", [*PANEL_TYPES, series.PANEL_LABEL], index=0,
                                  format_func=type_label)

        # STEP 78 §1: «Hecho con Claude», its own scripts and queue, filtered by style and level.
        is_series = video_type == series.PANEL_LABEL
        series_style = series_level = None
        if is_series:
            from script_schema import SERIES_LEVELS, SERIES_STYLES
            _style = st.selectbox("Estilo", ["Todos", *SERIES_STYLES])
            _level = st.selectbox("Nivel", ["Todos", *SERIES_LEVELS],
                                  format_func=lambda v: series.LEVEL_NAMES.get(v, v))
            series_style = None if _style == "Todos" else _style
            series_level = None if _level == "Todos" else _level
            st.caption(f"{len(series.queued(series_style, series_level))} guiones en cola")

        # STEP 80 §4/§5: the next «Cómo se dice» script's illustrations and AI background
        if video_type == "how_do_you_say":
            illustrations_panel()
            ai_background_panel()

        _modes = {"Random": "Al azar", "Select Category": "Elegir categoría", "Specific Topic": "Tema concreto"}
        selection_mode = st.radio("Tema", list(_modes), index=0, format_func=_modes.get)

        category = None
        topic_name = None

        if selection_mode == "Select Category":
            categories = list_categories()
            category = st.selectbox("Categoría", categories)
        elif selection_mode == "Specific Topic":
            categories = list_categories()
            category = st.selectbox("Categoría", categories)
            if category:
                topics = load_topics(category)
                topic_names = [t.get("english") or t.get("topic") or t.get("wrong") for t in topics]
                topic_name = st.selectbox("Tema concreto", topic_names)

        # ── the controls the engine has always accepted ──
        #
        # Each of these is a parameter run_pipeline_with_tracking already
        # took, or a name pipeline.resolve_profile already resolved. None of
        # them had a widget, which is the whole reason this page had three
        # controls for an engine with seven.
        with st.expander("Opciones", expanded=False):
            profiles = available_profiles()
            profile_name = st.selectbox(
                "Perfil de audiencia", profiles,
                index=profiles.index("adults") if "adults" in profiles else 0,
                help="Voz, fondos y categorías de temas.")

            # Named with its reason rather than silently missing. A profile
            # that is declared but cannot resolve is a fixable configuration
            # problem, and hiding it makes it an invisible one.
            for name, reason in unavailable_profiles().items():
                st.caption(f"Perfil «{name}» no disponible — {reason}")

            # NO BACKGROUND CONTROL AND NO ENGINE CONTROL.
            #
            # The selectbox listed 16 flat presets and pinning one is what
            # produced three of the last five videos; the v2 checkbox chose
            # an animated mesh gradient, which is flat by design and was the
            # fourth. Every video now gets this video's own Pexels footage,
            # or the local cache, or it fails.
            background = None

            # THE QUEUE, and why it is the default.
            #
            # Every dashboard video used to call the script model. With
            # scripts in the queue the page produces without a single API call, and the guard decides
            # which one -- never a topic already produced.
            _q = queue_status()
            if _q["ready"]:
                use_queue = st.checkbox(
                    f"Usar un guion de la cola ({_q['ready']} listos)", value=True,
                    help="Escritos de antemano y revisados por el guardián: sin llamada al "
                         "modelo y nunca un tema ya producido. Desmárcalo para que el modelo "
                         "escriba uno nuevo (OpenRouter, de pago).")
                if use_queue:
                    st.caption(" · ".join(f"{type_label(k)} {v}" for k, v in
                                          sorted(_q["by_type"].items())))
            else:
                use_queue = False
                st.caption("La cola está vacía: el modelo escribirá un guion nuevo "
                           "(OpenRouter, de pago)."
                           + (f" {_q['blocked']} guion(es) en cola bloqueados por el guardián."
                              if _q["blocked"] else ""))

            dry_run = st.checkbox(
                "Prueba (sin voz ni render)",
                help="Escribe el guion y resuelve el plan de voz, y para ahí: sin TTS ni "
                     "render, pero la llamada al modelo para el guion sí ocurre (OpenRouter: barato, no gratis).")

        generate_btn = st.button("Crear video", type="primary", width="stretch",
                                 disabled=is_series and not hasattr(series, "render_one"))

    with col2:
        st.markdown('<div class="section-header">En marcha</div>', unsafe_allow_html=True)

        # Same reason as the Dashboard panel: repaint this block, not the page.
        @st.fragment(run_every="2s")
        def _render_generation_status():
            jobs = get_active_jobs()
            if not jobs:
                return
            for job in jobs:
                st.markdown(f"**{type_label(job['video_type'])}** — {job.get('topic', 'eligiendo…')}")
                st.progress(job.get('progress', 0) / 100)
                st.caption(job.get('current_step', 'Empezando…'))

        _render_generation_status()
        # STEP 80 §3: the history and the failures are Inicio's; this page no longer repeats them
        st.caption("Lo terminado y los fallos están en «Inicio».")

        if generate_btn and is_series:
            job_id = start_series_generation(series_style, series_level)
            st.success(f"En marcha: `{job_id}` — el progreso aparece arriba.")
            st.rerun()
        elif generate_btn:
            # Queued, not awaited: the outcome arrives in the job list above,
            # which this page already renders from the ledger.
            try:
                job_id = start_generation(video_type, category, topic_name,
                                          profile_name=profile_name,
                                          background=background,
                                          use_queue=use_queue,
                                          dry_run=dry_run)
            except AlreadyRendering as e:
                st.error(str(e))
            else:
                st.success(f"En marcha: `{job_id}` — el progreso aparece arriba.")
                st.rerun()


# ============== QUEUE PAGE ==============
elif page == "Queue":
    st.markdown("## Cola")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown('<div class="section-header">Add to Queue</div>', unsafe_allow_html=True)

        st.write("**Quick Batch:**")
        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button("10 Random Quizzes", width="stretch"):
                total = batch_add([{"type": "quiz", "category": None,
                                    "topic": None} for _ in range(10)])
                st.success(f"Added 10 quizzes — {total} waiting.")
                st.rerun()
        with bc2:
            if st.button("5 of Each Type", width="stretch"):
                # "Each type" meant three of six, and the toast said 15
                # regardless. Both came from the hand-written list.
                total = batch_add([{"type": vtype, "category": None,
                                    "topic": None}
                                   for vtype in PANEL_TYPES
                                   for _ in range(5)])
                st.success(f"Added {5 * len(PANEL_TYPES)} videos — "
                           f"{total} waiting.")
                st.rerun()

        st.markdown("---")
        st.write("**Custom:**")
        q_type = st.selectbox("Type", PANEL_TYPES, key="queue_type")
        q_count = st.number_input("Count", min_value=1, max_value=50, value=5)
        if st.button("Add to Queue", width="stretch"):
            total = batch_add([{"type": q_type, "category": None,
                                "topic": None} for _ in range(q_count)])
            st.success(f"Added {q_count} {q_type} videos — {total} waiting.")
            st.rerun()

    with col2:
        _queued = batch_queue()
        _running = get_active_jobs()
        st.markdown(f'<div class="section-header">Queue ({len(_queued)} waiting)</div>',
                    unsafe_allow_html=True)

        if _running:
            st.info(f"Rendering now: {_running[0].get('video_type', '?')} — "
                    f"{_running[0].get('current_step', '...')}")

        if _queued:
            c1, c2 = st.columns(2)
            with c1:
                start_btn = st.button("▶️ Start Processing", type="primary",
                                      width="stretch",
                                      disabled=bool(_running))
            with c2:
                if st.button("Clear Queue", width="stretch"):
                    batch_clear()
                    st.rerun()

            by_type = {}
            for item in _queued:
                t = item["type"]
                by_type[t] = by_type.get(t, 0) + 1
            for t, count in by_type.items():
                st.write(f"**{t}**: {count} videos")

            st.caption("The queue lives on disk and one video renders at a "
                       "time. Closing this page does not stop it, and a "
                       "restart resumes from whatever is left.")

            if start_btn:
                # ONE item. The rest stay on disk and the worker chains to
                # them as each finishes — see batch_advance(). Starting them
                # all at once is what made them vanish on every restart.
                job_id = batch_advance()
                if job_id:
                    st.success(f"Started. {len(batch_queue())} still waiting — "
                               "watch progress on the Generate page.")
                else:
                    st.warning("Something is already rendering; the queue "
                               "continues on its own when it finishes.")
                st.rerun()
        elif _running:
            st.info("Queue empty — finishing the last video.")
        else:
            st.info("Queue is empty. Add videos above!")


# ============== REVIEW PAGE ==============
elif page == "Review":
    st.markdown("## Revisar")

    pending = get_pending_videos()

    # Arriving from Inicio's "Revisar" button on a specific artifact.
    _focus = st.session_state.pop("focus_artifact", None)
    pending = focus_first(pending, _focus)

    if not pending:
        st.info("No videos pending review. Generate some new videos!")
    else:
        st.write(f"**{len(pending)} videos pending review**")
        if _focus and any(v["name"] == _focus for v in pending):
            st.caption(f"↑ {_focus} está el primero — vienes de Inicio.")

        types_available = list(set(v["type"] for v in pending))
        filter_type = st.selectbox("Filtrar por tipo", ["All"] + types_available,
                                   format_func=lambda k: "Todos" if k == "All" else type_label(k))
        if filter_type != "All":
            pending = [v for v in pending if v["type"] == filter_type]

        st.markdown("---")

        for idx, video in enumerate(pending):
            col1, col2 = st.columns([2, 1])
            with col1:
                st.subheader(f"{video['name']}")
                st.write(f"**Type:** {video['type']} | **Created:** {video['created'].strftime('%Y-%m-%d %H:%M')}")
                if video.get("damaged"):
                    st.error(f"⚠️ {video['damaged']}. No se puede revisar hasta repararlo o volver a renderizarlo.")
                    continue
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
                # STEP 80 §1b: the metadata the render generated, editable here
                review_metadata_editor(video)
                if video["path"].exists():
                    lazy_video(video["path"], f"review_{video['path'].name}",
                               open_now=(idx == 0))

            with col2:
                st.write("")
                st.write("")
                if st.button("✅ Approve", key=f"approve_{idx}", type="primary", width="stretch"):
                    approve_video(video["path"])
                    st.success("Approved!")
                    st.rerun()
                if st.button("❌ Reject", key=f"reject_{idx}", width="stretch"):
                    reject_video(video["path"])
                    st.rerun()

            st.markdown("---")

        st.markdown("**Bulk Actions**")
        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button("✅ Approve All", width="stretch"):
                for v in pending:
                    approve_video(v["path"])
                st.success(f"Approved {len(pending)} videos!")
                st.rerun()
        with bc2:
            if st.button("❌ Reject All", width="stretch"):
                for v in pending:
                    reject_video(v["path"])
                st.rerun()


# ============== UPLOAD PAGE ==============
elif page == "Upload":
    st.markdown("## Subir")

    approved = get_approved_videos()

    # STEP 67: the channel's 24 h upload limit, read from the attempts log.
    from publication_log import read_attempts as _read_attempts
    from upload_limits import limit_block as _limit_block, published_last_24h as _last_24h
    _attempts = _read_attempts()
    st.caption(f"Subidos en las últimas 24 h: {len(_last_24h(_attempts, datetime.now()))}")
    _yt_block = _limit_block(_attempts, datetime.now())
    if _yt_block:
        st.error(_yt_block)

    # Arriving from Inicio's "Subir" button on a specific artifact.
    _focus = st.session_state.pop("focus_artifact", None)
    approved = focus_first(approved, _focus)

    # Platform status cards
    st.markdown('<div class="section-header">Connected Platforms</div>', unsafe_allow_html=True)

    platform_cols = st.columns(4)

    platforms = [
        {
            "name": "TikTok",
            "api": "tiktok",
            "icon": "🎵",
            "key": "TIKTOK_CLIENT_KEY",
            "desc": "Content Posting API",
            "color": "#ff0050",
        },
        {
            "name": "YouTube Shorts",
            "api": "youtube",
            "icon": "▶️",
            "key": "YOUTUBE_CLIENT_ID",
            "desc": "YouTube Data API v3",
            "color": "#ff0000",
        },
        {
            "name": "Instagram Reels",
            "api": "instagram",
            "icon": "📷",
            "key": "FB_PAGE_TOKEN",
            "desc": "Instagram API with Facebook Login",
            "color": "#e1306c",
        },
        {
            "name": "Facebook Reels",
            "api": "facebook",
            "icon": "📘",
            "key": "FB_PAGE_TOKEN",
            "desc": "Reels Publishing API",
            "color": "#1877f2",
        },
    ]

    platform_status = {}
    for col, platform in zip(platform_cols, platforms):
        with col:
            is_configured = bool(os.getenv(platform["key"], ""))
            if platform["api"] == "tiktok":
                # STEP 73: TikTok cannot authenticate yet; it is uploaded by hand
                # (buttons per video) until config.yaml upload.platforms names it again.
                is_configured = is_configured and "tiktok" in _upload_platforms()
            platform_status[platform["name"]] = is_configured
            badge_class = "status-connected" if is_configured else "status-disconnected"
            badge_text = "CONNECTED" if is_configured else "NOT CONFIGURED"
            # What this platform will publish AT, read from the one resolver
            # the uploaders themselves use. On the page, before the press:
            # the operator should never have to open a file to find out
            # whether a video is going out to an audience of zero.
            privacy = platform_privacy_label(platform["api"])

            st.markdown(f"""
            <div class="platform-card">
                <div class="platform-icon">{platform['icon']}</div>
                <div class="platform-name">{platform['name']}</div>
                <div style="color:var(--eu-muted);font-size:0.85rem;margin-bottom:12px">{platform['desc']}</div>
                <span class="status-badge {badge_class}">{badge_text}</span>
                <div style="color:var(--eu-ink);font-size:0.85rem;margin-top:10px">
                    publishes as <strong>{privacy}</strong>
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("")
    render_meta_queue(st)

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
            st.markdown("2. Add your TikTok, YouTube, Instagram or Facebook credentials")
            st.markdown("3. Come back here to upload")
            st.markdown("---")

        # Upload targets
        target_platforms = []
        tcols = st.columns(len(platforms))
        for col, platform in zip(tcols, platforms):
            with col:
                enabled = platform_status.get(platform["name"], False)
                # Reconcile the derived half (auth status) with the user half
                # (chosen targets) BEFORE rendering. No `value=` — a keyed
                # widget ignores it, which is the bug this replaces.
                reconcile_platform_target(
                    st.session_state, platform["name"], enabled)
                # The privacy rides on the label, not a caption below it:
                # the operator reads the thing they are about to tick.
                if st.checkbox(
                    f"{platform['icon']} {platform['name']} — "
                    f"{platform_privacy_label(platform['api'])}",
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
                    if video.get("damaged"):
                        st.error(f"⚠️ {video['damaged']}")
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
                        lazy_video(video["path"], f"upload_{video['path'].name}")

                with col2:
                    # Generate metadata from script
                    script = script_for_upload(video)
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

                    # STEP 80 §1b: start from what the render generated (sidecar «metadata»)
                    generated = (video.get("meta") or {}).get("metadata") or {}
                    if generated.get("title"):
                        meta = {"title": generated["title"], "description": generated.get("description", ""),
                                "hashtags": (generated.get("hashtags") or {}).get("youtube") or meta["hashtags"]}
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

                        # STEP 80 §1b: the two other titles the render proposed
                        for k, alt in enumerate(generated.get("alternatives") or []):
                            if st.button(f"Usar alternativa: {alt}", key=f"alt_{k}_{video['name']}"):
                                st.session_state[pending_key] = {
                                    "title": alt, "description": st.session_state.get(desc_key, ""),
                                    "hashtags": st.session_state.get(tags_key, "")}
                                st.rerun()

                        # Platform regeneration buttons («Regenerar»)
                        regen_cols = st.columns(3)
                        for i, (icon, pname, pkey) in enumerate([
                            ("🎵", "TikTok", "tiktok"),
                            ("▶️", "YouTube", "youtube"),
                            ("📸", "Instagram", "instagram"),
                        ]):
                            with regen_cols[i]:
                                if st.button(f"{icon} {pname}", key=f"regen_{pkey}_{video['name']}",
                                             width="stretch", help=f"Regenerate for {pname}"):
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

                # Upload button. STEP 65: the guard is asked BEFORE the click
                # too, so a refusal is on screen and the button stays grey.
                from upload_guard import NO_GATE, content_refusal
                allow_dup = False
                _pre = content_refusal(**upload_content(
                    video, script, st.session_state.get(title_key, ""),
                    st.session_state.get(desc_key, "")))
                if _pre and _pre.reason.startswith("Ya hay un vídeo"):
                    st.error(_pre.reason)
                    allow_dup = st.checkbox("Subir otra versión de todos modos",
                                            key=f"dup_{video['name']}")
                    if allow_dup:
                        _pre = None    # the duplicate is checked last, so nothing else failed
                elif _pre and _pre.reason == NO_GATE:
                    st.warning(f"⚠️ {NO_GATE}: el QA gate no ha dado veredicto. Vuelve a renderizar o pasa el gate.")
                elif _pre:
                    st.error(f"⛔ {_pre.reason}")
                if _yt_block and "YouTube Shorts" in target_platforms:
                    _pre = _pre or True        # the YouTube button waits for the slot (message above)
                if target_platforms and not _pre:
                    if st.button("📤 Upload", key=f"upload_{video['name']}", width="stretch"):
                        try:
                            from uploader import get_upload_manager
                            manager = get_upload_manager()
                            # Same resolver as the bulk path, so the two
                            # cannot drift apart again.
                            _resolved = resolve_upload_metadata(
                                video["name"], script, "", 
                                video.get("type", "educational"), category,
                                st.session_state, generated=(video.get("meta") or {}).get("metadata"),
                            )
                            vid_title = _resolved["title"]
                            vid_desc = _resolved["description"]
                            vid_tags = _resolved["hashtags"]

                            platform_map = {
                                "TikTok": "tiktok",
                                "YouTube Shorts": "youtube",
                                "Instagram Reels": "instagram",
                                "Facebook Reels": "facebook",
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
                                                   manager=manager, **upload_content(
                                                       video, script, sent_title, sent_desc,
                                                       allow_dup))
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
                                    elif isinstance(result, dict) and result.get("locked"):
                                        st.warning(result["error"])
                                    elif setup_msg := note_setup_failure(set(), platform_key, result):
                                        st.error(setup_msg)
                                    elif not (isinstance(result, dict) and result.get("in_flight")):
                                        from upload_limits import spanish as _spanish
                                        err = result.get("error", "Unknown") if isinstance(result, dict) else getattr(result, 'error', 'Unknown')
                                        st.error(f"Failed: {_spanish(err, _read_attempts(), datetime.now())}")

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
                    st.button("📤 Upload", key=f"upload_{video['name']}", disabled=True, width="stretch")

                btn_cols = st.columns(3)
                with btn_cols[0]:
                    if video["path"].exists():
                        lazy_download(video["path"], f"dl_{video['name']}")
                with btn_cols[2]:
                    if st.button("📅", key=f"metaq_{video['name']}", width="stretch",
                                 help="Encolar para Instagram/Facebook (franjas de config.yaml)"):
                        from publishers import schedule
                        try:
                            schedule.enqueue(video["path"])
                            st.toast("En cola para Instagram/Facebook")
                        except (OSError, ValueError) as e:
                            st.error(f"No se pudo encolar: {e}")
                with btn_cols[1]:
                    if st.button("↩️", key=f"unapprove_{video['name']}", width="stretch",
                                 help="Move back to pending"):
                        unapprove_video(video['path'])
                        st.rerun()

                # STEP 73 §4: TikTok is uploaded by hand from the app; this hands over the
                # file and the text, and records the upload so the queue and stats know.
                _tk_done = manual_tiktok_row(video["name"], _attempts)
                tk_cols = st.columns(2)
                with tk_cols[0]:
                    if st.button("🎵 Preparar para TikTok", key=f"tkprep_{video['name']}", width="stretch",
                                 help="Muestra el MP4 en Finder y copia el texto de TikTok"):
                        _tk = resolve_upload_metadata(video["name"], script, "tiktok",
                                                      video.get("type", "educational"), category,
                                                      st.session_state,
                                                      generated=(video.get("meta") or {}).get("metadata"))
                        try:
                            prepare_for_tiktok(video["path"], tiktok_caption(
                                _tk["title"], _tk["description"], _tk["hashtags"]))
                            st.toast("Texto copiado. El vídeo está seleccionado en Finder.")
                        except (OSError, subprocess.CalledProcessError) as e:
                            st.error(f"No se pudo preparar para TikTok: {e}")
                with tk_cols[1]:
                    if _tk_done:
                        st.caption(f"✅ Subido a TikTok a mano · {_tk_done.get('at', '')[:16].replace('T', ' ')}")
                    elif st.button("✅ Marcar como subido a mano", key=f"tkmanual_{video['name']}",
                                   width="stretch", help="Registra que lo subiste a TikTok desde la app"):
                        _tk = resolve_upload_metadata(video["name"], script, "tiktok",
                                                      video.get("type", "educational"), category,
                                                      st.session_state,
                                                      generated=(video.get("meta") or {}).get("metadata"))
                        try:
                            record_manual_tiktok(video["name"], video["path"], tiktok_caption(
                                _tk["title"], _tk["description"], _tk["hashtags"]))
                            st.rerun()
                        except OSError as e:
                            st.error(f"No se pudo registrar la subida: {e}")

                st.markdown("---")

        # Bulk upload
        if target_platforms and len(approved) > 1 and not (_yt_block and "YouTube Shorts" in target_platforms):
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
                        "Facebook Reels": "facebook",
                    }
                    uploaded_count = 0
                    from upload_limits import run_batch

                    def _bulk_one(video):
                        nonlocal_state["i"] += 1
                        i = nonlocal_state["i"]
                        results = []
                        script = script_for_upload(video)
                        category = script.get("_meta", {}).get("category", "")

                        any_success = False
                        platforms_done = []
                        for pname in target_platforms:
                            pkey = bulk_platform_map.get(pname, pname.lower())
                            if pkey in setup_pending:     # failed for its setup earlier in this batch
                                continue
                            # Was generate_metadata(script, ...) + adapt, which
                            # ignored session_state entirely and published text
                            # the operator never saw. One resolver now serves
                            # both upload paths.
                            adapted = resolve_upload_metadata(
                                video["name"], script, pkey,
                                video.get("type", "educational"), category,
                                st.session_state, generated=(video.get("meta") or {}).get("metadata"),
                            )
                            # No duplicate override in bulk: that is a per-video decision.
                            _v = _guard_decide(video["name"], pkey, manager=manager,
                                               **upload_content(video, script, adapted["title"],
                                                                adapted["description"]))
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
                            results.append(result)
                            if isinstance(result, dict) and result.get("locked"):
                                st.warning(f"{video['name']} · {pname}: {result['error']}")
                            setup_msg = note_setup_failure(setup_pending, pkey, result)
                            if setup_msg:
                                st.error(setup_msg)
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
                                "title": adapted["title"],
                            })
                            nonlocal_state["uploaded"] += 1

                        progress.progress((i + 1) / len(approved))
                        return results

                    nonlocal_state = {"i": -1, "uploaded": 0}
                    setup_pending = set()
                    # STEP 67: the batch stops at the first upload limit.
                    stopped = run_batch(approved, _bulk_one)
                    uploaded_count = nonlocal_state["uploaded"]
                    if stopped:
                        st.error(f"{stopped} Lote detenido tras {uploaded_count} vídeos.")
                    else:
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
                    if video.get("damaged"):
                        st.error(f"⚠️ {video['damaged']}")
                    upload_info = video.get("upload_info", {})
                    platforms_str = ", ".join(upload_info.get("platforms", ["Unknown"]))
                    uploaded_at = upload_info.get("uploaded_at", "")[:16]
                    st.caption(f"{video['type']} | Uploaded to: {platforms_str} | {uploaded_at}")

                    if video["path"].exists():
                        lazy_video(video["path"], f"upload_{video['path'].name}")

                with col2:
                    upload_title = upload_info.get("title", "")
                    if upload_title:
                        st.caption(f"Title: {upload_title[:60]}...")
                    if video["path"].exists():
                        lazy_download(video["path"], f"dl_uploaded_{video['name']}")

                st.markdown("---")

    # Upload history (session)
    if st.session_state.upload_history:
        with st.expander("Recent Upload Log"):
            for entry in reversed(st.session_state.upload_history[-10:]):
                icon = "✅" if entry["status"] == "success" else "❌"
                st.write(f"{icon} **{entry['video']}** → {entry['platform']} ({entry['time'][:16]})")


# ============== LIBRARY PAGE ==============
elif page == "Library":
    st.markdown("## Biblioteca")

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
            st.metric("Tipos de vídeo", len(set(v["type"] for v in all_videos)))

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
            filter_type = st.selectbox("Filtrar", types, key="lib_filter",
                                       format_func=lambda k: "Todos" if k == "All" else type_label(k))
        with fc2:
            search = st.text_input("Search", placeholder="Search by name...")

        filtered = all_videos
        if filter_type != "All":
            filtered = [v for v in filtered if v["type"] == filter_type]
        if search:
            filtered = [v for v in filtered if search.lower() in v["name"].lower()]

        # Nine per page. The grid used to draw every video on disk at once.
        per_page = 9
        pages = max(1, -(-len(filtered) // per_page))
        page_no = 1
        if pages > 1:
            page_no = st.number_input("Página", 1, pages, 1, key="lib_page")
        start = (page_no - 1) * per_page
        st.write(f"Showing {start + 1 if filtered else 0}–"
                 f"{min(start + per_page, len(filtered))} of {len(filtered)} videos")
        st.markdown("---")

        shown = filtered[start:start + per_page]
        rows = [shown[i:i+3] for i in range(0, len(shown), 3)]
        for row in rows:
            cols = st.columns(3)
            for idx, video in enumerate(row):
                with cols[idx]:
                    name = f"**{video['name'][:20]}...**" if len(video['name']) > 20 else f"**{video['name']}**"
                    st.write(name)
                    st.caption(f"{video['type']} | {video['created'].strftime('%m/%d %H:%M')}")
                    if video["path"].exists():
                        lazy_video(video["path"], f"lib_{video['path'].name}")
                    # output/video/ artifacts had no road out of the library.
                    # Promotion moves them into pending/, where they take the
                    # same Review -> Approve -> guarded Upload route as
                    # everything else.
                    if video.get("stage") == "batch":
                        if st.button("⬆️ Promote to Review",
                                     key=f"promote_{video['path']}",
                                     width="stretch"):
                            verdict = promote_to_review(video["path"])
                            if verdict["ok"]:
                                st.success(
                                    f"{verdict['artifact']} → pending/"
                                    f"{verdict['video_type']}/ — "
                                    f"{verdict['reason']}")
                                st.rerun()
                            else:
                                st.error(f"Not promoted: {verdict['reason']}")
                    if st.button("🗑️ Delete", key=f"del_{video['path']}", width="stretch"):
                        delete_video(video["path"])
                        st.rerun()


# ============== SCHEDULER PAGE ==============
elif page == "Scheduler":
    st.markdown("## Programar")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown('<div class="section-header">Configuration</div>', unsafe_allow_html=True)

        videos_per_batch = st.number_input(
            "Videos per batch", min_value=1, max_value=20,
            value=st.session_state.scheduler_config["videos_per_batch"]
        )

        st.write("**Video types:**")
        # One checkbox per type in VIDEO_TYPES. Four were written out here by
        # hand, so fill_blank and pronunciation could not be produced from the
        # unattended batch at all — not misconfigured, absent.
        enabled_types = st.session_state.scheduler_config["types"]
        selected_types = [
            vtype for vtype in PANEL_TYPES
            # No key=: a keyed widget ignores value= after its first draw
            # and would freeze at whatever was checked then, which is what
            # tests/test_admin_platform_targets pins. Labels are distinct, so
            # Streamlit's own keying is correct here.
            if st.checkbox(type_label(vtype), value=vtype in enabled_types)
        ]

        if st.button("💾 Save Config", width="stretch"):
            st.session_state.scheduler_config = {
                "videos_per_batch": videos_per_batch,
                "types": selected_types
            }
            st.success("Saved!")

    with col2:
        st.markdown('<div class="section-header">Control</div>', unsafe_allow_html=True)
        # STEP 75 §1: «Start Scheduler» set a flag nothing read. Batches run from here.
        # STEP 75 §3: these are paid jobs. Say how many and roughly what they cost, ask,
        # and go through the batch queue (one at a time, survives a restart).
        _est = batch_estimate_usd(videos_per_batch)
        _cost = f"≈ \\${_est:.2f}" if _est is not None else "coste desconocido (sin historial)"
        st.caption(f"{videos_per_batch} vídeo(s) · {_cost} según la media de output/costs.")
        _ok = st.checkbox(f"Sí, generar {videos_per_batch} vídeo(s) ({_cost})", key="batch_now_confirm",
                          disabled=not selected_types)
        if st.button("🚀 Generate Batch Now", width="stretch", disabled=not (_ok and selected_types)):
            total = batch_add(scheduler_batch(selected_types, videos_per_batch))
            batch_advance()
            st.success(f"{videos_per_batch} vídeo(s) en la cola ({total} esperando). Se generan "
                       "de uno en uno — el progreso está en Queue.")
        if not selected_types:
            st.caption("Elige al menos un tipo.")


# ============== TOPICS PAGE ==============
#
# topic_history.coverage() has always returned exactly what this page draws.
# Its only caller was its own test: the memory was computed on every run and
# never rendered, so "se me han repetido como 4 videos con el mismo tema" had
# no screen that could have answered it.
#
# Every number here is COMPUTED at draw time. None is typed into a caption,
# because a hardcoded 22% is wrong the day after it is written.
elif page == "Topics":
    st.markdown("## Temas")
    st.caption("Which topics have been used, and which keep coming back. "
               "Counted from the scripts on disk, not from a stored tally.")

    report = topic_memory_report()

    if not report["total"]:
        st.info("No topics found. Add category files under content/topics/.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Topics", f"{report['total']:,}")
        c2.metric("Ever used", f"{report['used']:,}")
        c3.metric("Never used", f"{report['unused']:,}")
        c4.metric("Coverage", f"{report['percent_used']:.0f}%")

        st.progress(min(1.0, report["percent_used"] / 100.0))

        st.markdown('<div class="section-header">Repeats</div>',
                    unsafe_allow_html=True)
        repeats = report["repeats"]
        if not repeats:
            st.success("No topic has been used twice.")
        else:
            st.caption(f"{len(repeats)} topic(s) generated more than once, "
                       "worst first. This is the list that explains a "
                       "repeated video.")
            st.dataframe(
                [{"Category": r["category"], "Topic": r["topic_id"],
                  "Times": r["times"]} for r in repeats],
                width="stretch", hide_index=True)

        st.markdown('<div class="section-header">By category</div>',
                    unsafe_allow_html=True)
        st.dataframe(
            [{"Category": row["category"], "Total": row["total"],
              "Used": row["used"], "Unused": row["unused"],
              "Coverage": f"{(100.0 * row['used'] / row['total']):.0f}%"
                          if row["total"] else "—"}
             for row in report["by_category"]],
            width="stretch", hide_index=True)


# ============== SETTINGS PAGE ==============
elif page == "Settings":
    st.markdown("## Ajustes")

    tab1, tab2, tab3 = st.tabs(["🔑 API Keys & Security", "🎬 Video Config", "🔊 Audio Config"])

    # ── API Keys Tab ──
    with tab1:
        st.markdown('<div class="section-header">API Key Management</div>', unsafe_allow_html=True)
        st.caption("Keys are stored in `.env` and never exposed in logs or version control.")

        # OpenRouter is the only paid AI (guion, voz, ASR, ilustraciones). Its key and voice live
        # in the environment or the Keychain; the panel only says where, never the value.
        import secret_store
        st.markdown("**OpenRouter (obligatoria)**")
        for env_var, label, description in (
                ("OPENROUTER_API_KEY", "Clave de OpenRouter", "Guion, voz, tiempos de palabra e ilustraciones"),
                ("OPENROUTER_VOICE_ID", "Voz de OpenRouter", "La voz premade del canal (Matilda)")):
            _where = secret_store.where(env_var)
            _css = "key-error" if _where == "no configurada" else "key-ok"
            st.markdown(f"**{label}** · `{env_var}`")
            st.markdown(f'<div class="key-status {_css}">{"FALTA" if _where == "no configurada" else _where}</div>',
                        unsafe_allow_html=True)
            st.caption(description)
        st.caption("Se guardan en el Llavero, no en un archivo: `security add-generic-password -s "
                   "english-ai-videos -a OPENROUTER_API_KEY -w` (igual con OPENROUTER_VOICE_ID).")
        st.markdown("---")

        api_groups = {
            "Voz": [
                ("ELEVENLABS_VOICE_ID", "Voice ID del canal", "Id de voz de cada petición; OpenRouter habla con OPENROUTER_VOICE_ID", False),
            ],
            "Social Media Uploads": [
                ("TIKTOK_CLIENT_KEY", "TikTok Client Key", "Content Posting API", False),
                ("TIKTOK_CLIENT_SECRET", "TikTok Client Secret", "Content Posting API", False),
                ("YOUTUBE_CLIENT_ID", "YouTube Client ID", "YouTube Data API v3", False),
                ("YOUTUBE_CLIENT_SECRET", "YouTube Client Secret", "YouTube Data API v3", False),
                ("IG_USER_ID", "Instagram User ID", "Optional: only checked against the Page's (setup-check)", False),
                ("FB_PAGE_ID", "Facebook Page ID", "Reels Publishing API", False),
                ("FB_PAGE_TOKEN", "Facebook Page Token", "Long-lived Page token", False),
            ],
            "Email": [
                ("BREVO_API_KEY", "Brevo API Key", "Transactional email API", False),
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
                    if st.button("Save", key=f"save_{env_var}", width="stretch"):
                        if new_value:
                            try:
                                save_env_key(env_var, new_value)
                                st.success(f"Saved!")
                                st.rerun()
                            except (ValueError, OSError) as e:
                                st.error(f"No se guardó: {e}")
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
        config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}
        # STEP 75 §1: the width/height/fps/style, output.* and default-type editors were
        # removed; nothing reads those keys. Backgrounds are Pexels footage.
        st.caption("Nothing here is configurable from the panel: size, fps and backgrounds are "
                   "fixed by the renderers. Edit config.yaml for anything else.")
        with st.expander("Raw config.yaml"):
            st.code((ROOT / "config.yaml").read_text(encoding="utf-8"), language="yaml")

    # ── Audio Config Tab ──
    with tab3:
        import yaml
        audio_config = (yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}).get("audio", {})
        # Only the four keys tts_bilingual reads. provider, voice_id, model, humanize and
        # speaker_boost had editors here and no reader (STEP 75 §1).
        st.caption("La voz va por OpenRouter (OPENROUTER_VOICE_ID); el modelo, de config.yaml audio.openrouter_model.")
        col1, col2 = st.columns(2)
        with col1:
            global_speed = st.slider("Global Speed", 0.5, 2.0, float(audio_config.get("global_speed", 1.0)), 0.05)
            stability = st.slider("Stability", 0.0, 1.0, float(audio_config.get("stability", 0.50)), 0.05)
        with col2:
            similarity = st.slider("Similarity Boost", 0.0, 1.0, float(audio_config.get("similarity_boost", 0.80)), 0.05)
            style = st.slider("Style", 0.0, 1.0, float(audio_config.get("style", 0.05)), 0.05)

        if st.button("💾 Save Audio Config", type="primary", width="stretch"):
            from config_edit import patch_config
            try:
                saved = patch_config({("audio", "global_speed"): global_speed, ("audio", "stability"): stability,
                                      ("audio", "similarity_boost"): similarity, ("audio", "style"): style})
                st.success(f"Audio config saved (copia: {saved.name}).")
            except (OSError, KeyError, TypeError, ValueError) as e:
                st.error(f"No se guardó nada: {e}")

    # STEP 74 §3: the same cleanup as `make clean`; the table is `make clean-dry`.
    st.markdown('<div class="section-header">Limpiar</div>', unsafe_allow_html=True)
    _clean = _cleanup_module()
    _plans = None
    # STEP 80 §3: walking the output tree took 0.4–1.7 s on every visit; only on request now
    if st.toggle("Calcular qué se puede limpiar", key="cleanup_show"):
        try:
            _plans = _clean.plan()
        except (OSError, subprocess.CalledProcessError) as e:
            st.error(f"No se pudo calcular la limpieza: {e}")
    if _plans is not None:
        _total = sum(p["bytes"] for p in _plans)
        st.caption("Borra vídeos ya subidos, rechazados, artefactos de más de 14 días, intermedios "
                   "y cachés. Nunca toca lo aprobado, audio/TTS, contenido, registros ni lo que git o un test usa.")
        st.code(_clean.table(_plans), language=None)
        _busy = cleanup_blockers()
        if _busy:
            st.warning(f"Hay trabajos en marcha ({', '.join(_busy)}). Espera a que terminen para limpiar.")
        _sure = st.checkbox(f"Sí, borrar {_clean.human(_total)}", key="cleanup_confirm",
                            disabled=bool(_busy) or not _total)
        if st.button("🧹 Limpiar", key="cleanup_run", disabled=not _sure or bool(_busy) or not _total):
            try:
                _freed = _clean.delete([p for pl in _clean.plan() for p in pl["paths"]])
                st.success(f"Liberado: {_clean.human(_freed)}")
            except (_clean.RefusedPath, OSError) as e:
                st.error(f"Limpieza detenida: {e}")


# ============== MANIM STUDIO ==============
# Everything lives in src/manim_studio.py; this file only routes to it.
elif page == "Manim":
    import manim_studio
    manim_studio.render()


# ============== LOGS PAGE ==============
elif page == "Performance":
    st.markdown("## Rendimiento")
    st.caption("Lo que hicieron los vídeos publicados en YouTube (lectura gratuita con el token del canal). "
               "Un vídeo de menos de 3 días todavía no se juzga.")
    import channel_stats
    if st.button("🔄 Actualizar estadísticas", type="primary"):
        try:
            with st.spinner("Leyendo YouTube…"):
                path = channel_stats.refresh()
            st.success(f"Guardado en {path.relative_to(ROOT)}")
        except Exception as e:                              # noqa: BLE001 — shown, not raised
            st.error(f"No se pudieron leer las estadísticas: {e}")
    snap = channel_stats.latest()
    if not snap:
        st.info("Todavía no hay estadísticas: pulsa «Actualizar estadísticas».")
    else:
        s = channel_stats.summary(snap["videos"])
        st.caption(f"Leídas {snap['read_at']} · {len(snap['videos'])} vídeos · Facebook: "
                   f"{(snap.get('facebook') or {}).get('note', '—') if isinstance(snap.get('facebook'), dict) else snap.get('facebook')}")
        st.markdown("### Por formato")
        st.dataframe([{"formato": f["type"], "vídeos": f["count"], "mediana": f["median"], "media": f["mean"],
                       "de +3 días": f["mature_count"], "mediana +3 días": f["mature_median"]} for f in s["formats"]],
                     hide_index=True)
        cols = st.columns(2)
        _row = lambda v: {"vistas": v["views"], "días publicado": v.get("days"), "formato": v["type"], "título": v["title"]}
        with cols[0]:
            st.markdown("### Top 10")
            st.dataframe([_row(v) for v in s["top"]], hide_index=True)
        with cols[1]:
            st.markdown("### Los 10 de abajo")
            st.dataframe([_row(v) for v in s["bottom"]], hide_index=True)
        st.markdown("### Por categoría")
        st.dataframe([{"categoría": c["category"], "vídeos": c["count"], "mediana": c["median"]} for c in s["categories"]],
                     hide_index=True)
    if snap:
        import ai_background
        st.markdown("### Fondo IA contra stock («Cómo se dice»)")
        ab = ai_background.compare(snap["videos"])
        st.dataframe([{"grupo": g, "vídeos de +3 días": v["n"], "mediana": v["median"], "media": v["mean"]}
                      for g, v in ab["groups"].items()], hide_index=True)
        if not ab["ready"]:
            st.caption(f"Todavía no se compara: cada grupo necesita {ai_background.MIN_PER_GROUP} vídeos de más de 3 días.")
    st.markdown("### Prioridad de la cola")
    try:
        import queue_priority
        _ranked = queue_priority.ranked(list(_queue_guard().queued_scripts()), snap)
        st.dataframe([{"guion": p.name, "prioridad": round(pr), "por qué": why} for p, pr, why in _ranked[:25]],
                     hide_index=True)
    except Exception as e:                                  # noqa: BLE001
        st.caption(f"Prioridad no disponible: {e}")

elif page == "Logs":
    st.markdown("## Registros")

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

    _log_names = {"All": "Todos", "Active": "En marcha", "Completed": "Terminados", "Failed": "Fallidos"}
    log_filter = st.selectbox("Filtrar", list(_log_names), format_func=_log_names.get)

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
        if st.button("Clear Failed Jobs", width="stretch"):
            jobs["history"] = [j for j in jobs.get("history", []) if j.get("status") != "failed"]
            save_jobs(jobs)
            st.success("Cleared!")
            st.rerun()
    with c2:
        if st.button("Clear All History", width="stretch"):
            jobs["history"] = []
            save_jobs(jobs)
            st.success("Cleared!")
            st.rerun()
