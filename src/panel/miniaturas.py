"""STEP 85b §6: the «Miniaturas mejores para lo publicado» block. Nothing is sent until the ticks and «Aplicar»."""
from __future__ import annotations

import base64
from pathlib import Path


def _uri(p: Path) -> str:
    return "data:image/webp;base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def render(st, rows: list, views: dict = None) -> None:
    import requests
    import thumbs
    from thumbs import better, publish
    st.markdown("<b>Miniaturas mejores para lo publicado</b>", unsafe_allow_html=True)
    if not st.checkbox("Buscar publicados con una miniatura mejor", key="mm_open"):
        return
    props = better.proposals(rows, views)
    if not props:
        st.caption("Nada que cambiar: lo publicado ya tiene la miniatura elegida, o YouTube aún no deja ponerlas en este canal.")
        st.caption(publish.capability_line())
        return
    left = better.MAX_PER_DAY - better.used_today()
    st.caption(f"{len(props)} propuestas, las más vistas primero. Hoy quedan {left} de {better.MAX_PER_DAY} cambios. No se envía nada hasta pulsar «Aplicar».")
    ticked = []
    for i, p in enumerate(props[:60]):
        c = st.columns([0.6, 1, 1, 4])
        folder = p["jpg"].parent
        after = folder / "thumb_270.webp"
        if c[0].checkbox("", key=f"mm_{i}_{p['artifact']}_{p['platform']}", label_visibility="collapsed"):
            ticked.append(p)
        if after.exists():
            c[2].markdown(f'<img src="{_uri(after)}" width="45" height="80" alt="">', unsafe_allow_html=True)
        c[1].caption("antes: la que eligió la plataforma")
        c[3].markdown(f"{p['title'][:70]} · {p['platform']} · {p['views']} vistas")
    if st.button(f"Aplicar ({len(ticked)})", disabled=not ticked, key="mm_apply"):
        import channel_stats
        res = better.apply(ticked, channel_stats._youtube_token, lambda: __import__("os").getenv("FB_PAGE_TOKEN", ""), requests.get, requests.post)
        for r in res:
            st.caption(f"{r['artifact']} · {r['platform']}: {r['result']}")
