"""STEP 55 robustness: eleven_v4 (language_code es, speed 0.92), one request per beat,
three takes of each beat — scored by the English-words audit, joined into one A/B file
(n beeps before take n) for the owner's ear. Also checks that v4 takes speed (no refusal)
and returns an alignment that covers every spoken token (what the scene syncs on).

    python3 probes/v4_takes.py make-vs-do:b18 can-could-pedir:b05 ...
"""
import contextlib, io, json, subprocess, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import gen_audio as G, lesson as L
from probes import english_fix as F, english_words_audit as E, variants as V

OUT = HERE / "audio" / "_probe" / "v4_takes"
TAKES = 3


def main():
    run, report, beat_files = V.Run(), {}, []
    with tempfile.TemporaryDirectory() as tmp:
        for spec in sys.argv[1:]:
            lesson_id, beat_id = spec.split(":")
            lesson = L.load(HERE / f"lessons/{lesson_id}.json")
            narration = next(b for b in lesson["beats"] if b["id"] == beat_id)["narration"]
            folder = OUT / f"{lesson_id}_{beat_id}"; folder.mkdir(parents=True, exist_ok=True)
            rows = {}
            for take in range(1, TAKES + 1):
                log = io.StringIO()
                with contextlib.redirect_stdout(log):          # gen_audio says so when a model refuses speed
                    words = F.ask(run, lesson, narration, "eleven_v4", {"language_code": "es"}, folder, take)
                audit = E.audit_beat(folder / f"{take}.mp3", words, narration, Path(tmp))
                rows[take] = {"speed_refused": "refused voice_settings.speed" in log.getvalue(),
                              "timed_words": len(words), "tokens": len(L.tokens(narration)),
                              "duration_s": round(G.probe_duration(folder / f"{take}.mp3"), 2),
                              "fails": [f"{r['time']}s {r['expected']!r} heard {r['heard_en']!r}"
                                        for r in audit if r["verdict"] == "FAIL"], "spans": len(audit)}
                print(f"{spec} take {take} FAIL {len(rows[take]['fails'])}/{len(audit)} {rows[take]['fails']} "
                      f"speed_refused={rows[take]['speed_refused']} words {len(words)}/{rows[take]['tokens']}", flush=True)
            report[spec] = rows
            beat_files.append(V.ab_file(folder, list(range(1, TAKES + 1))))
        gap = Path(tmp) / "gap.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "2",
                        "-codec:a", "libmp3lame", "-b:a", "320k", str(gap)], check=True)
        lst = Path(tmp) / "l.txt"
        lst.write_text("".join(f"file '{p}'\nfile '{gap}'\n" for p in beat_files))
        ab = OUT / "v4_takes_ab.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-ac", "1", "-codec:a", "libmp3lame", "-b:a", "320k", str(ab)], check=True)
    report["totals"] = {t: {"fails": sum(len(report[s][t]["fails"]) for s in sys.argv[1:]),
                            "spans": sum(report[s][t]["spans"] for s in sys.argv[1:])} for t in range(1, TAKES + 1)}
    report["characters_sent"] = sum(run.chars.values())
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print("totals:", report["totals"], "\ncharacters sent:", report["characters_sent"], "→", ab)


if __name__ == "__main__":
    main()
