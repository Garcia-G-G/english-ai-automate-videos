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
TTS_MODELS = ("eleven_turbo_v2_5", "eleven_flash_v2_5", "eleven_multilingual_v2")   # first two take language_code
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


def lesson_summary(path: Path) -> dict:
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

def render() -> None:                                  # pragma: no cover — UI
    import streamlit as st

    st.markdown("## 🎞️ Manim Studio")
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

    problems, notes = L.validate(lesson), L.warnings(lesson)
    st.caption(f"`lessons/{path.name}` · {L.character_count(lesson)} caracteres de narración · "
               f"{sum(1 for b in lesson['beats'] for x in L.segments(b['narration']) if 'text' in x)} segmentos de voz · "
               f"≈ ${estimate_cost_usd(lesson):.2f} por voz")
    with st.expander(f"Editar narración ({len(lesson['beats'])} golpes)", expanded=bool(problems)):
        st.caption("Edita solo la narración; el inglés va entre [[ ]]. Las palabras que la animación espera deben "
                   "decirse en la frase. Para cambiar la estructura (tipos, tablas, diálogos) edita el JSON abajo.")
        edited = st.data_editor(beats_table(lesson), key=f"editor_{lesson_id}", use_container_width=True, hide_index=True,
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
                                 help="turbo/flash v2.5 aceptan language_code por segmento (inglés en inglés). multilingual_v2 no.")
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
        r1, r2 = st.columns(2)
        render_voice = r1.selectbox("Voz para el vídeo", ready)
        quality = r2.selectbox("Calidad", list(R.QUALITIES), format_func=lambda q: R.QUALITIES[q][1],
                               index=list(R.QUALITIES).index(R.DEFAULT_QUALITY))
        stale_now = stale_beats(lesson, render_voice)
        if stale_now:
            st.warning(f"{len(stale_now)} golpe(s) de `{render_voice}` no coinciden con la narración actual; regenera el audio antes.")
        if st.button("Renderizar vídeo", type="primary", disabled=bool(stale_now) or changed):
            argv, env_add = R.render_command(manim_bin, quality, lesson_id, render_voice)

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

    # ── Renders ───────────────────────────────────────────────────────────────
    st.markdown("### Vídeos renderizados")
    rows = R.ledger(STUDIO_DIR)
    if not rows:
        st.caption("Todavía ninguno.")
    for row in rows[:12]:
        video = STUDIO_DIR / "renders" / row["file"]
        mins = f"{int(row['duration_s'] // 60)}:{int(row['duration_s'] % 60):02d}" if row.get("duration_s") else "?"
        with st.expander(f"{row['at']} · {row.get('lesson', '')} · {row['voice']} · {row['quality']} · {mins} · "
                         f"{row['bytes'] // 1024 // 1024} MB", expanded=row is rows[0]):
            if video.exists():
                st.video(str(video))
                st.caption(f"`{video}`")
                extras = []
                if row.get("poster") and (STUDIO_DIR / "renders" / row["poster"]).exists():
                    extras.append(f"miniatura `{row['poster']}`")
                chapters = STUDIO_DIR / "renders" / row["chapters"] if row.get("chapters") else None
                if chapters and chapters.exists():
                    extras.append("capítulos para YouTube:")
                if extras:
                    st.caption(" · ".join(extras))
                if chapters and chapters.exists():
                    st.code(chapters.read_text(encoding="utf-8"), language="text")
            else:
                st.caption("El archivo ya no está.")


def _job_monitor(st) -> None:                          # pragma: no cover — UI
    job_id = st.session_state.get("ms_job")
    if not job_id:
        return
    status = job_status(job_id)
    state = status.get("state", "starting")
    if state in ("starting", "running"):
        st.info(f"⏳ `{job_id}` en marcha… (esta página se refresca sola)")
        with st.expander("Log", expanded=True):
            st.code(job_log(job_id) or "…", language="text")
        time.sleep(3)
        st.rerun()
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
