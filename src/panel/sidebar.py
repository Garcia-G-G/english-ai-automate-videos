"""STEP 83 §1: the sidebar's pieces, as pure functions the tests can call: groups, badges, meter, brand."""
from __future__ import annotations

import base64
import io
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
BUBI = ROOT / "assets" / "branding" / "english-unlimited" / "simbolo_512.png"

#: The three groups, in the mock's order; every page the panel has is in exactly one.
GROUPS: List[Tuple[str, List[str]]] = [
    ("Producir", ["Dashboard", "Generate", "Queue", "Review", "Upload", "Manim"]),
    ("Canal", ["Performance", "Comments", "Library"]),
    ("Ajustes", ["Topics", "Scheduler", "Settings", "Logs"]),
]
#: page -> badge kind: "soft" for a plain count, "alert" for work that waits on Garcia
BADGE_KIND = {"Queue": "soft", "Review": "alert", "Comments": "alert"}


@lru_cache(maxsize=1)
def bubi_data_uri(px: int = 88) -> str:
    from PIL import Image
    im = Image.open(BUBI).convert("RGBA")
    im.thumbnail((px, px))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def brand_html(version_line: str) -> str:
    return (f'<div class="brand"><img src="{bubi_data_uri()}" alt="Bubi">'
            '<div><b>English <mark>Unlimited</mark></b><small>Estudio de vídeos</small></div></div>'
            f'<div class="eu-ver">{version_line}</div>')


def badge_css(counts: Dict[str, int]) -> str:
    """One ::after rule per nav button whose count is above 0, so a zero badge is simply not drawn.
    The number is written into the stylesheet (st.button labels cannot hold markup)."""
    rules = []
    for page, kind in BADGE_KIND.items():
        n = int(counts.get(page) or 0)
        if n <= 0:
            continue
        look = ("background: var(--card); color: var(--ink); border: 1px solid var(--line);" if kind == "soft"
                else "background: var(--badge); color: var(--white);")
        rules.append(f'section[data-testid="stSidebar"] .st-key-nav_{page} button::after {{ content: "{min(n, 999)}"; margin-left: auto; '
                     f"{look} font-size: 11px; font-weight: 800; border-radius: 99px; padding: 1px 8px; }}")
    return "\n".join(rules)


def meter_html(spent: Optional[float], cap: float, mean_per_video: Optional[float], per_video_cap: Optional[float]) -> str:
    """«$X de $15» with a bar and «Por vídeo $media · tope $0.25». A missing number reads «sin dato»."""
    if spent is None:
        top, bar = '<span class="sin-dato">sin dato</span>', 0.0
    else:
        top, bar = f"&#36;{spent:.2f} de &#36;{cap:.0f}", max(0.0, min(1.0, spent / cap if cap else 0.0))
    avg = "sin dato" if mean_per_video is None else f"&#36;{mean_per_video:.2f}"
    tope = "" if per_video_cap is None else f" · tope &#36;{per_video_cap:.2f}"
    return (f'<div class="meter"><div>OpenRouter · este mes</div><div class="num">{top}</div>'
            f'<div class="bar"><div style="width:{bar * 100:.0f}%"></div></div>'
            f'<div class="eu-ver">Por vídeo {avg}{tope}</div></div>')
