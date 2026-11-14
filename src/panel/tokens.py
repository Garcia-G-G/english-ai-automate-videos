"""STEP 83 §0: «Papel», the panel's palette. ONE source of truth: the CSS, the tests and
.streamlit/config.toml (which a test keeps in step) read these values.

Yellow is a highlighter and a post-it, never a text colour; coral is decorative only (alerts use `badge`).
"""
from __future__ import annotations

from typing import Dict, List, Tuple

PAPEL: Dict[str, str] = {
    "page": "#F5F1EA", "sand2": "#EFE8DC", "side": "#FFFFFF", "card": "#FFFFFF",
    "ink": "#191720", "muted": "#6B6672", "line": "#E3DCCF", "white": "#FFFFFF",
    "blue": "#1F6FD1", "blue_soft": "#E1ECFB", "blue_ink": "#164C93",
    "yellow": "#F6D35B", "yellow_soft": "#FCF0C4", "yellow_ink": "#6E5300",
    "coral": "#FF6F4F", "coral_soft": "#FFE1D8", "coral_ink": "#A0391F", "badge": "#C9401F",
    "green": "#12854F", "green_soft": "#DAF1E4", "green_ink": "#1F6B42",
    "red": "#D2433A", "red_soft": "#FADCD8", "red_ink": "#8E2B22",
}
THEME_TOML = {"primaryColor": "blue", "backgroundColor": "page", "secondaryBackgroundColor": "card", "textColor": "ink"}

#: (text token, background token, minimum contrast): every pair the CSS puts text on.
PAIRS: List[Tuple[str, str, float]] = [
    ("ink", "page", 4.5), ("ink", "card", 4.5), ("muted", "page", 4.5), ("muted", "card", 4.5), ("muted", "sand2", 4.5),
    ("white", "blue", 4.5), ("white", "green", 4.5), ("white", "badge", 4.5), ("white", "red", 4.5), ("white", "ink", 4.5),
    ("blue_ink", "blue_soft", 4.5), ("green_ink", "green_soft", 4.5), ("yellow_ink", "yellow_soft", 4.5),
    ("coral_ink", "coral_soft", 4.5), ("red_ink", "red_soft", 4.5), ("ink", "yellow", 4.5), ("ink", "sand2", 4.5),
    ("blue", "card", 4.5),                                   # blue as a link/text colour on white
]


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def var_block() -> str:
    return ":root { " + " ".join(f"--{k.replace('_', '-')}: {v};" for k, v in PAPEL.items()) + " }"


def theme_toml() -> str:
    lines = ['base = "light"'] + [f'{k} = "{PAPEL[v]}"' for k, v in THEME_TOML.items()]
    return "\n".join(lines)


def css() -> str:
    """The panel's stylesheet: the mock's components (.card .sticker .btn .tag .chip .nav .badge) plus the
    classes admin.py already writes, all on the tokens. Real st.button's are styled through keyed containers
    (.st-key-btn-primary and friends), never faked with HTML."""
    return var_block() + """
@import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap');
html, body, .stApp, [data-testid="stSidebar"], .stMarkdown, button, input, textarea, select {
  font-family: "Manrope", "Noto Color Emoji", system-ui, -apple-system, "Segoe UI", sans-serif; }
h1, h2, h3, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 { font-family: "Fredoka", "Manrope", system-ui, sans-serif !important;
  font-weight: 600 !important; letter-spacing: 0; color: var(--ink); }
h1 mark, .brand b mark { background: linear-gradient(transparent 58%, var(--yellow) 58%, var(--yellow) 90%, transparent 90%); color: inherit; padding: 0 4px; }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.2rem; max-width: 1280px; }
.sub { color: var(--muted); font-size: 15px; margin-top: 6px; }
.eyebrow { font-size: 11px; font-weight: 800; letter-spacing: .13em; color: var(--muted); text-transform: uppercase; }
.muted, .sin-dato { color: var(--muted); }
.num, .metric-value, .queue-count { font-variant-numeric: tabular-nums; }

/* components from the mock */
.card { background: var(--card); border: 1px solid var(--line); border-radius: 20px; padding: 22px; color: var(--ink); }
.sticker { background: var(--card); border: 2.5px solid var(--ink); border-radius: 22px; box-shadow: 7px 7px 0 var(--ink); color: var(--ink); }
.btn { white-space: nowrap; display: inline-flex; align-items: center; gap: 9px; font-weight: 800; font-size: 15px; border-radius: 14px;
  padding: 13px 22px; border: 2.5px solid var(--ink); background: var(--card); color: var(--ink); box-shadow: 4px 4px 0 var(--ink); }
.btn.primary { background: var(--blue); color: var(--white); font-size: 17px; padding: 15px 26px; }
.btn.green { background: var(--green); color: var(--white); }
.btn.ghost { box-shadow: none; border: 1.5px solid var(--line); font-weight: 700; font-size: 14px; padding: 11px 16px; }
.btn.sm { font-size: 13px; padding: 7px 12px; border-radius: 10px; box-shadow: 2px 2px 0 var(--ink); border-width: 2px; }
.tag { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 750; border-radius: 9px; padding: 4px 9px; background: var(--page); color: var(--ink); }
.tag.blue { background: var(--blue-soft); color: var(--blue-ink); } .tag.green { background: var(--green-soft); color: var(--green-ink); }
.tag.yellow { background: var(--yellow-soft); color: var(--yellow-ink); } .tag.coral { background: var(--coral-soft); color: var(--coral-ink); }
.tag.red { background: var(--red-soft); color: var(--red-ink); }
.chip { display: inline-flex; align-items: center; gap: 7px; background: var(--card); border: 1px solid var(--line); border-radius: 99px;
  padding: 6px 12px; font-size: 12.5px; font-weight: 650; color: var(--ink); }
.dot { width: 8px; height: 8px; border-radius: 99px; background: var(--green); display: inline-block; } .dot.amber { background: var(--yellow); }
.bar { height: 8px; background: var(--sand2); border-radius: 99px; margin: 7px 0 10px; overflow: hidden; }
.bar > div { height: 100%; border-radius: 99px; background: var(--blue); }
.bar.green > div { background: var(--green); } .bar.red > div { background: var(--red); }

/* sidebar */
section[data-testid="stSidebar"] { background: var(--side); border-right: 1px solid var(--line); }
section[data-testid="stSidebar"] .stButton button { justify-content: flex-start; border-radius: 11px; font-weight: 650; border: 1px solid transparent;
  box-shadow: none; padding: 0.35rem 0.8rem; min-height: 2.3rem; }
section[data-testid="stSidebar"] .stButton button[kind="secondary"] { background: transparent; color: var(--ink); }
section[data-testid="stSidebar"] .stButton button[kind="secondary"]:hover { background: var(--page); border-color: var(--line); }
section[data-testid="stSidebar"] .stButton button[kind="primary"] { background: var(--ink); color: var(--white); box-shadow: 3px 3px 0 var(--blue); border-color: var(--ink); }
section[data-testid="stSidebar"] .stButton button > div { justify-content: flex-start; width: 100%; }
.nav { display: flex; align-items: center; gap: 11px; padding: 8px 10px; border-radius: 11px; font-weight: 650; font-size: 14px; color: var(--ink); }
.nav.on { background: var(--ink); color: var(--white); box-shadow: 3px 3px 0 var(--blue); }
.badge { margin-left: auto; background: var(--badge); color: var(--white); font-size: 11px; font-weight: 800; border-radius: 99px; padding: 1px 8px; }
.badge.soft { background: var(--card); color: var(--ink); border: 1px solid var(--line); }
.brand { display: flex; align-items: center; gap: 10px; padding: 0 6px 14px; }
.brand img { width: 44px; height: 44px; }
.brand b { display: block; white-space: nowrap; font-size: 1.05rem; }
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.2rem; } .brand small { display: block; color: var(--muted); font-size: 11.5px; }
section[data-testid="stSidebar"] .stButton button [data-testid="stMarkdownContainer"] { flex: 1; text-align: left; }
.eu-brand, .brand b { font-family: "Fredoka", system-ui, sans-serif; font-weight: 700; font-size: 1.15rem; line-height: 1.1; color: var(--ink); }
.eu-brand mark { background: linear-gradient(transparent 58%, var(--yellow) 58%, var(--yellow) 92%, transparent 92%); color: inherit; padding: 0 2px; }
.eu-navlabel { font-size: 10.5px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); padding-top: 0.9rem; }
.eu-ver { font-size: 0.75rem; color: var(--muted); margin-top: 0.3rem; }
.meter { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px; margin-top: 10px; font-size: 12px; font-weight: 700; }

/* the classes admin.py already writes, on the new tokens */
.metric-card, .platform-card, .video-card, .upload-item { background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 20px; color: var(--ink); }
.metric-card { text-align: center; }
.metric-card .metric-value { font-family: "Fredoka", sans-serif; font-size: 2.3rem; font-weight: 600; color: var(--blue); margin: 6px 0; }
.metric-card .metric-label { font-size: 0.78rem; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; }
.platform-card { text-align: center; min-height: 190px; } .platform-card .platform-icon { font-size: 2.2rem; margin-bottom: 10px; }
.platform-card .platform-name { font-family: "Fredoka", sans-serif; font-size: 1.15rem; font-weight: 600; margin-bottom: 6px; color: var(--ink); }
.upload-item { display: flex; align-items: center; gap: 16px; padding: 14px; margin: 8px 0; } .video-card { padding: 14px; margin: 8px 0; }
.status-badge, .gate-badge { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 0.72rem; font-weight: 700; letter-spacing: .04em; }
.status-connected, .gate-pass, .key-ok { background: var(--green-soft); color: var(--green-ink); }
.status-disconnected, .key-missing { background: var(--sand2); color: var(--muted); }
.status-required, .gate-reject, .key-error { background: var(--red-soft); color: var(--red-ink); }
.gate-unknown { background: var(--yellow-soft); color: var(--yellow-ink); border: 1px dashed var(--yellow-ink); }
.key-status { padding: 8px 14px; border-radius: 10px; margin: 4px 0; font-size: 0.85rem; }
.stProgress > div > div > div > div { background: var(--blue); border-radius: 10px; }
.section-header { font-family: "Fredoka", sans-serif; font-size: 1.15rem; font-weight: 600; color: var(--ink); padding: 10px 0 8px; border-bottom: 2px solid var(--line); margin-bottom: 14px; }
.activity-item, .ledger-row { padding: 8px 14px; border-left: 3px solid var(--blue); margin: 6px 0; background: var(--card); border-radius: 0 10px 10px 0; font-size: 0.85rem; color: var(--ink); }
.ledger-row a { color: var(--blue); text-decoration: none; } .ledger-row a:hover { text-decoration: underline; }
.queue-head { display: flex; align-items: baseline; gap: 12px; padding: 14px 0 6px; border-bottom: 2px solid var(--line); margin-bottom: 10px; }
.queue-head .queue-count { font-family: "Fredoka", sans-serif; font-size: 1.6rem; font-weight: 600; color: var(--blue); }
.queue-head .queue-title { font-size: 1.05rem; font-weight: 700; color: var(--ink); } .queue-head .queue-action { margin-left: auto; font-size: 0.78rem; color: var(--muted); }
.artifact-name { font-size: 0.92rem; font-weight: 600; color: var(--ink); word-break: break-word; } .artifact-meta { font-size: 0.78rem; color: var(--muted); }
.census-ok { font-size: 0.75rem; color: var(--muted); } .census-mismatch { font-size: 0.78rem; color: var(--red-ink); font-weight: 700; }
.cost-line { padding: 10px 16px; border-radius: 12px; background: var(--card); border: 1px solid var(--line); font-size: 0.88rem; color: var(--ink); font-variant-numeric: tabular-nums; }
.art-row { display: flex; align-items: center; gap: 14px; padding: 8px 12px; background: var(--card); border: 1px solid var(--line); border-radius: 12px; }
.art-thumb { height: 80px; width: 45px; object-fit: cover; border-radius: 6px; flex: 0 0 auto; background: var(--sand2); }
.art-thumb-empty { height: 80px; width: 45px; flex: 0 0 auto; border-radius: 6px; border: 1px dashed var(--line); display: flex; align-items: center; justify-content: center; text-align: center; font-size: 0.55rem; line-height: 1.1; color: var(--muted); }
.art-body { min-width: 0; } .art-body .artifact-name { margin-bottom: 2px; } .art-note { font-size: 0.75rem; color: var(--yellow-ink); margin-top: 3px; }
.inicio-row div[data-testid="stVerticalBlock"] { gap: 0; }
[data-testid="stMarkdownContainer"] code, .stMarkdown code, [data-testid="stCaptionContainer"] code { background: var(--sand2) !important; color: var(--ink) !important; border-radius: 6px; padding: 1px 6px; font-size: 0.85em; }

/* Streamlit's own buttons, through keyed containers: st.container(key="btn-primary") etc. */
.st-key-btn-primary button { background: var(--blue); color: var(--white); border: 2.5px solid var(--ink); border-radius: 14px; font-weight: 800; box-shadow: 4px 4px 0 var(--ink); }
.st-key-btn-green button { background: var(--green); color: var(--white); border: 2.5px solid var(--ink); border-radius: 14px; font-weight: 800; box-shadow: 4px 4px 0 var(--ink); }
.st-key-btn-ghost button { background: var(--card); color: var(--ink); border: 1.5px solid var(--line); border-radius: 14px; font-weight: 700; box-shadow: none; }
.st-key-btn-primary button:hover, .st-key-btn-green button:hover { filter: brightness(1.06); }
.st-key-btn-primary button:disabled, .st-key-btn-green button:disabled { background: var(--sand2); color: var(--muted); box-shadow: none; border-color: var(--line); }
"""
