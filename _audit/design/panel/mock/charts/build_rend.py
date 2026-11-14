"""Draws the Rendimiento mock: real channel data from rend.json, charts as inline SVG."""
import json, math, datetime as dt

D = json.load(open("rend.json"))
FMT = {  # label, colour
    "how_do_you_say": ("Cómo se dice", "#1F6FD1"),
    "level_test": ("Test de nivel", "#FF6F4F"),
    "phrases_level": ("Frases", "#12854F"),
    "vocabulary": ("Vocabulario", "#2BB5A8"),
    "true_false_level": ("Verdadero/falso (nivel)", "#A59C90"),
    "say_it_level": ("Dilo en inglés", "#8A5CD6"),
    "educational": ("Educativo", "#A59C90"),
    "fill_blank": ("Completa", "#A59C90"),
    "fill_level": ("Completa (nivel)", "#A59C90"),
    "true_false": ("Verdadero/falso", "#A59C90"),
    "choose_level": ("Elige la correcta", "#A59C90"),
    "pronunciation": ("Pronunciación", "#A59C90"),
    "quiz": ("Quiz", "#A59C90"),
    "hecho_con_claude": ("Series (cómic, póster…)", "#E9A100"),
    "manim_lesson": ("Lecciones largas", "#6B6672"),
    "—": ("Sin tipo", "#C9C1B4"),
    "": ("Sin tipo", "#C9C1B4"),
}
MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
def k(n): return f"{n:,.0f}"
def fdate(s): d = dt.date.fromisoformat(s); return f"{d.day} {MES[d.month-1]}"

# ── A: daily views area (on ink) ──────────────────────────────
def area():
    W, H, pl, pr, pt, pb = 760, 230, 8, 8, 28, 34
    pts = D["daily"][-56:]; ups = D["uploads"][-56:]
    mx = max(v for _, v in pts) * 1.12
    n = len(pts); sx = (W - pl - pr) / (n - 1)
    xy = [(pl + i * sx, pt + (H - pt - pb) * (1 - v / mx)) for i, (_, v) in enumerate(pts)]
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    base = H - pb
    fill = path + f" L{xy[-1][0]:.1f},{base} L{xy[0][0]:.1f},{base} Z"
    s = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}"><defs><linearGradient id="ga" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#F6D35B" stop-opacity=".55"/><stop offset="1" stop-color="#F6D35B" stop-opacity="0"/></linearGradient></defs>']
    for g in (0.25, 0.5, 0.75):
        y = pt + (H - pt - pb) * (1 - g)
        s.append(f'<line x1="{pl}" x2="{W-pr}" y1="{y:.1f}" y2="{y:.1f}" stroke="#ffffff" stroke-opacity=".08"/>')
        s.append(f'<text x="{pl+2}" y="{y-5:.1f}" text-anchor="start" font-size="11" fill="#ffffff" fill-opacity=".38" font-weight="600">{k(mx*g)}</text>')
    s.append(f'<path d="{fill}" fill="url(#ga)"/><path d="{path}" fill="none" stroke="#F6D35B" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>')
    # uploads as small bars under the axis
    for i, (_, u) in enumerate(ups):
        if u:
            x = pl + i * sx
            s.append(f'<rect x="{x-2.2:.1f}" y="{base+8}" width="4.4" height="{min(u,9)*2.2+2:.1f}" rx="2" fill="#7FB2F0"/>')
    # peak
    pi = max(range(n), key=lambda i: pts[i][1]); px, py = xy[pi]
    s.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6" fill="#F6D35B" stroke="#191720" stroke-width="3"/>')
    s.append(f'<g transform="translate({px-58:.1f},{py-30:.1f})"><rect width="116" height="22" rx="11" fill="#F6D35B"/><text x="58" y="15" text-anchor="middle" font-size="12" font-weight="800" fill="#191720">{k(pts[pi][1])} · {fdate(pts[pi][0])}</text></g>')
    last = xy[-1]
    s.append(f'<circle cx="{last[0]:.1f}" cy="{last[1]:.1f}" r="5" fill="#fff"/>')
    for i in range(0, n, 7):
        s.append(f'<text x="{pl+i*sx:.1f}" y="{H-2}" font-size="11" fill="#ffffff" fill-opacity=".45" font-weight="600">{fdate(pts[i][0])}</text>')
    s.append("</svg>")
    return "".join(s)

# ── B: formats ────────────────────────────────────────────────
def formats():
    rows = [f for f in D["formats"] if f["f"] not in ("—", "")][:9]
    mx = rows[0]["med"]
    hd = rows[0]["med"]
    out = []
    for f in rows:
        lab, col = FMT.get(f["f"], (f["f"], "#A59C90"))
        w = 100 * f["med"] / mx
        star = ' <span class="crown">★ el que más rinde</span>' if f is rows[0] else ""
        ret = f'{f["ret"]:.0f} %' if f["ret"] else "—"
        out.append(f'<div class="fr"><div class="fl"><b>{lab}</b>{star}<small>{f["n"]} vídeos · {k(f["views"])} vistas · +{f["subs"]} subs</small></div>'
                   f'<div class="fb"><div style="width:{w:.1f}%;background:{col}"><span>{k(f["med"])}</span></div></div>'
                   f'<div class="fx">{f["med"]/hd*100:.0f}%</div><div class="fret"><i style="--p:{min(f["ret"] or 0,100):.0f}%"></i>{ret}</div></div>')
    return "".join(out)

# ── C: donut ──────────────────────────────────────────────────
def donut():
    src = D["sources"]; names = {"SHORTS": ("Feed de Shorts", "#1F6FD1"), "YT_SEARCH": ("Búsqueda", "#F6D35B"), "EXT": ("Fuera de YouTube", "#FF6F4F")}
    R, r, c = 78, 50, 92; a0 = -90; s = [f'<svg viewBox="0 0 184 184" width="184" height="184">']
    for key, pct in src.items():
        if pct <= 0: continue
        a1 = a0 + 360 * pct / 100
        large = 1 if a1 - a0 > 180 else 0
        def p(a, rad): return c + rad * math.cos(math.radians(a)), c + rad * math.sin(math.radians(a))
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = p(a0, R), p(a1, R), p(a1, r), p(a0, r)
        s.append(f'<path d="M{x0:.2f},{y0:.2f} A{R},{R} 0 {large} 1 {x1:.2f},{y1:.2f} L{x2:.2f},{y2:.2f} A{r},{r} 0 {large} 0 {x3:.2f},{y3:.2f} Z" fill="{names[key][1]}" stroke="#fff" stroke-width="3"/>')
        a0 = a1
    s.append(f'<text x="92" y="92" text-anchor="middle" font-family="Fredoka" font-weight="700" font-size="30" fill="#191720">{src["SHORTS"]:.0f}%</text><text x="92" y="112" text-anchor="middle" font-size="11.5" font-weight="700" fill="#6B6672">del feed</text></svg>')
    leg = "".join(f'<div><i style="background:{names[k_][1]}"></i>{names[k_][0]}<b>{v:.1f} %</b></div>' for k_, v in src.items())
    return "".join(s), leg

# ── D: typical curve ──────────────────────────────────────────
def curve():
    c = D["curve"]; tot = sum(c); W, H = 470, 190; bw = 22; gap = (W - 30 - bw * 15) / 14
    mx = c[0]; s = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}">']
    acc = 0
    for i, v in enumerate(c):
        h = max(2, (H - 52) * v / mx); x = 10 + i * (bw + gap); y = H - 24 - h
        col = "#1F6FD1" if i == 0 else "#B9D1F3"
        s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw}" height="{h:.1f}" rx="5" fill="{col}"/>')
        if i in (0, 1, 2, 3, 7, 14):
            s.append(f'<text x="{x+bw/2:.1f}" y="{H-8}" text-anchor="middle" font-size="11" font-weight="700" fill="#6B6672">{"día " if i==0 else ""}{i+1}</text>')
        if v and i < 4:
            s.append(f'<text x="{x+bw/2:.1f}" y="{y-6:.1f}" text-anchor="middle" font-size="11.5" font-weight="800" fill="#191720">{v}</text>')
    s.append("</svg>")
    return "".join(s), round(100 * c[0] / tot), round(100 * sum(c[:2]) / tot)

# ── E: hours ──────────────────────────────────────────────────
def hours():
    hs = {int(h): v for h, v in D["hours"].items()}
    W, H = 470, 190; bw = 15; s = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}">']
    mx = max(v[0] for v in hs.values()); best = max(hs, key=lambda h: hs[h][0] if hs[h][1] >= 5 else 0)
    x0 = 12; step = (W - 24) / 24
    for h in range(24):
        x = x0 + h * step
        if h in hs:
            v, n = hs[h]; hh = (H - 54) * v / mx; y = H - 26 - hh
            col = "#12854F" if h == best else ("#B9D1F3" if n >= 5 else "#E3DCCF")
            s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw}" height="{hh:.1f}" rx="4" fill="{col}"/>')
            if h == best:
                s.append(f'<text x="{x+bw/2:.1f}" y="{y-7:.1f}" text-anchor="middle" font-size="12" font-weight="800" fill="#12854F">{v}</text>')
        else:
            s.append(f'<rect x="{x:.1f}" y="{H-28}" width="{bw}" height="2" rx="1" fill="#E3DCCF"/>')
        if h % 3 == 0:
            s.append(f'<text x="{x+bw/2:.1f}" y="{H-8}" text-anchor="middle" font-size="11" font-weight="700" fill="#6B6672">{h}h</text>')
    for lab, hf in (("08:30", 8.5), ("12:00", 12), ("16:00", 16), ("19:30", 19.5)):
        x = x0 + hf * step + bw / 2
        s.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="14" y2="{H-26}" stroke="#191720" stroke-dasharray="3 4" stroke-opacity=".45"/><text x="{x:.1f}" y="10" text-anchor="middle" font-size="10" font-weight="800" fill="#191720" fill-opacity=".6">{lab}</text>')
    s.append("</svg>")
    return "".join(s), best, hs[best]

# ── F: scatter ────────────────────────────────────────────────
def scatter():
    W, H, pl, pb = 720, 300, 46, 30
    s = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}">']
    xmax, ymax = 140, 1700
    for gy in (0, 400, 800, 1200, 1600):
        y = 10 + (H - 10 - pb) * (1 - gy / ymax)
        s.append(f'<line x1="{pl}" x2="{W-6}" y1="{y:.1f}" y2="{y:.1f}" stroke="#E9E2D6"/><text x="{pl-8}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="#6B6672" font-weight="600">{k(gy)}</text>')
    for gx in (0, 25, 50, 75, 100, 125):
        x = pl + (W - pl - 6) * gx / xmax
        s.append(f'<text x="{x:.1f}" y="{H-8}" text-anchor="middle" font-size="11" fill="#6B6672" font-weight="600">{gx}%</text>')
    x100 = pl + (W - pl - 6) * 100 / xmax
    s.append(f'<line x1="{x100:.1f}" x2="{x100:.1f}" y1="10" y2="{H-pb}" stroke="#191720" stroke-dasharray="4 4" stroke-opacity=".35"/><text x="{x100+6:.1f}" y="22" font-size="10.5" font-weight="700" fill="#6B6672">a la derecha: lo ven más de una vez</text>')
    pts = sorted(D["scatter"], key=lambda p: p[2] == "how_do_you_say")
    for r, v, f in pts:
        x = pl + (W - pl - 6) * min(r, xmax - 2) / xmax; y = 10 + (H - 10 - pb) * (1 - v / ymax)
        col = FMT.get(f, ("", "#A59C90"))[1]; big = f == "how_do_you_say"
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{6.5 if big else 5}" fill="{col}" fill-opacity="{.85 if big else .7}" stroke="#fff" stroke-width="1.5"/>')
    s.append("</svg>")
    return "".join(s)

def top():
    em = ["🏠", "🍎", "🐶", "🤔", "🦶", "🎨", "🛋", "👵", "🛁", "🍓"]
    mx = D["top"][0]["v"]; out = []
    for i, t in enumerate(D["top"]):
        name = t["t"].replace(" #Shorts", "").replace("¿Cómo se dice ", "").replace("¿Cómo se dicen ", "").split(" en inglés")[0]
        out.append(f'<div class="tp"><span class="rk">{i+1}</span><span class="em">{em[i]}</span><div class="tn"><b>{name}</b><div class="tb"><div style="width:{100*t["v"]/mx:.0f}%"></div></div></div><span class="tv">{k(t["v"])}</span></div>')
    return "".join(out)

A = area(); B = formats(); C_svg, C_leg = donut(); Dc, d1, d2 = curve(); E, best, bestv = hours(); F = scatter(); T = top()
w = D["w"]; growth = round(100 * (w["v7"] - w["v14"]) / w["v14"])
last28 = sum(v for _, v in D["daily"][-28:]); prev28 = sum(v for _, v in D["daily"][-56:-28])
leg_fmt = "".join(f'<span><i style="background:{c}"></i>{l}</span>' for l, c in [("Cómo se dice", "#1F6FD1"), ("Frases", "#12854F"), ("Test de nivel", "#FF6F4F"), ("Dilo en inglés", "#8A5CD6"), ("Series", "#E9A100"), ("Vocabulario", "#2BB5A8"), ("Gramática y otros", "#A59C90")])

html = open("rend_tpl.html").read()
for key, val in dict(AREA=A, FORMATS=B, DONUT=C_svg, DONUTLEG=C_leg, CURVE=Dc, D1=str(d1), D2=str(d2), HOURS=E, BEST=f"{best}:00",
                     BESTV=str(bestv[0]), BESTN=str(bestv[1]), SCATTER=F, TOP=T, LEGFMT=leg_fmt,
                     TOTAL=k(D["total_views"]), SUBS=k(D["total_subs"]), LIKES=k(D["likes"]), SHARES=k(D["shares"]), COMMENTS=k(D["comments"]),
                     N=str(D["n"]), V7=k(w["v7"]), GROWTH=f"+{growth}", S7=str(w["s7"]), N7=str(w["n7"]),
                     L28=k(last28), X28=f"×{last28/prev28:.0f}" if prev28 else "", CURVEN=str(D["curve_n"])).items():
    html = html.replace("{{" + key + "}}", val)
open("rendimiento.html", "w").write(html)
print("ok", growth, last28, prev28, d1, d2, best, bestv)
