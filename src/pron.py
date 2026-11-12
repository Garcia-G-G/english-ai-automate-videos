"""Figured pronunciation for Spanish speakers (STEP 82 §3): «house» -> «jáus».

assets/pron/es_figurada.json maps an English word to {"pron": "jáus"} (a bare string works too).
Claude delivers the dictionary; a word missing from it gets a draft from the cheap metadata model
(config.yaml llm.models.metadata, never the script model), only from a panel job (Garcia's click),
cached in the dictionary with "review": true. Without a draft the tile shows the English alone.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from video.tablero import kit

logger = logging.getLogger(__name__)
PRON_PATH = kit.PRON_PATH

PROMPT = ("Escribe la pronunciación figurada en español de estas palabras en inglés, para un hispanohablante. "
          "Reglas: minúsculas, ortografía española, tilde en la vocal tónica, guiones entre sílabas si ayuda, "
          "máximo 14 caracteres, sin símbolos fonéticos (nada de IPA). Ejemplos: house=jáus, kitchen=kíchen, "
          "window=uíndou, bathroom=báz-rum. Responde SOLO un objeto JSON {{\"palabra\": \"pron\"}}.\nPalabras: {words}")


def draft(words: Iterable[str], chat: Optional[Callable] = None) -> Dict[str, str]:
    """One cheap-model call for all the words; only the VALID answers come back."""
    words = sorted({w.lower() for w in words})
    if not words:
        return {}
    import llm
    reply = (chat or llm.chat)("metadata", [{"role": "user", "content": PROMPT.format(words=json.dumps(words))}],
                               label="pron_draft")
    raw = llm.json_content(reply)
    return {w: str(p).strip().lower() for w, p in raw.items()
            if w.lower() in words and kit.valid_pron(str(p).strip().lower())}


def _read(path: Path) -> Dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def fill_missing(items: List[Dict], path: Path = None, chat: Optional[Callable] = None) -> int:
    """Draft and cache the figured pronunciation of every item that has none; sets item["pron"]
    for this render too. Never raises: a missing key or a bad reply leaves the tile English-only."""
    path = path or PRON_PATH
    book = _read(path)
    need = [i["english"] for i in items
            if not (i.get("pron") and kit.valid_pron(i["pron"])) and i["english"].lower() not in book]
    got: Dict[str, str] = {}
    if need:
        try:
            got = draft(need, chat)
        except Exception as exc:                          # noqa: BLE001 — a tile without pron is fine
            logger.warning("pron: no draft (%s); tiles show the English alone", exc)
        if got:
            book.update({w: {"pron": p, "review": True} for w, p in got.items()})
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(book, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, path)
            kit.pron_dictionary.cache_clear()
    for i in items:
        if i.get("pron") and kit.valid_pron(i["pron"]):
            continue
        entry = book.get(i["english"].lower())
        p = entry.get("pron") if isinstance(entry, dict) else entry
        if p and kit.valid_pron(p):
            i["pron"] = p
    return len(got)
