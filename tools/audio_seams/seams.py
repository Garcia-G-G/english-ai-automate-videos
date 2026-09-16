import json, subprocess, sys, math
import numpy as np

SR = 16000

def decode(path):
    p = subprocess.run(["ffmpeg","-v","error","-i",path,"-f","s16le","-acodec","pcm_s16le",
                        "-ac","1","-ar",str(SR),"-"], capture_output=True)
    if p.returncode != 0:
        sys.exit("ffmpeg fallo: " + p.stderr.decode()[:400])
    a = np.frombuffer(p.stdout, dtype="<i2").astype(np.float32) / 32768.0
    if a.size == 0:
        sys.exit("decodificacion vacia: " + path)
    return a

def db(x):
    if x.size == 0:
        return None
    r = float(np.sqrt(np.mean(x.astype(np.float64)**2)))
    return -120.0 if r <= 1e-6 else 20*math.log10(r)

def win(a, t0, t1):
    i0 = max(0, int(t0*SR)); i1 = min(a.size, int(t1*SR))
    return a[i0:i1] if i1 > i0 else a[0:0]

mp3, meta = sys.argv[1], sys.argv[2]
a = decode(mp3)
j = json.load(open(meta))
segs = j.get("segments") or j.get("segment_times") or []
print(f"archivo: {mp3.split('/')[-1]}")
print(f"muestras: {a.size}  duracion real: {a.size/SR:.3f}s  segmentos: {len(segs)}")
print()

def seg_bounds(s):
    if isinstance(s, dict):
        n = s.get("id") or s.get("name") or s.get("label") or "?"
        st = s.get("start"); en = s.get("end")
        if st is None: st = s.get("start_time")
        if en is None: en = s.get("end_time")
        return n, float(st), float(en)
    return str(s[0]), float(s[1]), float(s[2])

rows = []
for s in segs:
    try:
        rows.append(seg_bounds(s))
    except Exception as e:
        print("no pude leer segmento:", s, e)

hdr = f"{'segmento':22} {'inicio':>7} {'fin':>7} {'cola60ms':>9} {'post100ms':>10} {'caida':>7} {'cabeza60':>9} {'pre100':>8} {'hueco':>7}"
print(hdr); print("-"*len(hdr))
cortes_fin = 0; cortes_ini = 0
for k,(n,st,en) in enumerate(rows):
    tail = db(win(a, en-0.060, en))
    post = db(win(a, en, en+0.100))
    head = db(win(a, st, st+0.060))
    pre  = db(win(a, st-0.100, st))
    prev_end = rows[k-1][2] if k else 0.0
    gap = st - prev_end
    drop = (tail - post) if (tail is not None and post is not None) else float('nan')
    flag = ""
    if tail is not None and tail > -30 and drop >= 6:
        flag = " <-- CORTE AL FINAL"; cortes_fin += 1
    if pre is not None and head is not None and head > -30 and (head - pre) >= 6 and gap < 0.05:
        flag += " <-- ENTRADA BRUSCA"; cortes_ini += 1
    f=lambda v,w: (f"{v:{w}.1f}" if v is not None else " "*(w-1)+"-")
    print(f"{n[:22]:22} {st:7.2f} {en:7.2f} {f(tail,9)} {f(post,10)} {f(drop,7)} {f(head,9)} {f(pre,8)} {gap:7.2f}{flag}")

print()
print(f"empalmes con la palabra aun sonando (final): {cortes_fin} de {len(rows)}")
print(f"entradas bruscas (inicio):                   {cortes_ini} de {len(rows)}")
