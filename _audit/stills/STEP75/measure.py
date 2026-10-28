"""Baseline numbers for one final: bitrate, keyframes, B-frames, colour tags, loudness, duration."""
import json, re, statistics, subprocess, sys

def probe(path):
    s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=bit_rate,has_b_frames,color_space,color_primaries,color_transfer,color_range,codec_name,profile,pix_fmt"
        ":format=duration,bit_rate", "-of", "json", path], capture_output=True, text=True, check=True).stdout)
    kf = subprocess.run(["ffprobe", "-v", "error", "-skip_frame", "nokey", "-select_streams", "v:0",
        "-show_entries", "frame=pts_time", "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout
    times = sorted(float(t.strip(",")) for t in kf.split() if t.strip(","))
    gaps = [b - a for a, b in zip(times, times[1:])]
    eb = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-map", "0:a", "-af",
        "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    summary = eb[eb.rfind("Summary:"):]
    num = lambda k: float(re.search(k + r":\s+(-?[\d.]+)", summary).group(1))
    v = s["streams"][0]
    return {"codec": f"{v['codec_name']} {v.get('profile')} {v.get('pix_fmt')}",
            "video kbps": round(int(v.get("bit_rate") or 0) / 1000),
            "keyframes": len(times), "median kf gap s": round(statistics.median(gaps), 2) if gaps else None,
            "has_b_frames": v.get("has_b_frames"),
            "colour": "/".join(str(v.get(k, "-")) for k in ("color_space", "color_primaries", "color_transfer", "color_range")),
            "LUFS I": num("I"), "true peak dBTP": num("Peak"), "LRA LU": num("LRA"),
            "duration s": round(float(s["format"]["duration"]), 2)}

if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(json.dumps({"file": p, **probe(p)}, ensure_ascii=False))
