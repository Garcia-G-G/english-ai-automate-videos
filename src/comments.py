"""STEP 81 §3.2: the «Comentarios» page's engine. Read the channel's comments (free quota), draft a Spanish
reply with the cheap metadata model, and post one ONLY when Garcia clicks «Responder».

Nothing here posts by itself: `post_reply` is called from a button handler and from nowhere else. A draft
is validated before it is shown (length, no links, no personal data) and falls back to a plain thank-you.
Drafts are cached in output/comments/drafts.json so a comment costs at most one model call, ever.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "output" / "comments" / "drafts.json"
THREADS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
COMMENTS_URL = "https://www.googleapis.com/youtube/v3/comments"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
MAX_REPLY = 280
FALLBACK = "¡Gracias por comentar! Sigue practicando, lo estás haciendo muy bien. 🙌"
_URL = re.compile(r"(https?://|www\.|\b[\w-]+\.(com|net|org|io|me|co|es|mx)\b)", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
PROMPT = ("Eres Bubi, la mascota de English Unlimited, un canal de inglés para hispanohablantes. Escribe UNA respuesta "
          "breve (máximo 2 frases, español latinoamericano neutral, cálida) al comentario. No incluyas enlaces, "
          "correos, teléfonos ni datos personales, y no prometas nada. {bonus}\nComentario de {author}: «{text}»\n"
          "Responde solo con el texto de la respuesta.")


def clean_reply(text: str) -> Optional[str]:
    """The reply if it is safe to show: ≤ 280 characters, no link, no e-mail, no phone number; else None."""
    text = re.sub(r"\s+", " ", str(text or "")).strip().strip('"«»')
    if not text or len(text) > MAX_REPLY or _URL.search(text) or _EMAIL.search(text) or _PHONE.search(text):
        return None
    return text


def _headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def fetch_threads(token: str, get=None, max_results: int = 50) -> List[Dict]:
    """The channel's newest comment threads, newest first:
    [{id, video_id, author, text, published, replies}]. 1 quota unit a call."""
    import requests
    get = get or requests.get
    ch = get(CHANNELS_URL, params={"part": "id", "mine": "true"}, headers=_headers(token), timeout=30)
    ch.raise_for_status()
    items = ch.json().get("items") or []
    if not items:
        raise RuntimeError("YouTube no devolvió el canal de este token")
    resp = get(THREADS_URL, params={"part": "snippet", "allThreadsRelatedToChannelId": items[0]["id"], "order": "time",
                                    "maxResults": max_results, "textFormat": "plainText"},
               headers=_headers(token), timeout=30)
    resp.raise_for_status()
    out = []
    for it in resp.json().get("items", []):
        top = (it.get("snippet") or {}).get("topLevelComment", {}).get("snippet", {})
        out.append({"id": it["id"], "video_id": (it.get("snippet") or {}).get("videoId", ""),
                    "author": top.get("authorDisplayName", ""), "text": top.get("textDisplay", ""),
                    "published": top.get("publishedAt", ""), "replies": int((it.get("snippet") or {}).get("totalReplyCount", 0))})
    return out


def _cache(path: Path = None) -> Dict[str, str]:
    try:
        return json.loads((path or CACHE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def draft_reply(comment: Dict, answer: Optional[str] = None, chat: Optional[Callable] = None,
                path: Path = None) -> str:
    """A validated Spanish reply, from the cache when this comment was drafted before. `answer` is the
    bonus question's English answer for the comment's video, so the reply can confirm it."""
    path = path or CACHE
    cache = _cache(path)
    if comment["id"] in cache:
        return cache[comment["id"]]
    reply = FALLBACK
    try:
        import llm
        bonus = f"Si el comentario responde la pregunta bonus, confirma que la respuesta correcta es «{answer}»." if answer else ""
        resp = (chat or llm.chat)("metadata", [{"role": "user", "content": PROMPT.format(
            bonus=bonus, author=comment.get("author", ""), text=str(comment.get("text", ""))[:500])}],
            label="comment_draft", max_tokens=120)
        safe = clean_reply(resp.choices[0].message.content)
        reply = safe or FALLBACK
    except Exception:                                       # noqa: BLE001 — a draft is a convenience, never a failure
        return FALLBACK                                     # not cached: the next try may work
    cache[comment["id"]] = reply
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return reply


def post_reply(token: str, parent_id: str, text: str, post=None) -> str:
    """comments.insert: Garcia's click, the text as he edited it. Raises when the text is unsafe or the API
    refuses. Returns the new comment's id."""
    import requests
    safe = clean_reply(text)
    if safe is None:
        raise ValueError("La respuesta es demasiado larga (más de 280 caracteres) o lleva un enlace, correo o teléfono.")
    resp = (post or requests.post)(COMMENTS_URL, params={"part": "snippet"}, headers=_headers(token), timeout=30,
                                   json={"snippet": {"parentId": parent_id, "textOriginal": safe}})
    resp.raise_for_status()
    return str(resp.json().get("id", ""))


def bonus_answers(videos: List[Dict], roots: List[Path]) -> Dict[str, str]:
    """{video_id: the bonus question's English answer}, from each video's sidecar (`script_data._meta.bonus_used`)."""
    out: Dict[str, str] = {}
    by_artifact = {v.get("artifact"): v.get("id") for v in videos if v.get("artifact") and v.get("id")}
    for root in roots:
        for side in Path(root).rglob("*.json"):
            vid = by_artifact.get(side.stem)
            if not vid:
                continue
            try:
                used = (json.loads(side.read_text(encoding="utf-8")).get("script_data") or {}).get("_meta", {}).get("bonus_used")
            except (OSError, ValueError):
                continue
            if used and used.get("en"):
                out[vid] = used["en"]
    return out


THREADS = ROOT / "output" / "comments" / "threads.json"


def save_threads(threads: List[Dict], path: Path = None) -> None:
    """Keep the last list read, so the sidebar can count unanswered comments without calling the API."""
    path = path or THREADS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(threads, ensure_ascii=False), encoding="utf-8")


def unanswered_count(path: Path = None) -> int:
    """Threads with no reply in the cached list; 0 when nothing was ever loaded."""
    try:
        return sum(1 for t in json.loads((path or THREADS).read_text(encoding="utf-8")) if not t.get("replies"))
    except (OSError, ValueError, AttributeError):
        return 0
