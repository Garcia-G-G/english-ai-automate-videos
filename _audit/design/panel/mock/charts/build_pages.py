"""Cola, Crear, Biblioteca and the component sheet, in the Papel look."""
import re

SIDE = open("side_rend.html").read().replace('<div class="nav on"><i>↗</i>Rendimiento</div>', '<div class="nav"><i>↗</i>Rendimiento</div>')
def side(active):
    return re.sub(r'<div class="nav"><i>([^<]+)</i>' + active, r'<div class="nav on"><i>\1</i>' + active, SIDE, count=1)

FAM = {"casa": ("#FF7A59", "#D43B59"), "comida": ("#3DB36B", "#1F7A4D"), "cuerpo": ("#9B6BE8", "#6A3CB8"), "animales": ("#2BB5A8", "#157A78"),
       "ropa": ("#4C9BF0", "#2459B5"), "ciudad": ("#6C7BE8", "#3B3FA8"), "emociones": ("#F06BB0", "#B8307F"), "clima": ("#4FB6F2", "#1B76B8"),
       "vida": ("#2E4A8A", "#13234F"), "reto": ("#F5B82E", "#D9822B"), "test": ("#FF8A5B", "#E0533A")}

def thumb(fam, emoji, topic, kind="csd", w=None):
    a, b = FAM[fam]
    head = {"csd": "¿CÓMO SE DICE?", "test": "¿QUÉ NIVEL TIENES?", "reto": "RETO", "frase": "¿CÓMO SE DICE?", "dilo": "DILO EN INGLÉS"}[kind]
    tiles = "".join('<i></i>' for _ in range(10 if kind == "csd" else 4))
    cls = "tiles" if kind == "csd" else "tiles one"
    return (f'<div class="th9" style="background:linear-gradient(180deg,{a},{b})"><div class="h"><span>{head}</span></div>'
            f'<div class="c">{emoji} {topic}</div><div class="{cls}">{tiles}</div><img src="img/wow_s.png" class="bb"></div>')

THUMB_CSS = """
.th9 { aspect-ratio: 9/16; border-radius: 12px; border: 2px solid #1C1812; position: relative; overflow: hidden; color: #1C1812; }
.th9::before { content: ""; position: absolute; inset: 0; background-image: radial-gradient(rgba(255,255,255,.14) 1.1px, transparent 1.2px); background-size: 8px 8px; }
.th9 .h { position: relative; text-align: center; margin-top: 9%; }
.th9 .h span { font-family: Fredoka; font-weight: 700; font-size: 9.5px; background: #F2D66B; padding: 1px 4px; display: inline-block; transform: rotate(-1.5deg); }
.th9 .c { position: relative; margin: 5% auto 0; width: max-content; max-width: 88%; background: #fff; border: 1.2px solid #1C1812; box-shadow: 1.5px 1.5px 0 #1C1812; border-radius: 5px; font-family: Fredoka, Emo; font-weight: 700; font-size: 8px; padding: 1px 5px; transform: rotate(2deg); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.th9 .tiles { position: relative; display: grid; grid-template-columns: 1fr 1fr; gap: 4%; padding: 8% 7% 0; }
.th9 .tiles i { display: block; height: 15px; background: #fff; border: 1.2px solid #1C1812; border-radius: 5px; box-shadow: 1.5px 1.5px 0 #1C1812; }
.th9 .tiles.one { grid-template-columns: 1fr; } .th9 .tiles.one i { height: 18px; }
.th9 .bb { position: absolute; right: 5%; bottom: 4%; width: 30%; }
"""

HEAD = """<!doctype html><html lang="es"><head><meta charset="utf-8"><link rel="stylesheet" href="base.css"><link rel="stylesheet" href="theme-papel.css"><style>%s</style></head><body><div class="app">%s<main class="main">"""
FOOT = """</main></div></body></html>"""

# ───────────────────────── COLA ─────────────────────────
cola_css = THUMB_CSS + """
.fuel { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; margin-bottom: 24px; }
.gauge { background: var(--card); border: 1px solid var(--line); border-radius: 18px; padding: 16px; position: relative; }
.gauge.warn { border: 2.5px solid var(--ink); box-shadow: 5px 5px 0 var(--ink); background: #FFF8E6; }
.gauge .t { font-weight: 800; font-size: 13px; display: flex; align-items: center; gap: 7px; }
.gauge .t i { width: 10px; height: 10px; border-radius: 3px; }
.gauge .n { font-family: Fredoka; font-weight: 700; font-size: 38px; line-height: 1; margin: 10px 0 2px; }
.gauge .n small { font-family: Manrope; font-size: 13px; font-weight: 700; color: var(--muted); margin-left: 4px; }
.gauge .d { font-size: 12.5px; font-weight: 700; color: var(--muted); }
.gauge .meter2 { height: 10px; background: #F1ECE3; border-radius: 99px; margin: 12px 0 8px; overflow: hidden; }
.gauge .meter2 div { height: 100%; border-radius: 99px; }
.gauge .tag { margin-top: 2px; }
.qgrid { display: grid; grid-template-columns: 1fr 360px; gap: 24px; align-items: start; }
.qi { display: grid; grid-template-columns: 34px 54px 1fr 180px 110px; gap: 16px; align-items: center; padding: 12px 0; border-top: 1px solid #F1ECE3; }
.qi:first-of-type { border-top: 0; }
.qi .pos { font-family: Fredoka; font-weight: 700; font-size: 22px; color: var(--muted); text-align: center; }
.qi.first .pos { color: var(--ink); }
.qi .ti b { font-size: 15px; display: block; }
.qi .ti small { font-size: 12px; color: var(--muted); font-weight: 650; }
.qi .tags { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 5px; }
.score2 { display: flex; flex-direction: column; gap: 4px; }
.score2 .sb { height: 9px; border-radius: 99px; background: #F1ECE3; overflow: hidden; display: flex; }
.score2 .sb div { height: 100%; }
.score2 small { font-size: 11.5px; font-weight: 700; color: var(--muted); }
.qi .when { font-size: 12.5px; font-weight: 750; text-align: right; }
.qi .when b { display: block; font-family: Fredoka; font-weight: 500; font-size: 16px; }
.qi.first { background: var(--yellow-soft); margin: 0 -22px; padding: 12px 22px; border-radius: 0; border-top: 0; }
.mixcard .mix { display: flex; height: 34px; border-radius: 10px; overflow: hidden; border: 2px solid var(--ink); margin: 12px 0 10px; }
.mixcard .mix div { display: grid; place-items: center; color: #fff; font-weight: 800; font-size: 12px; }
.mixcard .ml { display: flex; flex-direction: column; gap: 7px; font-size: 13px; font-weight: 650; }
.mixcard .ml div { display: flex; align-items: center; gap: 8px; } .mixcard .ml i { width: 11px; height: 11px; border-radius: 3px; } .mixcard .ml b { margin-left: auto; }
.trays { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; }
.tray { border: 1.5px dashed #CFC5B4; border-radius: 14px; padding: 12px; }
.tray b { font-family: Fredoka; font-weight: 700; font-size: 24px; display: block; } .tray span { font-size: 12.5px; font-weight: 700; color: var(--muted); }
"""
gauges = [
    ("Cómo se dice", "#1F6FD1", 32, "3 al día", 11, True),
    ("Frases y vida real", "#12854F", 51, "1 cada 3 días", 150, False),
    ("Series «RETO»", "#E9A100", 98, "1 cada 3 días", 290, False),
    ("Test de nivel", "#FF6F4F", 90, "1 cada 3 días", 270, False),
    ("Gramática y otros", "#A59C90", 220, "solo huecos libres", None, False),
]
g_html = ""
for name, col, n, rate, days, warn in gauges:
    pct = 100 if days is None else min(100, days / 30 * 100)
    dtxt = "sin prisa" if days is None else (f"para <b>{days} días</b>" if days < 60 else "para más de 2 meses")
    tag = '<span class="tag coral">⚠ Se acaba pronto · escribe más</span>' if warn else ('<span class="tag green">De sobra</span>' if days and days > 60 else '<span class="tag">Al final de la cola</span>')
    g_html += (f'<div class="gauge{" warn" if warn else ""}"><div class="t"><i style="background:{col}"></i>{name}</div><div class="n">{n}<small>guiones</small></div>'
               f'<div class="d">{rate} · {dtxt}</div><div class="meter2"><div style="width:{pct:.0f}%;background:{col if not warn else "#E0533A"}"></div></div>{tag}</div>')

items = [
    ("animales", "🦒", "MÁS ANIMALES", "csd", "¿Cómo se dicen MÁS ANIMALES en inglés?", "Cómo se dice · secuela", ["★ Secuela · 1,336", "Tema A"], (1.0, 0.85, 1.0), "Hoy", "19:30"),
    ("cuerpo", "🦵", "MÁS CUERPO", "csd", "¿Cómo se dicen MÁS PARTES DEL CUERPO?", "Cómo se dice · secuela", ["★ Secuela · 1,259", "Tema A"], (1.0, 0.85, 1.0), "Mañana", "08:30"),
    ("vida", "💼", "ENTREVISTA", "frase", "Inglés para una entrevista de trabajo (2)", "Frases · vida real", ["Vida real", "Otro hueco"], (0.47, 1.0, 1.0), "Mañana", "12:00"),
    ("casa", "🛁", "MÁS BAÑO", "csd", "¿Cómo se dicen MÁS COSAS DEL BAÑO?", "Cómo se dice · secuela", ["★ Secuela · 1,199", "Tema A"], (1.0, 0.85, 0.5), "Mañana", "16:00"),
    ("comida", "🥤", "MÁS BEBIDAS", "csd", "¿Cómo se dicen MÁS BEBIDAS en inglés?", "Cómo se dice · secuela", ["★ Secuela · 1,150", "Tema A"], (1.0, 0.85, 0.5), "Mañana", "19:30"),
    ("reto", "😴", "TENGO SUEÑO", "reto", "RETO: «tengo sueño» en inglés", "Series · cómic", ["Otro hueco", "RETO 415–537"], (0.13, 1.0, 1.0), "Dom", "12:00"),
    ("ciudad", "🔧", "HERRAMIENTAS", "csd", "¿Cómo se dicen las HERRAMIENTAS?", "Cómo se dice", ["Tema C · ×0.35"], (1.0, 0.35, 1.0), "Dom", "16:00"),
]
q_html = ""
for i, (fam, em, top, kind, title, fmt, tags, (fs, ts, fr), day, hr) in enumerate(items):
    sc = fs * ts * fr
    tg = "".join(f'<span class="tag {"green" if "Secuela" in t else ("coral" if "C ·" in t else "")}">{t}</span>' for t in tags)
    q_html += (f'<div class="qi{" first" if i==0 else ""}"><span class="pos">{i+1}</span>{thumb(fam, em, top, kind)}'
               f'<div class="ti"><b>{title}</b><small>{fmt}</small><div class="tags">{tg}</div></div>'
               f'<div class="score2"><div class="sb"><div style="width:{sc*100:.0f}%;background:{"#1F6FD1" if sc>0.6 else ("#E9A100" if sc>0.3 else "#C9C1B4")}"></div></div>'
               f'<small>prioridad {sc:.2f} = formato {fs:.2f} × tema {ts:.2f} × frescura {fr:.1f}</small></div>'
               f'<div class="when"><b>{hr}</b>{day}</div></div>')

cola = HEAD % (cola_css, side("Cola")) + f"""
<div class="top"><div><h1>Cola</h1><div class="sub"><b>491 guiones</b> esperan turno. Salen solos en este orden, 4 al día.</div></div>
<div class="tools" style="display:flex;gap:10px"><span class="btn ghost">⇅ Reordenar</span><span class="btn sm" style="padding:10px 16px;font-size:14px">＋ Añadir guiones</span></div></div>
<div class="eyebrow" style="margin-bottom:10px">Combustible · cuántos días quedan de cada formato</div>
<div class="fuel">{g_html}</div>
<div class="qgrid">
  <section class="card"><div class="ch" style="display:flex;justify-content:space-between;margin-bottom:6px"><div><div class="eyebrow">Lo próximo</div><h2 style="margin-top:3px">Así se llenan los huecos</h2></div><span class="chip">Ver los 491 →</span></div>{q_html}</section>
  <div style="display:flex;flex-direction:column;gap:24px">
  <section class="card mixcard"><div class="eyebrow">La mezcla de cada día</div><h2 style="margin-top:3px">3 + 1</h2>
    <div class="mix"><div style="flex:3;background:#1F6FD1">Cómo se dice ×3</div><div style="flex:1;background:#12854F">+1</div></div>
    <div class="ml"><div><i style="background:#1F6FD1"></i>Cómo se dice y secuelas<b>75 %</b></div><div><i style="background:#12854F"></i>Frases → RETO → Test, por turnos<b>25 %</b></div><div><i style="background:#A59C90"></i>Gramática<b>solo si sobra hueco</b></div></div>
    <div class="note2" style="margin-top:12px;font-size:12.5px;color:var(--muted);font-weight:600">Nunca dos del mismo tema en 3 días.</div></section>
  <section class="card"><div class="eyebrow">Apartados</div><h2 style="margin:3px 0 0">Fuera de la cola</h2>
    <div class="trays"><div class="tray"><b>12</b><span>por reescribir · repiten palabras</span></div><div class="tray"><b>7</b><span>saltados · temporada o tema hecho</span></div></div></section>
  </div>
</div>
<div class="note">Maqueta · Cola. Recuentos reales del 14 nov; el orden y las puntuaciones son ilustrativos.</div>""" + FOOT
open("cola.html", "w").write(cola)

# ───────────────────────── CREAR ─────────────────────────
crear_css = THUMB_CSS + """
.cg { display: grid; grid-template-columns: 1fr 350px; gap: 24px; align-items: start; }
.types { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.tile { width: 56px; height: 56px; border-radius: 16px; border: 2px solid #1C1812; display: grid; place-items: center; font-size: 26px; flex: none; box-shadow: 2px 2px 0 #1C1812; font-family: Emo; }
.ty { background: var(--card); border: 1.5px solid var(--line); border-radius: 18px; padding: 12px; display: flex; flex-direction: column; gap: 10px; position: relative; }
.ty.on { border: 2.5px solid var(--ink); box-shadow: 5px 5px 0 var(--blue); }
.ty.on::after { content: "✓"; position: absolute; top: -10px; right: -10px; width: 28px; height: 28px; border-radius: 50%; background: var(--blue); color: #fff; display: grid; place-items: center; font-weight: 900; border: 2.5px solid var(--ink); }
.ty .th9 { width: 74px; } .ty .row { display: flex; gap: 12px; }
.ty b { font-size: 14.5px; display: block; } .ty small { color: var(--muted); font-size: 12px; font-weight: 650; display: block; line-height: 1.35; }
.ty .stat { display: flex; justify-content: space-between; border-top: 1px solid #F1ECE3; padding-top: 8px; font-size: 12px; font-weight: 750; color: var(--muted); }
.ty .stat b { display: inline; font-family: Fredoka; font-weight: 500; font-size: 14px; color: var(--ink); }
.ty.dim { opacity: .62; }
.seg2 { display: flex; background: var(--sand); border-radius: 12px; padding: 4px; gap: 4px; margin: 10px 0 14px; }
.seg2 span { flex: 1; text-align: center; padding: 8px; border-radius: 9px; font-weight: 750; font-size: 13px; color: var(--muted); }
.seg2 span.on { background: var(--card); color: var(--ink); box-shadow: 0 1px 3px rgba(0,0,0,.12); }
.topics { display: flex; flex-wrap: wrap; gap: 7px; }
.topics span { border: 1.5px solid var(--line); border-radius: 10px; padding: 6px 10px; font-weight: 700; font-size: 13px; background: var(--card); }
.topics span.on { background: var(--ink); color: #fff; border-color: var(--ink); }
.topics span em { font-style: normal; font-size: 11px; color: var(--muted); margin-left: 4px; }
.topics span.on em { color: #F6D35B; }
.go { margin-top: 18px; display: flex; flex-direction: column; gap: 10px; }
.go .btn.primary { justify-content: center; }
.go small { text-align: center; color: var(--muted); font-weight: 650; font-size: 12.5px; }
.job { display: flex; gap: 14px; align-items: center; }
.job .th9 { width: 62px; flex: none; }
.steps { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; margin: 14px 0 10px; }
.steps div { text-align: center; font-size: 11.5px; font-weight: 750; color: var(--muted); }
.steps div i { display: block; height: 7px; border-radius: 99px; background: #EAE3D6; margin-bottom: 6px; }
.steps div.done i { background: var(--green); } .steps div.now i { background: linear-gradient(90deg, var(--blue) 55%, #EAE3D6 55%); } .steps div.now { color: var(--ink); }
.loglines { font-size: 12.5px; font-weight: 600; color: var(--muted); line-height: 1.7; border-top: 1px solid #F1ECE3; padding-top: 10px; }
.loglines b { color: var(--green); }
"""
types = [
    ("casa", "🏠", "CASA", "csd", "Cómo se dice", "10 palabras de un tema, con la lista en el fotograma 0.", "858", "$0.11", True, False),
    ("vida", "💼", "ENTREVISTA", "frase", "Frases · vida real", "Una frase útil y cómo decirla.", "405", "$0.06", False, False),
    ("test", "🎯", "FAMILIA", "test", "Test de nivel", "¿Sabes las 10? A1, A2 o B1.", "502", "$0.09", False, False),
    ("reto", "😴", "SUEÑO", "reto", "Series «RETO»", "Cómic, mensajes, escena o póster.", "113", "$0.10", False, False),
    ("cuerpo", "🗣", "MÉDICO", "dilo", "Dilo en inglés", "Frases para un sitio: médico, banco…", "276", "$0.08", False, False),
    ("clima", "📚", "VOCAB", "frase", "Vocabulario", "Palabras de un tema con ejemplo.", "318", "$0.07", False, False),
    ("ropa", "✏️", "COMPLETA", "frase", "Gramática", "Completa, elige, verdadero o falso.", "~150", "$0.05", False, True),
    ("ciudad", "🎓", "LECCIÓN", "frase", "Lección larga", "8–10 min con Manim. Pocas vistas.", "40", "$1.10", False, True),
]
t_html = ""
for fam, em, top, kind, name, desc, med, cost, on, dim in types:
    a_, b_ = FAM[fam]
    t_html += (f'<div class="ty{" on" if on else ""}{" dim" if dim else ""}"><div class="row"><div class="tile" style="background:linear-gradient(160deg,{a_},{b_})">{em}</div><div><b>{name}</b><small>{desc}</small></div></div>'
               f'<div class="stat"><span>rinde <b>{med}</b></span><span>cuesta <b>{cost}</b></span></div></div>')
crear = HEAD % (crear_css, side("Crear")) + f"""
<div class="top"><div><h1>Crear</h1><div class="sub">Elige un formato y un tema. Sale con voz y te espera en <b>Revisar</b>.</div></div></div>
<div class="cg">
  <section><div class="eyebrow" style="margin-bottom:12px">1 · Formato <span style="text-transform:none;letter-spacing:0;font-weight:650">— «rinde» son las vistas típicas</span></div><div class="types">{t_html}</div></section>
  <div style="display:flex;flex-direction:column;gap:24px">
  <section class="sticker" style="padding:22px">
    <div class="eyebrow">2 · Tema</div>
    <div class="seg2"><span>Al azar</span><span class="on">Categoría</span><span>Tema concreto</span></div>
    <div class="topics"><span class="on">Casa<em>1,601</em></span><span>Comida<em>1,389</em></span><span>Animales<em>1,336</em></span><span>Cuerpo<em>1,259</em></span><span>Ropa<em>1,031</em></span><span>Cocina<em>1,079</em></span><span>Escuela<em>1,068</em></span><span>Clima</span><span>Ciudad</span><span>Emociones</span></div>
    <div class="go"><span class="btn primary">▶&#xFE0E; Crear vídeo</span><small>~42 s · ~\\$0.11 · listo en ~2 min · voz por OpenRouter</small></div>
  </section>
  <section class="card"><div class="eyebrow">En marcha</div>
    <div class="job" style="margin-top:10px">{thumb("casa","🛋","MÁS CASA","csd")}<div><b style="font-size:15px">¿Cómo se dicen MÁS COSAS DE LA CASA?</b><div class="muted" style="font-size:12.5px;font-weight:650">empezó hace 48 s · faltan ~70 s</div></div></div>
    <div class="steps"><div class="done"><i></i>Guion</div><div class="done"><i></i>Voz</div><div class="now"><i></i>Montaje</div><div><i></i>Sonido</div><div><i></i>Control</div></div>
    <div class="loglines"><b>✓</b> voz: 10 de 10 frases, \\$0.08<br><b>✓</b> pronunciación figurada: 10 de 10<br>⏳ dibujando fotogramas 412 de 1,260</div>
  </section></div>
</div>
<div class="note">Maqueta · Crear. «Rinde» = vistas típicas reales; costes por vídeo de los registros; el trabajo en marcha es ilustrativo.</div>""" + FOOT
open("crear.html", "w").write(crear.replace("\\$", "$"))

# ───────────────────────── BIBLIOTECA ─────────────────────────
bib_css = THUMB_CSS + """
.filters { display: flex; gap: 10px; align-items: center; margin-bottom: 20px; }
.fchip { border: 1.5px solid var(--line); background: var(--card); border-radius: 99px; padding: 7px 14px; font-weight: 750; font-size: 13px; }
.fchip.on { background: var(--ink); color: #fff; border-color: var(--ink); }
.fchip em { font-style: normal; color: var(--muted); margin-left: 5px; font-weight: 700; } .fchip.on em { color: #F6D35B; }
.search { margin-left: auto; display: flex; align-items: center; gap: 8px; background: var(--card); border: 1.5px solid var(--line); border-radius: 12px; padding: 9px 14px; width: 280px; color: var(--muted); font-weight: 600; font-size: 13.5px; }
.lib { display: grid; grid-template-columns: repeat(5, 1fr); gap: 20px; }
.vc { background: var(--card); border: 1px solid var(--line); border-radius: 18px; padding: 10px; display: flex; flex-direction: column; gap: 10px; }
.vc .th9 { width: 100%; border-radius: 12px; }
.vc .th9 .h span { font-size: 15px; } .vc .th9 .c { font-size: 12px; padding: 2px 7px; } .vc .th9 .tiles i { height: 26px; } .vc .th9 .tiles.one i { height: 32px; }
.vc .st { position: absolute; left: 8px; bottom: 8px; z-index: 2; font-size: 11px; font-weight: 800; border-radius: 8px; padding: 3px 8px; border: 1.5px solid #1C1812; }
.vc .dur { position: absolute; right: 8px; bottom: 8px; z-index: 2; background: rgba(28,24,18,.8); color: #fff; font-size: 11px; font-weight: 800; border-radius: 6px; padding: 2px 6px; }
.vc b { font-size: 13.5px; line-height: 1.3; display: block; }
.vc .meta { display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-weight: 700; color: var(--muted); }
.vc .views { display: flex; align-items: center; gap: 6px; }
.vc .views strong { font-family: Fredoka; font-weight: 700; font-size: 16px; color: var(--ink); }
.spark { display: flex; align-items: flex-end; gap: 2px; height: 18px; } .spark i { width: 4px; border-radius: 2px; background: #B9D1F3; } .spark i:first-child { background: var(--blue); }
.vc .acts { display: flex; gap: 6px; } .vc .acts span { flex: 1; text-align: center; border: 1.5px solid var(--line); border-radius: 10px; padding: 6px; font-size: 12.5px; font-weight: 750; }
.statsrow { display: flex; gap: 12px; margin-bottom: 18px; }
.statsrow div { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 10px 16px; display: flex; gap: 10px; align-items: baseline; }
.statsrow b { font-family: Fredoka; font-weight: 700; font-size: 22px; } .statsrow span { font-size: 12.5px; font-weight: 700; color: var(--muted); }
"""
vids = [
    ("casa", "🩺", "MÉDICO", "csd", "¿Cómo se dice MÉDICO?", "Publicado", "green", 661, "hoy", "0:41", [9, 2, 1]),
    ("vida", "🧩", "YA LO RESOLVÍ", "frase", "¿Sabes decir «YA LO RESOLVÍ»?", "Publicado", "green", 496, "ayer", "0:24", [8, 3, 1]),
    ("test", "👪", "FAMILIA", "test", "La FAMILIA: ¿sabes las 10?", "Publicado", "green", 368, "ayer", "0:38", [7, 3, 1]),
    ("cuerpo", "🏫", "ESCUELA", "dilo", "EN LA ESCUELA: frases para padres", "Publicado", "green", 263, "hoy", "0:44", [9, 1, 0]),
    ("animales", "🐛", "INSECTOS", "csd", "¿Cómo se dicen los INSECTOS?", "Programado", "yellow", None, "hoy 16:00", "0:40", None),
    ("casa", "👵", "MÁS FAMILIA", "csd", "¿Cómo se dice MÁS FAMILIA?", "En revisión", "blue", None, "pendiente", "0:31", None),
    ("clima", "📱", "TECNOLOGÍA", "csd", "¿Cómo se dice TECNOLOGÍA?", "Publicado", "green", 18, "hoy", "0:40", [2, 0, 0]),
    ("vida", "🌊", "ME DEJO LLEVAR", "frase", "¿Sabes decir «ME DEJO LLEVAR»?", "Publicado", "green", 200, "hoy", "0:22", [8, 2, 0]),
    ("comida", "🌳", "NATURALEZA", "csd", "¿Cómo se dice NATURALEZA?", "Publicado", "green", 6, "hoy", "0:41", [1, 0, 0]),
    ("reto", "🔗", "VERBOS + PREP.", "reto", "Completa: VERBOS + PREPOSICIÓN", "Publicado", "green", 160, "hoy", "0:29", [6, 2, 0]),
]
stc = {"green": "background:#DAF1E4;color:#1F6B42", "yellow": "background:#FCF0C4;color:#6E5300", "blue": "background:#E1ECFB;color:#164C93"}
v_html = ""
for fam, em, top, kind, title, st, sc, views, when, dur, sp in vids:
    th = thumb(fam, em, top, kind).replace('<div class="th9"', '<div class="th9"', 1)
    th = th[:-6] + f'<span class="st" style="{stc[sc]}">{st}</span><span class="dur">{dur}</span></div>'
    vw = (f'<span class="views"><strong>{views:,}</strong><span class="spark">' + "".join(f'<i style="height:{max(2,h*2)}px"></i>' for h in sp) + '</span></span>') if views is not None else '<span class="views">—</span>'
    v_html += f'<div class="vc">{th}<b>{title}</b><div class="meta">{vw}<span>{when}</span></div><div class="acts"><span>▶&#xFE0E; Ver</span><span>⋯</span></div></div>'
bib = HEAD % (bib_css, side("Biblioteca")) + f"""
<div class="top"><div><h1>Biblioteca</h1><div class="sub">Todo lo producido. Cada vídeo con sus vistas de los primeros días.</div></div></div>
<div class="statsrow"><div><b>79</b><span>vídeos en disco</span></div><div><b>1.6 GB</b><span>ocupan</span></div><div><b>71,097</b><span>vistas entre todos</span></div></div>
<div class="filters"><span class="fchip on">Todos<em>79</em></span><span class="fchip">Cómo se dice<em>41</em></span><span class="fchip">Frases<em>12</em></span><span class="fchip">Tests<em>9</em></span><span class="fchip">Series<em>10</em></span><span class="fchip">Otros<em>7</em></span><div class="search">⌕ Buscar por tema o palabra…</div></div>
<div class="lib">{v_html}</div>
<div class="note">Maqueta · Biblioteca. Títulos y vistas reales de los últimos días; miniaturas dibujadas como el fotograma 0 de cada formato.</div>""" + FOOT
open("biblioteca.html", "w").write(bib)

# ───────────────────────── COMPONENTES ─────────────────────────
comp_css = """
.cgrid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px; }
.lbl { font-size: 12px; font-weight: 800; color: var(--muted); letter-spacing: .06em; text-transform: uppercase; margin: 14px 0 6px; }
.inp { border: 1.5px solid var(--line); border-radius: 12px; padding: 11px 13px; font-size: 14.5px; font-weight: 600; background: #FFFDF9; display: flex; justify-content: space-between; align-items: center; }
.inp.focus { border: 2px solid var(--blue); box-shadow: 0 0 0 4px #E1ECFB; }
.inp .ph { color: #A39E96; } .step { display: flex; gap: 6px; } .step span { width: 28px; height: 28px; border-radius: 8px; background: var(--sand); display: grid; place-items: center; font-weight: 800; }
.seg2 { display: flex; background: var(--sand); border-radius: 12px; padding: 4px; gap: 4px; }
.seg2 span { flex: 1; text-align: center; padding: 8px; border-radius: 9px; font-weight: 750; font-size: 13px; color: var(--muted); }
.seg2 span.on { background: var(--card); color: var(--ink); box-shadow: 0 1px 3px rgba(0,0,0,.12); }
.tg { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 14px; margin: 8px 0; } .sw { width: 38px; height: 22px; border-radius: 99px; background: var(--green); position: relative; } .sw::after { content: ""; position: absolute; right: 3px; top: 3px; width: 16px; height: 16px; border-radius: 50%; background: #fff; } .sw.off { background: #CFC6B6; } .sw.off::after { right: auto; left: 3px; }
table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13.5px; }
th { text-align: left; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); font-weight: 800; padding: 8px 10px; border-bottom: 1.5px solid var(--line); }
td { padding: 10px; border-bottom: 1px solid #F1ECE3; font-weight: 600; } td.n { text-align: right; font-family: Fredoka; font-weight: 500; font-size: 15px; }
tr:hover td { background: #FBF8F3; }
.al { border-radius: 14px; padding: 12px 14px; font-weight: 650; font-size: 13.5px; display: flex; gap: 10px; margin-bottom: 10px; border: 1.5px solid; }
.al.i { background: #E1ECFB; border-color: #B9D1F3; color: #164C93; } .al.s { background: #DAF1E4; border-color: #A9DCBF; color: #1F6B42; } .al.w { background: #FCF0C4; border-color: #EED78A; color: #6E5300; } .al.e { background: #FADCD8; border-color: #F0B3AC; color: #8E2B22; }
.exp { border: 1.5px solid var(--line); border-radius: 14px; } .exp div { padding: 12px 14px; font-weight: 750; display: flex; justify-content: space-between; } .exp div + div { border-top: 1px solid var(--line); font-weight: 600; color: var(--muted); font-size: 13px; }
.tabs { display: flex; gap: 18px; border-bottom: 1.5px solid var(--line); } .tabs span { padding: 8px 0; font-weight: 750; color: var(--muted); } .tabs span.on { color: var(--ink); border-bottom: 3px solid var(--blue); margin-bottom: -1.5px; }
.toast { background: var(--ink); color: #fff; border-radius: 14px; padding: 12px 16px; font-weight: 700; display: flex; gap: 10px; align-items: center; box-shadow: 0 10px 30px rgba(0,0,0,.18); }
.toast b { color: #F6D35B; }
.empty { text-align: center; padding: 18px; border: 2px dashed #D9D0C0; border-radius: 16px; } .empty img { width: 70px; } .empty b { display: block; font-family: Fredoka; font-weight: 500; font-size: 17px; margin: 6px 0 2px; } .empty span { font-size: 13px; color: var(--muted); font-weight: 600; }
.skel { height: 12px; border-radius: 6px; background: linear-gradient(90deg, #EFE9DF, #F8F4EE, #EFE9DF); margin: 8px 0; }
.btnrow { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.btn.dis { opacity: .45; box-shadow: none; }
"""
comp = HEAD % (comp_css, side("Ajustes")) + """
<div class="top"><div><h1>Componentes</h1><div class="sub">Cómo debe verse cada pieza de Streamlit en el panel. <b>Nada con el aspecto por defecto.</b></div></div></div>
<div class="cgrid">
<section class="card"><h3>Campos</h3>
 <div class="lbl">Texto</div><div class="inp focus">¿Cómo se dice MÁS FAMILIA? <span class="muted" style="font-size:12px">58/100</span></div>
 <div class="lbl">Buscar</div><div class="inp"><span class="ph">⌕ Buscar por tema o palabra…</span></div>
 <div class="lbl">Desplegable</div><div class="inp">Cómo se dice <span>⌄</span></div>
 <div class="lbl">Número</div><div class="inp">5 <span class="step"><span>−</span><span>＋</span></span></div>
 <div class="lbl">Opciones (en vez de radio)</div><div class="seg2"><span>Al azar</span><span class="on">Categoría</span><span>Tema</span></div>
 <div class="lbl">Interruptor (en vez de checkbox)</div><div class="tg"><span class="sw"></span>YouTube</div><div class="tg"><span class="sw off"></span>TikTok</div>
</section>
<section class="card"><h3>Botones y avisos</h3>
 <div class="lbl">Botones</div><div class="btnrow"><span class="btn primary">▶&#xFE0E; Producir</span><span class="btn green">✓ Aprobar</span></div>
 <div class="btnrow" style="margin-top:12px"><span class="btn">Secundario</span><span class="btn ghost">Fantasma</span><span class="btn sm">Pequeño</span><span class="btn dis">Desactivado</span></div>
 <div class="lbl">Avisos</div>
 <div class="al i">ℹ Las estadísticas se actualizan solas cada 20 h.</div><div class="al s">✓ Programado para hoy a las 19:30.</div><div class="al w">⚠ Quedan 32 «Cómo se dice»: unos 11 días.</div><div class="al e">✕ Facebook no aceptó el vídeo: falta el permiso read_insights.</div>
 <div class="lbl">Notificación</div><div class="toast">✓ <span>En marcha: <b>MÁS ANIMALES</b> · listo en ~2 min</span></div>
</section>
<section class="card"><h3>Datos y estados</h3>
 <div class="lbl">Pestañas</div><div class="tabs"><span class="on">YouTube</span><span>Facebook</span><span>TikTok</span></div>
 <div class="lbl">Tabla</div><table><tr><th>Formato</th><th style="text-align:right">Vídeos</th><th style="text-align:right">Típicas</th></tr><tr><td>Cómo se dice</td><td class="n">52</td><td class="n">858</td></tr><tr><td>Test de nivel</td><td class="n">9</td><td class="n">502</td></tr><tr><td>Frases</td><td class="n">14</td><td class="n">405</td></tr></table>
 <div class="lbl">Desplegable de sección</div><div class="exp"><div>Detalles del disco <span>⌄</span></div><div>79 vídeos en disco · 79 en la lista · cuadran</div></div>
 <div class="lbl">Vacío</div><div class="empty"><img src="img/bien_hecho_s.png"><b>Nada que revisar</b><span>Produce el siguiente en Inicio.</span></div>
 <div class="lbl">Cargando</div><div class="skel" style="width:90%"></div><div class="skel" style="width:70%"></div>
</section>
</div>
<div class="note">Maqueta · Componentes: la guía para vestir los controles de Streamlit (campos, desplegables, radios, checkboxes, tablas, pestañas, avisos y estados).</div>""" + FOOT
open("componentes.html", "w").write(comp)
print("ok")
