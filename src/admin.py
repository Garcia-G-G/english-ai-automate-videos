#!/usr/bin/env python3
"""
Admin Dashboard for English AI Videos
Web interface for generating, reviewing, and managing videos.

Run: streamlit run src/admin.py
Opens: http://localhost:8501
"""

import streamlit as st
import json
import os
import sys
import shutil
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Callable
import subprocess
import uuid

# Setup paths
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

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

# Ensure directories exist
for d in [PENDING_DIR, APPROVED_DIR, REJECTED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============== PERSISTENT PROGRESS TRACKING ==============
JOBS_FILE = OUTPUT_DIR / "generation_jobs.json"


def load_jobs() -> dict:
    """Load all generation jobs from persistent storage."""
    if JOBS_FILE.exists():
        try:
            with open(JOBS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"active": [], "history": []}


def save_jobs(jobs: dict):
    """Save jobs to persistent storage."""
    with open(JOBS_FILE, 'w') as f:
        json.dump(jobs, f, indent=2, default=str)


def create_job(video_type: str, category: str = None, topic: str = None) -> str:
    """Create a new generation job and return its ID."""
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
    """Update a job's status and progress."""
    jobs = load_jobs()

    for job in jobs["active"]:
        if job["id"] == job_id:
            job.update(kwargs)
            job["updated_at"] = datetime.now().isoformat()
            break

    save_jobs(jobs)


def complete_job(job_id: str, success: bool, video_path: str = None, error: str = None):
    """Mark a job as complete and move to history."""
    jobs = load_jobs()

    # Find and remove from active
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

        # Add to history (keep last 20)
        jobs["history"].insert(0, completed_job)
        jobs["history"] = jobs["history"][:20]

    save_jobs(jobs)


def get_active_jobs() -> list:
    """Get all currently active jobs."""
    jobs = load_jobs()
    return jobs.get("active", [])


def get_job_history(limit: int = 5) -> list:
    """Get recent job history."""
    jobs = load_jobs()
    return jobs.get("history", [])[:limit]


# ============== PIPELINE WITH PROGRESS TRACKING ==============

def run_pipeline_with_tracking(job_id: str, video_type: str, category: str = None,
                                topic_name: str = None) -> dict:
    """Run the full pipeline with persistent progress tracking."""

    result = {
        "success": False,
        "video_path": None,
        "error": None
    }

    try:
        # Step 1: Select topic
        update_job(job_id,
                   status="running",
                   step_number=1,
                   current_step="Step 1/4: Selecting topic...",
                   progress=5)

        if category and topic_name:
            topic = find_topic(category, topic_name)
        else:
            category, topic = get_random_topic()
            topic_name = topic.get("english") or topic.get("topic") or topic.get("wrong")

        update_job(job_id,
                   category=category,
                   topic=topic_name,
                   current_step=f"Step 1/4: Topic selected - '{topic_name}'",
                   progress=10)

        # Step 2: Generate script with GPT
        update_job(job_id,
                   step_number=2,
                   current_step=f"Step 2/4: Generating script with GPT...",
                   progress=15)

        script_data = generate_script(category, topic, video_type)

        # Save script
        output_name = topic_name.replace(' ', '_').lower()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_name = f"{output_name}_{timestamp}"

        script_dir = SCRIPTS_DIR / video_type
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / f"{unique_name}.json"

        with open(script_path, 'w', encoding='utf-8') as f:
            json.dump(script_data, f, ensure_ascii=False, indent=2)

        update_job(job_id,
                   current_step=f"Step 2/4: Script generated - {script_path.name}",
                   progress=30)

        # Step 3: Generate TTS audio
        update_job(job_id,
                   step_number=3,
                   current_step="Step 3/4: Generating audio with OpenAI TTS...",
                   progress=35)

        audio_dir = AUDIO_DIR / video_type
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_path = audio_dir / f"{unique_name}.mp3"

        full_script = script_data.get('full_script', '')

        tts_cmd = [
            "python3", str(ROOT / "src" / "tts_openai.py"),
            full_script,
            "-o", str(audio_path)
        ]

        tts_result = subprocess.run(tts_cmd, capture_output=True, text=True)

        if tts_result.returncode != 0:
            raise Exception(f"TTS failed: {tts_result.stderr}")

        update_job(job_id,
                   current_step=f"Step 3/4: Audio generated - {audio_path.name}",
                   progress=55)

        # Merge script data with TTS timestamps
        json_path = audio_path.with_suffix('.json')
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                tts_data = json.load(f)
            for key, value in script_data.items():
                if key not in tts_data or key != 'words':
                    tts_data[key] = value
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(tts_data, f, ensure_ascii=False, indent=2)

        # Step 4: Render video
        update_job(job_id,
                   step_number=4,
                   current_step="Step 4/4: Rendering video (this may take a minute)...",
                   progress=60)

        pending_type_dir = PENDING_DIR / video_type
        pending_type_dir.mkdir(parents=True, exist_ok=True)
        video_path = pending_type_dir / f"{unique_name}.mp4"

        video_cmd = [
            "python3", str(ROOT / "src" / "video.py"),
            "-a", str(audio_path),
            "-d", str(json_path),
            "-o", str(video_path),
            "-t", video_type
        ]

        video_result = subprocess.run(video_cmd, capture_output=True, text=True)

        if video_result.returncode != 0:
            raise Exception(f"Video generation failed: {video_result.stderr}")

        update_job(job_id,
                   current_step=f"Step 4/4: Video rendered - {video_path.name}",
                   progress=95)

        # Save metadata alongside video
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

        # Complete the job
        complete_job(job_id, success=True, video_path=str(video_path))

    except Exception as e:
        result["error"] = str(e)
        complete_job(job_id, success=False, error=str(e))

    return result


# ============== HELPER FUNCTIONS ==============

def get_pending_videos() -> list:
    """Get all videos pending review."""
    videos = []
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
    """Get all approved videos."""
    videos = []
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
    """Get all videos in the library."""
    videos = []
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
    """Move video to approved folder."""
    video_type = video_path.parent.name
    dest_dir = APPROVED_DIR / video_type
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(video_path), str(dest_dir / video_path.name))
    meta_path = video_path.with_suffix('.json')
    if meta_path.exists():
        shutil.move(str(meta_path), str(dest_dir / meta_path.name))


def reject_video(video_path: Path):
    """Move video to rejected folder."""
    video_type = video_path.parent.name
    dest_dir = REJECTED_DIR / video_type
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(video_path), str(dest_dir / video_path.name))
    meta_path = video_path.with_suffix('.json')
    if meta_path.exists():
        shutil.move(str(meta_path), str(dest_dir / meta_path.name))


def delete_video(video_path: Path):
    """Delete a video and its metadata."""
    video_path.unlink(missing_ok=True)
    meta_path = video_path.with_suffix('.json')
    meta_path.unlink(missing_ok=True)


# ============== STREAMLIT UI ==============

st.set_page_config(
    page_title="English AI Videos - Admin",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better progress display
st.markdown("""
<style>
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #4CAF50, #8BC34A);
    }
    .job-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460;
        border-radius: 12px;
        padding: 16px;
        margin: 8px 0;
    }
    .job-running {
        border-left: 4px solid #4CAF50;
        animation: pulse 2s infinite;
    }
    .job-completed {
        border-left: 4px solid #2196F3;
    }
    .job-failed {
        border-left: 4px solid #f44336;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }
    .step-indicator {
        font-family: monospace;
        background: #0d1b2a;
        padding: 8px 12px;
        border-radius: 6px;
        margin: 4px 0;
    }
    .progress-container {
        background: #1b263b;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar navigation
st.sidebar.title("🎬 Video Admin")
page = st.sidebar.radio(
    "Navigate",
    ["🏠 Dashboard", "🎥 Generate", "📋 Queue", "✅ Review", "📤 Upload", "📚 Library", "⏰ Scheduler"],
    index=0
)

# Initialize session state
if 'queue_items' not in st.session_state:
    st.session_state.queue_items = []
if 'scheduler_enabled' not in st.session_state:
    st.session_state.scheduler_enabled = False
if 'scheduler_config' not in st.session_state:
    st.session_state.scheduler_config = {
        "videos_per_batch": 5,
        "interval_minutes": 60,
        "types": ["quiz", "educational", "true_false"]
    }


# ============== DASHBOARD PAGE ==============
if page == "🏠 Dashboard":
    st.title("🎬 English AI Videos Dashboard")

    # Stats
    col1, col2, col3, col4 = st.columns(4)

    pending = get_pending_videos()
    approved = get_approved_videos()
    library = get_library_videos()
    active_jobs = get_active_jobs()

    with col1:
        st.metric("📝 Pending Review", len(pending))
    with col2:
        st.metric("✅ Approved", len(approved))
    with col3:
        st.metric("📚 Library", len(library))
    with col4:
        st.metric("⚡ Active Jobs", len(active_jobs))

    # Active jobs section
    if active_jobs:
        st.divider()
        st.subheader("⚡ Currently Generating")
        for job in active_jobs:
            with st.container():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**{job['video_type']}** - {job.get('topic', 'Selecting...')}")
                    st.progress(job.get('progress', 0) / 100)
                    st.caption(job.get('current_step', 'Initializing...'))
                with col2:
                    st.write(f"Job: `{job['id']}`")

    st.divider()

    # Quick actions
    st.subheader("⚡ Quick Actions")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🎲 Generate Random Quiz", use_container_width=True):
            job_id = create_job("quiz")
            st.session_state.generating_job = job_id
            st.switch_page("pages" if False else st.rerun())
    with col2:
        if st.button("📚 Generate Random Educational", use_container_width=True):
            job_id = create_job("educational")
            st.session_state.generating_job = job_id
    with col3:
        if st.button("❓ Generate Random True/False", use_container_width=True):
            job_id = create_job("true_false")
            st.session_state.generating_job = job_id

    # Recent history
    st.divider()
    st.subheader("📊 Recent Generation History")

    history = get_job_history(5)
    if history:
        for job in history:
            status_icon = "✅" if job["status"] == "completed" else "❌"
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f"{status_icon} **{job.get('topic', 'Unknown')}** ({job['video_type']})")
            with col2:
                st.write(job["status"])
            with col3:
                if job.get("completed_at"):
                    completed = datetime.fromisoformat(job["completed_at"])
                    st.write(completed.strftime("%H:%M"))
    else:
        st.info("No generation history yet")


# ============== GENERATE PAGE ==============
elif page == "🎥 Generate":
    st.title("🎥 Generate Video")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("⚙️ Settings")

        video_type = st.selectbox(
            "Video Type",
            VIDEO_TYPES,
            index=0,
            help="Select the type of video to generate"
        )

        selection_mode = st.radio(
            "Topic Selection",
            ["🎲 Random", "📂 Select Category", "🎯 Specific Topic"],
            index=0
        )

        category = None
        topic_name = None

        if selection_mode == "📂 Select Category":
            categories = list_categories()
            category = st.selectbox("Category", categories)
        elif selection_mode == "🎯 Specific Topic":
            categories = list_categories()
            category = st.selectbox("Category", categories)
            if category:
                topics = load_topics(category)
                topic_names = [t.get("english") or t.get("topic") or t.get("wrong") for t in topics]
                topic_name = st.selectbox("Topic", topic_names)

        generate_btn = st.button("🚀 Generate Video", type="primary", use_container_width=True)

    with col2:
        st.subheader("📊 Generation Status")

        # Show active jobs first
        active_jobs = get_active_jobs()

        if active_jobs:
            st.markdown("### ⚡ Currently Running")
            for job in active_jobs:
                with st.container():
                    st.markdown(f"""
                    <div class="progress-container">
                        <strong>🎬 {job['video_type'].upper()}</strong> - {job.get('topic', 'Selecting...')}
                        <br><small>Job ID: {job['id']}</small>
                    </div>
                    """, unsafe_allow_html=True)

                    # Progress bar
                    progress = job.get('progress', 0)
                    st.progress(progress / 100)

                    # Step indicator
                    step = job.get('step_number', 0)
                    total = job.get('total_steps', 4)
                    current_step = job.get('current_step', 'Initializing...')

                    st.markdown(f"""
                    <div class="step-indicator">
                        📍 {current_step}
                        <br>
                        Progress: {progress}% | Step {step}/{total}
                    </div>
                    """, unsafe_allow_html=True)

                    # Auto-refresh while job is running
                    if job["status"] == "running":
                        time.sleep(1)
                        st.rerun()

            st.divider()

        # Recent history
        st.markdown("### 📜 Recent Videos (Last 5)")
        history = get_job_history(5)

        if history:
            for job in history:
                status = job["status"]
                if status == "completed":
                    icon = "✅"
                    color = "#4CAF50"
                else:
                    icon = "❌"
                    color = "#f44336"

                with st.expander(f"{icon} {job.get('topic', 'Unknown')} ({job['video_type']})", expanded=False):
                    st.write(f"**Status:** {status}")
                    st.write(f"**Category:** {job.get('category', 'N/A')}")

                    if job.get("completed_at"):
                        completed = datetime.fromisoformat(job["completed_at"])
                        st.write(f"**Completed:** {completed.strftime('%Y-%m-%d %H:%M:%S')}")

                    if job.get("error"):
                        st.error(f"Error: {job['error']}")

                    if job.get("video_path") and Path(job["video_path"]).exists():
                        st.video(job["video_path"])
        else:
            st.info("No videos generated yet. Click 'Generate Video' to start!")

        # Handle generate button
        if generate_btn:
            # Create job
            job_id = create_job(video_type, category, topic_name)

            st.success(f"🚀 Generation started! Job ID: `{job_id}`")
            st.info("⏳ Processing... The page will update automatically.")

            # Run pipeline in the same thread (synchronous for Streamlit)
            with st.spinner("Generating video..."):
                result = run_pipeline_with_tracking(job_id, video_type, category, topic_name)

            if result["success"]:
                st.success("✅ Video generated successfully!")
                st.balloons()
            else:
                st.error(f"❌ Generation failed: {result.get('error', 'Unknown error')}")

            st.rerun()


# ============== QUEUE PAGE ==============
elif page == "📋 Queue":
    st.title("📋 Batch Queue")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("➕ Add to Queue")

        st.write("**Quick Batch:**")
        batch_col1, batch_col2 = st.columns(2)

        with batch_col1:
            if st.button("🎲 10 Random Quizzes", use_container_width=True):
                for _ in range(10):
                    st.session_state.queue_items.append({"type": "quiz", "category": None, "topic": None})
                st.success("Added 10 quiz videos to queue!")
                st.rerun()

        with batch_col2:
            if st.button("📚 5 of Each Type", use_container_width=True):
                for vtype in ["quiz", "educational", "true_false"]:
                    for _ in range(5):
                        st.session_state.queue_items.append({"type": vtype, "category": None, "topic": None})
                st.success("Added 15 videos to queue!")
                st.rerun()

        st.divider()

        st.write("**Custom Add:**")
        q_type = st.selectbox("Type", VIDEO_TYPES, key="queue_type")
        q_count = st.number_input("Count", min_value=1, max_value=50, value=5)

        if st.button("➕ Add to Queue", use_container_width=True):
            for _ in range(q_count):
                st.session_state.queue_items.append({"type": q_type, "category": None, "topic": None})
            st.success(f"Added {q_count} {q_type} videos to queue!")
            st.rerun()

    with col2:
        st.subheader(f"📋 Queue ({len(st.session_state.queue_items)} items)")

        if st.session_state.queue_items:
            ctrl_col1, ctrl_col2 = st.columns(2)

            with ctrl_col1:
                start_btn = st.button("▶️ Start Processing", type="primary", use_container_width=True)
            with ctrl_col2:
                if st.button("🗑️ Clear Queue", use_container_width=True):
                    st.session_state.queue_items = []
                    st.rerun()

            st.divider()

            # Group by type
            by_type = {}
            for item in st.session_state.queue_items:
                t = item["type"]
                by_type[t] = by_type.get(t, 0) + 1

            for t, count in by_type.items():
                st.write(f"• **{t}**: {count} videos")

            # Process queue
            if start_btn:
                total = len(st.session_state.queue_items)
                progress_bar = st.progress(0)
                status_text = st.empty()
                step_text = st.empty()
                results_area = st.empty()

                completed = 0
                errors = 0

                while st.session_state.queue_items:
                    item = st.session_state.queue_items.pop(0)

                    # Create job
                    job_id = create_job(item["type"], item.get("category"), item.get("topic"))

                    status_text.info(f"⏳ Processing {completed + 1}/{total}: {item['type']} video...")
                    step_text.markdown(f"<div class='step-indicator'>Job ID: {job_id}</div>", unsafe_allow_html=True)

                    result = run_pipeline_with_tracking(
                        job_id,
                        video_type=item["type"],
                        category=item.get("category"),
                        topic_name=item.get("topic")
                    )

                    if result["success"]:
                        completed += 1
                    else:
                        errors += 1

                    progress_bar.progress((completed + errors) / total)
                    results_area.write(f"✅ Completed: {completed} | ❌ Errors: {errors}")

                status_text.success(f"🎉 Queue complete! {completed} successful, {errors} failed")
        else:
            st.info("Queue is empty. Add videos above!")

        # Show active jobs
        active_jobs = get_active_jobs()
        if active_jobs:
            st.divider()
            st.subheader("⚡ Active Jobs")
            for job in active_jobs:
                st.write(f"• {job['video_type']} - {job.get('current_step', 'Processing...')}")


# ============== REVIEW PAGE ==============
elif page == "✅ Review":
    st.title("✅ Review Videos")

    pending = get_pending_videos()

    if not pending:
        st.info("🎉 No videos pending review! Generate some new videos.")
    else:
        st.write(f"**{len(pending)} videos pending review**")

        types_available = list(set(v["type"] for v in pending))
        filter_type = st.selectbox("Filter by type", ["All"] + types_available)

        if filter_type != "All":
            pending = [v for v in pending if v["type"] == filter_type]

        st.divider()

        for idx, video in enumerate(pending):
            with st.container():
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.subheader(f"📹 {video['name']}")
                    st.write(f"**Type:** {video['type']} | **Created:** {video['created'].strftime('%Y-%m-%d %H:%M')}")

                    if video["meta"]:
                        with st.expander("📋 Details"):
                            if "script_data" in video["meta"]:
                                script = video["meta"]["script_data"]
                                if video["type"] == "quiz":
                                    st.write(f"**Question:** {script.get('question', 'N/A')}")
                                    st.write(f"**Options:** {script.get('options', {})}")
                                    st.write(f"**Correct:** {script.get('correct', 'N/A')}")
                                elif video["type"] == "educational":
                                    st.write(f"**Hook:** {script.get('hook', 'N/A')}")
                                elif video["type"] == "true_false":
                                    st.write(f"**Statement:** {script.get('statement', 'N/A')}")
                                    st.write(f"**Correct:** {script.get('correct', 'N/A')}")
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
                        st.warning("Rejected")
                        st.rerun()

                st.divider()

        st.subheader("Bulk Actions")
        col1, col2 = st.columns(2)

        with col1:
            if st.button("✅ Approve All", use_container_width=True):
                for video in pending:
                    approve_video(video["path"])
                st.success(f"Approved {len(pending)} videos!")
                st.rerun()

        with col2:
            if st.button("❌ Reject All", use_container_width=True):
                for video in pending:
                    reject_video(video["path"])
                st.warning(f"Rejected {len(pending)} videos")
                st.rerun()


# ============== UPLOAD PAGE ==============
elif page == "📤 Upload":
    st.title("📤 Upload Center")

    st.info("🚧 **Phase 4 Feature** - Upload integration coming soon!")

    approved = get_approved_videos()

    if not approved:
        st.warning("No approved videos ready for upload.")
    else:
        st.success(f"**{len(approved)} videos ready for upload**")

        st.divider()

        st.subheader("🔗 Connected Platforms")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.write("**TikTok**")
            st.write("⚪ Not connected")
            st.button("Connect TikTok", disabled=True, key="tiktok")

        with col2:
            st.write("**YouTube Shorts**")
            st.write("⚪ Not connected")
            st.button("Connect YouTube", disabled=True, key="youtube")

        with col3:
            st.write("**Instagram Reels**")
            st.write("⚪ Not connected")
            st.button("Connect Instagram", disabled=True, key="instagram")

        st.divider()

        st.subheader("📹 Ready for Upload")
        for video in approved:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f"**{video['name']}** ({video['type']})")
            with col2:
                st.write(video['created'].strftime("%Y-%m-%d"))
            with col3:
                st.button("📤 Upload", disabled=True, key=f"upload_{video['name']}")


# ============== LIBRARY PAGE ==============
elif page == "📚 Library":
    st.title("📚 Video Library")

    library = get_library_videos()
    pending = get_pending_videos()
    approved = get_approved_videos()

    all_videos = library + pending + approved

    if not all_videos:
        st.info("Library is empty. Generate some videos!")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Videos", len(all_videos))
        with col2:
            total_size = sum(v.get("size", 0) or v["path"].stat().st_size for v in all_videos)
            st.metric("Total Size", f"{total_size / (1024*1024):.1f} MB")
        with col3:
            types_count = len(set(v["type"] for v in all_videos))
            st.metric("Video Types", types_count)

        st.divider()

        col1, col2 = st.columns([1, 3])
        with col1:
            types = ["All"] + list(set(v["type"] for v in all_videos))
            filter_type = st.selectbox("Filter by Type", types, key="lib_filter")
        with col2:
            search = st.text_input("Search", placeholder="Search by name...")

        filtered = all_videos
        if filter_type != "All":
            filtered = [v for v in filtered if v["type"] == filter_type]
        if search:
            filtered = [v for v in filtered if search.lower() in v["name"].lower()]

        st.write(f"Showing {len(filtered)} videos")
        st.divider()

        cols_per_row = 3
        rows = [filtered[i:i+cols_per_row] for i in range(0, len(filtered), cols_per_row)]

        for row in rows:
            cols = st.columns(cols_per_row)
            for idx, video in enumerate(row):
                with cols[idx]:
                    name_display = f"**{video['name'][:20]}...**" if len(video['name']) > 20 else f"**{video['name']}**"
                    st.write(name_display)
                    st.write(f"📁 {video['type']}")

                    if video["path"].exists():
                        st.video(str(video["path"]))

                    st.write(f"📅 {video['created'].strftime('%m/%d %H:%M')}")

                    if st.button("🗑️ Delete", key=f"del_{video['path']}", use_container_width=True):
                        delete_video(video["path"])
                        st.rerun()


# ============== SCHEDULER PAGE ==============
elif page == "⏰ Scheduler":
    st.title("⏰ Auto-Generation Scheduler")

    st.info("Configure automatic video generation.")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("⚙️ Configuration")

        videos_per_batch = st.number_input(
            "Videos per batch",
            min_value=1,
            max_value=20,
            value=st.session_state.scheduler_config["videos_per_batch"]
        )

        interval = st.selectbox(
            "Generation interval",
            options=[15, 30, 60, 120, 240, 480],
            index=2,
            format_func=lambda x: f"{x} minutes" if x < 60 else f"{x//60} hour{'s' if x > 60 else ''}"
        )

        st.write("**Video types:**")
        type_quiz = st.checkbox("Quiz", value="quiz" in st.session_state.scheduler_config["types"])
        type_edu = st.checkbox("Educational", value="educational" in st.session_state.scheduler_config["types"])
        type_tf = st.checkbox("True/False", value="true_false" in st.session_state.scheduler_config["types"])

        selected_types = []
        if type_quiz: selected_types.append("quiz")
        if type_edu: selected_types.append("educational")
        if type_tf: selected_types.append("true_false")

        if st.button("💾 Save Configuration", use_container_width=True):
            st.session_state.scheduler_config = {
                "videos_per_batch": videos_per_batch,
                "interval_minutes": interval,
                "types": selected_types
            }
            st.success("Configuration saved!")

    with col2:
        st.subheader("▶️ Control")

        if st.session_state.scheduler_enabled:
            st.success("🟢 Scheduler is ACTIVE")
        else:
            st.warning("🔴 Scheduler is INACTIVE")

        st.divider()

        if not st.session_state.scheduler_enabled:
            if st.button("▶️ Start Scheduler", type="primary", use_container_width=True):
                st.session_state.scheduler_enabled = True
                st.rerun()
        else:
            if st.button("⏹️ Stop Scheduler", use_container_width=True):
                st.session_state.scheduler_enabled = False
                st.rerun()

        st.divider()

        if st.button("🚀 Generate Batch Now", use_container_width=True):
            if not selected_types:
                st.error("Select at least one video type!")
            else:
                progress = st.progress(0)
                status = st.empty()

                for i in range(videos_per_batch):
                    video_type = selected_types[i % len(selected_types)]
                    job_id = create_job(video_type)
                    status.info(f"⏳ Generating {i+1}/{videos_per_batch}: {video_type}...")

                    run_pipeline_with_tracking(job_id, video_type)
                    progress.progress((i + 1) / videos_per_batch)

                status.success(f"✅ Batch complete!")


# ============== SIDEBAR INFO ==============
st.sidebar.divider()
st.sidebar.subheader("📊 Quick Stats")
st.sidebar.write(f"• Pending: {len(get_pending_videos())}")
st.sidebar.write(f"• Approved: {len(get_approved_videos())}")
st.sidebar.write(f"• Queue: {len(st.session_state.queue_items)}")
st.sidebar.write(f"• Active Jobs: {len(get_active_jobs())}")

st.sidebar.divider()
if st.session_state.scheduler_enabled:
    st.sidebar.success("⏰ Scheduler: ON")
else:
    st.sidebar.write("⏰ Scheduler: OFF")

st.sidebar.divider()
st.sidebar.caption("English AI Videos v1.0")
