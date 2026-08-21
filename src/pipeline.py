#!/usr/bin/env python3
"""Shared generation pipeline — the single implementation of TTS + render.

Both entry points import this module:

    main.py            (CLI)        → argparse + paths + orchestration
    src/admin.py       (Streamlit)  → job tracking + paths + orchestration

Neither of them owns the TTS dispatch, the script/TTS JSON merge, or the
render subprocess any more.  Identical input must produce identical audio
regardless of which entry point ran it, so everything that decides
*provider / model / voice / language* lives here and nowhere else.

No module-level mutable state: every knob is an explicit argument.
"""

import json
import logging
import os
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

# API keys / TTS_PROVIDER come from .env for both entry points.
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:  # dotenv is optional at import time
    pass

from script_schema import validate_script  # noqa: E402

# Providers the factory knows about (tts_providers.get_tts_provider).
VALID_PROVIDERS = ("elevenlabs", "openai", "google", "edge")

# Keys owned by the TTS result — never overwritten by script data.
TTS_OWNED_KEYS = ('words', 'segments', 'duration', 'segment_times')

# How many lines of renderer output to keep for error messages.
RENDER_LOG_TAIL = 80

# A real mp3/mp4 is never this small; anything smaller is a failed write.
MIN_OUTPUT_BYTES = 1000

# Render timeout, sized from measurement rather than rounded (2026-07-28):
#   longest content in the repo   2038 frames (67.96s fill_blank)
#   worst whole-video frame rate  0.1121 s/frame (quiz; its answer-reveal
#                                 phase runs at 0.305 s/frame)
#   background pre-render + load  ~15s
#   worst legitimate render       2038 * 0.1121 + 15 = 244s
#   safety factor for a degraded machine (contention / low-power / swap): 4x
#   => 976s, taken to 1200s.
# The old 600s was under-sized: it left only 2.5x over that worst case, and a
# typical quiz already costs 139s. Anything still running at 20 minutes is a
# genuine hang and should be killed.
RENDER_TIMEOUT_S = 1200


class PipelineError(RuntimeError):
    """Base class for pipeline failures."""


class TTSError(PipelineError):
    """TTS generation failed."""


class RenderError(PipelineError):
    """Video render failed. Carries the renderer's last output lines.

    subprocess.run(capture_output=True) discards TimeoutExpired.stderr, so a
    render timeout used to leave no trace of what the renderer was doing.
    The tail is part of the exception message on purpose: it is what the user
    sees in the dashboard error box.
    """

    def __init__(self, message: str, tail=()):
        self.tail: List[str] = list(tail)
        if self.tail:
            message = (f"{message}\n"
                       f"--- renderer output (last {len(self.tail)} lines) ---\n"
                       + "\n".join(self.tail))
        super().__init__(message)


# ── Profile / background ──────────────────────────────────────────────

def resolve_profile(name: str = None) -> Dict:
    """Resolve the audience profile and export its env overrides.

    Priority: name arg > env VIDEO_PROFILE > config.yaml `profile:` > adults.
    Also pins VIDEO_PROFILE so the render subprocess sees the same profile.
    """
    from profiles import get_active_profile, apply_profile_env

    profile = get_active_profile(name)
    apply_profile_env(profile)
    os.environ["VIDEO_PROFILE"] = profile.get("name", "adults")
    return profile


#: The floor under tier 5. A literal, so the resolver can always answer.
#:
#: Returning None is what produced the defect this function exists to remove:
#: main.py and admin.py both handed None to the renderer, and the renderer
#: subprocess then picked its own palette — which is why every dashboard video
#: had a gen_NNN background and not one had the generated image it had paid
#: for. A resolver that can answer "I don't know" moves the decision somewhere
#: nobody is looking.
#:
#: static_midnight measures 7.13:1 behind the headline and renders once rather
#: than per frame.
TERMINAL_PRESET = "static_midnight"


def resolve_background(profile: Dict = None, background: str = None, *,
                       topic: str = None, category: str = None,
                       entry: Dict = None, fast_mode: bool = False,
                       on_record=None) -> str:
    """THE place a background is decided. Both entry points call this.

    Returns a value generate_video accepts: a preset name, "clips:<dir>", or
    "photo:<path>". NEVER None, and never raises — a background problem must
    cost a plain background, never the video.

    Priority, and the order is the specification:

      0. fast mode              -> a cheap static preset
      1. explicit `background`  -> returned untouched, because --background is
                                   an instruction and not a default
      2. profile clips mode     -> clips:<dir>
      3. topic + category       -> generate an image, GATE it, and use it only
                                   on PASS
      4. background_mode fixed  -> the configured preset
      5. terminal fallback      -> one preset from the enabled rotation, and
                                   TERMINAL_PRESET if even that is empty

    Tier 4 keys on background_mode == "fixed" rather than on
    default_background being set, because default_background IS set in
    config.yaml today; keying on it would make tier 5 unreachable and retire
    the rotation the palette cull exists to curate. default_background is
    still honoured, as the step above the literal inside tier 5.

    This replaces main._background_for_topic and the `random` branch of
    video.backgrounds.get_default_background, which were the same algorithm
    written twice against the same config key — so applying the palette cull
    would have fixed one path and left the other, which is the dashboard's.
    """
    # ── 0. fast mode ──
    if fast_mode:
        logger.info("background: fast mode -> dark_professional")
        return "dark_professional"

    # ── 1. an explicit instruction ──
    if background:
        return background

    video_cfg = (profile or {}).get("video", {}) or {}

    # ── 2. the profile wants clips ──
    if video_cfg.get("background_mode") == "clips":
        clips_dir = video_cfg.get("clips_dir", "assets/clips")
        logger.info("background: profile is clips mode -> %s", clips_dir)
        return f"clips:{clips_dir}"

    # ── 3. this video's own image ──
    if topic:
        resolved = _generated_background(topic, category, entry, on_record)
        if resolved:
            return resolved
        # every failure inside there has already logged its reason

    # ── 4. config pins one ──
    cfg = _video_config()
    if cfg.get("background_mode") == "fixed":
        pinned = cfg.get("default_background")
        if pinned:
            logger.info("background: config is fixed -> %s", pinned)
            return pinned

    # ── 5. the floor ──
    return _terminal_preset(cfg)


def _video_config() -> Dict:
    """The `video:` block of config.yaml, or an empty dict."""
    try:
        import yaml
        cfg = yaml.safe_load(Path(ROOT / "config.yaml").read_text()) or {}
        return cfg.get("video") or {}
    except Exception:                                       # noqa: BLE001
        return {}


def _terminal_preset(cfg: Dict = None) -> str:
    """One preset from the enabled rotation. Always returns something.

    The single place the enabled rotation is read, so the palette cull can be
    applied once and take effect on every path.
    """
    cfg = _video_config() if cfg is None else cfg
    try:
        from backgrounds import BACKGROUND_PRESETS, resolve_enabled
        pool = [n for n in resolve_enabled(cfg.get("enabled_backgrounds") or [])
                if n in BACKGROUND_PRESETS]
        if pool:
            import random as _random
            # SystemRandom so a seeded global RNG cannot pin every video to
            # the same background.
            return _random.SystemRandom().choice(pool)
        pinned = cfg.get("default_background")
        if pinned and pinned in BACKGROUND_PRESETS:
            logger.warning("background: enabled rotation is empty -> %s", pinned)
            return pinned
    except Exception:                                       # noqa: BLE001
        logger.exception("background: could not read the rotation")
    logger.warning("background: nothing usable configured -> %s", TERMINAL_PRESET)
    return TERMINAL_PRESET


def _generated_background(topic: str, category: str = None,
                          entry: Dict = None, on_record=None):
    """Generate an image for `topic` and gate it. None means "use a fallback".

    The gate is BLOCKING: a refused image is never used, it becomes a
    palette. Nothing in here raises.
    """
    def _record(payload):
        if entry is not None:
            entry["background"] = payload
        if on_record is not None:
            try:
                on_record(payload)
            except Exception:                               # noqa: BLE001
                logger.exception("background: could not record the decision")

    try:
        from topic_background import generate_for_topic
        from topic_background_gate import accept
    except Exception:                                       # noqa: BLE001
        logger.warning("background: generation unavailable for %r "
                       "— falling back", topic)
        _record({"source": "palette", "reason": "module unavailable"})
        return None

    try:
        made = generate_for_topic(topic, category)
    except Exception as exc:                                # noqa: BLE001
        logger.exception("background: generation raised for %r", topic)
        _record({"source": "palette", "reason": f"generation raised: {exc}"})
        return None

    if not made:
        logger.warning("background: generation failed for %r — falling back", topic)
        _record({"source": "palette", "reason": "generation failed"})
        return None

    verdict = accept(made["path"], topic=topic)
    payload = {
        "source": "generated" if verdict["passes"] else "palette",
        "image": made["path"],
        "worst_ratio": round(verdict["worst_ratio"], 3),
        "floor": verdict["floor"],
        "gate": "PASS" if verdict["passes"] else "REJECT",
        "cost_usd": made.get("cost_usd"),
    }
    if not verdict["passes"]:
        payload["reason"] = (f"gate refused {verdict['worst_ratio']:.2f}:1 "
                             f"(floor {verdict['floor']})")
        logger.warning("background: gate refused %.2f:1 for %r — falling back",
                       verdict["worst_ratio"], topic)
        _record(payload)
        return None

    _record(payload)
    return f"photo:{made['path']}"


# ── TTS ───────────────────────────────────────────────────────────────

def resolve_provider_name() -> str:
    """The TTS provider both entry points must agree on."""
    name = os.getenv("TTS_PROVIDER", "elevenlabs").strip().lower()
    if name not in VALID_PROVIDERS:
        logger.warning("Unknown TTS_PROVIDER=%r — using 'elevenlabs'", name)
        name = "elevenlabs"
    return name


def _bilingual_enabled() -> bool:
    return os.getenv("ELEVENLABS_BILINGUAL", "1").strip() not in ("0", "false")


def resolve_tts_plan(script_data: Dict, provider_name: str = None) -> Dict:
    """Resolve provider / model / voice / per-segment language — no API calls.

    This is the same resolution the real run performs, so a dry-run plan is
    evidence about the real run and not a separate code path.
    """
    if not script_data:
        raise ValueError("resolve_tts_plan requires script_data")

    provider_name = provider_name or resolve_provider_name()
    video_type = script_data.get('type', 'educational')

    plan = {
        "provider": provider_name,
        "video_type": video_type,
        "voice_id": None,
        "model_id": None,
        "path": None,          # which code path inside the provider runs
        "segments": [],
    }

    if provider_name == "elevenlabs":
        if video_type in ("educational", "pronunciation") and _bilingual_enabled():
            from tts_bilingual import plan_calls, resolve_settings
            settings = resolve_settings()
            calls = plan_calls(script_data, settings)
            plan["voice_id"] = settings["voice_id"]
            plan["model_id"] = settings["model_id"]
            plan["path"] = "tts_bilingual.generate_bilingual_narration"
            plan["segments"] = [
                {
                    "index": c["index"],
                    "language_code": c["lang"],
                    "is_english": c["is_english"],
                    "speed": c["speed"],
                    "text": c["text"],
                }
                for c in calls
            ]
        else:
            # Same env resolution as tts_elevenlabs DEFAULT_VOICE_ID / MODEL_ID,
            # read directly so a dry-run never imports the ElevenLabs SDK.
            plan["voice_id"] = (os.getenv("VIDEO_PROFILE_VOICE_ID")
                                or os.getenv("ELEVENLABS_VOICE_ID")
                                or "ZOgeDYxfyev5qgOXq2lN")
            plan["model_id"] = (os.getenv("VIDEO_PROFILE_TTS_MODEL")
                                or os.getenv("ELEVENLABS_MODEL")
                                or "eleven_v3")
            plan["path"] = f"tts_elevenlabs.generate_{video_type}_audio_segmented"
    elif provider_name == "openai":
        plan["voice_id"] = os.getenv("OPENAI_TTS_VOICE", "nova")
        plan["model_id"] = os.getenv("OPENAI_TTS_MODEL", "tts-1")
        plan["path"] = "tts_openai"
    else:
        plan["path"] = f"tts_{provider_name}"

    return plan


def format_tts_plan(plan: Dict) -> str:
    """Human-readable, byte-comparable rendering of a TTS plan."""
    lines = [
        "TTS PLAN (dry-run — no API calls)",
        f"  provider   : {plan['provider']}",
        f"  video_type : {plan['video_type']}",
        f"  path       : {plan['path']}",
        f"  voice_id   : {plan['voice_id']}",
        f"  model_id   : {plan['model_id']}",
        f"  segments   : {len(plan['segments'])}",
    ]
    for seg in plan["segments"]:
        lines.append(
            f"  [{seg['index']:02d}] language_code={seg['language_code']:<3} "
            f"speed={seg['speed']:.2f} text={seg['text']!r}"
        )
    return "\n".join(lines)


def generate_tts(script_data: Dict,
                 audio_path,
                 script_path=None,
                 allow_edge_fallback: bool = False,
                 dry_run: bool = False) -> Tuple[Optional[Path], Optional[Path]]:
    """Generate narration audio + the companion timestamps JSON.

    Args:
        script_data: The script dict. Required — there is no text-only mode.
        audio_path:  Output mp3 path. The JSON lands next to it.
        script_path: Path to the script JSON on disk (providers use it for
                     automatic English detection).
        allow_edge_fallback: On provider failure, retry with Edge TTS.
                     OFF by default: the fallback silently changes voice,
                     language handling and output schema.
        dry_run:     Resolve and log the plan (provider / model / voice /
                     per-segment language_code), call no API, write
                     <audio>.ttsplan.json, and return (None, None).

    Returns:
        (audio_path, json_path)

    Raises:
        ValueError on missing script_data, TTSError on generation failure.
    """
    if script_data is None:
        raise ValueError("generate_tts requires script_data (there is no text-only mode)")

    # VALIDATION POINT 2 of 3: TTS input.
    #
    # A script can reach here without passing point 1 — main.py --script loads
    # a JSON file straight off disk, and the dashboard replays saved scripts.
    # Both bypass the generator entirely, so this is not a redundant check.
    #
    # It subsumes the old full_script length test, which is now a min_length
    # constraint on the model (script_schema.ScriptBase.full_script).
    dropped = []
    validate_script(script_data, source=str(script_path) if script_path else None,
                    drop_unknown=True, on_drop=dropped.extend)
    if dropped:
        logger.warning("Script carries %d key(s) not in the schema: %s",
                       len(dropped), ", ".join(dropped))

    audio_path = Path(audio_path)
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    provider_name = resolve_provider_name()

    logger.info("=" * 50)
    logger.info("STEP 2: Generating Audio (TTS)")
    logger.info("=" * 50)
    logger.info("Engine: %s", provider_name)
    logger.info("Output: %s", audio_path)

    if dry_run:
        plan = resolve_tts_plan(script_data, provider_name)
        for line in format_tts_plan(plan).splitlines():
            logger.info(line)
        plan_path = audio_path.with_suffix('.ttsplan.json')
        with open(plan_path, 'w', encoding='utf-8') as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        logger.info("Dry-run plan written: %s", plan_path)
        return None, None

    from tts_providers import get_tts_provider

    try:
        provider = get_tts_provider(provider_name)
        provider.generate_from_script(
            script_data, str(audio_path),
            script_path=str(script_path) if script_path else None,
        )
    except Exception as e:
        logger.error("TTS failed (%s): %s", provider_name, e)
        if allow_edge_fallback and provider_name != "edge":
            logger.warning("Falling back to Edge TTS (voice and language handling change)")
            provider = get_tts_provider("edge")
            provider.generate_from_script(
                script_data, str(audio_path),
                script_path=str(script_path) if script_path else None,
            )
        else:
            raise TTSError(f"TTS failed ({provider_name}): {e}") from e

    if not audio_path.exists():
        raise TTSError(f"Audio file not created: {audio_path}")
    if audio_path.stat().st_size < MIN_OUTPUT_BYTES:
        raise TTSError(f"Audio file too small ({audio_path.stat().st_size} bytes): {audio_path}")

    json_path = audio_path.with_suffix('.json')
    if not json_path.exists():
        raise TTSError(f"TTS timestamps file missing: {json_path}")

    return audio_path, json_path


def merge_script_into_tts(script_data: Dict, json_path) -> None:
    """Merge script fields into the TTS JSON, preserving TTS-owned keys.

    TTS_OWNED_KEYS come from the audio and must survive: overwriting them
    with the script's copies desynchronises the renderer from the audio.
    """
    json_path = Path(json_path)
    if not script_data or not json_path.exists():
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        tts_data = json.load(f)

    for key, value in script_data.items():
        if key not in TTS_OWNED_KEYS:
            tts_data[key] = value

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(tts_data, f, ensure_ascii=False, indent=2)


# ── Video ─────────────────────────────────────────────────────────────

def render_video(audio_path,
                 data_path,
                 video_path,
                 video_type: str = None,
                 background: str = None,
                 use_v2: bool = False,
                 timeout: float = None) -> Path:
    """Render the video via `python -m video`, streaming its output to the log.

    Raises RenderError (with the renderer's last output lines) on non-zero
    exit, timeout, or a missing/too-small output file.
    """
    audio_path = Path(audio_path)
    data_path = Path(data_path)
    video_path = Path(video_path)
    video_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-u", "-m", "video",
        "-a", str(audio_path.resolve()),
        "-d", str(data_path.resolve()),
        "-o", str(video_path.resolve()),
    ]
    if video_type:
        cmd.extend(["-t", video_type])
    # ALWAYS passed. resolve_background never returns None, and the renderer
    # requires -b, so there is no path where the subprocess picks its own.
    cmd.extend(["-b", background or TERMINAL_PRESET])
    if use_v2:
        cmd.append("--v2")

    logger.info("=" * 50)
    logger.info("STEP 3: Generating Video")
    logger.info("=" * 50)
    logger.info("Type: %s", video_type or 'auto-detect')
    if background:
        logger.info("Background: %s", background)
    logger.info("Output: %s", video_path)

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(SRC), env.get("PYTHONPATH", "")) if p)

    tail = deque(maxlen=RENDER_LOG_TAIL)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(SRC),
        env=env,
    )

    def _pump():
        for line in proc.stdout:
            line = line.rstrip()
            tail.append(line)
            logger.info("[video] %s", line)

    reader = threading.Thread(target=_pump, daemon=True)
    reader.start()

    try:
        returncode = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        reader.join(timeout=5)
        raise RenderError(f"Video render timed out after {timeout}s", tail)

    reader.join(timeout=5)

    if returncode != 0:
        raise RenderError(f"Video render failed (exit code {returncode})", tail)
    if not video_path.exists():
        raise RenderError(f"Video file not created: {video_path}", tail)
    if video_path.stat().st_size < MIN_OUTPUT_BYTES:
        raise RenderError(
            f"Video file too small ({video_path.stat().st_size} bytes): {video_path}", tail)

    logger.info("Video created: %s (%d bytes)", video_path, video_path.stat().st_size)
    return video_path


def finalize_video(video_path, audio_json_path, variant_seed: str = None) -> Dict:
    """Gate the artifact, and append the outro ONLY if it passes.

    ORDER MATTERS AND IT IS THIS WAY ROUND. A rejected video gets no outro:
    the outro is a call to action pointing at Learning Routes, and putting the
    brand on the end of something the gate just refused is worse than shipping
    nothing. Appending first and gating after would also mean measuring a file
    whose audio has a concat seam in it, which is not the artifact the gate
    was calibrated against.

    Returns a dict describing what happened. Never raises for a rejection —
    one bad video must not take a batch down.
    """
    from qa_gate import analyze, verdict
    from video.outro import append_outro, measure_seam, select_variant

    # Resolve first: qa_gate.analyze reports paths relative to the project
    # root and raises on a relative input, and callers pass whatever they have.
    video_path = Path(video_path).resolve()
    report = analyze(Path(audio_json_path).resolve())
    if report is None:
        return {"video": str(video_path), "gate": "NO_REPORT",
                "outro_appended": False,
                "reason": "no paired audio artifact to gate"}

    v = verdict(report)
    if v["verdict"] != "PASS":
        logger.warning("QA gate REJECTED %s (%s) — no outro appended",
                       audio_json_path, v["blocking_flags"])
        return {"video": str(video_path), "gate": "REJECT",
                "blocking_flags": v["blocking_flags"], "outro_appended": False}

    variant = select_variant(seed=variant_seed or str(video_path))
    seam_t = float(report.get("measured_duration") or 0.0)

    # THE ARTIFACT KEEPS ITS NAME. append_outro defaults to writing
    # <name>_with_outro.mp4, which would change the stem — and the stem is the
    # ledger's key and the idempotency guard's key (publication_log,
    # upload_guard). A finalisation step must not rename the thing the
    # publication record identifies, so the outro'd file replaces the original.
    tmp_out = str(video_path).replace(".mp4", ".outro.tmp.mp4")
    append_outro(str(video_path), variant, output_path=tmp_out)
    os.replace(tmp_out, str(video_path))
    final = str(video_path)
    seam = measure_seam(final, seam_t) if seam_t else None

    # Logged so a later A/B read can attribute performance to copy.
    logger.info("outro variant %s appended to %s", variant["id"], final)
    return {"video": final, "gate": "PASS", "outro_appended": True,
            "outro_variant": variant["id"], "seam": seam}
