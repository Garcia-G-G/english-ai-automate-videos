"""STEP 55 step 1: is every English span ([[ ]]) of a beat heard as English? Local, free.

Each span is cut from the beat audio by its word timings, padded with silence and
transcribed by the local Whisper (src/asr_timings.py) twice: language="en" and "es".
A span FAILS when Whisper-en does not hear the expected words in a row (case,
punctuation and contractions do not count; a neighbour word bleeding into the cut does
not either). Whisper-es runs on the FAILs only: hearing something else too («maque» for
«make») is the strongest signal, `es_too`. Whisper `small` (WHISPER_LOCAL_MODEL): `base`
heard «Door» for a clean «Do» and failed a third of make-vs-do.

    python3 probes/english_words_audit.py [lesson ...]      # default: the five approved lessons

Writes audio/_probe/english_words/report.json and fails.mp3 (3 s around each FAIL, a beep
between clips, in the order of the report's table).
"""
import json, re, subprocess, sys, tempfile, unicodedata
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent.parent / "src"))
import os
os.environ.setdefault("WHISPER_LOCAL_MODEL", "small")
import lesson as L
import asr_timings as A

OUT = HERE / "audio" / "_probe" / "english_words"
APPROVED = ["hacer-preguntas", "make-vs-do", "used-to-soler", "present-perfect-vs-past", "preposiciones-in-on-at"]
VOICE = "english-teacher"
EDGE, PAD = 0.02, 0.4          # seconds of the beat kept around a span / silence added for Whisper
CLIP = 3.0
CONTRACTIONS = [(r"n't\b", " not"), (r"'m\b", " am"), (r"'re\b", " are"), (r"'ve\b", " have"), (r"'ll\b", " will"),
                (r"'d\b", " would"), (r"\bcan not\b", "cannot")]


SAME = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven",
        "8": "eight", "9": "nine", "10": "ten", "for": "four", "to": "two", "too": "two"}   # Whisper writes 4 for «for»


def normal(text: str) -> list:
    t = unicodedata.normalize("NFKD", text.lower().replace("’", "'"))
    t = "".join(c for c in t if not unicodedata.combining(c))        # café = cafe
    for pattern, repl in CONTRACTIONS:
        t = re.sub(pattern, repl, t)
    return [SAME.get(w, w) for w in re.sub(r"[^\w ]+", " ", t.replace("'", "")).split()]


def spans(narration: str, words: list) -> list:
    """[(expected text, start, end)] — words.json has one entry per spoken token, in order."""
    toks = L.tokens(narration)
    if len(toks) != len(words):
        raise ValueError(f"{len(words)} timed words for {len(toks)} tokens")
    out, run = [], []
    for tok, w in zip(toks + [{"en": False}], words + [None]):
        if tok["en"]:
            run.append((tok["text"], w))
        elif run:
            out.append((" ".join(t for t, _ in run), run[0][1]["start"], run[-1][1]["end"]))
            run = []
    return out


def cut(src: Path, start: float, end: float, target: Path, pad: float = 0.0):
    af = f"adelay={int(pad * 1000)},apad=pad_dur={pad}" if pad else "anull"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0.0, start):.3f}", "-to", f"{end:.3f}", "-i", str(src),
                    "-af", af, "-ac", "1", "-ar", "44100", str(target)], check=True)


def hear(wav: Path, language: str) -> str:
    model = A._local_model()                      # local only: never the paid API
    if model is None:
        raise RuntimeError("local whisper is not available")
    result = model.transcribe(str(wav), language=language, fp16=False, temperature=0.0,
                              condition_on_previous_text=False, verbose=None)
    return result["text"].strip()


def heard(expected: str, text) -> bool:
    """The expected words in a row; a span of 5+ words may lose one («favour»/«favor», «He»/«Hey»):
    the owner hears short words go Spanish, not long sentences."""
    e, h = normal(expected), normal(text or "")
    if any(h[i:i + len(e)] == e for i in range(len(h) - len(e) + 1)):
        return True
    if len(e) < 5:
        return False
    lcs = [0] * (len(h) + 1)                      # longest common subsequence, one row
    for a in e:
        prev = 0
        for j, b in enumerate(h, 1):
            prev, lcs[j] = lcs[j], prev + 1 if a == b else max(lcs[j], lcs[j - 1])
    return lcs[-1] >= len(e) - 1


def audit_beat(mp3: Path, words: list, narration: str, tmp: Path) -> list:
    rows = []
    for expected, start, end in spans(narration, words):
        wav = tmp / "span.wav"
        cut(mp3, start - EDGE, end + EDGE, wav, PAD)
        en = hear(wav, "en")
        ok = heard(expected, en)
        es = None if ok else hear(wav, "es")
        rows.append({"time": round(start, 2), "end": round(end, 2), "expected": expected, "heard_en": en, "heard_es": es,
                     "verdict": "ok" if ok else "FAIL", "es_too": not ok and not heard(expected, es)})
    return rows


def lesson_report(folder: Path, lesson: dict, beat_ids) -> list:
    """After a lesson's audio: audit `beat_ids` (and any beat not audited for its current text),
    keep the rest from folder/english_audit.json, rewrite it, return [(beat, row)] for every FAIL.
    A report for the owner's ear — not a retry — until he has calibrated it (STEP 55 step 3)."""
    path = folder / "english_audit.json"
    saved = json.loads(path.read_text()) if path.exists() else {}
    narrations = {b["id"]: b["narration"] for b in lesson["beats"]}
    audit = {}
    with tempfile.TemporaryDirectory() as tmp:
        for b in json.loads((folder / "manifest.json").read_text())["beats"]:
            old = saved.get(b["id"])
            if b["id"] not in beat_ids and old and old["text"] == b["text"]:
                audit[b["id"]] = old
                continue
            words = json.loads((folder / b["words"]).read_text())
            audit[b["id"]] = {"text": b["text"], "rows": audit_beat(folder / b["mp3"], words, narrations[b["id"]], Path(tmp))}
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=1))
    return [(beat, r) for beat, a in audit.items() for r in a["rows"] if r["verdict"] == "FAIL"]


def beep_file(clips: list, target: Path):
    with tempfile.TemporaryDirectory() as tmp:
        beep, gap = Path(tmp) / "b.wav", Path(tmp) / "g.wav"
        for path, src in ((beep, "sine=frequency=880:sample_rate=44100"), (gap, "anullsrc=r=44100:cl=mono")):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", src, "-t", "0.15" if path == beep else "0.6",
                            "-af", "volume=0.25", "-ac", "1", "-ar", "44100", str(path)], check=True)
        parts = []
        for n, (mp3, start, end) in enumerate(clips):
            wav = Path(tmp) / f"c{n}.wav"
            mid = (start + end) / 2
            cut(mp3, max(0.0, mid - CLIP / 2), mid + CLIP / 2, wav)
            parts += [gap, beep, gap, wav]
        lst = Path(tmp) / "l.txt"; lst.write_text("".join(f"file '{p}'\n" for p in parts + [gap]))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-codec:a", "libmp3lame", "-b:a", "320k", str(target)], check=True)


def main():
    lessons = sys.argv[1:] or APPROVED
    OUT.mkdir(parents=True, exist_ok=True)
    report, fails = {"lessons": {}}, []
    with tempfile.TemporaryDirectory() as tmp:
        for lesson_id in lessons:
            beats = {b["id"]: b for b in L.load(HERE / f"lessons/{lesson_id}.json")["beats"]}
            folder = HERE / "audio" / lesson_id / VOICE
            cache = OUT / f"{lesson_id}.json"             # one lesson's transcripts: lessons can run in parallel
            if cache.exists() and cache.stat().st_mtime > (folder / "manifest.json").stat().st_mtime:
                rows = json.loads(cache.read_text())
                for r in rows:                            # the verdict is re-judged; the hearing is not redone
                    r["verdict"] = "ok" if heard(r["expected"], r["heard_en"]) else "FAIL"
                    r["es_too"] = r["verdict"] == "FAIL" and not heard(r["expected"], r["heard_es"])
                fails += [{"lesson": lesson_id, **r} for r in rows if r["verdict"] == "FAIL"]
                report["lessons"][lesson_id] = {"spans": len(rows), "fails": sum(r["verdict"] == "FAIL" for r in rows),
                                                "rows": rows}
                print(f"{lesson_id}: {report['lessons'][lesson_id]['fails']}/{len(rows)} FAIL (cached)", flush=True)
                continue
            rows = []
            for b in json.loads((folder / "manifest.json").read_text())["beats"]:
                mp3 = folder / b["mp3"]
                words = json.loads((folder / b["words"]).read_text())
                for r in audit_beat(mp3, words, beats[b["id"]]["narration"], Path(tmp)):
                    rows.append({"beat": b["id"], **r})
                    if r["verdict"] == "FAIL":
                        fails.append({"lesson": lesson_id, "beat": b["id"], **r})
                        print(f"FAIL {lesson_id} {b['id']} {r['time']:>6}s  {r['expected']!r:28} en {r['heard_en']!r:28} "
                              f"es {r['heard_es']!r}{'  es_too' if r['es_too'] else ''}", flush=True)
            cache.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
            report["lessons"][lesson_id] = {"spans": len(rows), "fails": sum(r["verdict"] == "FAIL" for r in rows), "rows": rows}
            print(f"{lesson_id}: {report['lessons'][lesson_id]['fails']}/{len(rows)} FAIL", flush=True)
    report["fails"] = fails
    report["whisper_model"] = A.LOCAL_MODEL
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    if fails:
        beep_file([(HERE / "audio" / f["lesson"] / VOICE / f"{f['beat']}.mp3", f["time"], f["end"]) for f in fails],
                  OUT / "fails.mp3")
    print("\n| # | lesson | beat | time | expected | heard-en | heard-es | verdict |\n|---|---|---|---|---|---|---|---|")
    for n, f in enumerate(fails, 1):
        print(f"| {n} | {f['lesson']} | {f['beat']} | {f['time']} | {f['expected']} | {f['heard_en']} | {f['heard_es']} | "
              f"FAIL{' (es too)' if f['es_too'] else ''} |")


if __name__ == "__main__":
    main()
