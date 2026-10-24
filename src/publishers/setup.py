"""What the Meta setup is missing, said in Spanish with the fix (STEP 72 §2).

    report = setup_report()        # GETs only; never prints or returns a token
    report["problems"]             # [] means Instagram and Facebook can publish

Used by `tools/meta_publish.py setup-check` (and `make meta-check`) and by the
panel's Meta card.
"""
from __future__ import annotations

import os
from typing import Dict, List

from env_setup import ensure_env_loaded

from .common import GRAPH, MetaError, call, debug_token, expiry_text
from .meta_instagram import NOT_LINKED

NEEDED = ("pages_show_list", "pages_read_engagement", "pages_manage_posts",
          "instagram_basic", "instagram_content_publish")
#: Meta error codes that no retry can fix: the setup has to change first.
SETUP_CODES = {10, 190, 200}
SETUP_WORDS = ("permission", "permiso", "video_url", NOT_LINKED.lower())


def is_setup_error(error: str) -> bool:
    """True for a failure only a setup change fixes: token, permissions, Instagram link."""
    text = (error or "").lower()
    if any(f"code={c} " in text for c in SETUP_CODES):
        return True
    return any(w in text for w in SETUP_WORDS)


def setup_report() -> Dict:
    ensure_env_loaded()
    page_id, token = os.getenv("FB_PAGE_ID", ""), os.getenv("FB_PAGE_TOKEN", "")
    out: Dict = {"page": None, "instagram": None, "token": None,
                 "permissions": {"granted": [], "missing": list(NEEDED)}, "notes": [], "problems": []}
    problems: List[str] = out["problems"]
    if not (page_id and token):
        problems.append("Falta FB_PAGE_ID o FB_PAGE_TOKEN en .env: sigue README → Meta.")
        return out

    try:
        info = debug_token(token)
    except MetaError as exc:
        info = {}
        problems.append(f"No se pudo leer el token ({exc}): genera otro (README → Meta).")
    if info:
        out["token"] = {"type": info.get("type"), "valid": info.get("is_valid"),
                        "expires": expiry_text(info)}
        granted = sorted(info.get("scopes") or [])
        missing = [p for p in NEEDED if p not in granted]
        out["permissions"] = {"granted": granted, "missing": missing}
        if not info.get("is_valid"):
            problems.append("El token no es válido: genera otro (README → Meta).")
        if info.get("type") != "PAGE":
            problems.append(f"El token es de tipo {info.get('type')}, no de Página: copia el token "
                            "de la Página que da /me/accounts.")
        if out["token"]["expires"] != "never":
            problems.append(f"El token caduca ({out['token']['expires']}): saca el de la Página desde "
                            "un token de usuario extendido, que no caduca.")
        if missing:
            problems.append(f"Faltan permisos: {', '.join(missing)}. Genera el token de usuario con "
                            "ellos en Graph API Explorer y vuelve a sacar el de la Página.")

    try:
        page = call("get", f"{GRAPH}/{page_id}", token,
                    params={"fields": "name,instagram_business_account{id,username}", "access_token": token})
    except MetaError as exc:
        problems.append(f"La Página {page_id} no responde ({exc}): revisa FB_PAGE_ID y el token.")
        return out
    out["page"] = {"name": page.get("name"), "id": page_id}
    account = page.get("instagram_business_account") or {}
    if not account.get("id"):
        problems.append(f"{NOT_LINKED}: vincúlala en Meta Business Suite → Configuración → "
                        "Cuentas de Instagram, y vuelve a ejecutar setup-check.")
        return out
    out["instagram"] = {"username": account.get("username"), "id": str(account["id"])}
    env_ig = os.getenv("IG_USER_ID", "")
    if env_ig and env_ig != out["instagram"]["id"]:
        out["notes"].append(f"IG_USER_ID en .env ({env_ig}) no es el de la Página "
                            f"({out['instagram']['id']}); se usa el de la Página. Puedes borrarlo.")
    return out


def report_lines(report: Dict) -> List[str]:
    """The report as the CLI and the panel print it."""
    page, ig, tok, perms = report["page"], report["instagram"], report["token"], report["permissions"]
    lines = [f"Página: {page['name']} ({page['id']})" if page else "Página: —",
             f"Instagram: @{ig['username']} ({ig['id']})" if ig else NOT_LINKED if page else "Instagram: —",
             (f"Token: {tok['type']}, caduca: {'nunca' if tok['expires'] == 'never' else tok['expires']}"
              if tok else "Token: —"),
             (f"Permisos: los {len(NEEDED)} necesarios" if not perms["missing"]
              else f"Permisos: faltan {', '.join(perms['missing'])}")]
    lines += [f"Aviso: {n}" for n in report["notes"]]
    lines += [f"✗ {p}" for p in report["problems"]] or ["✓ Todo listo para publicar."]
    return lines
