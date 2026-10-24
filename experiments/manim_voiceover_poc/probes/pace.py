"""STEP 54: four paces for one beat, one multilingual_v2 request per beat as gen_audio does now,
joined into one A/B file (n beeps before variant n, 320 kbps) for the owner's ear.

    1 today       speed 1.0 — the approved audio, reused (no cost)
    2 0.92        speed 0.92 for the whole beat
    3 0.88        speed 0.88 for the whole beat
    4 0.92+room   variant 2's audio + 0.5 s room tone after each sentence, + 0.8 s at the end
                  (the gap between beats), no cost

    python3 probes/pace.py make-vs-do:b18 can-could-pedir:b05 can-could-pedir:b08
"""
import contextlib, io, json, re, subprocess, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import gen_audio as G, lesson as L
from probes import beat_onsets as B, onset as O, variants as V

OUT = HERE / "audio" / "_probe" / "pace"
SENTENCE_GAP, BEAT_GAP = 0.5, 0.8
# variant 1: what the owner approved (the re-rendered lesson, else the variant-4 probe — same request)
TODAY = {"make-vs-do": "audio/make-vs-do/english-teacher/{beat}", "can-could-pedir": "audio/_probe/variants/can-could-pedir_{beat}/4"}


def ask(run, lesson, beat, speed, folder, variant):
    text = L.spoken_text(beat["narration"])
    settings = {**(lesson.get("voice_settings") or {}), "speed": speed}
    log = io.StringIO()
    with contextlib.redirect_stdout(log):                    # gen_audio says so when a model refuses speed
        audio, words, _ = run.ask(variant, text, "es", "eleven_multilingual_v2", settings)
    refused = "refused voice_settings.speed" in log.getvalue()
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.mp3"; raw.write_bytes(audio)
        _, cuts = G.stitch([raw], [text], folder / f"{variant}.mp3")
    words = [{"word": w["word"], "start": max(0.0, w["start"] - cuts[0]), "end": max(0.0, w["end"] - cuts[0])} for w in words]
    (folder / f"{variant}.words.json").write_text(json.dumps(words, ensure_ascii=False, indent=1))
    return words, refused


def room_tone(x, secs, path):
    """`secs` of the beat's own quietest 40 ms, looped — room tone, not digital zero."""
    n = int(0.04 * O.RATE)
    k = min(range(0, len(x) - n, n // 2), key=lambda i: float((x[i:i + n] ** 2).mean()))
    piece = x[k:k + n]
    reps = int(secs * O.RATE) // n + 1
    import numpy as np
    pcm = (np.clip(np.tile(piece, reps)[:int(secs * O.RATE)], -1, 1) * 32767).astype("<i2").tobytes()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(O.RATE), "-ac", "1", "-i", "pipe:0",
                    "-af", "afade=t=in:d=0.01,areverse,afade=t=in:d=0.01,areverse", str(path)], input=pcm, check=True)


def with_pauses(src, words, target):
    """Cut after every sentence-final word, at the quietest point before the next word; insert room tone."""
    x = O.load(src)
    cuts = []
    for w, nxt in zip(words, words[1:]):
        if re.search(r"[.?!]['\"»”]?$", w["word"]) and nxt["start"] > w["end"]:
            a, b = int(w["end"] * O.RATE), int(nxt["start"] * O.RATE)
            e = O._fine(x[a:b])
            cuts.append((a + int(e.argmin()) * O.FINE) / O.RATE if len(e) else (w["end"] + nxt["start"]) / 2)
    with tempfile.TemporaryDirectory() as tmp:
        tone, tail = Path(tmp) / "tone.wav", Path(tmp) / "tail.wav"
        room_tone(x, SENTENCE_GAP, tone); room_tone(x, BEAT_GAP, tail)
        parts, edges = [], [0.0] + cuts + [None]
        for n, (a, b) in enumerate(zip(edges, edges[1:])):
            part = Path(tmp) / f"p{n}.wav"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ss", f"{a:.4f}"]
                           + (["-to", f"{b:.4f}"] if b is not None else []) + ["-ac", "1", "-ar", str(O.RATE), str(part)], check=True)
            parts += [part, tone] if b is not None else [part, tail]
        lst = Path(tmp) / "l.txt"; lst.write_text("".join(f"file '{p}'\n" for p in parts))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-codec:a", "libmp3lame", "-b:a", "128k", str(target)], check=True)
    shifted = [{**w, "start": round(w["start"] + SENTENCE_GAP * sum(c <= w["start"] for c in cuts), 3),
                "end": round(w["end"] + SENTENCE_GAP * sum(c <= w["start"] for c in cuts), 3)} for w in words]
    target.with_suffix(".words.json").write_text(json.dumps(shifted, ensure_ascii=False, indent=1))
    return shifted, len(cuts)


def main():
    run, report, beat_files = V.Run(), {}, []
    for spec in sys.argv[1:]:
        lesson_id, beat_id = spec.split(":")
        lesson = L.load(HERE / f"lessons/{lesson_id}.json")
        beat = next(b for b in lesson["beats"] if b["id"] == beat_id)
        folder = OUT / f"{lesson_id}_{beat_id}"; folder.mkdir(parents=True, exist_ok=True)
        today = HERE / TODAY[lesson_id].format(beat=beat_id)
        (folder / "1.mp3").write_bytes(today.with_suffix(".mp3").read_bytes())
        words = {1: json.loads(Path(str(today) + ".words.json").read_text())}
        refused = {}
        words[2], refused[2] = ask(run, lesson, beat, 0.92, folder, 2)
        words[3], refused[3] = ask(run, lesson, beat, 0.88, folder, 3)
        words[4], sentences = with_pauses(folder / "2.mp3", words[2], folder / "4.mp3")
        rows = {}
        for v in (1, 2, 3, 4):
            dirty = [r for r in B.score(folder / f"{v}.mp3", words[v], beat["narration"]) if r["dirty"]]
            rows[v] = {"duration_s": round(G.probe_duration(folder / f"{v}.mp3"), 2),
                       "dirty": [f"{r['at']}s {r['text'][:18]} ({r['dirty']})" for r in dirty],
                       "speed_refused": refused.get(v, refused.get(2) if v == 4 else False)}
            print(f"{spec} {v} {rows[v]}", flush=True)
        rows["sentence_pauses_inserted"] = sentences
        beat_files.append(V.ab_file(folder, [1, 2, 3, 4]))
        report[spec] = rows
    with tempfile.TemporaryDirectory() as tmp:                 # one file: the three beats, 2 s apart
        gap = Path(tmp) / "gap.mp3"                            # same codec as the beat files, for the concat demuxer
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "2",
                        "-codec:a", "libmp3lame", "-b:a", "320k", str(gap)], check=True)
        lst = Path(tmp) / "l.txt"
        lst.write_text("".join(f"file '{p}'\nfile '{gap}'\n" for p in beat_files))
        ab = OUT / "pace_ab.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-ac", "1", "-codec:a", "libmp3lame", "-b:a", "320k", str(ab)], check=True)
    report["characters_sent"] = sum(run.chars.values())
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print("characters sent:", run.chars, "→", ab)


if __name__ == "__main__":
    main()
