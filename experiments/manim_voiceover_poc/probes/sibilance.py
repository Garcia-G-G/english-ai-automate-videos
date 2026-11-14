"""§5: sibilance A/B — A current, B style 0.1, C speaker_boost off (new generations, the real
pipeline); D = A + deesser, E = A stitched at 192 kbps (offline). One labelled file + a metric."""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import gen_audio as G, lesson as L

NARRATION = "Las cosas sencillas se aprenden despacio. [[She sells sea shells, so she says yes.]]"
BASE = {"stability": 0.45, "similarity_boost": 0.8, "style": 0.3, "use_speaker_boost": True}   # the lessons' settings
out = HERE / "audio/_probe/sibilance"; out.mkdir(parents=True, exist_ok=True)
key = G.read_env(G.DEFAULT_ENV)["ELEVENLABS_API_KEY"]
voice = json.loads((HERE / "audio/used-to-soler/english-teacher/manifest.json").read_text())["voice_id"]
speeds = {"en": 0.92, "es": 1.0}

def generate(tag, settings, bitrate="128k"):
    segs = L.segments(NARRATION)
    raws = []
    with tempfile.TemporaryDirectory() as tmp:
        for n, seg in enumerate(segs):
            before, after, ids = G.stitch_context(segs, n, "", [])
            audio, _, _ = G.eleven_segment(key, voice, seg["text"], seg["lang"], "eleven_turbo_v2_5",
                                           {**settings, "speed": speeds[seg["lang"]]}, before, after, ids)
            raw = out / f"{tag}_raw{n}.mp3"; raw.write_bytes(audio); raws.append(raw)
    G.stitch(raws, [s["text"] for s in segs], out / f"{tag}.mp3")
    return raws

def restitch(raws, target, bitrate):
    # gen_audio.stitch encodes at 128k; E re-encodes the same stitched PCM at 192k
    with tempfile.TemporaryDirectory() as tmp:
        G.stitch(raws, [s["text"] for s in L.segments(NARRATION)], Path(tmp) / "x.mp3")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out / "A.wav"), "-b:a", bitrate, str(target)], check=True)

def to_wav(src, dst):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "44100", str(dst)], check=True)

def sibilance_p95(path):
    pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", "44100", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(pcm, "<i2").astype(float) / 32768
    n, hop = 1024, 441
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n)
    spec = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    f = np.fft.rfftfreq(n, 1 / 44100)
    total, band = spec.sum(1), spec[:, (f >= 5000) & (f <= 10000)].sum(1)
    level = 10 * np.log10(total + 1e-12)
    voiced = level > level.max() - 30
    share = 10 * np.log10(band[voiced] / total[voiced] + 1e-12)
    return round(float(np.percentile(share, 95)), 1)

if __name__ == "__main__":
    if not (out / "A.mp3").exists():
        rawA = generate("A", BASE)
        generate("B", {**BASE, "style": 0.1})
        generate("C", {**BASE, "use_speaker_boost": False})
    # D: A + de-esser (the brief's start values); E: the A beat at 192 kbps instead of 128
    to_wav(out / "A.mp3", out / "A.wav")
    raws = sorted(out.glob("A_raw*.mp3"))
    with tempfile.TemporaryDirectory() as tmp:            # rebuild A's stitched PCM losslessly, then encode at 192k
        wavs = []
        for i, r in enumerate(raws):
            w = Path(tmp) / f"s{i}.wav"; G.prepare_segment(r, w); wavs.append(w)
        G.level_match(wavs)
        gap = Path(tmp) / "gap.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                        "-t", f"{G.gap_after(L.segments(NARRATION)[0]['text']):.3f}", str(gap)], check=True)
        lst = Path(tmp) / "l.txt"
        lst.write_text("".join(f"file '{p}'\n" for p in [wavs[0], gap, *wavs[1:]]))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-codec:a", "libmp3lame", "-b:a", "192k", str(out / "E.mp3")], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out / "A.mp3"), "-af", "deesser=i=0.4:m=0.5:f=0.5:s=o",
                    "-b:a", "128k", str(out / "D.mp3")], check=True)
    # the A/B file: n beeps before variant n, everything at 320 kbps so the file itself does not smear
    parts = []
    with tempfile.TemporaryDirectory() as tmp:
        def tone(path, secs, freq=None):
            src = f"sine=frequency={freq}:sample_rate=44100" if freq else "anullsrc=r=44100:cl=mono"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", src, "-t", str(secs),
                            "-af", "volume=0.25" if freq else "anull", "-ac", "1", "-ar", "44100", str(path)], check=True)
        beep, gap, rest = Path(tmp) / "beep.wav", Path(tmp) / "gap.wav", Path(tmp) / "rest.wav"
        tone(beep, 0.12, 880); tone(gap, 0.12); tone(rest, 1.2)
        for i, v in enumerate("ABCDE"):
            parts += [beep, gap] * (i + 1) + [rest]
            w = Path(tmp) / f"{v}.wav"; to_wav(out / f"{v}.mp3", w); parts += [w, rest]
        lst = Path(tmp) / "l.txt"; lst.write_text("".join(f"file '{p}'\n" for p in parts))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-codec:a", "libmp3lame", "-b:a", "320k", str(out / "sibilance_ab.mp3")], check=True)
    labels = {"A": "current (style 0.3, speaker boost on)", "B": "style 0.1", "C": "speaker boost off",
              "D": "A + ffmpeg deesser i=0.4 m=0.5 f=0.5", "E": "A encoded at 192 kbps"}
    rows = {v: sibilance_p95(out / f"{v}.mp3") for v in "ABCDE"}
    (out / "sibilance_metric.json").write_text(json.dumps({"metric": "5–10 kHz share of energy on voiced frames, p95, dB",
                                                           "variants": {v: {"what": labels[v], "p95_db": rows[v]} for v in rows}},
                                                          ensure_ascii=False, indent=1))
    for v in "ABCDE":
        print(v, labels[v], rows[v])
