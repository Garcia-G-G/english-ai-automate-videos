#!/usr/bin/env python3
"""Measure the onset gate on fresh takes of one level script's English clips. PAID (ElevenLabs).

    python3 tools/onset_calibrate.py content/queue/_done/lv001_cocina.json --takes 3
    python3 tools/onset_calibrate.py --on-disk DIR [DIR ...]      # FREE: clips already stored

--on-disk (STEP 76 §3): the first-10 ms level (dBFS) of every .mp3 under the given folders,
as a histogram, and the threshold that separates clips rising from the noise floor from
clips that start at speech level (the cut-ins the owner hears at −16…−20 dBFS).

Every take is requested exactly as generate_level_audio_segmented asks for it,
kept raw (untrimmed, what the gate sees) under _audit/onset_<model>/, and its
three gate values printed as a markdown table plus a JSON file beside them.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def english_lines(script):
    import tts_elevenlabs as TE
    from tts_common import clean_for_tts
    plan = TE.LEVEL_PLANS[script["type"]]
    out = []
    for i, item in enumerate(script["items"], start=1):
        for role in ("prompt", "answer"):
            field, lang = plan[role]
            if lang == "en" and (role == "answer" or plan["speak_prompt"]):
                text = item[field]
                out.append((f"{role}_{i}", clean_for_tts(text if text.endswith((".", "?", "!")) else f"{text}.",
                                                         keep_tags=TE._KEEP_TAGS)))
    return out


def first_levels(dirs):
    """{path: first-10 ms dBFS} for every .mp3 under `dirs`."""
    import stitch
    return {str(p): stitch.first_dbfs(stitch.load(p)) for d in dirs for p in sorted(Path(d).rglob("*.mp3"))}


def histogram(values, width=2):
    lines = []
    for lo in range(int(min(values) // width * width), int(max(values)) + width, width):
        n = sum(lo <= v < lo + width for v in values)
        if n:
            lines.append(f"{lo:5d} … {lo + width:4d} dBFS  {'#' * n} {n}")
    return "\n".join(lines)


def propose(values, cut_in=(-20.0, -16.0)):
    """The middle of the gap between the highest clip under the cut-in band and the band's
    floor: every clip at or above it is flagged, every clip below it rose from the floor."""
    below = sorted(v for v in values if v < cut_in[0])
    if not below:
        return cut_in[0] - 3.0
    top = below[-1]
    return round((top + cut_in[0]) / 2, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script", nargs="?")
    ap.add_argument("--takes", type=int, default=3)
    ap.add_argument("--on-disk", nargs="+", metavar="DIR")
    args = ap.parse_args()
    if args.on_disk:
        levels = first_levels(args.on_disk)
        values = list(levels.values())
        print(f"{len(values)} clips\n{histogram(values)}")
        t = propose(values)
        print(f"\nproposed threshold: {t} dBFS — flags {sum(v >= t for v in values)}, keeps {sum(v < t for v in values)}")
        return
    if not args.script:
        ap.error("a script, or --on-disk DIR")
    import tts_elevenlabs as TE
    from tts_common import extract_english_words_from_script

    script = json.loads(Path(args.script).read_text(encoding="utf-8"))
    out_dir = ROOT / "_audit" / f"onset_{TE.MODEL_ID}" / script["_meta"]["topic_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    words = extract_english_words_from_script(script)
    rows, chars = [], 0
    for seg_id, text in english_lines(script):
        for take in range(args.takes):
            path = out_dir / f"{seg_id}.take{take}.mp3"
            if not path.exists():
                TE.generate_segment_audio(text=text, output_path=str(path), voice_id=TE.DEFAULT_VOICE_ID,
                                          segment_type="default", english_words=words)
                chars += len(text)
            v = TE._onset_values(str(path))
            rows.append({"seg": seg_id, "text": text, "take": take, **v,
                         "fails_only_start": (v["start_db"] is not None and v["start_db"] >= -30
                                              and v["fragment"] is None and v["doubled_onset"] is None)})
    (out_dir / "values.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"model {TE.MODEL_ID}, {chars} characters requested\n")
    print("| clip | text | take | start-to-peak dB | fragment | doubled_onset |\n|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['seg']} | {r['text']} | {r['take']} | {r['start_db']} | {r['fragment']} | {r['doubled_onset']} |")


if __name__ == "__main__":
    main()
