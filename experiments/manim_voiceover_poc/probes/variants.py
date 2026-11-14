"""Six ways to voice one beat, scored by probes.beat_onsets and joined into one A/B file per
beat (n beeps before variant n, 320 kbps) for the owner's ear.

    1 old       the files from before the stitching fix (given with --old DIR, no cost)
    2 now       next_text only at a switch / beat start, onset gate
    3 now+same  as 2, but previous_text = the last text in the same language
    4 v2-one    the whole beat in one request, eleven_multilingual_v2
    5 v3-one    the whole beat in one request, eleven_v3
    6 carrier   as 2, each segment asked as «So, …» / «Bueno, …» and cut at its first real word

    python3 probes/variants.py make-vs-do:b18 can-could-pedir:b05 can-could-pedir:b08 --old DIR
"""
import argparse, json, re, subprocess, sys, tempfile, urllib.error
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import gen_audio as G, lesson as L
from probes import beat_onsets as B

NAMES = {1: "old", 2: "now", 3: "now+same-language context", 4: "one request, multilingual_v2",
         5: "one request, eleven_v3", 6: "carrier word"}
CARRIER = {"en": "So,", "es": "Bueno,"}
OUT = HERE / "audio" / "_probe" / "variants"


class Run:
    def __init__(self):
        env = G.read_env(G.DEFAULT_ENV)
        self.key = env["ELEVENLABS_API_KEY"]
        self.voice = json.loads((HERE / "audio/used-to-soler/english-teacher/manifest.json").read_text())["voice_id"]
        self.chars = {}

    def ask(self, variant, text, lang, model, settings, prev="", nxt="", ids=()):
        self.chars[variant] = self.chars.get(variant, 0) + len(text)
        try:
            return G.eleven_segment(self.key, self.voice, text, lang, model, settings, prev, nxt, list(ids))
        except urllib.error.HTTPError as error:        # eleven_v3 takes fewer settings: retry with the bare minimum
            if model != "eleven_v3" or error.code not in (400, 422):
                raise
            print(f"  note: {model} refused the settings ({error.code}); retrying with stability 0.5 only")
            return G.eleven_segment(self.key, self.voice, text, lang, model, {"stability": 0.5}, "", "", [])


def context(segs, n, policy):
    if policy == "same":
        last = next((x["lang"] for x in reversed(segs[:n]) if "lang" in x), None)
        if last is not None and last != segs[n]["lang"]:      # a switch: previous text in this segment's language
            same = next((x["text"] for x in reversed(segs[:n]) if x.get("lang") == segs[n]["lang"]), "")
            return same, " ".join(x["text"] for x in segs[n + 1:] if "text" in x), []
    return G.stitch_context(segs, n, "", [])


def cut_carrier(mp3: Path, words: list, out: Path) -> list:
    """Drop the carrier word: cut 30 ms before the first real word, 5 ms fade in."""
    real = [w for w in words if re.search(r"\w", w["word"])]
    t = max(real[0]["end"], real[1]["start"] - 0.03)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(mp3), "-af", "afade=t=in:d=0.005",
                    "-codec:a", "libmp3lame", "-b:a", "128k", str(out)], check=True)
    return [{"word": w["word"], "start": max(0.0, w["start"] - t), "end": max(0.0, w["end"] - t)}
            for w in words[words.index(real[1]):]]


def stitched(run, variant, lesson, beat, policy, carrier, folder):
    segs = L.segments(beat["narration"], lesson.get("language", "es"))
    settings = lesson.get("voice_settings") or {"stability": 0.45, "similarity_boost": 0.8, "style": 0.3, "use_speaker_boost": True}
    speeds = {"en": float(lesson.get("english_speed", 0.92)), "es": 1.0}
    files, pieces, log = [], [], []
    with tempfile.TemporaryDirectory() as tmp:
        for n, seg in enumerate(segs):
            path = Path(tmp) / f"s{n}.mp3"
            if "pause" in seg:
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                                "-t", f"{seg['pause']:.2f}", "-codec:a", "libmp3lame", "-b:a", "128k", str(path)], check=True)
                files.append(path); pieces.append({"words": []}); continue
            prev, nxt, ids = context(segs, n, policy)
            text = f"{CARRIER[seg['lang']]} {seg['text']}" if carrier else seg["text"]
            takes = []
            for attempt in range(1 + G.ONSET_RETRIES):
                audio, words, _ = run.ask(variant, text, seg["lang"], "eleven_turbo_v2_5",
                                          {**settings, "speed": speeds[seg["lang"]]}, prev, nxt, ids)
                take = Path(tmp) / f"s{n}_t{attempt}.mp3"
                take.write_bytes(audio)
                if carrier:
                    cut = Path(tmp) / f"s{n}_t{attempt}_cut.mp3"
                    words = cut_carrier(take, words, cut)
                    take = cut
                takes.append({"path": take, "words": words, "onset": G.onset_report(take)})
                if takes[-1]["onset"]["clean"]:
                    break
            best = G.cleanest(takes)
            log.append({"segment": n, "text": seg["text"], "takes": len(takes), "clean": best["onset"]["clean"]})
            files.append(best["path"]); pieces.append({"words": best["words"]})
        target = folder / f"{variant}.mp3"
        offsets, cuts = G.stitch(files, [s.get("text", ".") for s in segs], target)
        for piece, off, c in zip(pieces, offsets, cuts):
            piece["offset"], piece["lead_cut"] = off, c
    words = G.shift_words(pieces)
    (folder / f"{variant}.words.json").write_text(json.dumps(words, ensure_ascii=False, indent=1))
    return target, words, log


def one_request(run, variant, lesson, beat, model, folder):
    text = L.spoken_text(beat["narration"])
    settings = lesson.get("voice_settings") or {"stability": 0.45, "similarity_boost": 0.8, "style": 0.3, "use_speaker_boost": True}
    if model == "eleven_v3":
        settings = {**settings, "stability": 0.5}            # v3 takes 0.0 / 0.5 / 1.0
    audio, words, _ = run.ask(variant, text, "es", model, settings)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.mp3"; raw.write_bytes(audio)
        target = folder / f"{variant}.mp3"
        _, cuts = G.stitch([raw], [text], target)
    words = [{"word": w["word"], "start": max(0.0, w["start"] - cuts[0]), "end": max(0.0, w["end"] - cuts[0])} for w in words]
    (folder / f"{variant}.words.json").write_text(json.dumps(words, ensure_ascii=False, indent=1))
    return target, words, []


def ab_file(folder: Path, variants: list) -> Path:
    def tone(path, secs, freq=None):
        src = f"sine=frequency={freq}:sample_rate=44100" if freq else "anullsrc=r=44100:cl=mono"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", src, "-t", str(secs),
                        "-af", "volume=0.25" if freq else "anull", "-ac", "1", "-ar", "44100", str(path)], check=True)
    with tempfile.TemporaryDirectory() as tmp:
        beep, gap, rest = Path(tmp) / "b.wav", Path(tmp) / "g.wav", Path(tmp) / "r.wav"
        tone(beep, 0.12, 880); tone(gap, 0.12); tone(rest, 1.2)
        parts = []
        for v in variants:
            wav = Path(tmp) / f"{v}.wav"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(folder / f"{v}.mp3"), "-ac", "1", "-ar", "44100",
                            str(wav)], check=True)
            parts += [beep, gap] * v + [rest, wav, rest]
        lst = Path(tmp) / "l.txt"; lst.write_text("".join(f"file '{p}'\n" for p in parts))
        out = folder / f"{folder.name}_ab.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-codec:a", "libmp3lame", "-b:a", "320k", str(out)], check=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("beats", nargs="+", help="lesson:beat")
    ap.add_argument("--old", type=Path, required=True, help="folder with <lesson>_<beat>.mp3 / .words.json from before the fix")
    args = ap.parse_args()
    run, report = Run(), {}
    for spec in args.beats:
        lesson_id, beat_id = spec.split(":")
        lesson = L.load(HERE / f"lessons/{lesson_id}.json")
        beat = next(b for b in lesson["beats"] if b["id"] == beat_id)
        folder = OUT / f"{lesson_id}_{beat_id}"; folder.mkdir(parents=True, exist_ok=True)
        built = {}
        old = folder / "1.mp3"
        old.write_bytes((args.old / f"{lesson_id}_{beat_id}.mp3").read_bytes())
        built[1] = (old, json.loads((args.old / f"{lesson_id}_{beat_id}.words.json").read_text()), [])
        built[2] = stitched(run, 2, lesson, beat, "now", False, folder)
        built[3] = stitched(run, 3, lesson, beat, "same", False, folder)
        built[4] = one_request(run, 4, lesson, beat, "eleven_multilingual_v2", folder)
        built[5] = one_request(run, 5, lesson, beat, "eleven_v3", folder)
        built[6] = stitched(run, 6, lesson, beat, "now", True, folder)
        rows = {}
        for v, (mp3, words, log) in built.items():
            scored = B.score(mp3, words, beat["narration"])
            rows[v] = {"variant": NAMES[v], "segment_starts": len(scored),
                       "dirty": [f"{r['at']}s {r['text'][:18]} ({r['dirty']})" for r in scored if r["dirty"]],
                       "retried": sum(1 for x in log if x["takes"] > 1)}
            print(f"{spec} {v} {NAMES[v]:30} dirty {len(rows[v]['dirty'])}/{len(scored)}  {rows[v]['dirty']}", flush=True)
        report[spec] = {"ab_file": str(ab_file(folder, list(built))), "variants": rows}
    report["characters_sent"] = run.chars
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print("characters sent per variant:", run.chars, "total", sum(run.chars.values()))


if __name__ == "__main__":
    main()
