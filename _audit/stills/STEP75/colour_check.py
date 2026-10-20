#!/usr/bin/env python3
"""ΔE (CIE76, Lab D65) of the brand blue and sticky yellow as a player would decode a frame.

    python3 _audit/stills/STEP75/colour_check.py FINAL.mp4 SECONDS [--matrix bt709|bt601] [--still out.png]

Untagged files are decoded the way most players treat untagged SD/HD-ambiguous video
(--matrix bt601); tagged ones with the matrix they declare. For each target the pixels
within ΔE 12 of it are taken and their median ΔE reported.
"""
import argparse
import subprocess

import numpy as np

TARGETS = {"title blue #1B6FA8": (0x1B, 0x6F, 0xA8), "sticky yellow #F2D66B": (0xF2, 0xD6, 0x6B)}


def lab(rgb):
    c = np.asarray(rgb, float) / 255
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]).T
    xyz /= (0.95047, 1.0, 1.08883)
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("t", type=float)
    ap.add_argument("--matrix", default="bt709"); ap.add_argument("--still")
    a = ap.parse_args()
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(a.t), "-i", a.video, "-frames:v", "1", "-vf",
                          f"scale=in_color_matrix={a.matrix}:in_range=tv,format=rgb24", "-f", "rawvideo", "-"],
                         capture_output=True, check=True, timeout=60).stdout
    img = np.frombuffer(raw, np.uint8).reshape(1920, 1080, 3)
    if a.still:
        from PIL import Image
        Image.fromarray(img).save(a.still)
    L = lab(img.reshape(-1, 3))
    for name, rgb in TARGETS.items():
        d = np.linalg.norm(L - lab(rgb), axis=1)
        near = d[d < 12]
        print(f"{name:24} pixels={near.size:7d} median ΔE={np.median(near) if near.size else float('nan'):.2f} "
              f"best ΔE={d.min():.2f}")


if __name__ == "__main__":
    main()
