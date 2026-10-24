"""§3: one segment, four stitching variants, two takes each — which context makes the onset dirty?
   a: previous_text + next_text + previous_request_ids   b: no ids   c: next_text only   d: none"""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(Path(__file__).parent))
import gen_audio as G, lesson as L, onset as O

env = G.read_env(G.DEFAULT_ENV); key = env["ELEVENLABS_API_KEY"]
voice = json.loads((HERE / "audio/used-to-soler/english-teacher/manifest.json").read_text())["voice_id"]
out = HERE / "audio/_probe/stitching"; out.mkdir(parents=True, exist_ok=True)
TARGETS = [("make-vs-do", "b18", 0), ("make-vs-do", "b18", 1), ("make-vs-do", "b18", 3),
           ("can-could-pedir", "b05", 3), ("present-perfect-vs-past", "b10", 3)]
chars, rows = 0, []
for lesson_id, beat_id, n in TARGETS:
    lesson = L.load(HERE / f"lessons/{lesson_id}.json")
    beats = lesson["beats"]; i = next(k for k, b in enumerate(beats) if b["id"] == beat_id)
    settings = lesson.get("voice_settings") or {"stability": 0.45, "similarity_boost": 0.8, "style": 0.3, "use_speaker_boost": True}
    speeds = {"en": float(lesson.get("english_speed", 0.92)), "es": 1.0}
    segs = [s for s in L.segments(beats[i]["narration"]) if "text" in s]
    prev_beat = L.spoken_text(beats[i - 1]["narration"]) if i else ""
    ctx = lambda m: (" ".join(s["text"] for s in segs[:m]).strip() or prev_beat, " ".join(s["text"] for s in segs[m + 1:]).strip())
    seg = segs[n]
    for take in (1, 2):
        ids = []
        if n > 0:                                   # (a) needs a real id: say the segment before it first
            p_before, p_after = ctx(n - 1)
            _, _, rid = G.eleven_segment(key, voice, segs[n - 1]["text"], segs[n - 1]["lang"], "eleven_turbo_v2_5",
                                         {**settings, "speed": speeds[segs[n - 1]["lang"]]}, p_before, p_after, [])
            chars += len(segs[n - 1]["text"]); ids = [rid] if rid else []
        before, after = ctx(n)
        variants = {"a": (before, after, ids), "b": (before, after, []), "c": ("", after, []), "d": ("", "", [])}
        for v, (pt, nt, pi) in variants.items():
            audio, _, _ = G.eleven_segment(key, voice, seg["text"], seg["lang"], "eleven_turbo_v2_5",
                                           {**settings, "speed": speeds[seg["lang"]]}, pt, nt, pi)
            chars += len(seg["text"])
            f = out / f"{lesson_id}_{beat_id}_{n:02d}_{seg['lang']}_{v}{take}.mp3"; f.write_bytes(audio)
            x = O.load(f); e = O.env_db(x); s, _ = O.onset(x)
            first = round(float(e[0] - e.max()), 1); frag = O.fragment(e, s, e.max())
            rows.append({"segment": f"{lesson_id} {beat_id}_{n:02d}", "text": seg["text"], "lang": seg["lang"],
                         "switch": n > 0 and segs[n - 1]["lang"] != seg["lang"], "variant": v, "take": take,
                         "first_5ms_db": first, "fragment": frag, "clean": first < -30 and frag is None, "file": f.name})
            print(rows[-1], flush=True)
(out / "variants.json").write_text(json.dumps({"characters": chars, "rows": rows}, ensure_ascii=False, indent=1))
print("characters sent:", chars)
