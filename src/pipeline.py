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
TTS_OWNED_KEYS = ('words', 'segments', 'duration', 'segment_times',
                  'timing_source', 'tts_calls')

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


class BackgroundUnavailable(PipelineError):
    """No footage could be found and no preset was asked for.

    Raised instead of substituting one of the 76 flat presets in the enabled
    rotation. `un default solo puede renderizar MENOS, nunca algo falso` — a
    colour field where moving footage was promised is not less, it is
    something else, and it reports itself complete.

    The caller marks the job failed; admin.run_pipeline_with_tracking
    already funnels every exception into complete_job(success=False), so a
    refusal ends as a readable failed row rather than a stuck one.
    """


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




def resolve_background(profile: Dict = None, background: str = None, *,
                       topic: str = None, category: str = None,
                       entry: Dict = None,
                       dest_dir=None, duration: float = None,
                       on_record=None) -> str:
    """THE place a background is decided. Both entry points call this.

    Returns "clips:<dir>" — the ONLY shape there is — or raises
    BackgroundUnavailable. It no longer returns a preset name, a photo path,
    or None, because footage is the only background now.

    Priority, and the order is the specification:

      1. explicit `background`  -> a clips directory, or "clips:<dir>".
                                   A PRESET NAME IS REFUSED, not obeyed.
      2. profile clips mode     -> clips:<dir>
      3. topic + a destination  -> fetch this video's OWN footage into that
                                   directory and return clips:<that dir>
      4. topic + a destination  -> the local cache, when the network gave us
                                   nothing. Free, and still footage.
         refuse                 -> BackgroundUnavailable, naming every tier
                                   that declined.

    WHAT WAS REMOVED, AND WHY IT KEPT COMING BACK.

    There were EIGHT ways a flat background reached the screen, and three
    successive packages each closed some and preserved one more escape
    hatch nobody had asked for. Gone in one cut: fast_mode's static preset,
    the $0.041 generated-image tier, the config pin, the 76-name terminal
    rotation, the v2 branch, and this function's willingness to hand back
    whatever string the caller passed.

    `si es tan simple como quitar todo lo que no sean los videos y ya`. The
    consequence was accepted explicitly: Pexels failing with an empty cache
    means NO VIDEO, not an ugly one.

    WHERE TIER 3 SITS, AND WHY THERE. Below tier 2, because tier 2 is a
    CONFIGURED instruction and this is a default — the same reasoning that
    keeps tier 1 above everything. It requires `dest_dir` and fires only
    when given one: footage belongs to ONE artifact, so a caller with
    nowhere to put clips falls through to the cache and then to the refusal.
    """
    attempts: List[Dict] = []

    def decided(value, tier, tier_name, payload: Dict = None):
        """THE ONLY EXIT. Records what was chosen, then hands it back.

        Five of the seven return paths used to record nothing, because
        `on_record` was threaded into the clip and image tiers only. That
        made `background: null` ambiguous between "an instruction nobody
        logged" and "the floor fired behind your back" — opposite
        situations, indistinguishable on the job row. Routing every return
        through here makes the ambiguity unrepresentable, and
        test_background_floor asserts by AST that no `return` bypasses it.
        """
        record = dict(payload or {})
        record.setdefault("kind", "preset")
        if record["kind"] == "preset":
            record.setdefault("preset", value)
        record["tier"] = tier
        record["tier_name"] = tier_name
        if attempts:
            # What was tried and declined on the way here, so a cache hit
            # can be told from a first-choice fetch without reading a log.
            record["attempts"] = list(attempts)
        _emit_background_record(entry, on_record, record)
        return value

    def declined(tier_name: str, reason: str):
        attempts.append({"tier": tier_name, "reason": reason})

    # ── 1. an explicit clips directory ──
    #
    # IT NO LONGER ACCEPTS A PRESET NAME. `--background static_fire` used to
    # render a colour field; a preset is not a background any more, so the
    # instruction is refused and says why rather than quietly obeying.
    # A bare path is accepted as well as a "clips:" value, because typing
    # the directory is the natural thing to do and means the same thing.
    if background:
        if background.startswith("clips:"):
            return decided(background, 1, "explicit_clips",
                           {"kind": "clips", "dir": background[len("clips:"):],
                            "source": "explicit"})
        if Path(background).is_dir():
            return decided(f"clips:{background}", 1, "explicit_clips",
                           {"kind": "clips", "dir": background,
                            "source": "explicit"})
        reason = (f"{background!r} is not a clips directory. Backgrounds are "
                  "footage now: pass a directory of .mp4 files, or "
                  "'clips:<dir>'. The preset rotation was removed.")
        decided(None, "refused", "refused",
                {"kind": "refused", "reason": reason,
                 "requested": background})
        logger.error("background: %s", reason)
        raise BackgroundUnavailable(reason)

    video_cfg = (profile or {}).get("video", {}) or {}

    # ── 2. the profile wants clips ──
    if video_cfg.get("background_mode") == "clips":
        clips_dir = video_cfg.get("clips_dir", "assets/clips")
        logger.info("background: profile is clips mode -> %s", clips_dir)
        return decided(f"clips:{clips_dir}", 2, "profile_clips",
                       {"kind": "clips", "dir": clips_dir,
                        "source": "profile"})

    # ── 3. this video's own footage ──
    if topic and dest_dir:
        resolved, payload = _clip_background(topic, category, dest_dir,
                                             duration)
        if resolved:
            return decided(resolved, 3, "pexels", payload)
        declined("pexels", "no usable clip for any query")
    elif topic:
        declined("pexels", "no dest_dir — footage belongs to one artifact")

    # ── 5. the local cache: still footage, and free ──
    #
    # 220 clips were on disk — 102 cache slots alone — and no tier had ever
    # consulted one as a fallback. A degraded background that is STILL
    # FOOTAGE keeps the rule the flat presets broke; a colour field does not.
    if topic and dest_dir:
        resolved, payload = _cache_background(topic, category, dest_dir,
                                              duration)
        if resolved:
            logger.warning("background: Pexels declined for %r — reused %d "
                           "cached clip(s) instead of a flat preset",
                           topic, payload.get("clip_count", 0))
            return decided(resolved, 4, "clip_cache", payload)
        declined("clip_cache", "no clips on disk")

    # ── refuse ──
    #
    # THERE IS NO FLOOR ANY MORE, and that is the whole point. It used to be
    # 76 flat presets — 69 static gradients and 7 animated ones, none of them
    # footage — so a total Pexels decline silently produced a colour field.
    #
    # `el objetivo es poner los videos que tenemos de Pexels`. Pexels failing
    # with an empty cache now means NO VIDEO, not an ugly one; that trade was
    # asked for explicitly. Nothing degrades to a colour field because there
    # is no colour field left to degrade to.
    reason = ("no footage available: " +
              "; ".join(f"{a['tier']} ({a['reason']})" for a in attempts)
              if attempts else "no footage available and no topic to fetch for")
    decided(None, "refused", "refused",
            {"kind": "refused", "reason": reason})
    logger.error("background: %s", reason)
    raise BackgroundUnavailable(reason)


def _video_config() -> Dict:
    """The `video:` block of config.yaml, or an empty dict."""
    try:
        import yaml
        cfg = yaml.safe_load(Path(ROOT / "config.yaml").read_text()) or {}
        return cfg.get("video") or {}
    except Exception:                                       # noqa: BLE001
        return {}


def _emit_background_record(entry: Dict, on_record, payload: Dict) -> None:
    """Write one background decision to both sinks. THE only recorder.

    `entry` is the batch path's dict and `on_record` the dashboard's
    callback; both are optional and neither may be allowed to cost the
    video its render, so a raising callback is logged and swallowed.
    """
    if entry is not None:
        entry["background"] = payload
    if on_record is not None:
        try:
            on_record(payload)
        except Exception:                                   # noqa: BLE001
            logger.exception("background: could not record the decision")


#: Words too common to carry meaning when matching a cached clip's query
#: against this video's. Deliberately tiny: the motion vocabulary
#: ("aerial", "drone", "slow", "handheld") is NOT here, because a motion
#: match is a real match — it is how the cache offers something that at
#: least moves the way the missing footage would have.
_MATCH_STOPWORDS = frozenset((
    "a", "an", "the", "of", "in", "on", "at", "to", "and", "or", "with",
    "from", "into", "over", "under", "for", "by", "as", "is", "its",
))


def _match_words(text: str) -> set:
    """Lowercase word set for relevance matching, minus the noise words."""
    import re as _re
    return {w for w in _re.findall(r"[a-z0-9]+", str(text or "").lower())
            if len(w) > 2 and w not in _MATCH_STOPWORDS}


def _cache_background(topic: str, category: str = None, dest_dir=None,
                      duration: float = None):
    """Footage from the LOCAL CACHE when the network gave us none.

    220 clips were on disk — 102 cache slots, plus what previous artifacts
    kept — and no tier had ever consulted one as a fallback. This tier costs
    $0.00, needs no network, and still hands back video, which is the entire
    point: a degraded background that is STILL FOOTAGE keeps the rule that a
    flat colour field breaks.

    HOW THE CLIP IS CHOSEN. The cache is keyed by the query that fetched it
    and each slot keeps that query in query.json, so relevance is a set
    intersection over words — no similarity engine, no model, no second API.
    The topic and category are weighted double against the generated
    queries, so "laptop keyboard / technology" prefers a keyboard clip over
    a volcano one that merely shares the words "slow motion". Ties break on
    the slot name so the same video picks the same clip twice running.

    When nothing overlaps at all the highest-scoring-zero wins, which is a
    deterministic arbitrary clip. That is the documented fallback and it is
    still footage.

    Returns (value, payload), or (None, None) to fall through to the refusal.
    """
    if not dest_dir:
        return None, None
    try:
        import topic_clips as _clips
    except Exception:                                       # noqa: BLE001
        logger.exception("background: topic_clips is unavailable")
        return None, None

    cache_dir = Path(getattr(_clips, "CACHE_DIR", ""))
    if not cache_dir.is_dir():
        return None, None

    try:
        want = _clips.clips_needed(duration or 30.0)
    except Exception:                                       # noqa: BLE001
        want = 1
    try:
        queries = _clips.build_queries(topic, category, count=want)
    except Exception:                                       # noqa: BLE001
        # UnknownCategory and friends. The cache is the fallback tier; it
        # must not need the thing that already failed.
        queries = []

    strong = _match_words(topic) | _match_words(category)
    weak = set()
    for query in queries:
        weak |= _match_words(query)

    candidates = []
    for slot in sorted(cache_dir.iterdir()):
        if not slot.is_dir():
            continue
        files = sorted(slot.glob("*.mp4"))
        if not files:
            continue
        meta = {}
        meta_path = slot / "query.json"
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {}
        cached_query = str(meta.get("query") or slot.name.replace("_", " "))
        words = _match_words(cached_query)
        score = 2 * len(strong & words) + len(weak & words)
        candidates.append((-score, slot.name, files[0], meta, cached_query))

    if not candidates:
        return None, None

    candidates.sort(key=lambda c: (c[0], c[1]))
    out_dir = Path(dest_dir)
    records, placed_bytes = [], 0
    for negative, _name, source, meta, cached_query in candidates[:max(1, want)]:
        try:
            dest = _clips._place(source, out_dir)
        except Exception:                                   # noqa: BLE001
            logger.exception("background: could not place cached clip %s", source)
            continue
        size = dest.stat().st_size
        placed_bytes += size
        records.append({"query": cached_query, "path": str(dest),
                        "bytes": size, "score": -negative, **meta})

    if not records:
        return None, None

    return f"clips:{out_dir}", {
        "kind": "clips",
        "source": "cache",
        "dir": str(out_dir),
        "topic": topic,
        "category": category,
        "queries": queries,
        "clips": records,
        "clip_count": len(records),
        "bytes": placed_bytes,
        "megabytes": round(placed_bytes / 1e6, 2),
        "cost_usd": 0.0,
        "matched_by": "query token overlap (topic/category weighted double)",
        "attribution": getattr(_clips, "ATTRIBUTION_LINE", ""),
    }


def _clip_background(topic: str, category: str = None, dest_dir=None,
                     duration: float = None):
    """Fetch this video's footage into `dest_dir`. Returns (value, payload).

    (None, None) means "fall through". Nothing in here raises: a background
    problem costs a background, never the video — the caller treats the
    empty result as "try the next tier" without a guard.

    IT NO LONGER RECORDS. Recording moved to resolve_background.decided(),
    because a tier that records its own decision can only describe the tier
    it is; the record has to name the tier that actually WON, and five of
    the seven paths had no way to say so.

    There is no gate call here, unlike the image tier. Contrast for a clip
    cannot be settled at fetch time: the same file is a different picture at
    t=2 and t=18, so it is measured against the composited scrim at render
    time by clip_contrast.worst_over_clip. Fetching is fetching.
    """
    try:
        from topic_clips import fetch_for_topic
    except Exception:                                       # noqa: BLE001
        logger.exception("background: topic_clips is unavailable")
        return None, None

    try:
        result = fetch_for_topic(topic, category, duration=duration or 30.0,
                                 out_dir=Path(dest_dir))
    except Exception:                                       # noqa: BLE001
        # UnknownCategory lands here too. It is a real defect and it is
        # logged as one, but it must not cost the video its render.
        logger.exception("background: could not fetch clips for %r (%s)",
                         topic, category)
        return None, None

    if not result:
        logger.warning("background: no clips for %r (%s) — falling through",
                       topic, category)
        return None, None

    logger.info("background: %d clips (%.1f MB) for %r -> %s",
                result["clip_count"], result["megabytes"], topic, result["dir"])
    return f"clips:{result['dir']}", {"kind": "clips", "source": "pexels",
                                      **result}


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
                 timeout: float = None,
                 font_path: str = None,
                 native_language: str = "es") -> Path:
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
    # ALWAYS passed, and always a clips value. resolve_background raises
    # rather than returning None, so `background or <a preset>` — which is
    # what this line used to say — was dead code guarding an impossible case
    # with the very thing the cascade exists to avoid.
    cmd.extend(["-b", background])
    cmd.extend(["--native-language", native_language])

    logger.info("=" * 50)
    logger.info("STEP 3: Generating Video")
    logger.info("=" * 50)
    logger.info("Type: %s", video_type or 'auto-detect')
    if background:
        logger.info("Background: %s", background)
    logger.info("Output: %s", video_path)

    env = os.environ.copy()
    if font_path:
        env["VIDEO_FONT_PATH"] = str(Path(font_path).resolve())
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
