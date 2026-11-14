"""STEP 55 step 2: four ways to keep English words English inside a one-request beat,
joined into one A/B file (n beeps before variant n, 320 kbps) for the owner's ear.

    1 today       the approved lesson audio, reused (no cost; speed 1.0, the others 0.92)
    2 quoted      same request, every [[ ]] span in double quotes after a comma pause
    3 dictionary  same request + a pronunciation dictionary of alias rules (English respellings)
    4 v4          eleven_v4, one request, language_code "es"

Each is scored by the step-1 audit (FAIL count) and the onset detector (must stay clean).

    python3 probes/english_fix.py make-vs-do:b14 ... --onset make-vs-do:b18 can-could-pedir:b05 can-could-pedir:b08
"""
import argparse, json, re, subprocess, sys, tempfile, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import gen_audio as G, lesson as L
from probes import beat_onsets as B, english_words_audit as E, variants as V

OUT = HERE / "audio" / "_probe" / "english_fix"
SPEED = L.DEFAULT_SPEED
TODAY = {"can-could-pedir": "audio/_probe/variants/can-could-pedir_{beat}/4"}    # approved shape, not a lesson render
DEFAULT_TODAY = "audio/{lesson}/english-teacher/{beat}"
# English respellings for the words the audit failed on; case-insensitive, whole words only
ALIASES = {"do": "doo", "does": "duz", "did": "didd", "make": "mayk", "made": "mayd", "be": "bee",
           "in": "inn", "on": "onn", "at": "att", "since": "sinss", "for": "forr", "use": "yooz", "used": "yoozd"}


def quoted(narration: str) -> str:
    """«entre [[make]] y [[do]]» → «entre, [["make"]] y, [["do"]]»: a comma pause unless punctuation is already there."""
    def wrap(m):
        before = narration[:m.start()].rstrip()
        comma = "," if before and before[-1] not in ".,;:!?¿¡" else ""
        return f"{comma} [[\"{m.group(1)}\"]]"
    return re.sub(r"\s*\[\[(.+?)\]\]", wrap, narration).strip()


def dictionary(key: str) -> dict:
    rules = [{"type": "alias", "string_to_replace": w, "alias": a, "case_sensitive": False, "word_boundaries": True}
             for w, a in ALIASES.items()]
    request = urllib.request.Request("https://api.elevenlabs.io/v1/pronunciation-dictionaries/add-from-rules",
                                     data=json.dumps({"name": "step55-english-words", "rules": rules}).encode(),
                                     method="POST", headers={"xi-api-key": key, "Content-Type": "application/json"})
    made = json.load(urllib.request.urlopen(request, timeout=60))
    return {"pronunciation_dictionary_id": made["id"], "version_id": made["version_id"]}


def ask(run, lesson, narration, model, extra, folder, variant):
    text = L.spoken_text(narration)
    settings = {**(lesson.get("voice_settings") or {"stability": 0.45, "similarity_boost": 0.8, "style": 0.3,
                                                      "use_speaker_boost": True}), "speed": SPEED}
    run.chars[variant] = run.chars.get(variant, 0) + len(text)
    audio, words, _ = G.eleven_segment(run.key, run.voice, text, "es", model, settings, on_body=lambda b: b.update(extra))
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.mp3"; raw.write_bytes(audio)
        _, cuts = G.stitch([raw], [text], folder / f"{variant}.mp3")
    words = [{"word": w["word"], "start": max(0.0, w["start"] - cuts[0]), "end": max(0.0, w["end"] - cuts[0])} for w in words]
    (folder / f"{variant}.words.json").write_text(json.dumps(words, ensure_ascii=False, indent=1))
    return words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("beats", nargs="+", help="lesson:beat with FAILs")
    ap.add_argument("--onset", nargs="*", default=[], help="lesson:beat that must stay clean for the onset detector")
    args = ap.parse_args()
    run, report, beat_files = V.Run(), {}, []
    locator = dictionary(run.key)
    with tempfile.TemporaryDirectory() as tmp:
        for spec in args.beats + args.onset:
            lesson_id, beat_id = spec.split(":")
            lesson = L.load(HERE / f"lessons/{lesson_id}.json")
            narration = next(b for b in lesson["beats"] if b["id"] == beat_id)["narration"]
            folder = OUT / f"{lesson_id}_{beat_id}"; folder.mkdir(parents=True, exist_ok=True)
            today = HERE / TODAY.get(lesson_id, DEFAULT_TODAY).format(lesson=lesson_id, beat=beat_id)
            (folder / "1.mp3").write_bytes(today.with_suffix(".mp3").read_bytes())
            words = {1: json.loads(Path(str(today) + ".words.json").read_text())}
            narrations = {1: narration, 2: quoted(narration), 3: narration, 4: narration}
            words[2] = ask(run, lesson, narrations[2], G.ONE_REQUEST_MODEL, {}, folder, 2)
            words[3] = ask(run, lesson, narration, G.ONE_REQUEST_MODEL, {"pronunciation_dictionary_locators": [locator]}, folder, 3)
            words[4] = ask(run, lesson, narration, "eleven_v4", {"language_code": "es"}, folder, 4)
            rows = {}
            for v in (1, 2, 3, 4):
                mp3 = folder / f"{v}.mp3"
                audit = E.audit_beat(mp3, words[v], narrations[v], Path(tmp))
                dirty = [r for r in B.score(mp3, words[v], narrations[v]) if r["dirty"]]
                rows[v] = {"fails": [f"{r['time']}s {r['expected']!r} heard {r['heard_en']!r}" for r in audit if r["verdict"] == "FAIL"],
                           "spans": len(audit), "onset_dirty": [f"{r['at']}s {r['text'][:18]} ({r['dirty']})" for r in dirty],
                           "duration_s": round(G.probe_duration(mp3), 2)}
                print(f"{spec} {v} FAIL {len(rows[v]['fails'])}/{len(audit)} onset {len(dirty)}  {rows[v]['fails']} {rows[v]['onset_dirty']}",
                      flush=True)
            report[spec] = rows
            beat_files.append(V.ab_file(folder, [1, 2, 3, 4]))
        gap = Path(tmp) / "gap.mp3"                                   # one file: the beats, 2 s apart
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "2",
                        "-codec:a", "libmp3lame", "-b:a", "320k", str(gap)], check=True)
        lst = Path(tmp) / "l.txt"
        lst.write_text("".join(f"file '{p}'\nfile '{gap}'\n" for p in beat_files))
        ab = OUT / "english_fix_ab.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-ac", "1", "-codec:a", "libmp3lame", "-b:a", "320k", str(ab)], check=True)
    totals = {v: {"fails": sum(len(report[s][v]["fails"]) for s in args.beats + args.onset),
                  "spans": sum(report[s][v]["spans"] for s in args.beats + args.onset),
                  "onset_dirty": sum(len(report[s][v]["onset_dirty"]) for s in args.onset)} for v in (1, 2, 3, 4)}
    report["totals"], report["characters_sent"], report["aliases"] = totals, run.chars, ALIASES
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print("totals:", totals, "\ncharacters sent:", run.chars, "→", ab)


if __name__ == "__main__":
    main()
