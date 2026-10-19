#!/usr/bin/env python3
"""Manim Studio — the admin page for long, narrated, bilingual lesson videos.

The pipeline lives in experiments/manim_voiceover_poc/ (lesson.py, gen_script.py,
gen_audio.py, lesson_scene.py, batch_run.py, renders.py); this page only drives it:

  write   a topic → gen_script.py (OpenAI) → lessons/<id>.json, or edit a lesson here
  voice   ElevenLabs, per segment with language_code (English reads as English,
          Spanish as Spanish), word timings kept → audio/<lesson>/<voice>/
  render  lesson_scene.py in the background → renders/<lesson>/…mp4 + ledger row
  batch   several lessons, one click, audio + render each

Keys (ELEVENLABS_API_KEY, OPENAI_API_KEY) come from the repo's .env or the studio's own
.env written by the panel below; they are never displayed or sent anywhere else.
Every function under the Streamlit surface is plain and tested without a browser.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
STUDIO_DIR = Path(os.environ.get("MANIM_STUDIO_DIR", ROOT / "experiments" / "manim_voiceover_poc"))
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

# A MISSING STUDIO IS A MESSAGE, NOT A TRACEBACK. These three live in
# STUDIO_DIR, which is a separate tree with its own venv; `MANIM_STUDIO_DIR`
# can also point somewhere that does not exist yet. Importing them at module
# scope meant `import manim_studio` raised, and admin.py imports this module
# from inside the page router -- so a clone without the studio answered the
# Manim page with a Streamlit traceback instead of telling anyone what was
# missing. render() checks STUDIO_IMPORT_ERROR first and shows the install
# panel; every function below is reached only from there.
try:
    import lesson as L  # noqa: E402
    import renders as R  # noqa: E402
    import publish as P  # noqa: E402
    STUDIO_IMPORT_ERROR: Optional[str] = None
except ImportError as exc:                     # pragma: no cover — clone without the tree
    L = R = P = None
    STUDIO_IMPORT_ERROR = str(exc)

MATILDA = "XrExE9yKIg1WjnnlVkGX"
PRICE_PER_1K_CHARS = 0.10
ENV_KEYS = ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "OPENAI_API_KEY", "LR_BASE_URL", "LR_STUDIO_TOKEN")
TTS_MODELS = ("eleven_v4", "eleven_multilingual_v2", "eleven_turbo_v2_5", "eleven_flash_v2_5")   # first: the owner's pick by ear
WRITER_MODELS = ("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini")
LEVELS = ("A1", "A2", "B1", "B2")


# ── Pure helpers (tested) ──────────────────────────────────────────────────────

def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "voice"


def estimate_cost_usd(lesson: dict, voices: int = 1) -> float:
    return round(L.character_count(lesson) * voices / 1000 * PRICE_PER_1K_CHARS, 3)


def mask(value: str) -> str:
    if not value:
        return "—"
    return f"{value[:4]}…{value[-4:]}" if len(value) > 12 else "••••"


def read_env_file(path: Path) -> dict:
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env_file(path: Path, updates: dict) -> None:
    """Set/replace the given keys, keep every other line, mode 600. Values are never logged."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = {k: v for k, v in updates.items() if v is not None}
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        out.append(f"{key}={pending.pop(key)}" if key in pending else line)
    out.extend(f"{k}={v}" for k, v in pending.items())
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def effective_env(studio_dir: Path = STUDIO_DIR, root: Path = ROOT) -> dict:
    """Studio .env wins over the repo .env; the process env fills the rest; says where each came from."""
    root_env, local_env = read_env_file(root / ".env"), read_env_file(studio_dir / ".env")
    result = {}
    for key in ENV_KEYS:
        for source, values in (("studio", local_env), ("root", root_env), ("process", os.environ)):
            if values.get(key):
                result[key], result[key + "_SOURCE"] = values[key], source
                break
        else:
            result[key], result[key + "_SOURCE"] = "", "missing"
    return result


def lesson_files(studio_dir: Path = STUDIO_DIR) -> list:
    return sorted((studio_dir / "lessons").glob("*.json")) if (studio_dir / "lessons").exists() else []


_SUMMARY_MEMO: dict = {}


def _stamp(path: Path):
    try:
        st = Path(path).stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def lesson_summary(path: Path) -> dict:
    """Memoised on the lesson file and the render ledger (whose fit drives the
    minutes estimate). The Manim page summarised all ~22 lessons on every
    click -- 63 file reads per rerun, measured 2026-10-13."""
    ledger = Path(L.__file__).resolve().parent / "renders" / "ledger.jsonl"
    key = (str(path), _stamp(path), _stamp(ledger))
    hit = _SUMMARY_MEMO.get(str(path))
    if hit is not None and hit[0] == key:
        return dict(hit[1])
    summary = _lesson_summary_uncached(path)
    _SUMMARY_MEMO[str(path)] = (key, dict(summary))
    return summary


def _lesson_summary_uncached(path: Path) -> dict:
    lesson = L.load(path)
    return {"id": lesson.get("id", path.stem), "title": lesson.get("title", path.stem), "level": lesson.get("level", ""),
            "beats": len(lesson.get("beats", [])), "minutes": L.estimate_minutes(lesson), "chars": L.character_count(lesson),
            "problems": len(L.validate(lesson))}


def voices_with_audio(lesson_id: str, studio_dir: Path = STUDIO_DIR) -> list:
    folder = studio_dir / "audio" / lesson_id
    return sorted(p.name for p in folder.iterdir() if (p / "manifest.json").exists()) if folder.exists() else []


def stale_beats(lesson: dict, voice: str, studio_dir: Path = STUDIO_DIR) -> list:
    """Beat ids whose narration changed since that voice's audio was generated (or never made)."""
    manifest = studio_dir / "audio" / lesson["id"] / voice / "manifest.json"
    recorded = {}
    if manifest.exists():
        recorded = {b["id"]: (b.get("text"), b.get("pauses", [])) for b in json.loads(manifest.read_text(encoding="utf-8")).get("beats", [])}
    return [b["id"] for b in lesson["beats"]
            if recorded.get(b["id"]) != (L.spoken_text(b["narration"]), L.pauses(b["narration"]))]


def beats_table(lesson: dict) -> list:
    return [{"id": b["id"], "tipo": b["type"], "narración": b["narration"]} for b in lesson["beats"]]


def apply_table(lesson: dict, rows: list) -> dict:
    """Narration edits from the table back into the lesson; ids and types are read-only."""
    by_id = {r["id"]: r.get("narración", "") for r in rows}
    for beat in lesson["beats"]:
        if beat["id"] in by_id:
            beat["narration"] = by_id[beat["id"]].strip()
    return lesson


def audio_command(lesson_id: str, voice_slug: str, voice_id: str, model: str, force: bool = False) -> list:
    argv = [sys.executable, "gen_audio.py", "--lesson", f"lessons/{lesson_id}.json", "--voices", f"{voice_slug}={voice_id}",
            "--model", model]
    return argv + ["--force"] if force else argv


def script_command(topic: str, level: str, minutes: int, model: str, extra: str = "") -> list:
    argv = [sys.executable, "gen_script.py", "--topic", topic, "--level", level, "--minutes", str(int(minutes)), "--model", model]
    if extra.strip():
        argv += ["--extra", extra.strip()]
    return argv


def batch_command(lesson_ids: list, voice_slug: str, voice_id: str, quality: str, model: str) -> list:
    return [sys.executable, "batch_run.py", "--lessons", *lesson_ids, "--voices", f"{voice_slug}={voice_id}",
            "--quality", quality, "--model", model]


def fetch_voices(api_key: str, timeout: int = 20) -> list:
    request = urllib.request.Request("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": api_key})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    return [{"voice_id": v["voice_id"], "name": v["name"], "labels": v.get("labels") or {}} for v in data.get("voices", [])]


# ── Background jobs (subprocess + thread; state on disk so page reruns see it) ─

def jobs_dir(studio_dir: Path = STUDIO_DIR) -> Path:
    path = studio_dir / "renders" / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def start_job(kind: str, argv: list, env: dict, cwd: Path, on_success=None, studio_dir: Path = STUDIO_DIR) -> str:
    job_id = f"{kind}-{datetime.now().strftime('%H%M%S')}"
    folder = jobs_dir(studio_dir)
    status_path, log_path = folder / f"{job_id}.json", folder / f"{job_id}.log"

    def write(**fields):
        status_path.write_text(json.dumps({"id": job_id, "kind": kind, "argv": argv, **fields}, ensure_ascii=False))

    def run():
        started = time.time()
        write(state="running", started=started)
        try:
            with log_path.open("w", encoding="utf-8") as log:
                log.write("$ " + " ".join(argv) + "\n\n")
                log.flush()
                code = subprocess.run(argv, cwd=str(cwd), env={**os.environ, **env}, stdout=log,
                                      stderr=subprocess.STDOUT).returncode
        except OSError as error:
            log_path.write_text(f"{error}\n")
            code = -1
        result = {}
        if code == 0 and on_success:
            try:
                result = on_success(time.time() - started) or {}
            except Exception as error:               # noqa: BLE001 — shown in the page
                code, result = -2, {"error": str(error)}
        write(state="done" if code == 0 else "failed", code=code, seconds=round(time.time() - started, 1), result=result)

    threading.Thread(target=run, name=job_id, daemon=True).start()
    return job_id


def job_status(job_id: str, studio_dir: Path = STUDIO_DIR) -> dict:
    path = jobs_dir(studio_dir) / f"{job_id}.json"
    if not path.exists():
        return {"state": "starting"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"state": "running"}


def job_log(job_id: str, tail: int = 40, studio_dir: Path = STUDIO_DIR) -> str:
    path = jobs_dir(studio_dir) / f"{job_id}.log"
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-tail:]) if path.exists() else ""


# ── The page ───────────────────────────────────────────────────────────────────

# ── YouTube (STEP 56): the long lessons, through the Shorts' uploader and guard ──
YT_HASHTAGS = ("#AprenderInglés", "#InglésFácil", "#GramáticaInglesa")
YT_TAGS = ("aprender inglés", "inglés fácil", "gramática inglesa", "clases de inglés", "inglés para hispanohablantes",
           "curso de inglés", "learn english", "english grammar", "english lesson", "english for spanish speakers")
YT_CTA = "Suscríbete: una lección nueva cada semana."
from metadata_generator import SITE_LINE  # noqa: E402 — the Shorts' line, word for word
YT_GENERIC_HEADINGS = {"introducción", "practica", "práctica", "resumen", "repaso"}
YT_VIDEO_TYPE = "manim_lesson"


def _sentences(text: str) -> list:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def youtube_metadata(lesson: dict, render_row: dict, studio_dir: Path = STUDIO_DIR) -> dict:
    """{title, description, tags, hashtags} for one render, from the lesson itself — no API.
    Description: 2-sentence summary · «En esta lección:» bullets from the headings · the
    render's chapter list as written (0:00 first) · CTA · the hashtags, once."""
    level = (lesson.get("kicker") or "").split("·")[-1].strip() or lesson.get("level", "")
    title = lesson["title"] + (f" | Inglés {level}" if level else "")
    if len(title) > 100:
        title = lesson["title"][:100]
    beats = lesson.get("beats", [])
    opening = next((b for b in beats if b.get("type") == "title"), beats[0] if beats else {"narration": ""})
    sentences = [s for s in _sentences(L.spoken_text(opening.get("narration", ""))) if s.rstrip(".!") != "Hola"]
    summary = " ".join(sentences[:2])
    headings = [re.sub(r"^Parte\s+\d+\s*·\s*", "", b.get("text", "")).strip() for b in beats if b.get("type") == "heading"]
    bullets = [h for h in headings if h and h.lower() not in YT_GENERIC_HEADINGS][:5]
    chapters_path = studio_dir / "renders" / render_row["chapters"] if render_row.get("chapters") else None
    chapters = chapters_path.read_text(encoding="utf-8").strip() if chapters_path and chapters_path.exists() else ""
    if chapters and not chapters.startswith("0:00"):
        chapters = ""                                  # YouTube ignores a list that does not start at 0:00
    specific = lesson.get("hashtags") or ["#" + "".join(w.capitalize() for w in lesson["id"].split("-"))]
    hashtags = list(dict.fromkeys(list(YT_HASHTAGS) + [h if h.startswith("#") else "#" + h for h in specific]))[:5]
    parts = [summary, "En esta lección:\n" + "\n".join(f"• {b}" for b in bullets) if bullets else "",
             chapters, SITE_LINE, YT_CTA, " ".join(hashtags)]
    words = [w for w in re.split(r"\W+", re.sub(r"\|.*", "", lesson["title"]).lower()) if len(w) > 1]
    tags = list(dict.fromkeys(list(YT_TAGS) + [" ".join(lesson["id"].split("-")), lesson["title"].split(":")[0].lower()]
                              + ([f"inglés {level}"] if level else []) + words))[:15]
    return {"title": title, "description": "\n\n".join(p for p in parts if p), "tags": tags, "hashtags": hashtags}


def youtube_json_path(render_row: dict, studio_dir: Path = STUDIO_DIR) -> Path:
    return (studio_dir / "renders" / render_row["file"]).with_suffix(".youtube.json")


def youtube_publication(render_row: dict) -> Optional[dict]:
    """The ledger row of this render's YouTube upload, or None — what «Subido · fecha · enlace» reads."""
    from publication_log import find_by_artifact
    rows = [r for r in find_by_artifact(Path(render_row["file"]).stem) if r.get("platform") == "youtube"]
    return rows[0] if rows else None


def youtube_consent_note(youtube) -> Optional[str]:
    """The warning BEFORE the click, only when there is no usable token at all (none, or one missing
    a required scope): that click opens Google's consent. None otherwise — like the Shorts upload."""
    from uploader import LOOPBACK_TIMEOUT_S
    if not youtube._missing_scopes():
        return None
    return (f"Antes de subir, Google te pedirá permiso (aún no hay una autorización guardada). Al pulsar se abre "
            f"una pestaña de Google: elige la cuenta del canal, marca todas las casillas y acepta antes de "
            f"{LOOPBACK_TIMEOUT_S // 60} minutos.")


CAPTIONS_SKIPPED_NOTE = ("Los subtítulos en español no se subirán: la cuenta no dio ese permiso. "
                         "YouTube genera los suyos automáticamente.")


def youtube_captions_note(youtube) -> Optional[str]:
    """The small grey line when the token uploads but cannot send captions (no youtube.force-ssl)."""
    from uploader import YOUTUBE_OPTIONAL_SCOPES
    if youtube._missing_scopes() or not youtube._missing_scopes(YOUTUBE_OPTIONAL_SCOPES):
        return None
    return CAPTIONS_SKIPPED_NOTE


def lesson_of(render_row: dict, studio_dir: Path = STUDIO_DIR) -> Optional[dict]:
    """The lesson a render came from, or None when its file is gone."""
    path = studio_dir / "lessons" / f"{render_row.get('lesson', '')}.json"
    return L.load(path) if render_row.get("lesson") and path.exists() else None


# ── Review → upload (STEP 61 Part A) ──────────────────────────────────────────
# One current render per lesson (the newest), reviewed before it can be uploaded. Decisions are
# appended to renders/reviews.jsonl; «subida» is read from the publication ledger, never from it.
REVIEW_STATUSES = ("por revisar", "aprobada", "rehacer")


def reviews_path(studio_dir: Path = STUDIO_DIR) -> Path:
    return studio_dir / "renders" / "reviews.jsonl"


def record_review(file: str, status: str, note: str = "", reopen: bool = False,
                  studio_dir: Path = STUDIO_DIR) -> dict:
    """Append one decision. `reopen` is «Usar esta versión»: an older render becomes the current one."""
    if status not in REVIEW_STATUSES:
        raise ValueError(f"unknown review status {status!r}")
    line = {"file": file, "status": status, "note": note.strip(), "at": datetime.now().isoformat(timespec="seconds")}
    if reopen:
        line["reopen"] = True
    path = reviews_path(studio_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    return line


def review_lines(studio_dir: Path = STUDIO_DIR) -> list:
    path = reviews_path(studio_dir)
    if not path.exists():
        return []
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            lines.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return lines


def latest_reviews(studio_dir: Path = STUDIO_DIR) -> dict:
    """{file: its last decision} — the last line wins."""
    return {line["file"]: line for line in review_lines(studio_dir) if line.get("file")}


def _reviewable(row: dict) -> bool:
    """Demos and draft qualities (under 1080p) never reach review: they are tests and drafts."""
    m = re.match(r"(\d+)p", str(row.get("quality") or ""))
    return bool(row.get("lesson")) and not row["lesson"].startswith("demo") and bool(m) and int(m.group(1)) >= 1080


def current_render_per_lesson(rows: list, studio_dir: Path = STUDIO_DIR, lines: Optional[list] = None) -> dict:
    """{lesson: row}: the newest render on disk, unless an older one was reopened after it."""
    lines = review_lines(studio_dir) if lines is None else lines
    on_disk = [r for r in rows if _reviewable(r) and (studio_dir / "renders" / r["file"]).exists()]
    current = {}
    for row in sorted(on_disk, key=lambda r: r.get("at", "")):
        current[row["lesson"]] = row
    by_file = {r["file"]: r for r in on_disk}
    for line in lines:                                 # in order: a later reopen beats an earlier one
        row = by_file.get(line.get("file"))
        if line.get("reopen") and row and line.get("at", "") > current[row["lesson"]].get("at", ""):
            current[row["lesson"]] = row
    return current


def review_board(studio_dir: Path = STUDIO_DIR, publication=None) -> dict:
    """The «Revisar y subir» tab as data: por_revisar, aprobadas, rehacer, subidas, anteriores.
    Each entry is (row, review line or None); anteriores also carry whether the file is gone."""
    publication = publication or youtube_publication
    rows = [r for r in R.ledger(studio_dir) if _reviewable(r)]
    lines = review_lines(studio_dir)
    last = {line["file"]: line for line in lines if line.get("file")}
    current = {r["file"] for r in current_render_per_lesson(rows, studio_dir, lines).values()}
    board = {"por_revisar": [], "aprobadas": [], "rehacer": [], "subidas": [], "anteriores": []}
    for row in rows:
        review = last.get(row["file"])
        published = publication(row)
        if published:
            board["subidas"].append((row, published))
        elif row["file"] in current:
            status = review["status"] if review else "por revisar"
            board[{"por revisar": "por_revisar", "aprobada": "aprobadas", "rehacer": "rehacer"}[status]].append((row, review))
        else:
            board["anteriores"].append((row, not (studio_dir / "renders" / row["file"]).exists()))
    return board


def redo_note(lesson_id: str, studio_dir: Path = STUDIO_DIR) -> Optional[str]:
    """The note under the editor when this lesson's current render was marked «rehacer»."""
    for row, review in review_board(studio_dir)["rehacer"]:
        if row["lesson"] == lesson_id:
            return review.get("note") or "sin nota"
    return None


def english_flags(row: dict, studio_dir: Path = STUDIO_DIR) -> list:
    """[(beat, expected English)] the English-words audit flagged for this render's voice."""
    path = studio_dir / "audio" / row["lesson"] / row.get("voice", "") / "english_audit.json"
    if not path.exists():
        return []
    audit = json.loads(path.read_text(encoding="utf-8"))
    return [(beat, r.get("expected", "")) for beat, entry in audit.items()
            for r in entry.get("rows", []) if r.get("verdict") != "ok"]


def voice_model(row: dict, studio_dir: Path = STUDIO_DIR) -> Optional[str]:
    path = studio_dir / "audio" / row["lesson"] / row.get("voice", "") / "manifest.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("model")
    except (OSError, json.JSONDecodeError):
        return None


YT_AUTH_ERRORS = {
    "timeout": "No se completó la autorización en Google a tiempo. Pulsa otra vez y acepta en la pestaña que se abre.",
    "access_denied": "Google no dio el permiso (cancelaste o no marcaste las casillas). Pulsa otra vez y acepta todo.",
    "state_mismatch": "La respuesta de Google no correspondía a esta petición. Pulsa otra vez.",
    "exchange_failed": "Google aceptó pero no entregó el token. Pulsa otra vez.",
}


def upload_to_youtube(render_row: dict, meta: dict, privacy: Optional[str] = None, on_progress=None,
                      studio_dir: Path = STUDIO_DIR, manager=None) -> dict:
    """One click → one upload, through the Shorts' guard and ledger: decide (no second publication),
    attempt before a byte, upload_video(shorts=False), record; then the poster as thumbnail and the
    .srt as Spanish captions — each a note on failure, never a failed upload.
    Returns {ok, url, upload_id, notes, refused}."""
    from publication_log import (ATTEMPT_FAILED, ATTEMPT_PUBLISHED, ATTEMPT_SESSION, ATTEMPT_STARTED,
                                 PublicationRecordError, record_attempt, record_upload_result)
    from upload_guard import decide
    from uploader import UploadManager

    video = studio_dir / "renders" / render_row["file"]
    artifact = video.stem
    manager = manager or UploadManager()
    verdict = decide(artifact, "youtube", manager=manager)
    if not verdict.should_upload:
        return {"ok": False, "refused": verdict.reason, "upload_id": verdict.upload_id, "url": None, "notes": []}
    youtube = manager.uploaders["youtube"]
    if not youtube.authenticate():
        reason = youtube.last_auth_error if youtube.is_configured() else None
        note = YT_AUTH_ERRORS.get(reason, f"Autorización de YouTube fallida ({reason}). Pulsa otra vez.") if reason \
            else "Faltan YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET en .env."
        return {"ok": False, "refused": None, "url": None, "upload_id": None, "notes": [note]}
    from upload_limits import claim, release
    if not claim(artifact, "youtube"):                 # STEP 67: a second press while it uploads does nothing
        return {"ok": False, "refused": "ya se está subiendo esta lección", "upload_id": None, "url": None, "notes": []}
    try:
        return _upload_lesson(youtube, video, artifact, render_row, meta, privacy, on_progress, studio_dir)
    finally:
        release(artifact, "youtube")


def _upload_lesson(youtube, video, artifact, render_row, meta, privacy, on_progress, studio_dir) -> dict:
    from publication_log import (ATTEMPT_FAILED, ATTEMPT_PUBLISHED, ATTEMPT_SESSION, ATTEMPT_STARTED,
                                 PublicationRecordError, read_attempts, record_attempt, record_upload_result)
    from upload_limits import spanish
    youtube_json_path(render_row, studio_dir).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    size = video.stat().st_size
    record_attempt(artifact=artifact, platform="youtube", status=ATTEMPT_STARTED, video_path=str(video),
                   file_size=size, detail=meta["title"][:120])
    result = youtube.upload_video(
        str(video), meta["title"], meta["description"], [t.lstrip("#") for t in meta["tags"]], shorts=False,
        privacy=privacy, on_progress=on_progress,
        on_session=lambda uri, sz: record_attempt(artifact=artifact, platform="youtube", status=ATTEMPT_SESSION,
                                                  video_path=str(video), session_uri=uri, file_size=sz,
                                                  detail=meta["title"][:120]))
    if not result.success:
        record_attempt(artifact=artifact, platform="youtube", status=ATTEMPT_FAILED, video_path=str(video),
                       session_uri=result.session_uri, file_size=size, detail=str(result.error)[:300])
        return {"ok": False, "refused": None, "url": None, "upload_id": None,
                "notes": [f"No se subió: {spanish(result.error, read_attempts(), datetime.now())}"]}
    notes = []
    try:
        record_upload_result(artifact=artifact, video_path=str(video), video_type=YT_VIDEO_TYPE, platform="youtube",
                             result=result, sent_title=meta["title"], sent_description=meta["description"],
                             sent_hashtags=meta["tags"])
        record_attempt(artifact=artifact, platform="youtube", status=ATTEMPT_PUBLISHED, video_path=str(video),
                       session_uri=result.session_uri, upload_id=result.upload_id, detail="recorded")
    except PublicationRecordError as exc:              # live but unnamed: leave the attempt open, say it loudly
        record_attempt(artifact=artifact, platform="youtube", status=ATTEMPT_SESSION, video_path=str(video),
                       session_uri=result.session_uri, upload_id=result.upload_id,
                       detail=f"published but record failed: {exc}")
        notes.append(f"UPLOADED BUT NOT RECORDED — note the id {result.upload_id}: {exc}")
    poster = studio_dir / "renders" / render_row["poster"] if render_row.get("poster") else None
    notes.append(youtube.set_thumbnail(result.upload_id, str(poster))[1] if poster and poster.exists() else "no poster beside the render")
    srt = video.with_suffix(".srt")
    notes.append(youtube.upload_captions(result.upload_id, str(srt))[1] if srt.exists() else "no .srt beside the render")
    return {"ok": True, "refused": None, "url": result.url, "upload_id": result.upload_id, "notes": notes}


def render() -> None:                                  # pragma: no cover — UI
    import streamlit as st

    st.markdown("## Lecciones")
    st.caption("Guion (IA o a mano) → voz de ElevenLabs por segmentos, inglés en inglés y español en español → "
               "render de Manim en segundo plano → vídeos largos, uno por lección.")

    if STUDIO_IMPORT_ERROR is not None:
        st.error(f"El studio no está instalado en `{STUDIO_DIR}` "
                 f"(`{STUDIO_IMPORT_ERROR}`).")
        st.caption("El código del studio vive en el repo; lo que falta es su entorno, "
                   "o `MANIM_STUDIO_DIR` apunta a otro sitio.")
        st.code(f"cd {STUDIO_DIR}\npython3 -m venv .venv && .venv/bin/pip install "
                '"manim==0.21.0" "manim-voiceover==0.4.0"\nbrew install pango ffmpeg',
                language="bash")
        return

    if not (STUDIO_DIR / R.SCENE_FILE).exists():
        st.error(f"No encuentro `{R.SCENE_FILE}` en `{STUDIO_DIR}`.")
        return

    board = review_board()
    waiting = len(board["por_revisar"]) + len(board["aprobadas"])
    tab_make, tab_review = st.tabs(["Hacer lección", f"Revisar y subir ({waiting})"])
    with tab_review:
        _review_tab(st, board)

    with tab_make:
        env = effective_env()
        el_key, oa_key = env["ELEVENLABS_API_KEY"], env["OPENAI_API_KEY"]
        manim_bin = R.manim_binary(STUDIO_DIR)
        local_env_path = STUDIO_DIR / ".env"
        files = lesson_files()

        # ── Environment ───────────────────────────────────────────────────────────
        with st.expander("Entorno", expanded=not (manim_bin and el_key)):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Manim", "listo" if manim_bin else "falta")
            c2.metric("ffmpeg", "listo" if shutil.which("ffmpeg") else "falta")
            src = {"studio": ".env studio", "root": ".env repo", "process": "entorno", "missing": "falta"}
            c3.metric("ElevenLabs", src[env["ELEVENLABS_API_KEY_SOURCE"]])
            c4.metric("OpenAI (guiones)", src[env["OPENAI_API_KEY_SOURCE"]])
            if not manim_bin:
                st.code(f"cd {STUDIO_DIR}\npython3 -m venv .venv && .venv/bin/pip install "
                        '"manim==0.21.0" "manim-voiceover==0.4.0"\nbrew install pango ffmpeg', language="bash")
            st.caption(f"Las claves se guardan en `{local_env_path}` (solo este studio, permisos 600, ignorado por git); "
                       "si falta una, se usa la del `.env` de la raíz. Nunca se muestran enteras.")
            e1, e2, e3, e4 = st.columns(4)
            e1.text_input("ElevenLabs actual", mask(el_key), disabled=True)
            e2.text_input("OpenAI actual", mask(oa_key), disabled=True)
            e3.text_input("Voice ID por defecto", env["ELEVENLABS_VOICE_ID"] or "—", disabled=True)
            e4.text_input("Learning Routes", f"{env['LR_BASE_URL'] or P.DEFAULT_BASE} · token {mask(env['LR_STUDIO_TOKEN'])}", disabled=True)
            with st.form("studio_env", clear_on_submit=True):
                new_el = st.text_input("Nueva clave de ElevenLabs", type="password", help="Vacío = conservar")
                new_oa = st.text_input("Nueva clave de OpenAI", type="password", help="Vacío = conservar")
                new_voice = st.text_input("Voice ID por defecto", env["ELEVENLABS_VOICE_ID"] or MATILDA)
                l1, l2 = st.columns(2)
                new_base = l1.text_input("URL de Learning Routes", env["LR_BASE_URL"] or P.DEFAULT_BASE,
                                         help="http://localhost:3000 en desarrollo; https://learningroutes.com en producción")
                new_lr = l2.text_input("Token del studio (studio.api_token en las credenciales de Rails)", type="password",
                                       help="Vacío = conservar. Lo generas con bin/rails secret y lo pones en las credenciales y aquí.")
                if st.form_submit_button("Guardar entorno", type="primary"):
                    updates = {"ELEVENLABS_VOICE_ID": new_voice.strip() or None, "LR_BASE_URL": new_base.strip() or None,
                               "ELEVENLABS_API_KEY": new_el.strip() or None, "OPENAI_API_KEY": new_oa.strip() or None,
                               "LR_STUDIO_TOKEN": new_lr.strip() or None}
                    write_env_file(local_env_path, updates)
                    st.session_state.pop("el_voices", None)
                    st.success("Entorno guardado.")
                    st.rerun()

        # ── 1. Write ──────────────────────────────────────────────────────────────
        st.markdown("### 1 · Guion")
        with st.expander("Nueva lección con IA", expanded=not files):
            if len(oa_key) <= 10:
                st.info("Sin clave de OpenAI no se pueden escribir guiones automáticamente. Ponla en «Entorno».")
            with st.form("new_lesson"):
                topic = st.text_input("Tema", placeholder="Ej.: Past simple: verbos regulares e irregulares del día a día")
                f1, f2, f3 = st.columns(3)
                level = f1.selectbox("Nivel", LEVELS, index=1)
                minutes = f2.slider("Minutos", 3, 12, 7)
                writer = f3.selectbox("Modelo", WRITER_MODELS, help="gpt-4o escribe mejor; gpt-4o-mini cuesta centavos")
                extra = st.text_area("Indicaciones extra (opcional)", height=60,
                                     placeholder="Ej.: incluye un diálogo en una entrevista de trabajo; público: adultos de Colombia")
                if st.form_submit_button("Escribir guion", type="primary", disabled=len(oa_key) <= 10):
                    if topic.strip():
                        st.session_state.ms_job = start_job("guion", script_command(topic, level, minutes, writer, extra), {}, STUDIO_DIR)
                        st.rerun()
                    else:
                        st.warning("Escribe un tema.")
            st.caption("El guion sigue `prompts/lesson_script.md`: ~5 golpes por minuto, diálogos, tabla, tips, 3 quizzes, "
                       "resumen; todo el inglés entre [[ ]] para que la voz lo lea en inglés. Se valida y, si hace falta, se "
                       "corrige una vez antes de guardarse en `lessons/`.")

        if not files:
            st.info("Todavía no hay lecciones en `lessons/`. Escribe una arriba.")
            _job_monitor(st)
            return

        summaries = [lesson_summary(p) for p in files]
        labels = {f"{s['title']}  ·  {s['beats']} golpes · ≈{s['minutes']} min · {s['level']}" + (" · ⚠" if s["problems"] else ""): p
                  for s, p in zip(summaries, files)}
        chosen_label = st.selectbox("Lección", list(labels), index=len(labels) - 1 if "ms_pick" not in st.session_state else
                                    min(st.session_state.ms_pick, len(labels) - 1))
        st.session_state.ms_pick = list(labels).index(chosen_label)
        path = labels[chosen_label]
        lesson = L.load(path)
        lesson_id = lesson["id"]
        redo = redo_note(lesson_id)
        if redo:
            st.warning(f"{lesson_id}: marcada para rehacer — {redo}")

        problems, notes = L.validate(lesson), L.warnings(lesson)
        st.caption(f"`lessons/{path.name}` · {L.character_count(lesson)} caracteres de narración · "
                   f"{sum(1 for b in lesson['beats'] for x in L.segments(b['narration']) if 'text' in x)} segmentos de voz · "
                   f"≈ ${estimate_cost_usd(lesson):.2f} por voz")
        with st.expander(f"Editar narración ({len(lesson['beats'])} golpes)", expanded=bool(problems)):
            st.caption("Edita solo la narración; el inglés va entre [[ ]]. Las palabras que la animación espera deben "
                       "decirse en la frase. Para cambiar la estructura (tipos, tablas, diálogos) edita el JSON abajo.")
            edited = st.data_editor(beats_table(lesson), key=f"editor_{lesson_id}", width="stretch", hide_index=True,
                                    disabled=["id", "tipo"], column_config={"narración": st.column_config.TextColumn(width="large")})
            candidate = apply_table(json.loads(json.dumps(lesson)), edited)
            changed = candidate != lesson
            cand_problems = L.validate(candidate)
            for problem in cand_problems:
                st.warning(problem)
            for note in L.warnings(candidate):
                st.info(note)
            if st.button("Guardar narración", type="primary", disabled=not changed or bool(cand_problems)):
                L.save(candidate, path)
                st.success("Guardada. Solo los golpes cambiados se regenerarán al pedir la voz.")
                st.rerun()
            with st.expander("JSON completo (avanzado)"):
                raw = st.text_area("lesson.json", json.dumps(lesson, ensure_ascii=False, indent=2), height=320, key=f"raw_{lesson_id}")
                if st.button("Guardar JSON"):
                    try:
                        new = json.loads(raw)
                        errs = L.validate(new)
                        if errs:
                            st.error("\n".join(errs))
                        else:
                            L.save(new, path)
                            st.success("Guardado.")
                            st.rerun()
                    except json.JSONDecodeError as error:
                        st.error(f"JSON inválido: {error}")

        # ── 2. Voice ──────────────────────────────────────────────────────────────
        st.markdown("### 2 · Voz")
        ready = voices_with_audio(lesson_id)
        voice_slug, voice_id, tts_model = None, None, TTS_MODELS[0]
        if len(el_key) <= 10:
            st.info("Sin clave de ElevenLabs no se puede generar la voz. Ponla en «Entorno». El render sí funciona con audios ya hechos.")
        else:
            if st.session_state.get("el_voices") is None:
                try:
                    st.session_state.el_voices = fetch_voices(el_key)
                except Exception as error:                     # noqa: BLE001
                    st.session_state.el_voices = []
                    st.warning(f"No pude listar las voces ({error}). Pega un voice_id a mano.")
            voices = st.session_state.el_voices or []
            options = {f"{v['name']} — {v['labels'].get('gender', '?')}, {v['labels'].get('accent', '?')}, "
                       f"{v['labels'].get('use_case', v['labels'].get('description', ''))}": v for v in voices}
            preferred = env["ELEVENLABS_VOICE_ID"] or MATILDA
            default_index = next((i for i, v in enumerate(options.values()) if v["voice_id"] == preferred),
                                 next((i for i, v in enumerate(options.values()) if v["voice_id"] == MATILDA), 0))
            v1, v2, v3 = st.columns([2, 1, 1])
            chosen = options.get(v1.selectbox("Voz", list(options) or ["(pega un voice_id)"], index=default_index))
            manual = v2.text_input("voice_id", chosen["voice_id"] if chosen else preferred)
            voice_id = manual.strip() or MATILDA
            voice_slug = slugify(chosen["name"] if chosen and chosen["voice_id"] == voice_id else voice_id[:8])
            tts_model = v3.selectbox("Modelo TTS", TTS_MODELS,
                                     help="eleven_v4: una petición por beat, en español, inglés bien pronunciado (elegido de oído). multilingual_v2: el anterior. turbo/flash: más baratos.")
            stale = stale_beats(lesson, voice_slug)
            force = st.checkbox("Regenerar todos los golpes (forzar)", value=False,
                                help="Para oír un cambio del generador de audio, no del texto: rehace la voz completa de esta lección.")
            todo = [b["id"] for b in lesson["beats"]] if force else stale
            cost = round(sum(len(L.spoken_text(b["narration"])) for b in lesson["beats"] if b["id"] in todo) / 1000 * PRICE_PER_1K_CHARS, 3)
            label = (f"Generar audio · {voice_slug} · {len(todo)} de {len(lesson['beats'])} golpes (≈ ${cost:.2f})" if todo
                     else f"Audio de {voice_slug} al día")
            if st.button(label, disabled=not todo or bool(problems) or changed, type="primary",
                         help="Guarda la narración primero" if changed else None):
                st.session_state.ms_job = start_job("audio", audio_command(lesson_id, voice_slug, voice_id, tts_model, force), {}, STUDIO_DIR)
                st.rerun()
        if ready:
            st.caption("Voces con audio para esta lección: " + ", ".join(
                f"`{v}`" + (f" ({len(stale_beats(lesson, v))} desactualizados)" if stale_beats(lesson, v) else "") for v in ready))

        # ── 3. Render ─────────────────────────────────────────────────────────────
        st.markdown("### 3 · Vídeo")
        if not manim_bin:
            st.info("Instala Manim (ver «Entorno») para renderizar aquí.")
        elif not ready:
            st.info("Primero genera el audio de una voz.")
        else:
            r1, r2, r3 = st.columns(3)
            render_voice = r1.selectbox("Voz para el vídeo", ready)
            quality = r2.selectbox("Calidad", list(R.QUALITIES), format_func=lambda q: R.QUALITIES[q][1],
                                   index=list(R.QUALITIES).index(R.DEFAULT_QUALITY))
            themes, default_theme = R.theme_names(STUDIO_DIR)
            preferred_theme = lesson.get("theme") or default_theme
            theme = r3.selectbox("Tema", themes, index=themes.index(preferred_theme) if preferred_theme in themes else 0,
                                 help="sand: papel cálido (por defecto) · stone: papel gris · dark: escenario oscuro")
            stale_now = stale_beats(lesson, render_voice)
            if stale_now:
                st.warning(f"{len(stale_now)} golpe(s) de `{render_voice}` no coinciden con la narración actual; regenera el audio antes.")
            if st.button("Renderizar vídeo", type="primary", disabled=bool(stale_now) or changed):
                argv, env_add = R.render_command(manim_bin, quality, lesson_id, render_voice, theme)

                def after_render(seconds, _q=quality, _v=render_voice, _l=lesson_id):
                    return R.register(R.rendered_output(_q, STUDIO_DIR), _l, _v, _q, seconds, STUDIO_DIR)

                st.session_state.ms_job = start_job("render", argv, env_add, STUDIO_DIR, on_success=after_render)
                st.rerun()

        # ── 4. Batch ──────────────────────────────────────────────────────────────
        with st.expander("Lote · varias lecciones, audio + vídeo, un clic"):
            if len(el_key) <= 10 or not manim_bin:
                st.info("El lote necesita la clave de ElevenLabs y Manim instalado.")
            else:
                picked = st.multiselect("Lecciones", [s["id"] for s in summaries], default=[s["id"] for s in summaries if not s["problems"]])
                bq = st.selectbox("Calidad del lote", list(R.QUALITIES), format_func=lambda q: R.QUALITIES[q][1],
                                  index=list(R.QUALITIES).index(R.DEFAULT_QUALITY), key="bq")
                total_chars = sum(s["chars"] for s in summaries if s["id"] in picked)
                st.caption(f"{len(picked)} lección(es) · ≈ {sum(s['minutes'] for s in summaries if s['id'] in picked):.0f} min de vídeo · "
                           f"audio ≈ ${total_chars / 1000 * PRICE_PER_1K_CHARS:.2f} como máximo (lo ya generado no se repite)")
                if st.button("Lanzar lote", disabled=not picked or not voice_slug):
                    st.session_state.ms_job = start_job("lote", batch_command(picked, voice_slug, voice_id, bq, tts_model), {}, STUDIO_DIR)
                    st.rerun()

        # ── 5. Publish into a Learning Routes step ────────────────────────────────
        st.markdown("### 4 · Publicar en un curso de Learning Routes")
        lr_base, lr_token = env["LR_BASE_URL"] or P.DEFAULT_BASE, env["LR_STUDIO_TOKEN"]
        if len(lr_token) < 16:
            st.info("Pon la URL y el token del studio en «Entorno» (el servidor necesita WP-38 con `studio.api_token`).")
        else:
            if st.button("Cargar cursos") or "lr_steps" not in st.session_state:
                try:
                    st.session_state.lr_steps = P.flatten_steps(P.fetch_routes(lr_base, lr_token))
                    st.session_state.pop("lr_error", None)
                except P.PublishError as error:
                    st.session_state.lr_steps, st.session_state.lr_error = [], str(error)
            if st.session_state.get("lr_error"):
                st.warning(st.session_state.lr_error)
            steps = st.session_state.get("lr_steps") or []
            if steps:
                labels = {f"{r['route']} › {r['module']} › {r['step_title']}" + (" · 🎞 ya tiene vídeo" if r["has_video"] else ""): r
                          for r in steps}
                picked = labels[st.selectbox("Paso del curso", list(labels))]
                p1, p2 = st.columns(2)
                topic, extra = P.topic_for(picked)
                if p1.button("Escribir guion desde este paso", disabled=len(oa_key) <= 10,
                             help="gen_script.py con el título del paso como tema y su descripción como guía"):
                    st.session_state.ms_job = start_job("guion", script_command(topic, picked.get("level") or "A2", 7, WRITER_MODELS[0], extra),
                                                        {}, STUDIO_DIR)
                    st.rerun()
                latest = P.latest_render(lesson_id, STUDIO_DIR)
                if not latest:
                    p2.caption("Esta lección aún no tiene un vídeo renderizado.")
                elif p2.button(f"Publicar «{lesson['title']}» en este paso", type="primary"):
                    video = STUDIO_DIR / "renders" / latest["file"]
                    try:
                        result = P.publish(lr_base, lr_token, picked["step_id"], video, video.with_suffix(".srt"), lesson["title"],
                                           latest.get("duration_s") or 0, lesson_id, latest.get("voice", ""))
                        st.success(f"Publicado en «{picked['step_title']}» (HTTP {result['status']}). Vídeo: `{result.get('video_url', '?')}`")
                        if not result.get("subtitles_sent"):
                            st.warning("Se publicó SIN subtítulos: no había `.srt` junto al render, y el servidor borra los "
                                       "subtítulos del vídeo anterior. Renderiza de nuevo para tenerlos.")
                        st.session_state.pop("lr_steps", None)
                    except P.PublishError as error:
                        st.error(str(error))
                if latest:
                    st.caption(f"Se publicará `{latest['file']}` ({latest.get('voice')}, {latest.get('quality')}, "
                               f"{int((latest.get('duration_s') or 0) // 60)}:{int((latest.get('duration_s') or 0) % 60):02d}).")

        _job_monitor(st)


YT_PRIVACY_WORDS = {"public": "Pública", "unlisted": "Oculta", "private": "Privada"}   # YouTube Studio's words


def _upload_notes(st) -> None:                         # pragma: no cover — UI
    """Yellow only when the click opens Google's consent; grey when only captions will be skipped."""
    from uploader import UploadManager
    youtube = UploadManager().uploaders["youtube"]
    consent = youtube_consent_note(youtube)
    if consent:
        st.warning(consent)
    captions = youtube_captions_note(youtube)
    if captions:
        st.caption(captions)


def _upload_button(st, row: dict, meta: dict, privacy: Optional[str], key: str) -> None:   # pragma: no cover — UI
    """The one «Subir a YouTube» button both doors share (the lesson panel and «Subir → Lecciones»)."""
    @st.fragment
    def _upload():
        from publication_log import read_attempts
        from upload_limits import limit_block
        block = limit_block(read_attempts(), datetime.now())
        if block:                                       # STEP 67: wait for the channel's slot
            st.error(block)
            return
        if not st.button("Subir a YouTube", type="primary", key=key + "_go"):
            return
        bar = st.progress(0.0, text="Subiendo…")
        outcome = upload_to_youtube(row, meta, privacy=privacy,
                                    on_progress=lambda sent, total: bar.progress(sent / total, text=f"Subiendo… {sent * 100 // total} %"))
        if outcome["refused"]:
            st.warning(f"No se sube otra vez: {outcome['refused']}.")
        elif outcome["ok"]:
            bar.progress(1.0, text="Subido")
            st.success(f"Subido: {outcome['url']}")
        for note in outcome["notes"]:
            (st.info if outcome["ok"] else st.error)(note)
    _upload()


def _mins(row: dict) -> str:
    return f"{int(row['duration_s'] // 60)}:{int(row['duration_s'] % 60):02d}" if row.get("duration_s") else "?"


def _review_tab(st, board: dict) -> None:             # pragma: no cover — UI
    """«Revisar y subir»: por revisar and listas para subir on one page, like the Shorts."""
    from publication_log import read_attempts
    from upload_limits import published_last_24h
    from uploader import resolve_privacy
    st.caption(f"Subidos en las últimas 24 h: {len(published_last_24h(read_attempts(), datetime.now()))}")
    st.markdown(f"#### Por revisar ({len(board['por_revisar'])})")
    if not board["por_revisar"]:
        st.caption("Nada por revisar.")
    for row, _ in board["por_revisar"]:
        lesson = lesson_of(row)
        model = voice_model(row)
        cost = f" · ≈${estimate_cost_usd(lesson):.2f}" if lesson else ""
        with st.expander(f"{row['lesson']} · {row['at'][:10]} · {_mins(row)} · voz {model or row.get('voice')}"
                         f"{' · ' + str(row['speed']) + '×' if row.get('speed') else ''}{cost}"):
            _lazy_video(st, STUDIO_DIR / "renders" / row["file"], key=f"rev_{row['file']}")
            flags = english_flags(row)
            st.caption("Palabras en inglés a escuchar: " + ", ".join(f"{b} «{t}»" for b, t in flags) if flags
                       else "Palabras en inglés: 0 avisos")
            note = st.text_input("Nota", key=f"rev_note_{row['file']}")
            c1, c2 = st.columns(2)
            if c1.button("✓ Aprobar", type="primary", key=f"rev_ok_{row['file']}"):
                record_review(row["file"], "aprobada", note)
                st.rerun()
            if c2.button("✗ Rehacer", key=f"rev_redo_{row['file']}"):
                record_review(row["file"], "rehacer", note)
                st.rerun()

    st.markdown(f"#### Listas para subir ({len(board['aprobadas'])})")
    if not board["aprobadas"]:
        st.caption("Aprueba un vídeo arriba para poder subirlo.")
    else:
        _upload_notes(st)
    default = resolve_privacy("youtube")
    for row, _ in board["aprobadas"]:
        lesson = lesson_of(row)
        saved = youtube_json_path(row)
        meta = json.loads(saved.read_text(encoding="utf-8")) if saved.exists() else youtube_metadata(lesson, row)
        key = f"yt_{row['file']}"
        with st.container(border=True):
            st.markdown(f"**{row['lesson']}** · {row['at'][:10]} · {_mins(row)}")
            c1, c2 = st.columns([1, 3])
            poster = STUDIO_DIR / "renders" / row["poster"] if row.get("poster") else None
            if poster and poster.exists():
                c1.image(str(poster), caption="Miniatura")
            title = c2.text_input("Título", meta["title"], max_chars=100, key=key + "_title")
            description = c2.text_area("Descripción", meta["description"], height=240, key=key + "_desc",
                                       help="Los capítulos deben empezar en 0:00 o YouTube los ignora.")
            tags = c2.text_input("Etiquetas (separadas por comas)", ", ".join(meta["tags"]), key=key + "_tags")
            privacy = c2.selectbox("Visibilidad", list(YT_PRIVACY_WORDS), index=list(YT_PRIVACY_WORDS).index(default),
                                   format_func=YT_PRIVACY_WORDS.get, key=key + "_privacy")
            edited = {"title": title.strip(), "description": description.strip(), "hashtags": meta.get("hashtags", []),
                      "tags": [t.strip() for t in tags.split(",") if t.strip()][:15]}
            _upload_button(st, row, edited, privacy=None if privacy == default else privacy, key=key)

    with st.expander(f"Subidas ({len(board['subidas'])})"):
        for row, published in board["subidas"]:
            st.markdown(f"**{row['lesson']}** · Subido · {published['published_at'][:10]} · "
                        f"{published.get('url') or published.get('upload_id')}")
    with st.expander(f"Versiones anteriores y rehechas ({len(board['anteriores']) + len(board['rehacer'])})"):
        for row, review in board["rehacer"]:
            st.caption(f"{row['file']} · marcada para rehacer — {review.get('note') or 'sin nota'}")
        for row, missing in board["anteriores"]:
            if missing:
                st.caption(f"~~{row['file']}~~ · el archivo ya no está")
                continue
            c1, c2 = st.columns([4, 1])
            c1.caption(f"{row['file']} · {row['at'][:10]} · {_mins(row)}")
            if c2.button("Usar esta versión", key=f"rev_use_{row['file']}"):
                record_review(row["file"], "por revisar", reopen=True)
                st.rerun()


def _lazy_video(st, path, key: str, open_now: bool = False) -> None:   # pragma: no cover — UI
    """A player that costs nothing until asked for (same rule as admin.lazy_video)."""
    state_key = f"_lazy_video_{key}"
    if open_now or st.session_state.get(state_key):
        st.video(str(path))
        return
    if st.button("▶️ Ver vídeo", key=f"_lazy_btn_{key}"):
        st.session_state[state_key] = True
        st.video(str(path))


def _job_monitor(st) -> None:                          # pragma: no cover — UI
    job_id = st.session_state.get("ms_job")
    if not job_id:
        return
    status = job_status(job_id)
    state = status.get("state", "starting")
    if state in ("starting", "running"):
        fragment = getattr(st, "fragment", None)
        if fragment is None:                           # very old Streamlit
            st.info(f"⏳ `{job_id}` en marcha… (esta página se refresca sola)")
            with st.expander("Log", expanded=True):
                st.code(job_log(job_id) or "…", language="text")
            time.sleep(3)
            st.rerun()
            return

        # A FRAGMENT, not sleep(3) + st.rerun(). The old loop re-ran the WHOLE
        # page every three seconds for the length of a render -- every lesson
        # summary, every player -- and the page sat greyed out ("running…")
        # most of the time. Now only this box repaints; when the job leaves
        # the running state one full rerun shows the result.
        @fragment(run_every=3)
        def _live():
            now = job_status(job_id)
            if now.get("state", "starting") not in ("starting", "running"):
                st.rerun()
            st.info(f"⏳ `{job_id}` en marcha… (este recuadro se refresca solo)")
            with st.expander("Log", expanded=True):
                st.code(job_log(job_id) or "…", language="text")

        _live()
    elif state == "done":
        result = status.get("result", {})
        st.success(f"✅ `{job_id}` terminó en {status.get('seconds')} s.")
        with st.expander("Log"):
            st.code(job_log(job_id, 30) or "", language="text")
        if result.get("file"):
            st.video(str(STUDIO_DIR / "renders" / result["file"]))
        if st.button("Cerrar", key="close_job"):
            del st.session_state.ms_job
            st.session_state.pop("el_voices", None)
            st.rerun()
    else:
        st.error(f"❌ `{job_id}` falló (código {status.get('code')}). {status.get('result', {}).get('error', '')}")
        st.code(job_log(job_id, tail=60) or "(sin log)", language="text")
        if st.button("Cerrar", key="close_job"):
            del st.session_state.ms_job
            st.rerun()
