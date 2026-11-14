"""What each platform does with what we send — the limits it enforces silently or with a 400 —
checked and fixed in one place before every upload, and used by tools/upload_audit.py.

Every limit carries its official source (read 27 Oct 2026). A limit that is only folklore
(«more than 15 hashtags and YouTube ignores them all» — the official figure is 60) is not here.

    YouTube   title ≤ 100 chars, no < or >          developers.google.com/youtube/v3/docs/videos
              description ≤ 5000 BYTES, no < or >    (same page; «á», «ñ», «¿» are 2 bytes, emoji 4)
              snippet.tags ≤ 500 chars, commas count, a tag with a space counts its quotes
              > 60 hashtags → every hashtag ignored  support.google.com/youtube/answer/6390658
              Shorts ≤ 3 min, vertical or square     support.google.com/youtube/answer/15424877
              links in a Short's description are not clickable   support.google.com/youtube/answer/13748639
    Facebook  Reels 3–90 s, 9:16                     developers.facebook.com/docs/video-api/guides/reels-publishing
    Instagram caption ≤ 2200 chars, ≤ 30 hashtags, ≤ 20 @ tags
              developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media

House rules on top (not platform limits): no hashtag in a YouTube title (the title is a search
surface, and «#Shorts» is not needed for a vertical video under 3 min), and one spelling per
hashtag (#aprenderingles vs #aprenderinglés: no official page says whether they are one hashtag,
so we pick one and stop splitting the bet). Case never splits a hashtag.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Tuple

YT_TITLE_CHARS = 100
YT_DESCRIPTION_BYTES = 5000
YT_TAGS_CHARS = 500
YT_HASHTAGS_MAX = 60
YT_SHORT_MAX_S = 180.0
FB_REEL_S = (3.0, 90.0)
IG_CAPTION_CHARS = 2200
IG_HASHTAGS_MAX = 30
IG_MENTIONS_MAX = 20

HASHTAG = re.compile(r"(?<![\w#])#[^\s#.,;:!?¡¿()\[\]{}\"'«»<>]+")
URL = re.compile(r"https?://\S+|www\.\S+|\b[a-z0-9-]+\.(?:com|org|net|io|es)\b", re.I)


def fold(tag: str) -> str:
    """#AprenderInglés → aprenderingles: what makes two spellings the same hashtag to a person."""
    text = unicodedata.normalize("NFD", tag.lstrip("#").casefold())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def hashtags_in(text: str) -> List[str]:
    return HASHTAG.findall(text or "")


def tags_length(tags: Iterable[str]) -> int:
    """snippet.tags as YouTube counts it: commas between items count, a tag with a space counts
    as if quoted («Foo Baz» = 9)."""
    tags = [t for t in tags if t]
    return sum(len(t) + (2 if " " in t else 0) for t in tags) + max(0, len(tags) - 1)


def _cut_words(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    window = text[:limit + 1]
    cut = window.rsplit(" ", 1)[0].rstrip(" ,;:-·") if " " in window else ""
    return cut if cut else text[:limit]


def _cut_bytes(text: str, limit: int) -> str:
    if len(text.encode("utf-8")) <= limit:
        return text
    out = text.encode("utf-8")[:limit].decode("utf-8", "ignore")
    keep = out.rsplit("\n", 1)[0] if "\n" in out else out.rsplit(" ", 1)[0]
    return keep.rstrip()


def _one_spelling(text: str) -> Tuple[str, List[str]]:
    """Each hashtag once, in the spelling it first appears with; later repeats and other
    spellings of it are dropped."""
    seen, dropped = {}, []

    def keep(m):
        key = fold(m.group(0))
        if key in seen:
            dropped.append(m.group(0))
            return ""
        seen[key] = m.group(0)
        return m.group(0)
    out = HASHTAG.sub(keep, text)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r" +\n", "\n", out).strip()
    return out, dropped


def youtube(title: str, description: str, tags: Iterable[str] = ()) -> Dict:
    """{title, description, tags, changes}: what YouTube will accept and show as meant."""
    changes = []
    t = title or ""
    in_title = hashtags_in(t)
    if in_title:
        t = HASHTAG.sub("", t)
        changes.append(f"quitados del título: {' '.join(in_title)}")
    if "<" in t or ">" in t:
        changes.append("quitados «<» «>» del título")
    t = re.sub(r"\s{2,}", " ", t.replace("<", "").replace(">", "")).strip()
    if len(t) > YT_TITLE_CHARS:
        t = _cut_words(t, YT_TITLE_CHARS)
        changes.append(f"título recortado a {len(t)} caracteres, en una palabra")

    d = description or ""
    if "<" in d or ">" in d:
        d = d.replace("<", "").replace(">", "")
        changes.append("quitados «<» «>» de la descripción")
    d, dropped = _one_spelling(d)
    if dropped:
        changes.append(f"hashtags repetidos o con otra grafía: {' '.join(dropped)}")
    tags_in_text = hashtags_in(d)
    if len(tags_in_text) > YT_HASHTAGS_MAX:
        for extra in tags_in_text[YT_HASHTAGS_MAX:]:
            d = d.replace(extra, "", 1)
        d = re.sub(r"[ \t]{2,}", " ", d).strip()
        changes.append(f"más de {YT_HASHTAGS_MAX} hashtags: quitados los últimos")
    if len(d.encode("utf-8")) > YT_DESCRIPTION_BYTES:
        d = _cut_bytes(d, YT_DESCRIPTION_BYTES)
        changes.append(f"descripción recortada a {len(d.encode('utf-8'))} bytes")

    out_tags, seen = [], set()
    for tag in (x.lstrip("#").replace("<", "").replace(">", "").strip() for x in tags):
        if tag and fold(tag) not in seen and tags_length(out_tags + [tag]) <= YT_TAGS_CHARS:
            seen.add(fold(tag))
            out_tags.append(tag)
    if len(out_tags) < len([x for x in tags if x]):
        changes.append(f"etiquetas: {len(out_tags)} de {len([x for x in tags if x])} (repetidas o más de {YT_TAGS_CHARS} caracteres)")
    return {"title": t, "description": d, "tags": out_tags, "changes": changes}


def instagram(caption: str) -> Dict:
    """{caption, changes}: ≤ 30 hashtags (the last ones go), one spelling each, ≤ 2200 chars."""
    changes = []
    c, dropped = _one_spelling(caption or "")
    if dropped:
        changes.append(f"hashtags repetidos o con otra grafía: {' '.join(dropped)}")
    tags = hashtags_in(c)
    if len(tags) > IG_HASHTAGS_MAX:
        for extra in tags[IG_HASHTAGS_MAX:]:
            c = c.replace(extra, "", 1)
        c = re.sub(r"[ \t]{2,}", " ", c).strip()
        changes.append(f"más de {IG_HASHTAGS_MAX} hashtags: quitados los últimos")
    if len(c) > IG_CAPTION_CHARS:
        c = _cut_words(c, IG_CAPTION_CHARS)
        changes.append(f"texto recortado a {len(c)} caracteres")
    return {"caption": c, "changes": changes}


def problems(platform: str, title: str = "", description: str = "", tags: Iterable[str] = (),
             duration: Optional[float] = None, short: bool = True) -> List[Dict]:
    """[{code, severity, message}] for one upload as sent. severity: «bloquea» (the platform
    refuses or ignores it), «aviso» (it goes out, but not as meant)."""
    out = []

    def add(code, severity, message):
        out.append({"code": code, "severity": severity, "message": message})
    text = f"{title or ''}\n{description or ''}"
    folded = {}
    for h in hashtags_in(text):                         # case does not split a hashtag; accents may
        folded.setdefault(fold(h), set()).add(h.casefold())
    split = sorted(" / ".join(sorted(v)) for v in folded.values() if len(v) > 1)
    if platform == "youtube":
        if len(title or "") > YT_TITLE_CHARS:
            add("yt_title_len", "bloquea", f"título de {len(title)} caracteres (máximo {YT_TITLE_CHARS})")
        if len((description or "").encode("utf-8")) > YT_DESCRIPTION_BYTES:
            add("yt_description_bytes", "bloquea", f"descripción de {len(description.encode('utf-8'))} bytes (máximo {YT_DESCRIPTION_BYTES})")
        if "<" in text or ">" in text:
            add("yt_angle_brackets", "bloquea", "«<» o «>» en el título o la descripción")
        n = len(hashtags_in(text))
        if n > YT_HASHTAGS_MAX:
            add("yt_hashtags_60", "bloquea", f"{n} hashtags: con más de {YT_HASHTAGS_MAX} YouTube los ignora todos")
        if tags_length(t.lstrip("#") for t in tags) > YT_TAGS_CHARS:
            add("yt_tags_len", "bloquea", f"etiquetas de {tags_length(t.lstrip('#') for t in tags)} caracteres (máximo {YT_TAGS_CHARS})")
        if hashtags_in(title or ""):
            add("yt_hashtag_in_title", "aviso", f"hashtag en el título: {' '.join(hashtags_in(title))}")
        if short and URL.search(description or ""):
            add("yt_short_link", "aviso", "enlace en la descripción de un Short: no se puede pulsar")
        if short and duration and duration > YT_SHORT_MAX_S:
            add("yt_short_len", "bloquea", f"{duration:.0f} s: un Short dura como mucho 3 min")
    if platform == "facebook" and duration is not None and not FB_REEL_S[0] <= duration <= FB_REEL_S[1]:
        add("fb_reel_len", "bloquea", f"{duration:.1f} s: un Reel por API dura de 3 a 90 s")
    if platform == "instagram":
        if len(description or "") > IG_CAPTION_CHARS:
            add("ig_caption_len", "bloquea", f"texto de {len(description)} caracteres (máximo {IG_CAPTION_CHARS})")
        if len(hashtags_in(description)) > IG_HASHTAGS_MAX:
            add("ig_hashtags_30", "bloquea", f"{len(hashtags_in(description))} hashtags (máximo {IG_HASHTAGS_MAX})")
        if len(re.findall(r"(?<!\w)@\w", description or "")) > IG_MENTIONS_MAX:
            add("ig_mentions_20", "bloquea", f"más de {IG_MENTIONS_MAX} menciones")
    if split:
        add("hashtag_spellings", "aviso", "el mismo hashtag con y sin tilde (puede que el alcance se reparta; "
            "YouTube no documenta si son el mismo): " + "; ".join(split))
    return out
