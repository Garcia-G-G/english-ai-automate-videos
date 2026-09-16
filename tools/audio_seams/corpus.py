import json,glob,subprocess,math,os
import numpy as np
SR=16000
def load(p):
    r=subprocess.run(["ffmpeg","-v","error","-i",p,"-f","s16le","-ac","1","-ar",str(SR),"-"],capture_output=True)
    return np.frombuffer(r.stdout,dtype="<i2").astype(np.float32)/32768.0
def db(x):
    if x.size==0: return None
    r=float(np.sqrt(np.mean(x.astype(np.float64)**2)))
    return -120.0 if r<=1e-6 else 20*math.log10(r)

rows=[]
files=sorted(glob.glob("output/audio/*/*.json"))
for jf in files:
    mp3=jf[:-5]+".mp3"
    if not os.path.exists(mp3): continue
    try: j=json.load(open(jf))
    except Exception: continue
    segs=j.get("segments")
    if not isinstance(segs,list) or not segs or not isinstance(segs[0],dict): continue
    a=load(mp3)
    if a.size==0: continue
    real=a.size/SR; decl=j.get("duration")
    vt=jf.split("/")[2]
    drift = (real-decl) if isinstance(decl,(int,float)) else float('nan')
    hard=0; tot=0
    for s in segs:
        en=s.get("end")
        if en is None or en<=0.05: continue
        if s.get("id","").startswith("countdown"): continue
        tail=db(a[int((en-0.060)*SR):int(en*SR)])
        post=db(a[int(en*SR):int((en+0.100)*SR)])
        if tail is None or post is None: continue
        tot+=1
        if tail>-30 and (tail-post)>=6: hard+=1
    rows.append((vt,os.path.basename(mp3)[:34],decl,real,drift,hard,tot))

print(f"{'tipo':14} {'archivo':34} {'declarado':>9} {'real':>7} {'deriva':>7} {'cortes':>8}")
print("-"*90)
agg={}
for vt,nm,decl,real,drift,hard,tot in rows:
    print(f"{vt:14} {nm:34} {decl if decl is None else f'{decl:9.2f}'} {real:7.2f} {drift:7.3f} {hard:4d}/{tot:<4d}")
    d=agg.setdefault(vt,[0,0,0]); d[0]+=hard; d[1]+=tot; d[2]+=1
print()
print("RESUMEN por tipo: segmentos cortados en seco / total")
for vt,(h,t,n) in sorted(agg.items()):
    print(f"  {vt:14} {h:4d}/{t:<5d} ({100*h/t if t else 0:5.1f}%)  en {n} videos")
