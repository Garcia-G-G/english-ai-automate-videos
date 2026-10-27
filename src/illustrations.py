"""STEP 80 §4: one illustration per English word, drawn once, ever, then reused in every video.

    assets/illustrations/<word>.png      e.g. apple.png, ice_cream.png

House style: flat, thick ink outline, the brand palette, a cream ground, no text. Drawn through
OpenRouter's image models — `meta/muse-image` ($0.01 an image, takes a style reference), else
`bytedance-seed/seedream-5-0-flash` (from $0.018) — with one style reference image
(assets/illustrations/style_ref.png once Claude provides it; the Bubi sheet until then).

Only from the panel's own click (the STEP 79 §00 grant), only for missing words, under the
OpenRouter caps ($0.25 per Short, $15 a month); the panel says «N ilustraciones nuevas · $X» first.
"""
from __future__ import annotations

import base64
import json
import re
import unicodedata
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "assets" / "illustrations"
STYLE_REF = LIBRARY / "style_ref.png"
BUBI_SHEET = ROOT / "assets" / "branding" / "english-unlimited" / "guia_de_marca.png"
URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS = (("meta/muse-image", 0.010), ("bytedance-seed/seedream-5-0-flash", 0.018))
PROMPT = ("A single flat illustration of «{word}» for an English vocabulary video. House style: flat colours, "
          "thick dark ink outline, the brand palette of the reference image, a plain cream background, centred, "
          "no text, no letters, no words, no watermark.")


def slug(word: str) -> str:
    """The file name a word is kept under: «Ice cream» → ice_cream."""
    text = unicodedata.normalize("NFD", word.casefold())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def path_for(word: str, library: Optional[Path] = None) -> Path:
    return (library or LIBRARY) / f"{slug(word)}.png"


def words_of(script: Dict) -> List[str]:
    """The English words a list script teaches, in order (how_do_you_say)."""
    return [i["english"] for i in script.get("items") or [] if i.get("english")]


def missing(words: Iterable[str], library: Optional[Path] = None) -> List[str]:
    seen, out = set(), []
    for w in words:
        if slug(w) and slug(w) not in seen and not path_for(w, library).exists():
            seen.add(slug(w))
            out.append(w)
    return out


def estimate_usd(n: int) -> float:
    return round(n * MODELS[0][1], 3)


def style_reference() -> Optional[Path]:
    return STYLE_REF if STYLE_REF.exists() else (BUBI_SHEET if BUBI_SHEET.exists() else None)


def _data_url(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def _request(word: str, model: str, key: str, opener) -> bytes:
    ref = style_reference()
    content = [{"type": "text", "text": PROMPT.format(word=word)}]
    if ref is not None:
        content.append({"type": "image_url", "image_url": {"url": _data_url(ref)}})
    body = json.dumps({"model": model, "modalities": ["image", "text"],
                       "messages": [{"role": "user", "content": content}]}).encode()
    request = urllib.request.Request(URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Title": "English Unlimited"})
    with opener(request, timeout=180) as response:
        answer = json.load(response)
    images = ((answer.get("choices") or [{}])[0].get("message") or {}).get("images") or []
    url = (images[0].get("image_url") or {}).get("url", "") if images else ""
    if not url.startswith("data:image"):
        raise RuntimeError(f"{model} returned no image for «{word}»")
    return base64.b64decode(url.split(",", 1)[1])


def generate(words: Iterable[str], opener=None, library: Optional[Path] = None) -> Dict[str, str]:
    """Draw the missing words; {word: model used or the error}. Every image is checked against
    the caps and the lock before it is asked, and logged once it comes back."""
    import secret_store
    import tts_openrouter
    import voice_lock
    from cost_tracker import get_tracker
    opener = opener or urllib.request.urlopen
    out = {}
    for word in missing(words, library):
        for model, price in MODELS:
            try:
                tts_openrouter.check_caps(price)
                voice_lock.check(f"una ilustración de «{word}» en OpenRouter ({model})")
                key = secret_store.get(tts_openrouter.KEY_NAME)
                if not key:
                    raise tts_openrouter.OpenRouterRefused("No hay clave de OpenRouter. No se pidió nada.")
                png = _request(word, model, key, opener)
            except (tts_openrouter.OpenRouterRefused, voice_lock.VoiceLocked):
                raise
            except Exception as error:                      # noqa: BLE001 — the next model, then a note
                out[word] = f"error: {str(error)[:120]}"
                continue
            target = path_for(word, library)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(png)
            get_tracker()._add_entry("openrouter_image", model, price, "illustration",
                                     {"word": word, "provider": "openrouter"})
            out[word] = model
            break
    return out
