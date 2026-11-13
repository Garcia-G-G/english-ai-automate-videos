#!/usr/bin/env python3
"""STEP 81 §7: neutral Latin-American Spanish. A word map for Spain-only words, applied to SPANISH fields only.

    python3 tools/es_latam_lint.py            # report mode: writes _audit/stills/STEP81/latam.md, changes nothing
    python3 tools/es_latam_lint.py --apply    # rewrites the queued scripts (titles included)

It never touches English fields, translations keys, hashtags, `_meta` or anything inside [[ ]]. «tío» is NOT
mapped: it stays (an uncle is an uncle). Ambiguous words are guarded: «primer piso» stays a floor, «vale la pena»
and «cuánto vale» keep their verb; only the interjection «vale» becomes «está bien».
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "content" / "queue"
REPORT = ROOT / "_audit" / "stills" / "STEP81" / "latam.md"
#: keys whose values are English, data or markup: never rewritten
SKIP_KEYS = {"english", "english_phrases", "translations", "hashtags", "_meta", "_validation_warnings", "type", "emoji",
             "words", "word", "phonetic", "segments", "segment_times", "design_variant", "pron"}
ORDINALS = r"(?:primer|segundo|tercer|cuarto|quinto|último|siguiente|cada|del|qué|cuál|al)"   # a floor, not a flat


def _case(src: str, dst: str) -> str:
    if src.isupper() and len(src) > 1:
        return dst.upper()
    return dst[:1].upper() + dst[1:] if src[:1].isupper() else dst


def _plain(pattern: str, repl: str):
    rx = re.compile(rf"\b{pattern}\b", re.I)
    return lambda text: rx.sub(lambda m: _case(m.group(0), repl), text)


def _gendered(rx: str, table: Dict[str, str]):
    """Article + noun pairs («la tarta» -> «el pastel») where the gender changes, then the bare noun."""
    pat = re.compile(rx, re.I)
    return lambda text: pat.sub(lambda m: _case(m.group(0), table[re.sub(r"\s+", " ", m.group(0).lower())]), text)


def _piso(text: str) -> str:
    def sub(m):
        before = text[:m.start()].rstrip().lower()
        if re.search(rf"{ORDINALS}$", before):
            return m.group(0)
        return _case(m.group(0), "departamentos" if m.group(0).lower().endswith("s") else "departamento")
    return re.sub(r"\bpisos?\b", sub, text, flags=re.I)


def _vale(text: str) -> str:
    def sub(m):
        before = text[:m.start()].rstrip()
        after = text[m.end():].lstrip()
        if (not before or before[-1] in '¡¿,.:;"«(') and (not after or after[0] in '!.,?»")'):
            return _case(m.group(0), "está bien")
        return m.group(0)
    return re.sub(r"\bvale\b", sub, text, flags=re.I)


_VOSOTROS_VERBS = {"sois": "son", "tenéis": "tienen", "queréis": "quieren", "podéis": "pueden", "habéis": "han", "vais": "van",
                   "decís": "dicen", "sabéis": "saben", "estáis": "están", "hacéis": "hacen", "venís": "vienen", "hablás": "hablan"}


def _VERBS(text: str) -> str:
    """The second-person-plural verb that agreed with «vosotros» follows it to «ustedes»."""
    for old, new in _VOSOTROS_VERBS.items():
        text = _plain(old, new)(text)
    return text


RULES: List[Tuple[str, Callable[[str], str]]] = [
    ("coger → tomar", lambda t: _plain("cojo", "tomo")(_plain("coge", "toma")(_plain("cogen", "toman")(_plain("cogemos", "tomamos")(
        _plain("cogió", "tomó")(_plain("cogí", "tomé")(_plain("cogiste", "tomaste")(_plain("cogido", "tomado")(_plain("coger", "tomar")(t)))))))))),
    ("móvil → celular", lambda t: _plain("móviles", "celulares")(_plain("móvil", "celular")(t))),
    ("piso → departamento", _piso),
    ("zumo → jugo", lambda t: _plain("zumos", "jugos")(_plain("zumo", "jugo")(t))),
    ("patata → papa", lambda t: _plain("patatas", "papas")(_plain("patata", "papa")(t))),
    ("vale → está bien", _vale),
    ("camarero → mesero", lambda t: _plain("camareros", "meseros")(_plain("camarera", "mesera")(_plain("camareras", "meseras")(_plain("camarero", "mesero")(t))))),
    ("ordenador → computadora", lambda t: _plain("ordenadores", "computadoras")(_plain("ordenador", "computadora")(t))),
    ("gafas → lentes", _plain("gafas", "lentes")),
    ("grifo → llave del agua", lambda t: _plain("grifo", "llave del agua")(_gendered(
        r"\b(?:el|un|del) grifo\b", {"el grifo": "la llave del agua", "un grifo": "una llave del agua",
                                      "del grifo": "de la llave"})(_plain(r"grifo\s*/\s*llave", "llave")(t)))),
    ("tarta → pastel", lambda t: _plain("tartas", "pasteles")(_plain("tarta", "pastel")(_gendered(
        r"\b(?:las|una|la|unas) tartas?\b", {"la tarta": "el pastel", "una tarta": "un pastel", "las tartas": "los pasteles",
                                              "unas tartas": "unos pasteles"})(t)))),
    ("melocotón → durazno", lambda t: _plain("melocotones", "duraznos")(_plain("melocotón", "durazno")(t))),
    ("aparcar → estacionar", lambda t: _plain("aparcamiento", "estacionamiento")(_plain("aparcar", "estacionar")(t))),
    ("finde → fin de semana", _plain("finde", "fin de semana")),
    ("fregar → lavar los platos", lambda t: _plain("fregar", "lavar los platos")(_plain("fregar los platos", "lavar los platos")(t))),
    ("echar de menos → extrañar", lambda t: _plain("echamos de menos", "extrañamos")(_plain("echan de menos", "extrañan")(_plain(
        "echas de menos", "extrañas")(_plain("echa de menos", "extraña")(_plain("echo de menos", "extraño")(_plain("echar de menos", "extrañar")(t))))))),
    ("sin blanca → sin dinero", _plain("sin blanca", "sin dinero")),
    ("vosotros → ustedes", lambda t: _VERBS(_plain("vosotras", "ustedes")(_plain("vosotros", "ustedes")(t)))),
    ("chaqueta → chamarra", lambda t: _plain("chaquetas", "chamarras")(_plain("chaqueta", "chamarra")(t))),
]
_PROTECT = re.compile(r"(\[\[.*?\]\])", re.S)


_TWIN = re.compile(r"\b(\w+)\s*/\s*\1\b", re.I)         # «jugo / jugo» after a map: say it once


def fix(text: str) -> str:
    """`text` in neutral Spanish. Anything inside [[ ]] is left exactly as written."""
    parts = _PROTECT.split(text)
    for i in range(0, len(parts), 2):
        before = parts[i]
        for _name, rule in RULES:
            parts[i] = rule(parts[i])
        if parts[i] != before:
            parts[i] = _TWIN.sub(lambda m: m.group(1), parts[i])
    return "".join(parts)


def fix_script(data):
    """(new data, [(field path, before, after)]) over every Spanish string of a script."""
    changes: List[Tuple[str, str, str]] = []

    def walk(node, path):
        if isinstance(node, dict):
            return {k: (v if k in SKIP_KEYS else walk(v, f"{path}.{k}" if path else k)) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v, f"{path}[{i}]") for i, v in enumerate(node)]
        if isinstance(node, str):
            new = fix(node)
            if new != node:
                changes.append((path, node, new))
            return new
        return node
    return walk(data, ""), changes


def problems(data) -> List[str]:
    """One line per Spain-only word left in a script, for the queue guard's report."""
    return [f"latam: {path}: «{before[:40]}» → «{after[:40]}»" for path, before, after in fix_script(data)[1]]


def scripts() -> List[Path]:
    return sorted(p for p in QUEUE.rglob("*.json") if "_done" not in p.parts and "_skipped" not in p.parts)


def main(argv: List[str]) -> int:
    apply = "--apply" in argv
    rows, touched = [], 0
    for path in scripts():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        new, changes = fix_script(data)
        if not changes:
            continue
        touched += 1
        rel = path.relative_to(ROOT)
        rows += [f"| `{rel}` | {field} | {before} → {after} |" for field, before, after in changes]
        if apply:
            path.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("# Neutral Latin-American Spanish lint (STEP 81 §7)\n\n"
                      f"{touched} scripts, {len(rows)} changes ({'applied' if apply else 'report only'}).\n\n"
                      "| file | field | before → after |\n|---|---|---|\n" + "\n".join(r.replace("\n", " ") for r in rows) + "\n",
                      encoding="utf-8")
    print(f"{touched} scripts, {len(rows)} changes -> {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
