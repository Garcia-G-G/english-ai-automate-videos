import subprocess, sys, math
import numpy as np
SR=16000
p=subprocess.run(["ffmpeg","-v","error","-i",sys.argv[1],"-f","s16le","-ac","1","-ar",str(SR),"-"],capture_output=True)
a=np.frombuffer(p.stdout,dtype="<i2").astype(np.float32)/32768.0
def db(x):
    if x.size==0: return -120.0
    r=float(np.sqrt(np.mean(x.astype(np.float64)**2)))
    return -120.0 if r<=1e-6 else 20*math.log10(r)
def prof(t0,label,n=12,step=0.010):
    vals=[]
    for k in range(n):
        s=t0+k*step
        vals.append(db(a[int(s*SR):int((s+step)*SR)]))
    print(f"{label:22} " + " ".join(f"{v:6.0f}" for v in vals))
# zeros exactos?
def zeros(t0,t1):
    seg=np.frombuffer(p.stdout,dtype="<i2")[int(t0*SR):int(t1*SR)]
    return int(np.count_nonzero(seg)), seg.size
print("== huecos: muestras NO CERO / total ==")
for (t0,t1,nm) in [(2.32,2.82,"tras question"),(7.60,8.00,"tras option_a"),(19.0,20.7,"tras think"),(20.79,25.29,"cuenta atras"),(30.53,31.43,"tras answer")]:
    nz,tot=zeros(t0,t1); print(f"{nm:18} {nz:8d} / {tot:8d}   {'DIGITAL PURO' if nz==0 else 'tiene senal'}")
print()
print("== perfil en pasos de 10 ms (dB) ==")
print(f"{'':22} " + " ".join(f"{k*10:6d}" for k in range(12)))
for (t,nm) in [(0.00,"question INICIO"),(4.71,"option_a INICIO"),(8.00,"option_b INICIO"),(2.82,"transition INICIO"),(33.19,"explanation INICIO"),(26.29,"answer INICIO")]:
    prof(t,nm)
print()
print("== perfil de CIERRE, ultimos 120 ms ==")
for (t,nm) in [(2.32,"question FIN"),(7.60,"option_a FIN"),(10.74,"option_b FIN"),(37.75,"explanation FIN")]:
    prof(t-0.120,nm)
