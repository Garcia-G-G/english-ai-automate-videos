"""STEP 83 §2: the data and the markup of the new Inicio. Pure functions over what the panel already reads
(stats snapshot, ledger, queue); nothing here calls an API or invents a number. A missing value is «sin dato»."""
from __future__ import annotations

import html
import math
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
TZ = ZoneInfo("America/Costa_Rica")
THUMBS = ROOT / "output" / "thumbs" / "scripts"
SIN = '<span class="sin-dato">sin dato</span>'
PER_DAY = 4
GREEN_AT, RED_BELOW, WEAK_BELOW, CAP = 1.2, 0.5, 0.25, 2.0


def e(text) -> str:
    return html.escape(str(text), quote=True)


def greeting(now: datetime, name: str) -> str:
    h = now.astimezone(TZ).hour
    word = "Buenos días" if h < 12 else ("Buenas tardes" if h < 19 else "Buenas noches")
    return f"{word}, {name}"


DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def date_line(now: datetime) -> str:
    n = now.astimezone(TZ)
    return f"{DAYS[n.weekday()].capitalize()} {n.day} de {MONTHS[n.month - 1]}"


def normals(videos: List[Dict]) -> Dict[str, Optional[float]]:
    """«Lo normal» per format: the median views of its videos older than 3 days (the stats' own mature median)."""
    import channel_stats
    out = {}
    for f in channel_stats.summary(videos)["formats"]:
        out[f["type"]] = f["mature_median"] if f["mature_median"] is not None else None
    return out


def bar(video: Dict, normal: Optional[float]) -> Dict:
    """{ratio, width, colour, label} for one video against its format's normal; ratio None without one."""
    views, days = int(video.get("views", 0)), max(0, video.get("days") or 0)
    if not normal:
        return {"ratio": None, "width": 0, "colour": "blue", "label": f"{views:,} · sin dato de lo normal"}
    ratio = views / normal
    colour = "green" if ratio >= GREEN_AT else ("red" if ratio < RED_BELOW and days >= 1 else "blue")
    label = f"{ratio:.1f}× lo normal" if ratio >= 1 else f"{ratio * 100:.0f} % · día {days}"
    return {"ratio": ratio, "width": min(ratio, CAP) / CAP * 100, "colour": colour, "label": label}


def recent(videos: List[Dict], days: int = 7, n: int = 5) -> List[Dict]:
    return sorted((v for v in videos if v.get("days") is not None and v["days"] <= days), key=lambda v: v["days"])[:n]


def week_totals(videos: List[Dict], days: int = 7) -> Dict:
    week = [v for v in videos if v.get("days") is not None and v["days"] <= days]
    views = sum(int(v.get("views", 0)) for v in week)
    return {"views": views, "videos": len(week), "mean": round(views / len(week)) if week else None}


def postit(videos: List[Dict], norm: Dict[str, Optional[float]]) -> Optional[Dict]:
    """The post-it, only when a rule fires: weak videos (≥ 1 day old, < 25 % of their format's normal), else a
    ≥ 2× winner this week. None otherwise."""
    weak = [v for v in videos if (v.get("days") or 0) >= 1 and (v.get("days") or 0) <= 7 and norm.get(v.get("type"))
            and int(v.get("views", 0)) < WEAK_BELOW * norm[v["type"]]]
    if weak:
        return {"kind": "weak", "videos": sorted(weak, key=lambda v: v["views"])[:3]}
    win = [v for v in videos if (v.get("days") or 0) <= 7 and norm.get(v.get("type")) and int(v.get("views", 0)) >= 2 * norm[v["type"]]]
    if win:
        best = max(win, key=lambda v: v["views"] / norm[v["type"]])
        return {"kind": "win", "videos": [best], "ratio": best["views"] / norm[best["type"]]}
    return None


def days_of_queue(n: int) -> int:
    return math.ceil(n / PER_DAY) if n > 0 else 0


def stats_chip(age_hours: Optional[float]) -> Tuple[str, str]:
    """(text, dot class): green up to 24 h, amber after, grey without a snapshot."""
    if age_hours is None:
        return "Estadísticas: sin dato", "amber"
    return f"Estadísticas al día · hace {int(age_hours)} h", ("dot" if age_hours <= 24 else "dot amber")


def slot_states(now: datetime, slots_today: List[datetime], ledger: List[Dict], videos: List[Dict],
                fill: Dict[datetime, str]) -> List[Dict]:
    """One dict per slot of today: state published | scheduled | free, with what the card says. `ledger` is the
    publication log; a YouTube row whose scheduled_for (else published_at) lies within 70 min of the slot owns it."""
    by_id = {v.get("id"): v for v in videos}
    out = []
    for at in slots_today:
        mine = None
        for r in ledger:
            if r.get("platform") != "youtube":
                continue
            raw = (r.get("extra") or {}).get("scheduled_for") or r.get("published_at")
            try:
                t = datetime.fromisoformat(raw)
            except (TypeError, ValueError):
                continue
            t = t if t.tzinfo else t.replace(tzinfo=TZ)
            if abs((t - at).total_seconds()) <= 70 * 60:
                mine = r
                break
        if mine is None:
            out.append({"at": at, "state": "free", "title": "", "fills": fill.get(at) or "", "past": at <= now})
            continue
        also = [p for p in ("youtube", "facebook") if any(r.get("artifact") == mine.get("artifact") and r.get("platform") == p for r in ledger)]
        v = by_id.get(mine.get("upload_id"))
        live = at <= now
        out.append({"at": at, "state": "published" if live else "scheduled", "title": mine.get("published_title") or "",
                    "views": int(v["views"]) if v and live else None, "platforms": also})
    return out


def flow_cells(free_today: int, next_free: Optional[datetime], pending: int, approved: int, queued: int) -> List[Dict]:
    return [
        {"page": "Generate", "label": "Producir", "n": free_today, "hot": free_today > 0,
         "line": f"Siguiente hueco {next_free:%H:%M}" if next_free else "Todo el día cubierto"},
        {"page": "Review", "label": "Por revisar", "n": pending, "hot": False, "line": "vídeos esperando tu visto bueno"},
        {"page": "Upload", "label": "Por subir", "n": approved, "hot": False, "line": "aprobados, sin programar"},
        {"page": "Queue", "label": "Guiones en cola", "n": queued, "hot": False,
         "line": f"para {days_of_queue(queued)} días" if queued else "cola vacía"},
    ]


def slots_sentence(states: List[Dict], now: Optional[datetime] = None) -> str:
    """Only slots still ahead count as missing: a past slot with no video is gone, not something to fill."""
    free = [s for s in states if s["state"] == "free" and (now is None or s["at"] > now)]
    if not free:
        return "Hoy está todo listo."
    done = len(states) - len(free)
    return f"Hoy salen {len(states)} vídeos y ya hay {done} en su sitio. Falta{'n' if len(free) > 1 else ''} {len(free)} " \
           f"para {', '.join(f'{s['at']:%H:%M}' for s in free)}."


def frame0_png(script_id: str, script: Dict, mtime: float, root: Path = None) -> Optional[Path]:
    """Frame 0 of a how_do_you_say script, drawn by the Tablero kit with no audio, cached at 270×480 in
    output/thumbs/scripts/<id>.png and re-drawn only when the script changes. None for other types."""
    if script.get("type") != "how_do_you_say" or not script.get("items"):
        return None
    root = root or THUMBS
    path = root / f"{script_id}.png"
    if path.exists() and path.stat().st_mtime >= mtime:
        return path
    from video.tablero import frame as F, kit
    fam = kit.family_for(F.topic(script))
    img = kit.background(fam, 0.0)
    img.alpha_composite(kit.header(F.title_emoji(script), F.topic(script)), (0, 0))
    for i, it in enumerate(script["items"][:10]):
        kit.place_tile(img, kit.tile(i, it["emoji"], it["spanish"], it["english"], kit.pron_for(it), "blank"), i)
    kit.draw_footer(img)
    kit.place_bubi(img, "simbolo", 0.0)
    root.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").resize((270, 480)).save(path)
    return path


def fallback_card_html(script: Dict) -> str:
    """Types without a Tablero frame 0: a card in the topic family's colours with the emoji and the topic."""
    from video.tablero import kit
    top, bottom = kit.families()[kit.family_for(script.get("theme") or script.get("title") or "")]
    emoji = (script.get("items") or [{}])[0].get("emoji", "🎬")
    return (f'<div style="width:270px;height:480px;border-radius:16px;border:2.5px solid var(--ink);display:flex;flex-direction:column;'
            f'align-items:center;justify-content:center;gap:12px;background:linear-gradient({top},{bottom});color:#fff;text-align:center;padding:16px">'
            f'<div style="font-size:64px">{e(emoji)}</div><b style="font-family:Fredoka;font-size:22px">{e(script.get("theme") or script.get("title") or "")}</b></div>')


def agenda_html(states: List[Dict], tomorrow_free: int, tomorrow_ready: int) -> str:
    rows = []
    for s in states:
        t = f"{s['at']:%H:%M}"
        if s["state"] == "published":
            views = SIN if s.get("views") is None else f"{s['views']:,} vistas"
            body = f'<b>{e(s["title"])}</b><div class="muted">{views}</div>'
            dot = '<span class="dot"></span>'
        elif s["state"] == "scheduled":
            body = f'<b>{e(s["title"])}</b><div class="muted">Programado en {" y ".join(p.capitalize() for p in s["platforms"])}</div>'
            dot = '<span class="dot" style="background:transparent;border:2px solid var(--blue)"></span>'
        else:
            if s.get("past"):
                body = '<div style="border:1.5px dashed var(--line);border-radius:12px;padding:8px 10px"><b>Pasó sin vídeo</b><div class="muted">Este hueco ya no se puede llenar</div></div>'
            else:
                who = e(s["fills"]) if s["fills"] else "sin guion en cola"
                body = f'<div style="border:1.5px dashed var(--line);border-radius:12px;padding:8px 10px"><b>Hueco libre</b><div class="muted">Lo llena: {who}</div></div>'
            dot = '<span class="dot amber"></span>'
        rows.append(f'<div style="display:flex;gap:12px;align-items:flex-start;padding:8px 0"><span class="num muted" style="width:44px">{t}</span>{dot}<div>{body}</div></div>')
    return ('<div class="card"><h3>Agenda de hoy</h3>' + "".join(rows) +
            f'<div class="muted" style="margin-top:8px">Mañana: {tomorrow_free} huecos · ya hay guion para {tomorrow_ready}</div></div>')


def recent_html(videos: List[Dict], norm: Dict[str, Optional[float]]) -> str:
    tot = week_totals(videos)
    rows = []
    for v in recent(videos):
        b = bar(v, norm.get(v.get("type")))
        line = "" if b["ratio"] is None else '<div style="position:absolute;left:50%;top:-2px;bottom:-2px;border-left:2px dashed var(--ink)"></div>'
        rows.append(f'<div style="display:grid;grid-template-columns:1fr 220px 150px;gap:12px;align-items:center;padding:6px 0">'
                    f'<span>{e((v.get("title") or "")[:48])}</span>'
                    f'<div class="bar {b["colour"] if b["colour"] != "blue" else ""}" style="position:relative;margin:0"><div style="width:{b["width"]:.0f}%"></div>{line}</div>'
                    f'<span class="num"><b>{int(v.get("views", 0)):,}</b> <span class="muted">· {e(b["label"])}</span></span></div>')
    mean = SIN if tot["mean"] is None else f'{tot["mean"]:,}'
    body = "".join(rows) or f'<div class="muted">Sin vídeos en los últimos 7 días.</div>'
    return (f'<div class="card"><h3>Cómo van tus últimos vídeos</h3><div class="muted">Últimos 7 días · {tot["views"]:,} vistas · '
            f'{tot["videos"]} vídeos · media {mean}</div>{body}'
            '<div class="muted" style="margin-top:8px">La línea discontinua es lo normal de su formato · verde ≥ 1,2× · rojo &lt; 0,5×</div></div>')


def render_seconds(history: List[Dict], vtype: str) -> Optional[float]:
    """Median render time of the last 10 completed jobs of this type; None with fewer than 3 («sin dato»)."""
    secs = []
    for j in history:
        if j.get("status") != "completed" or j.get("video_type") != vtype:
            continue
        try:
            secs.append((datetime.fromisoformat(j["completed_at"]) - datetime.fromisoformat(j["created_at"])).total_seconds())
        except (KeyError, TypeError, ValueError):
            continue
        if len(secs) == 10:
            break
    return statistics.median(secs) if len(secs) >= 3 else None


def facts_html(vtype: str, duration_s: Optional[float], cost: Optional[float], render_s: Optional[float], repeated: int) -> str:
    def cell(label, value):
        return f'<div><div class="eyebrow">{label}</div><div class="num"><b>{value}</b></div></div>'
    return ('<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:12px 0">'
            + cell("Duración estimada", SIN if duration_s is None else f"~{duration_s:.0f} s")
            + cell("Coste estimado", SIN if cost is None else f"&#36;{cost:.2f}")
            + cell("Tiempo de render", SIN if render_s is None else f"~{render_s / 60:.0f} min")
            + cell("Palabras repetidas", str(repeated)) + "</div>")


def highlight_topic(title: str) -> str:
    """The title, escaped, with its first run of 3+ capital letters (the topic) highlighted."""
    import re
    safe = e(title)
    return re.sub(r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]{3,}[A-ZÁÉÍÓÚÑ])", r"<mark>\1</mark>", safe, count=1)
