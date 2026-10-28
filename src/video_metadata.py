"""STEP 80 §1b: title, description and hashtags generated again, at render time, into the sidecar.

`build(script, video_type)` returns

    {"title", "alternatives": [2 titles], "description", "hashtags": {platform: [...]},
     "source": "llm" | "template", "checks": {...}}

**The title, the data decides.** `how_do_you_say` keeps `how_do_you_say_title()` exactly («¿Cómo se
dice(n) [CATEGORÍA] en inglés? + emoji», the winning formula; the LLM never touches it).
`phrases_level` and the series use the script's own title. Other types: the LLM proposes 3 and the
code picks by rules (≤ 70 characters, one emoji at the end, a Spanish search phrase, no clickbait,
no empty quotes); the other two are kept as alternatives.

**The description**: a first line of ≤ 120 characters that promises the payoff; the content as a
searchable list («Manzana = apple · Pera = pear», the phrases, or «Se dice: … / No: …»); one
question that invites a comment; the site line. Every word the list names must be in the script,
else the list is built from the script.

**Hashtags**: YouTube gets 3–5 plus #Shorts, ordered topic → broad → audience → #englishunlimited;
the other platforms take theirs through the existing adapt_for_platform.

**One LLM call per video** (through OpenRouter, src/llm.py, logged by the cost tracker), and only inside a render
Garcia launched from the panel (the STEP 79 §00 grant). Any failure, or no grant, falls back to the
deterministic template: it never blocks a video.

**Guards**, before anything is written: no empty quotes, no leftover {} or [[ ]], platform lengths,
not an English-only title, not a title already published.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Callable, Dict, List, Optional

import metadata_generator as M

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "output" / "published" / "ledger.jsonl"

TITLE_MAX = 70
FIRST_LINE_MAX = 120
SEARCH_PHRASES = ("en inglés", "en ingles", "cómo se dice", "como se dice", "cómo decir", "como decir",
                  "se dice", "inglés", "ingles")
CLICKBAIT = re.compile(r"solo el \d+\s*%|nadie sabe|99\s*%|te va a volar|no vas a creer|increíble pero", re.I)
#: Words that only Spanish has (a title must read as Spanish for this audience).
SPANISH_HINT = re.compile(r"[ñáéíóú¿¡]|\b(?:el|la|los|las|que|cómo|como|se|en|de|dice|inglés|tu|no|es|para|por)\b", re.I)
OWN_TITLE_TYPES = ("phrases_level", "hecho_con_claude")
COMMENT_QUESTION = {"how_do_you_say": "¿Cuántas sabías? Dímelo en comentarios 👇",
                    "phrases_level": "¿Cuál usarías hoy? Cuéntamelo en comentarios 👇",
                    "hecho_con_claude": "¿Tú también lo decías así? Dímelo en comentarios 👇"}
DEFAULT_QUESTION = "¿Lo sabías? Dímelo en comentarios 👇"
BROAD = ["#aprenderingles", "#inglesfacil"]
AUDIENCE = "#inglesparahispanohablantes"
BRAND = "#englishunlimited"


# ── the script's own content ─────────────────────────────────────────

def _fold(text: str) -> str:
    text = unicodedata.normalize("NFD", str(text).casefold())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def script_pairs(script: Dict, video_type: str) -> List[tuple]:
    """(spanish, english) pairs the video teaches, from the script itself."""
    if video_type == "hecho_con_claude":
        c = script.get("correction") or {}
        return [(c.get("right", ""), c.get("wrong", ""))] if c.get("right") else []
    return [(i.get("spanish", ""), i.get("english", "")) for i in script.get("items") or []
            if i.get("spanish") and i.get("english")]


def content_list(script: Dict, video_type: str) -> str:
    """The deterministic searchable list (STEP 80 §1b, item 2)."""
    if video_type == "hecho_con_claude":
        c = script.get("correction") or {}
        return f"Se dice: {c.get('right', '')} · No: {c.get('wrong', '')}" if c.get("right") else ""
    pairs = script_pairs(script, video_type)
    if video_type == "phrases_level":
        return "\n".join(f"• {es} → {en}" for es, en in pairs)
    return " · ".join(f"{es} = {en}" for es, en in pairs)


def list_matches_script(listed: str, script: Dict, video_type: str) -> bool:
    """Every English word or phrase the list names is one the script teaches."""
    if video_type == "hecho_con_claude":                    # the right and the wrong form, as written
        c = script.get("correction") or {}
        return bool(c.get("right")) and _fold(c["right"]) in _fold(listed) and _fold(c.get("wrong", "")) in _fold(listed)
    known = {_fold(en).strip(" .!?¿¡") for _es, en in script_pairs(script, video_type)}
    if not known:
        return False
    named = re.findall(r"(?:=|→|Se dice:|No:)\s*([^·•\n/]+)", listed)
    named = [_fold(n).strip(" .!?¿¡") for n in named if n.strip()]
    return bool(named) and all(n in known for n in named)


def topic_tag(script: Dict, video_type: str) -> str:
    theme = (script.get("theme") or "").strip()
    for article in ("el ", "la ", "los ", "las "):
        if theme.lower().startswith(article):
            theme = theme[len(article):]
    word = re.sub(r"[^a-z0-9]", "", _fold(theme.split(" (")[0]).replace(" ", ""))
    if video_type == "how_do_you_say" and word:
        return f"#{word}eningles"
    return "#vocabularioeningles"


# ── rules and guards ─────────────────────────────────────────────────

def _ends_with_one_emoji(title: str) -> bool:
    emojis = [c for c in title if unicodedata.category(c) == "So"]
    return len(emojis) == 1 and unicodedata.category(title.rstrip()[-1]) == "So"


def title_ok(title: str) -> List[str]:
    """Why a proposed title breaks the rules ([] when it does not)."""
    out = M.metadata_problems(title)
    if len(title) > TITLE_MAX:
        out.append(f"over {TITLE_MAX} characters")
    if not _ends_with_one_emoji(title):
        out.append("not one emoji at the end")
    if not any(p in _fold(title) for p in map(_fold, SEARCH_PHRASES)):
        out.append("no Spanish search phrase")
    if CLICKBAIT.search(title):
        out.append("clickbait")
    return out


def published_titles(ledger: Path = LEDGER) -> set:
    titles = set()
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                t = json.loads(line).get("published_title") or ""
            except ValueError:
                continue
            titles.add(_fold(re.sub(r"\s*#\w+", "", t)).strip())
    return titles


def guard(meta: Dict, published: Optional[set] = None) -> List[str]:
    """STEP 80 §1b item 5, on what is about to be written."""
    problems = [f"title: {p}" for p in M.metadata_problems(meta["title"])]
    problems += [f"description: {p}" for p in M.metadata_problems(meta["description"])]
    if len(meta["title"]) > M.PLATFORM_LIMITS["youtube"]["title"]:
        problems.append("title: over YouTube's 100")
    if len(meta["description"]) > M.PLATFORM_LIMITS["tiktok"]["description"]:
        problems.append("description: over 2200")
    if not SPANISH_HINT.search(meta["title"]):
        problems.append("title: English only")
    if published is not None and _fold(meta["title"]).strip() in published:
        problems.append("title: already published")
    return problems


# ── the LLM ──────────────────────────────────────────────────────────

PROMPT = """Eres el editor de un canal de Shorts que enseña inglés a hispanohablantes.
Tipo de vídeo: {video_type}. Contenido (lo que enseña el vídeo):
{content}
Devuelve SOLO un JSON con:
- "titles": 3 títulos en español, ≤ 70 caracteres, que contengan «en inglés» o «cómo se dice» o «cómo decir», con UN emoji al final, sin clickbait tipo «Solo el 10 %».
- "first_line": una frase de ≤ 120 caracteres que prometa lo que el espectador aprende.
- "list": el contenido como lista buscable, una línea, «español = english · español = english», solo con lo que está arriba.
- "question": una pregunta corta que invite a comentar.
"""


def ask_llm(script: Dict, video_type: str, client=None) -> Optional[Dict]:
    """One LLM call through OpenRouter (logged), only inside a render Garcia launched. None otherwise."""
    import voice_lock
    if voice_lock.locked():
        return None                                         # not from the panel's click: template
    try:
        import llm
        content = content_list(script, video_type) or (script.get("title") or "")
        resp = llm.chat("metadata", [{"role": "user", "content": PROMPT.format(video_type=video_type, content=content)}],
                        label="video_metadata", client_=client, temperature=0.7,
                        response_format={"type": "json_object"})
        return llm.json_content(resp)
    except Exception as error:                              # noqa: BLE001 — never blocks a video
        logger.warning("metadata LLM failed (%s): the template is used", error)
        return None


# ── build ────────────────────────────────────────────────────────────

def _hashtags(script: Dict, video_type: str, pool: List[str]) -> Dict[str, List[str]]:
    youtube = [topic_tag(script, video_type), *BROAD, AUDIENCE, BRAND][:5]
    out = {"youtube": youtube + ["#Shorts"]}
    base = {"title": "", "description": "", "hashtags": pool}
    for platform in ("tiktok", "instagram", "facebook"):
        out[platform] = [f"#{h.lstrip('#')}" for h in M.adapt_for_platform(base, platform)["hashtags"]][:5]
    return out


def build(script: Dict, video_type: str, category: str = "", llm: Optional[Callable] = None,
          published: Optional[set] = None) -> Dict:
    """The metadata a render writes into its sidecar (see the module docstring)."""
    base = M.generate_metadata(script, video_type, category)          # the deterministic template
    proposal = (llm or ask_llm)(script, video_type)
    published = published_titles() if published is None else published
    checks = {}

    # the title
    if video_type == "how_do_you_say":
        title, alternatives = M.how_do_you_say_title(script), []
    elif video_type in OWN_TITLE_TYPES and (script.get("video_title") or script.get("title")):
        title, alternatives = script.get("video_title") or script.get("title"), []
    else:
        proposed = [t.strip() for t in (proposal or {}).get("titles", []) if isinstance(t, str)]
        good = [t for t in proposed if not title_ok(t) and _fold(t).strip() not in published]
        checks["titles_refused"] = {t: title_ok(t) for t in proposed if title_ok(t)}
        title = good[0] if good else base["title"]
        alternatives = (good[1:] + [t for t in proposed if t not in good])[:2]

    # the description
    first = ((proposal or {}).get("first_line") or "").strip()
    if not first or len(first) > FIRST_LINE_MAX or M.metadata_problems(first):
        first = (script.get("video_description") or script.get("caption") or base["description"]).split("\n")[0]
        first = first[:FIRST_LINE_MAX].rstrip()
    listed = ((proposal or {}).get("list") or "").strip()
    if not list_matches_script(listed, script, video_type):
        checks["list_from_script"] = True
        listed = content_list(script, video_type)
    question = ((proposal or {}).get("question") or "").strip()
    if not question or M.metadata_problems(question) or "?" not in question:
        question = COMMENT_QUESTION.get(video_type, DEFAULT_QUESTION)
    description = M.with_site_line("\n\n".join(p for p in (first, listed, question) if p))

    meta = {"title": title, "alternatives": alternatives, "description": description,
            "hashtags": _hashtags(script, video_type, base["hashtags"]),
            "source": "llm" if proposal else "template"}
    problems = guard(meta, published)
    if problems:
        logger.warning("metadata refused (%s): the template is used", problems)
        checks["refused"] = problems
        meta.update(title=base["title"], description=base["description"], alternatives=[], source="template")
        if guard(meta, None):                                # last resort, always clean
            meta.update(title=M.TITLE_TEMPLATES.get(video_type, ["Aprende inglés hoy 🦊"])[0],
                        description=M.with_site_line(DEFAULT_QUESTION))
    meta["checks"] = checks
    return meta
