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
import time
from pathlib import Path
from datetime import datetime
from typing import Optional
import subprocess
import uuid

logger = logging.getLogger(__name__)

# Setup paths
ROOT = Path(__file__).parent.parent
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

# Output directories
OUTPUT_DIR = ROOT / "output"
SCRIPTS_DIR = OUTPUT_DIR / "scripts"
AUDIO_DIR = OUTPUT_DIR / "audio"
VIDEO_DIR = OUTPUT_DIR / "video"
PENDING_DIR = OUTPUT_DIR / "pending"
APPROVED_DIR = OUTPUT_DIR / "approved"
REJECTED_DIR = OUTPUT_DIR / "rejected"

for d in [PENDING_DIR, APPROVED_DIR, REJECTED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============== PERSISTENT PROGRESS TRACKING ==============
JOBS_FILE = OUTPUT_DIR / "generation_jobs.json"


def load_jobs() -> dict:
    if JOBS_FILE.exists():
        try:
            with open(JOBS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"active": [], "history": []}


def save_jobs(jobs: dict):
    with open(JOBS_FILE, 'w') as f:
        json.dump(jobs, f, indent=2, default=str)


def create_job(video_type: str, category: str = None, topic: str = None) -> str:
    job_id = str(uuid.uuid4())[:8]
    job = {
        "id": job_id,
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
    jobs = load_jobs()
    jobs["active"].append(job)
    save_jobs(jobs)
    return job_id


def update_job(job_id: str, **kwargs):
    jobs = load_jobs()
    for job in jobs["active"]:
        if job["id"] == job_id:
            job.update(kwargs)
            job["updated_at"] = datetime.now().isoformat()
            break
    save_jobs(jobs)


def complete_job(job_id: str, success: bool, video_path: str = None, error: str = None):
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
                                topic_name: str = None) -> dict:
    result = {"success": False, "video_path": None, "error": None}

    try:
        update_job(job_id, status="running", step_number=1,
                   current_step="Selecting topic...", progress=5)

        if category and topic_name:
            topic = find_topic(category, topic_name)
        else:
            category, topic = get_random_topic()
            topic_name = (topic.get("english") or topic.get("topic") or topic.get("wrong")
                         or topic.get("word") or topic.get("sentence") or str(topic))

        update_job(job_id, category=category, topic=topic_name,
                   current_step=f"Topic: '{topic_name}'", progress=10)

        # Step 2: Generate script
        update_job(job_id, step_number=2,
                   current_step="Generating script with GPT...", progress=15)

        script_data = generate_script(category, topic, video_type)

        import re as _re
        output_name = _re.sub(r'[^\w\-]', '_', topic_name).strip('_').lower()
        output_name = _re.sub(r'_+', '_', output_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_name = f"{output_name}_{timestamp}"

        script_dir = SCRIPTS_DIR / video_type
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / f"{unique_name}.json"

        with open(script_path, 'w', encoding='utf-8') as f:
            json.dump(script_data, f, ensure_ascii=False, indent=2)

        update_job(job_id, current_step=f"Script generated", progress=30)

        # Step 3: Generate TTS audio
        tts_provider = os.getenv("TTS_PROVIDER", "elevenlabs").lower()
        tts_modules = {
            "elevenlabs": "tts_elevenlabs",
            "openai": "tts_openai",
            "google": "tts_google",
            "edge": "tts",
        }
        tts_module = tts_modules.get(tts_provider, "tts_elevenlabs")

        update_job(job_id, step_number=3,
                   current_step=f"Generating audio ({tts_provider})...", progress=35)

        audio_dir = AUDIO_DIR / video_type
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_path = audio_dir / f"{unique_name}.mp3"

        full_script = script_data.get('full_script', '')
        if not full_script or len(full_script.strip()) < 10:
            raise Exception(f"Script text too short ({len(full_script)} chars)")

        tts_script_path = audio_dir / f"{unique_name}.json"
        with open(tts_script_path, 'w', encoding='utf-8') as f:
            json.dump(script_data, f, ensure_ascii=False, indent=2)

        tts_cmd = [
            "python3", str(ROOT / "src" / f"{tts_module}.py"),
            "--script", str(tts_script_path.resolve()),
            "-o", str(audio_path.resolve())
        ]

        tts_env = os.environ.copy()
        tts_env["PYTHONPATH"] = str(ROOT / "src")

        tts_result = subprocess.run(tts_cmd, capture_output=True, text=True,
                                    timeout=300, cwd=str(ROOT), env=tts_env)

        if tts_result.returncode != 0:
            raise Exception(f"TTS failed: {tts_result.stderr[-500:]}")
        if not audio_path.exists():
            raise Exception(f"Audio file not created")
        if audio_path.stat().st_size < 1000:
            raise Exception(f"Audio file too small ({audio_path.stat().st_size} bytes)")

        update_job(job_id, current_step="Audio generated", progress=55)

        # Merge script data with TTS timestamps
        json_path = audio_path.with_suffix('.json')
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                tts_data = json.load(f)
            for key, value in script_data.items():
                if key not in ('words', 'segments', 'duration', 'segment_times'):
                    tts_data[key] = value
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(tts_data, f, ensure_ascii=False, indent=2)

        # Step 4: Render video
        update_job(job_id, step_number=4,
                   current_step="Rendering video...", progress=60)

        json_path = audio_path.with_suffix('.json')
        if not json_path.exists():
            raise Exception(f"TTS data file missing")

        pending_type_dir = PENDING_DIR / video_type
        pending_type_dir.mkdir(parents=True, exist_ok=True)
        video_path = pending_type_dir / f"{unique_name}.mp4"

        video_cmd = [
            "python3", "-m", "video",
            "-a", str(audio_path.resolve()),
            "-d", str(json_path.resolve()),
            "-o", str(video_path.resolve()),
            "-t", video_type
        ]

        video_result = subprocess.run(video_cmd, capture_output=True, text=True,
                                      cwd=str(ROOT / "src"), timeout=600)

        if video_result.returncode != 0:
            raise Exception(f"Video render failed: {video_result.stderr[-500:]}")
        if not video_path.exists():
            raise Exception("Video file not created")
        if video_path.stat().st_size < 1000:
            raise Exception(f"Video file too small ({video_path.stat().st_size} bytes)")

        update_job(job_id, current_step="Video rendered", progress=95)

        # Save metadata
        meta_path = video_path.with_suffix('.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump({
                "job_id": job_id,
                "video_type": video_type,
                "category": category,
                "topic": topic_name,
                "script_data": script_data,
                "created_at": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)

        result["success"] = True
        result["video_path"] = str(video_path)
        complete_job(job_id, success=True, video_path=str(video_path))

    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        result["error"] = error_msg
        complete_job(job_id, success=False, error=error_msg[:2000])
        logger.error("[Pipeline ERROR]: %s", error_msg)

    return result


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
                    "created": datetime.fromtimestamp(video_file.stat().st_mtime)
                })
    return sorted(videos, key=lambda x: x["created"], reverse=True)


def get_approved_videos() -> list:
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
                videos.append({
                    "path": video_file,
                    "type": type_dir.name,
                    "name": video_file.stem,
                    "meta": meta,
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
                    "created": datetime.fromtimestamp(video_file.stat().st_mtime)
                })
    return sorted(videos, key=lambda x: x["created"], reverse=True)


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
    active_jobs = get_active_jobs()
    all_videos = pending + approved + library

    # Metrics row
    cols = st.columns(5)
    metrics = [
        ("Total Videos", len(all_videos), "📹"),
        ("Pending", len(pending), "📝"),
        ("Approved", len(approved), "✅"),
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

    # Active jobs
    if active_jobs:
        st.markdown('<div class="section-header">⚡ Currently Generating</div>', unsafe_allow_html=True)
        for job in active_jobs:
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"**{job['video_type'].upper()}** — {job.get('topic', 'Selecting...')}")
                st.progress(job.get('progress', 0) / 100)
                st.caption(job.get('current_step', 'Initializing...'))
            with c2:
                st.code(job['id'])
                if job.get("status") == "running":
                    time.sleep(2)
                    st.rerun()

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
                    job_id = create_job(vtype)
                    with st.spinner(f"Generating {label}..."):
                        run_pipeline_with_tracking(job_id, vtype)
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

        active_jobs = get_active_jobs()
        if active_jobs:
            for job in active_jobs:
                st.markdown(f"**{job['video_type'].upper()}** — {job.get('topic', 'Selecting...')}")
                st.progress(job.get('progress', 0) / 100)
                st.caption(job.get('current_step', 'Initializing...'))
                if job["status"] == "running":
                    time.sleep(1)
                    st.rerun()
            st.markdown("---")

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
            job_id = create_job(video_type, category, topic_name)
            st.success(f"Generation started! Job: `{job_id}`")
            with st.spinner("Generating video..."):
                result = run_pipeline_with_tracking(job_id, video_type, category, topic_name)
            if result["success"]:
                st.success("Video generated!")
                st.balloons()
            else:
                st.error(f"Failed: {result.get('error', 'Unknown')[:300]}")
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
                total = len(st.session_state.queue_items)
                progress_bar = st.progress(0)
                status_text = st.empty()
                completed = 0
                errors = 0

                while st.session_state.queue_items:
                    item = st.session_state.queue_items.pop(0)
                    job_id = create_job(item["type"])
                    status_text.info(f"Processing {completed + 1}/{total}: {item['type']}...")
                    result = run_pipeline_with_tracking(job_id, item["type"])
                    if result["success"]:
                        completed += 1
                    else:
                        errors += 1
                    progress_bar.progress((completed + errors) / total)

                status_text.success(f"Done! {completed} successful, {errors} failed")
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
                if st.checkbox(
                    f"{platform['icon']} {platform['name']}",
                    value=enabled,
                    disabled=not enabled,
                    key=f"target_{platform['name']}"
                ):
                    target_platforms.append(platform["name"])

        st.markdown("---")

        # Video list with upload buttons
        for video in approved:
            col1, col2, col3 = st.columns([3, 2, 1])

            with col1:
                st.write(f"**{video['name']}**")
                st.caption(f"{video['type']} | {video['created'].strftime('%Y-%m-%d %H:%M')}")

            with col2:
                # Generate caption from metadata
                caption = ""
                hashtags = ""
                if video.get("meta") and "script_data" in video["meta"]:
                    script = video["meta"]["script_data"]
                    caption = script.get("hook", script.get("question", script.get("statement", "")))
                    tags = script.get("hashtags", ["#LearnEnglish", "#AprendeIngles"])
                    hashtags = " ".join(tags) if isinstance(tags, list) else str(tags)

                with st.expander("Edit Caption"):
                    vid_caption = st.text_area(
                        "Caption",
                        value=f"{caption}\n\n{hashtags}",
                        key=f"caption_{video['name']}",
                        height=80
                    )

            with col3:
                if target_platforms:
                    if st.button("📤 Upload", key=f"upload_{video['name']}", use_container_width=True):
                        try:
                            from uploader import get_upload_manager
                            manager = get_upload_manager()

                            platform_map = {
                                "TikTok": "tiktok",
                                "YouTube Shorts": "youtube",
                                "Instagram Reels": "instagram",
                            }
                            for platform_name in target_platforms:
                                platform_key = platform_map.get(platform_name, platform_name.lower())
                                with st.spinner(f"Uploading to {platform_name}..."):
                                    result = manager.upload(
                                        platform_key,
                                        str(video["path"]),
                                        title=vid_caption.split("\n")[0][:100],
                                        description=vid_caption,
                                        hashtags=hashtags.split() if hashtags else []
                                    )
                                    if result.get("success"):
                                        st.success(f"Uploaded to {platform_name}!")
                                        st.session_state.upload_history.append({
                                            "video": video["name"],
                                            "platform": platform_name,
                                            "time": datetime.now().isoformat(),
                                            "status": "success"
                                        })
                                    else:
                                        st.error(f"Failed: {result.get('error', 'Unknown error')}")
                        except ImportError:
                            st.error("Upload module not available. Check installation.")
                        except Exception as e:
                            st.error(f"Upload error: {str(e)}")
                else:
                    st.button("📤 Upload", key=f"upload_{video['name']}", disabled=True, use_container_width=True)

                if st.button("↩️", key=f"unapprove_{video['name']}", use_container_width=True,
                             help="Move back to pending"):
                    unapprove_video(video['path'])
                    st.rerun()

        # Bulk upload
        if target_platforms and len(approved) > 1:
            st.markdown("---")
            st.markdown("**Bulk Upload**")
            if st.button(f"📤 Upload All {len(approved)} Videos to {', '.join(target_platforms)}", type="primary"):
                progress = st.progress(0)
                try:
                    from uploader import get_upload_manager
                    manager = get_upload_manager()

                    bulk_platform_map = {
                        "TikTok": "tiktok",
                        "YouTube Shorts": "youtube",
                        "Instagram Reels": "instagram",
                    }
                    for i, video in enumerate(approved):
                        caption = ""
                        if video.get("meta") and "script_data" in video["meta"]:
                            script = video["meta"]["script_data"]
                            caption = script.get("hook", script.get("question", ""))

                        for pname in target_platforms:
                            pkey = bulk_platform_map.get(pname, pname.lower())
                            manager.upload(
                                pkey,
                                str(video["path"]),
                                title=caption[:100],
                                description=caption,
                            )
                        progress.progress((i + 1) / len(approved))

                    st.success(f"Uploaded {len(approved)} videos!")
                except Exception as e:
                    st.error(f"Bulk upload error: {str(e)}")

    # Upload history
    if st.session_state.upload_history:
        st.markdown("---")
        st.markdown('<div class="section-header">Upload History</div>', unsafe_allow_html=True)
        for entry in reversed(st.session_state.upload_history[-10:]):
            icon = "✅" if entry["status"] == "success" else "❌"
            st.write(f"{icon} **{entry['video']}** → {entry['platform']} ({entry['time'][:16]})")


# ============== LIBRARY PAGE ==============
elif page == "Library":
    st.markdown("## 📚 Video Library")

    library = get_library_videos()
    pending = get_pending_videos()
    approved = get_approved_videos()
    all_videos = library + pending + approved

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
                progress = st.progress(0)
                status = st.empty()
                for i in range(videos_per_batch):
                    vtype = selected_types[i % len(selected_types)]
                    job_id = create_job(vtype)
                    status.info(f"Generating {i+1}/{videos_per_batch}: {vtype}...")
                    run_pipeline_with_tracking(job_id, vtype)
                    progress.progress((i + 1) / videos_per_batch)
                status.success("Batch complete!")


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
