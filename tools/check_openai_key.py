"""Verifica la clave de OpenAI sin gastar tokens y sin imprimirla.

    python3 tools/check_openai_key.py

Prueba las DOS claves que puede ver el proyecto, porque no tienen por qué ser
la misma:

  .env           lo que lee src/tts_elevenlabs.py con load_dotenv(override=True)
  entorno shell  lo que lee cualquier módulo que use load_dotenv() sin override
                 o que mire os.environ directamente

Si ~/.bash_profile exporta la clave con un $(security find-generic-password …)
que no se evalúa, el entorno del shell lleva el TEXTO del comando en vez de la
clave, y todo lo que no use override falla con 401 aunque .env esté bien.

Usa GET /v1/models: no consume tokens, no cuesta nada.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def mask(v):
    return f"{v[:8]}…{v[-4:]} (len {len(v)})" if v else "(vacía)"


def from_dotenv():
    p = ROOT / ".env"
    if not p.exists():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(?:export\s+)?OPENAI_API_KEY\s*=\s*(.*)\s*$", line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return None


def probe(key):
    req = urllib.request.Request("https://api.openai.com/v1/models",
                                 headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            n = len(json.load(r).get("data", []))
            return f"OK  HTTP {r.status} — la clave funciona ({n} modelos visibles)"
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode(errors="replace")).get("error", {})
        except Exception:                                   # noqa: BLE001
            err = {}
        msg = re.sub(r"sk-[A-Za-z0-9_\-]{6,}", "sk-***", err.get("message", ""))
        why = {401: "clave inválida o revocada",
               429: "clave válida pero sin saldo o con límite",
               403: "clave válida sin permiso para este recurso"}.get(e.code, "")
        return f"FALLA HTTP {e.code} {('— ' + why) if why else ''}\n      {msg[:160]}"
    except Exception as e:                                  # noqa: BLE001
        return f"NO LLEGA A OPENAI — {type(e).__name__}: {str(e)[:120]}"


def main():
    dot, sh = from_dotenv(), os.environ.get("OPENAI_API_KEY")
    print(f".env           {mask(dot)}")
    print(f"entorno shell  {mask(sh)}")
    if sh and sh.lower().startswith("securi"):
        print("  !! el shell lleva el TEXTO de un comando 'security …', no una clave:"
              " ~/.bash_profile no está evaluando la sustitución")
    print()
    seen = {}
    for label, key in ((".env", dot), ("shell", sh)):
        if not key:
            continue
        if key in seen:
            print(f"{label:6} misma clave que {seen[key]}, no la pruebo dos veces")
            continue
        seen[key] = label
        print(f"{label:6} {probe(key)}")
    if not dot and not sh:
        print("No hay OPENAI_API_KEY ni en .env ni en el shell.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
