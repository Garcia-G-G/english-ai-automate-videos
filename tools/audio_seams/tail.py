import subprocess,sys,math
import numpy as np
SR=16000
def load(p):
    r=subprocess.run(["ffmpeg","-v","error","-i",p,"-f","s16le","-ac","1","-ar",str(SR),"-"],capture_output=True)
    return np.frombuffer(r.stdout,dtype="<i2").astype(np.float32)/32768.0
def db(x):
    if x.size==0: return -120.0
    r=float(np.sqrt(np.mean(x.astype(np.float64)**2)))
    return -120.0 if r<=1e-6 else 20*math.log10(r)
a=load(sys.argv[1])
print(f"{'':26} " + " ".join(f"{(k-10)*10:+5d}" for k in range(20)))
for spec in sys.argv[2:]:
    nm,t=spec.split("@"); t=float(t)
    vals=[db(a[int((t-0.100+k*0.010)*SR):int((t-0.100+(k+1)*0.010)*SR)]) for k in range(20)]
    print(f"{nm:26} " + " ".join(f"{v:5.0f}" for v in vals))
