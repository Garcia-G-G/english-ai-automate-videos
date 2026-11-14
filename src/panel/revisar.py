"""STEP 83 §3: the data behind the new Revisar. Frames drawn with ffmpeg (free), the six checks read from the
sidecar, the reject reasons. A value the sidecar does not hold is «sin dato», never a tick."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SIN = "sin dato"
REASONS = ["audio", "imagen", "texto", "otro"]
LUFS_OK = (-24.0, -12.0)


def duration_seconds(mp4: Path) -> Optional[float]:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        return float(out)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def frame_times(duration: float, outro_start: Optional[float] = None) -> List[float]:
    """0 %, 25 %, 50 %, 75 %, the outro and the end."""
    outro = outro_start if outro_start is not None else max(0.0, duration - 4.0)
    return [0.0, duration * 0.25, duration * 0.5, duration * 0.75, min(outro, duration - 0.1), max(0.0, duration - 0.1)]


def _frame(mp4: Path, t: float, out: Path, width: int) -> bool:
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(mp4), "-frames:v", "1",
                        "-vf", f"scale={width}:-2", str(out)], capture_output=True, timeout=60)
    return r.returncode == 0 and out.exists()


def frames(mp4: Path, outro_start: Optional[float] = None) -> Tuple[Optional[Path], Optional[Path]]:
    """(frame 0 large, 6-frame strip), cached next to the sidecar and drawn once per MP4 (re-drawn only when the
    MP4 is newer). None when ffmpeg cannot read it."""
    f0, strip = mp4.with_name(mp4.stem + "_f0.png"), mp4.with_name(mp4.stem + "_strip.png")
    fresh = lambda p: p.exists() and p.stat().st_mtime >= mp4.stat().st_mtime           # noqa: E731
    if fresh(f0) and fresh(strip):
        return f0, strip
    dur = duration_seconds(mp4)
    if not dur:
        return None, None
    if not _frame(mp4, 0.0, f0, 540):
        return None, None
    from PIL import Image
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    tiles = []
    for k, t in enumerate(frame_times(dur, outro_start)):
        p = tmp / f"{k}.png"
        if _frame(mp4, t, p, 180):
            tiles.append(Image.open(p).convert("RGB"))
    if not tiles:
        return f0, None
    sheet = Image.new("RGB", (len(tiles) * 186, tiles[0].height), (245, 241, 234))
    for k, im in enumerate(tiles):
        sheet.paste(im, (k * 186, 0))
    sheet.save(strip)
    return f0, strip


def checks(meta: Dict, repeated_words: Optional[int], title_problem: Optional[str], title_checked: bool) -> List[Dict]:
    """The six checks: [{key, label, state ok|bad|none, value}]. Only what the sidecar / guards hold counts."""
    deess = (meta or {}).get("deesser") or {}
    lufs = deess.get("input_lufs")
    gate = (meta or {}).get("gate")
    flags = (meta or {}).get("blocking_flags") or []
    out = []
    if lufs is None:
        out.append({"key": "volume", "label": "Volumen", "state": "none", "value": SIN})
    else:
        out.append({"key": "volume", "label": "Volumen", "state": "ok" if LUFS_OK[0] <= lufs <= LUFS_OK[1] else "bad",
                    "value": f"{lufs:.1f} LUFS"})
    out.append({"key": "sync", "label": "Voz y texto a la vez", "state": "none", "value": SIN})
    out.append({"key": "vowels", "label": "Vocales en español", "state": "none", "value": SIN})
    out.append({"key": "motion", "label": "Siempre hay movimiento", "state": "none", "value": SIN})
    if repeated_words is None:
        out.append({"key": "words", "label": "Palabras nuevas", "state": "none", "value": SIN})
    else:
        out.append({"key": "words", "label": "Palabras nuevas", "state": "ok" if repeated_words <= 3 else "bad",
                    "value": f"{repeated_words} repetidas"})
    if not title_checked:
        out.append({"key": "text", "label": "Título y texto limpios", "state": "none", "value": SIN})
    else:
        out.append({"key": "text", "label": "Título y texto limpios", "state": "bad" if title_problem else "ok",
                    "value": title_problem or "sin problemas"})
    return out


def verdict(meta: Dict, rows: List[Dict]) -> str:
    """«Pasa el control de calidad: N de M» or the reason it does not (the gate's own flags first)."""
    gate = (meta or {}).get("gate")
    flags = (meta or {}).get("blocking_flags") or []
    if gate and gate != "PASS":
        return f"No pasa el control de calidad: {', '.join(map(str, flags)) or gate}"
    known = [r for r in rows if r["state"] != "none"]
    good = sum(1 for r in known if r["state"] == "ok")
    if gate == "PASS":
        return f"Pasa el control de calidad: {good} de {len(rows)} comprobaciones con dato"
    return f"Sin veredicto del control de calidad ({good} de {len(rows)} comprobaciones con dato)"


def save_reject_reason(sidecar: Path, reason: str, note: str, now_iso: str) -> None:
    """Write why a video was rejected into its sidecar, before it is moved to rejected/."""
    if not sidecar.exists():
        return
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    data["rejected"] = {"reason": reason, "note": note.strip()[:200], "at": now_iso}
    sidecar.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def cost_of(meta: Dict) -> Optional[float]:
    total = ((meta or {}).get("cost") or {}).get("total_usd")
    return float(total) if total is not None else None
