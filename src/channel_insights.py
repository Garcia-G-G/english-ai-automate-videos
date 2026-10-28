"""What works on this channel, as a short Spanish brief for the script writer's prompt.

Built from the latest YouTube statistics on disk (channel_stats.latest()), so it moves with the
channel instead of freezing a reading: the best and worst mature titles of the type being written,
and the median views of every type. The fixed lessons below come from the 2026-10-27 review of
113 Shorts plus the owner's retention exports (_audit/analytics/README.md, _audit/steps/STEP_80.md).
"""

from __future__ import annotations

import statistics
from typing import Dict, List, Optional

#: Measured on the channel; each line names its evidence so it can be re-checked.
LESSONS = (
    "Las categorías A1 básicas (casa, comida, cuerpo, familia, ropa, animales…) rinden 6-10 veces más "
    "que los temas situacionales (hotel 141, restaurante 100, playa 214 vistas frente a ~1.000).",
    "El título nombra el tema concreto en MAYÚSCULAS («¿Cómo se dice ROPA en inglés? 👕»); sin tema, "
    "las vistas caen a la mitad.",
    "Los ganchos de error típico de hispanohablantes funcionan («No digas 'I go to home'» 994 vistas) "
    "cuando el error se ve grande desde el primer segundo.",
    "La primera frase es una pregunta directa al espectador y el contenido completo se ve desde el "
    "fotograma 1: se decide en ~2 s si seguir mirando.",
    "Los videos de ~60 s se vuelven a ver; los de 75-90 s se ven al 63-76 %. Nada de relleno.",
    "Cada video debe sentirse distinto (palabras, ejemplos, intro): YouTube desmonetiza el contenido "
    "repetitivo hecho con plantilla.",
)


def _mature(stats: Optional[Dict], min_days: int) -> List[Dict]:
    return [v for v in (stats or {}).get("videos", []) if (v.get("days") or 0) >= min_days and v.get("type")]


def brief(video_type: str, stats: Optional[Dict] = None, top: int = 5, theme: str = "") -> str:
    """The Spanish block appended to a script prompt: this channel's numbers, then the most-viewed
    Shorts on the same topic across YouTube (market_research). Lessons only when neither exists."""
    import queue_priority
    if stats is None:
        try:
            import channel_stats
            stats = channel_stats.latest()
        except Exception:                                   # noqa: BLE001 — a missing snapshot is not an error
            stats = None
    videos = _mature(stats, queue_priority.MATURE_DAYS)
    lines = ["LO QUE FUNCIONA EN ESTE CANAL (datos reales; úsalo para decidir palabras, gancho y tono):"]
    lines += [f"- {lesson}" for lesson in LESSONS]
    own = sorted((v for v in videos if v["type"] == video_type), key=lambda v: -int(v.get("views", 0)))
    if own:
        lines.append(f"Mejores títulos de este formato ({video_type}):")
        lines += [f"  · {int(v['views'])} vistas — {v['title']}" for v in own[:top]]
        if len(own) > top + 2:
            lines.append("Peores (evita su enfoque):")
            lines += [f"  · {int(v['views'])} vistas — {v['title']}" for v in own[-3:]]
    by_type: Dict[str, List[int]] = {}
    for v in videos:
        by_type.setdefault(v["type"], []).append(int(v.get("views", 0)))
    ranked = sorted(((statistics.median(n), t) for t, n in by_type.items() if len(n) >= queue_priority.MIN_VIDEOS),
                    reverse=True)
    if ranked:
        lines.append("Vistas medianas por formato: " + ", ".join(f"{t} {m:.0f}" for m, t in ranked) + ".")
    import market_research as M
    outside = M.top_videos(video_type, theme)
    if outside:
        lines.append("LO MÁS VISTO EN TODO YOUTUBE sobre este tema y formato (otros canales; estudia sus "
                     "títulos y ganchos, qué prometen y cuánto duran, y supéralos sin copiarlos):")
        lines += [f"  · {M.views_label(v['views'])} vistas, {v['seconds']} s, {v['channel']} — {v['title']}"
                  for v in outside]
        tags = sorted({t.lower() for v in outside for t in v["tags"]})[:25]
        if tags:
            lines.append("Etiquetas que usan: " + ", ".join(tags) + ".")
    return "\n".join(lines)
