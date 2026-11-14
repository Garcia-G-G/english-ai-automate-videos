#!/usr/bin/env python3
"""STEP 85b §2 proofs ($0): the three fixture cases with their measurements, saved to _audit/stills/STEP85b/.

    .venv/bin/python tools/thumbs_fixture_proofs.py
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
import thumbs as T  # noqa: E402
from thumbs import checks  # noqa: E402
from test_tablero_frame import _data  # noqa: E402
from video.how_do_you_say import Timeline  # noqa: E402
from video.tablero import frame as F  # noqa: E402

OUT = ROOT / "_audit" / "stills" / "STEP85b"


def main() -> None:
    d, dur = _data()
    draw = lambda t: F.create_frame_tablero(t, d, dur)                                   # noqa: E731
    tl = Timeline(d, dur)
    b = F.Beats(tl)
    black = lambda t: np.zeros((1920, 1080, 3), dtype=np.uint8)                          # noqa: E731
    cases = [("mid-flip (3rd tile flipping)", draw, b.fill_end[2] + F.FLIP_DUR / 4),
             ("settled, 3 tiles later", draw, tl.es[3][0] + 0.5),
             ("black transition frame", black, 1.0)]
    sheet = Image.new("RGB", (3 * 540 + 40, 960 + 330), (24, 24, 24))
    font = ImageFont.load_default(size=17)
    report = {}
    for i, (name, fn, t) in enumerate(cases):
        m = T.measure(fn, t)
        report[name] = m
        sheet.paste(Image.fromarray(fn(t)).resize((540, 960), Image.LANCZOS), (10 + i * 550, 10))
        verdict = "PASS" if m["ok"] else "REJECTED"
        lines = [f"{name}: {verdict}", f"t={m['t']}s  steady={m['steady']} (max {T.STEADY_MAX})", f"sharp={m['sharp']} (min {T.SHARP_MIN})",
                 f"luma={m['luma']} edges={m['edges']}"]
        dr = ImageDraw.Draw(sheet)
        for k, line in enumerate(lines):
            dr.text((20 + i * 550, 980 + 24 * k), line, fill=(120, 230, 120) if m["ok"] else (255, 120, 120), font=font)
    report["checks"] = checks.tablero_checks(d)
    r = report["checks"]["readable_small"]
    dr = ImageDraw.Draw(sheet)
    dr.text((20, 1090), f"nothing cut: {report['checks']['nothing_cut']}", fill=(220, 220, 220), font=font)
    dr.text((20, 1115), f"contrast: {r['contrast']}", fill=(220, 220, 220), font=font)
    dr.text((20, 1140), f"x-height at 180x320 (warning, not failure): {r['xheight_px']}", fill=(255, 210, 120), font=font)
    OUT.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT / "fixtures_section2.png")
    (OUT / "fixtures_section2.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v.get("ok", v.get("ok")) if isinstance(v, dict) else v for k, v in report.items()}))


if __name__ == "__main__":
    main()
