#!/usr/bin/env python3
"""Measure the onset gate on fresh takes of one level script's English clips. PAID (ElevenLabs).

    python3 tools/onset_calibrate.py content/queue/_done/lv001_cocina.json --takes 3

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--takes", type=int, default=3)
    args = ap.parse_args()
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
