"""STEP 85b §0-§2: natural thumbnails, chosen per video and checked by measurements.

Every thumbnail is a REAL frame of its video. For the formats drawn by our PIL kits it is drawn directly at
1080x1920 (lossless), never grabbed from the compressed MP4. Each artifact gets `<stem>.thumb/` next to its
sidecar (not a shared `thumb/`: several artifacts live in one folder) holding `thumb.jpg` (what is uploaded),
`cands/` (A, B, C as PNG) and `thumb.json` (the chosen one, the metrics and why).
"""
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from . import web  # noqa: E402

W, H = 1080, 1920
STEADY_DT = 0.12                 # frames compared at t ± this
SLIDE_STEP, SLIDE_MAX = 0.04, 0.6
#: calibrated 2026-11 on settled Tablero frames vs mid-flip ones (see tests/test_thumbs.py)
STEADY_MAX = 1.2                 # mean absolute difference (0-255) on a 270x480 grey frame
SHARP_MIN = 300.0                # half the weakest of 10 settled frames measured (631 to 1830)
LUMA_RANGE = (40.0, 215.0)
EDGE_MIN = 0.02                  # share of pixels that are edges
JPEG_MAX = 2_000_000


def thumb_dir(mp4: Path) -> Path:
    return Path(mp4).with_name(Path(mp4).stem + ".thumb")


# ── measurements ─────────────────────────────────────────────────────

def _grey(rgb: np.ndarray, size=(270, 480)) -> np.ndarray:
    return np.asarray(Image.fromarray(rgb).convert("L").resize(size, Image.BILINEAR), dtype=np.float32)


def steadiness(draw: Callable[[float], np.ndarray], t: float, dt: float = STEADY_DT) -> float:
    """Mean absolute difference of the frame at t against the ones at t-dt and t+dt (0 = perfectly still)."""
    mid = _grey(draw(t))
    return float(max(np.abs(mid - _grey(draw(max(0.0, t - dt)))).mean(), np.abs(mid - _grey(draw(t + dt))).mean()))


def laplacian_variance(rgb: np.ndarray, box: Tuple[int, int, int, int] = (0, 430, W, 1475)) -> float:
    g = np.asarray(Image.fromarray(rgb).convert("L"), dtype=np.float32)[box[1]:box[3], box[0]:box[2]]
    lap = 4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    return float(lap.var())


def luminance_and_edges(rgb: np.ndarray) -> Tuple[float, float]:
    g = np.asarray(Image.fromarray(rgb).convert("L"), dtype=np.float32)
    gx, gy = np.abs(np.diff(g, axis=1))[:-1], np.abs(np.diff(g, axis=0))[:, :-1]
    return float(g.mean()), float(((gx + gy) > 40).mean())


def measure(draw: Callable[[float], np.ndarray], t: float, frame: Optional[np.ndarray] = None, sharp_min: float = SHARP_MIN) -> Dict:
    frame = frame if frame is not None else draw(t)
    luma, edges = luminance_and_edges(frame)
    m = {"t": round(t, 3), "steady": round(steadiness(draw, t), 3), "sharp": round(laplacian_variance(frame), 1),
         "luma": round(luma, 1), "edges": round(edges, 4)}
    m["steady_ok"] = m["steady"] <= STEADY_MAX
    m["sharp_ok"] = m["sharp"] >= sharp_min
    m["not_blank_ok"] = LUMA_RANGE[0] <= luma <= LUMA_RANGE[1] and edges >= EDGE_MIN
    m["ok"] = m["steady_ok"] and m["sharp_ok"] and m["not_blank_ok"]
    return m


def settle(draw: Callable[[float], np.ndarray], t: float, limit: float, sharp_min: float = SHARP_MIN) -> Tuple[float, Dict]:
    """The candidate's moment: t if it passes, else the first passing frame sliding forward in 40 ms steps up to
    0.6 s (never past `limit`). Returns (t, metrics); metrics["shift"] is how far it slid, and metrics["ok"]
    is False when nothing in the window passed (the steadiest is returned)."""
    best, best_m, shift = t, measure(draw, t, sharp_min=sharp_min), 0.0
    if best_m["ok"]:
        return best, {**best_m, "shift": 0.0}
    steadiest = (best, best_m, 0.0)
    while shift + SLIDE_STEP <= SLIDE_MAX and t + shift + SLIDE_STEP <= limit:
        shift += SLIDE_STEP
        m = measure(draw, t + shift, sharp_min=sharp_min)
        if m["ok"]:
            return t + shift, {**m, "shift": round(shift, 2)}
        if m["steady"] < steadiest[1]["steady"]:
            steadiest = (t + shift, m, round(shift, 2))
    return steadiest[0], {**steadiest[1], "shift": steadiest[2]}


# ── the moment rule, per format ──────────────────────────────────────

def hdys_moments(data: Dict, duration: float) -> List[Tuple[str, float]]:
    """A: the 4th tile just lit, three done (right after the 3rd reveal settles); B: frame 0; C: the 6th reveal
    settled. The Tablero beats the renderer already derives."""
    from video.how_do_you_say import Timeline
    from video.tablero.frame import Beats
    tl = Timeline(data, duration)
    b = Beats(tl)
    out = []
    if tl.n > 3:
        out.append(("A", tl.es[3][0] + 0.5))                      # after the 3rd reveal's «bien_hecho» hold: Bubi is `wow`
    out.append(("B", 0.0))
    if tl.n > 6:
        out.append(("C", b.flip_end[5] + 0.3))
    return out


def level_moments(data: Dict, duration: float, sixth: bool = False) -> List[Tuple[str, float]]:
    """phrases_level / vida real: the first Spanish phrase lit, its English NOT yet revealed. level_test, say_it_level
    and the grammar types: the first question on screen with its options, before any answer. Both are
    `LevelTimeline.row[0]` (the row lights up with its prompt) plus a short settle, kept before `answer[0]`.
    C: the 6th reveal settled (phrases) or the second question (the others)."""
    from video.how_do_you_say import LevelTimeline
    tl = LevelTimeline(data, duration)
    first = lambda i: tl.row[i] + min(0.5, max(0.0, (tl.answer[i][0] - tl.row[i]) / 2))      # noqa: E731
    out = [("A", first(0)), ("B", 0.0)]
    if sixth and tl.n > 6:
        from video.tablero.frame import FLIP_DUR
        out.append(("C", tl.answer[5][0] + FLIP_DUR + 0.3))
    elif tl.n > 1:
        out.append(("C", first(1)))
    return out


# ── encoding ─────────────────────────────────────────────────────────

def encode_jpeg(rgb: np.ndarray) -> bytes:
    """1080x1920 sRGB, quality 92, 4:4:4 chroma, progressive, no metadata; under 2 MB (quality down to 86, then 4:2:0)."""
    im = Image.fromarray(rgb).convert("RGB")
    for q, sub in ((92, 0), (90, 0), (88, 0), (86, 0), (86, 2)):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, subsampling=sub, progressive=True, optimize=True)
        if buf.tell() <= JPEG_MAX:
            return buf.getvalue()
    return buf.getvalue()


# ── making a video's thumbnails ──────────────────────────────────────

def make_with_kit(mp4: Path, data: Dict, duration: float, draw: Callable[[float], np.ndarray], moments: List[Tuple[str, float]],
                  sharp_min: float = SHARP_MIN, checks: Optional[Callable[[Dict], Dict]] = None,
                  root: Optional[Path] = None) -> Dict:
    """Candidates drawn losslessly by a PIL kit at their moments, measured, the default chosen, thumb.jpg written."""
    folder = thumb_dir(mp4) if root is None else root
    (folder / "cands").mkdir(parents=True, exist_ok=True)
    cands: Dict[str, Dict] = {}
    for label, t in moments:
        tt, m = settle(draw, t, duration, sharp_min)
        Image.fromarray(draw(tt)).save(folder / "cands" / f"{label}.png")
        cands[label] = {**m, "t": round(tt, 3), "wanted": round(t, 3), "source": "kit"}
    chosen = next((k for k in ("A", "B", "C") if k in cands and cands[k]["ok"]), None)
    why = "A: the format's moment passed every check" if chosen == "A" else (
        f"A failed or is missing; {chosen} is the first candidate that passes" if chosen else "no candidate passed: A kept")
    chosen = chosen or ("A" if "A" in cands else next(iter(cands)))
    return _finish(folder, chosen, cands, why, checks(data) if checks else None)


def make_for_tablero(mp4: Path, data: Dict, duration: float, root: Optional[Path] = None) -> Dict:
    from video.tablero import frame as F
    from .checks import tablero_checks
    return make_with_kit(mp4, data, duration, lambda t: F.create_frame_tablero(t, data, duration), hdys_moments(data, duration),
                         checks=tablero_checks, root=root)


#: the notebook's text is thin ink on paper: its settled frames measure about a third of the Tablero's (STEP 85b §2)
NOTEBOOK_SHARP_MIN = SHARP_MIN / 3


def make_for_kit(mp4: Path, data: Dict, duration: float) -> Optional[Dict]:
    """The kit-drawn formats other than the Tablero hdys: Tablero phrases, the notebook hdys and every level type.
    Returns None when the format has no kit moment rule (the caller falls back to the MP4)."""
    vtype, variant = data.get("type"), data.get("design_variant") or "tablero"
    from video.tablero import frame as F
    if vtype == "how_do_you_say" and variant != "tablero":
        from video.how_do_you_say import create_frame_how_do_you_say
        return make_with_kit(mp4, data, duration, lambda t: create_frame_how_do_you_say(t, data, duration), hdys_moments(data, duration),
                             NOTEBOOK_SHARP_MIN)
    if vtype == "phrases_level" and variant == "tablero":
        return make_with_kit(mp4, data, duration, lambda t: F.create_frame_tablero_phrases(t, data, duration),
                             level_moments(data, duration, sixth=True))
    if vtype in ("level_test", "say_it_level", "true_false_level", "fill_level", "choose_level", "phrases_level"):
        from video.how_do_you_say import create_frame_level
        return make_with_kit(mp4, data, duration, lambda t: create_frame_level(t, data, duration), level_moments(data, duration),
                             NOTEBOOK_SHARP_MIN)
    return None


def _finish(folder: Path, chosen: str, cands: Dict, why: str, checks: Optional[Dict] = None) -> Dict:
    pick(folder, chosen)
    info = {"chosen": chosen, "why": why, "metrics": cands}
    if checks:                                              # nothing cut + readable small (x-height is a warning)
        info["checks"] = checks
    (folder / "thumb.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return web.make_web(folder) or info


def pick(folder: Path, label: str) -> Path:
    """Make candidate `label` the uploaded thumbnail (Revisar's switch): no re-render, just a re-encode of the PNG."""
    png = folder / "cands" / f"{label}.png"
    if not png.exists():
        raise FileNotFoundError(f"no candidate {label}")
    out = folder / "thumb.jpg"
    out.write_bytes(encode_jpeg(np.asarray(Image.open(png).convert("RGB"))))
    info_path = folder / "thumb.json"
    if info_path.exists():
        info = json.loads(info_path.read_text(encoding="utf-8"))
        info["chosen"] = label
        info_path.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        web.make_web(folder)                                # the panel's WebPs follow the choice, still no re-render
    return out


def choose(mp4: Path, label: str) -> Path:
    """Revisar's click: switch thumb.jpg (and the panel's WebPs) to candidate `label` and tell the sidecar. Marked as
    Garcia's pick so a later backfill never overwrites it."""
    folder = thumb_dir(mp4)
    out = pick(folder, label)
    info_path = folder / "thumb.json"
    info = json.loads(info_path.read_text(encoding="utf-8"))
    info["manual"] = True
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    sidecar = Path(mp4).with_suffix(".json")
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        meta.setdefault("thumbnail", {}).update({"chosen": label, "metrics": info["metrics"].get(label, {}), "manual": True})
        sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, ValueError):
        pass                                                # no sidecar yet: thumb.json still has the choice
    return out


def carry(src_mp4: Path, dest_dir: Path) -> None:
    """The move helpers call this: the `<stem>.thumb/` folder travels with the MP4 and its sidecar."""
    folder = thumb_dir(src_mp4)
    if folder.is_dir():
        target = dest_dir / folder.name
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(folder), str(target))


# ── any format: the dispatcher the render calls ──────────────────────

def _extract(mp4: Path, t: float, out: Path) -> bool:
    import subprocess
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-accurate_seek", "-i", str(mp4), "-frames:v", "1",
                        "-vf", f"scale={W}:{H}:flags=lanczos", str(out)], capture_output=True, timeout=60)
    return r.returncode == 0 and out.exists()


def make_from_mp4(mp4: Path, duration: float, root: Optional[Path] = None) -> Dict:
    """For formats we cannot redraw: A at 20 % (past the intro), B frame 0, C at 45 %, extracted from the MP4 with
    an accurate seek and lanczos. Measured on sharpness and not-blank only (a steadiness check needs the kit)."""
    folder = thumb_dir(mp4) if root is None else root
    (folder / "cands").mkdir(parents=True, exist_ok=True)
    cands: Dict[str, Dict] = {}
    for label, frac in (("A", 0.20), ("B", 0.0), ("C", 0.45)):
        png = folder / "cands" / f"{label}.png"
        t = duration * frac
        if not _extract(mp4, t, png):
            continue
        frame = np.asarray(Image.open(png).convert("RGB"))
        luma, edges = luminance_and_edges(frame)
        m = {"t": round(t, 3), "sharp": round(laplacian_variance(frame), 1), "luma": round(luma, 1), "edges": round(edges, 4),
             "source": "mp4"}
        m["ok"] = m["sharp"] >= SHARP_MIN / 3 and LUMA_RANGE[0] <= luma <= LUMA_RANGE[1] and edges >= EDGE_MIN
        cands[label] = m
    if not cands:
        raise RuntimeError("no frame could be extracted")
    chosen = next((k for k in ("A", "B", "C") if k in cands and cands[k]["ok"]), next(iter(cands)))
    return _finish(folder, chosen, cands, f"{chosen}: first extracted frame that is sharp and not blank (no kit for this format)")


def make_for_video(mp4: Path, data: Dict, duration: float) -> Optional[Dict]:
    """The render's call. Never raises: a missing thumbnail must not fail a video. Returns the thumb.json info."""
    import logging
    try:
        if data.get("type") == "how_do_you_say" and (data.get("design_variant") or "tablero") == "tablero" \
                and data.get("segment_times") and data.get("items"):
            return make_for_tablero(mp4, data, duration)
        if data.get("segment_times") and data.get("items"):
            try:
                info = make_for_kit(mp4, data, duration)
                if info:
                    return info
            except Exception:                               # noqa: BLE001 — a kit that cannot draw falls back to the MP4
                logging.getLogger(__name__).exception("thumbnails: kit draw failed for %s, using the MP4", mp4)
        return make_from_mp4(mp4, duration)
    except Exception:                                       # noqa: BLE001
        logging.getLogger(__name__).exception("thumbnails: could not make them for %s", mp4)
        return None
