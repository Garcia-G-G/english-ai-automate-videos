"""STEP 85b §5: the panel's WebPs, the 24-character placeholder and Revisar's «Miniatura» row."""
import base64
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
import thumbs as T  # noqa: E402
from test_tablero_frame import _data  # noqa: E402


def _made(tmp_path):
    d, dur = _data()
    mp4 = tmp_path / "v.mp4"
    T.make_for_tablero(mp4, d, dur)
    return mp4, T.thumb_dir(mp4)


def test_the_webps_and_the_placeholder_are_made_with_the_thumbnail(tmp_path):
    mp4, folder = _made(tmp_path)
    assert Image.open(folder / "thumb_270.webp").size == (270, 480) and Image.open(folder / "thumb_540.webp").size == (540, 960)
    assert {p.name for p in (folder / "cands").glob("*.webp")} == {"A.webp", "B.webp", "C.webp"}
    assert Image.open(folder / "cands" / "A.webp").size == (180, 320)
    ph = json.loads((folder / "thumb.json").read_text())["placeholder"]
    assert len(ph) == 24 and len(base64.b64decode(ph)) == 18          # 2x3 RGB pixels


def test_switching_a_candidate_re_makes_the_webps_without_a_render(tmp_path):
    mp4, folder = _made(tmp_path)
    before = (folder / "thumb_270.webp").read_bytes()
    T.pick(folder, "B")
    assert (folder / "thumb_270.webp").read_bytes() != before


def test_choose_marks_the_pick_as_garcias_and_tells_the_sidecar(tmp_path):
    mp4, folder = _made(tmp_path)
    mp4.with_suffix(".json").write_text(json.dumps({"thumbnail": {"chosen": "A"}}))
    T.choose(mp4, "C")
    assert json.loads((folder / "thumb.json").read_text())["manual"] is True
    assert json.loads(mp4.with_suffix(".json").read_text())["thumbnail"]["chosen"] == "C"


def test_row_img_has_a_fixed_box_lazy_loading_and_the_placeholder(tmp_path):
    mp4, _ = _made(tmp_path)
    html = T.web.row_img(mp4)
    assert 'width="45" height="80"' in html and 'loading="lazy"' in html and 'decoding="async"' in html
    assert "data:image/webp;base64," in html and "linear-gradient" in html


def test_row_img_is_none_for_a_video_made_before_this_step(tmp_path):
    assert T.web.row_img(tmp_path / "old.mp4") is None


def test_ensure_thumbnail_still_works_for_older_videos(tmp_path):
    import subprocess
    import thumbnails
    mp4 = tmp_path / "q.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=540x960:r=10:d=3", "-pix_fmt", "yuv420p", str(mp4)], check=True)
    assert thumbnails.ensure_thumbnail(mp4, thumbs_dir=tmp_path / "t")


class _St:
    def __init__(self, click=None):
        self.out, self.click = [], click

    def markdown(self, *a, **k): self.out.append(("md", a[0]))
    def caption(self, text): self.out.append(("cap", text))
    def rerun(self): self.out.append(("rerun",))

    def columns(self, n):
        return [self for _ in range(n)]

    def button(self, label, key=None):
        return key == self.click


def test_revisar_row_shows_three_candidates_outlines_the_chosen_and_switches_on_click(tmp_path):
    from panel import revisar
    mp4, folder = _made(tmp_path)
    st = _St()
    revisar.miniatura_row(st, mp4)
    imgs = [o[1] for o in st.out if o[0] == "md" and "<img" in o[1]]
    assert len(imgs) == 3 and sum("3px solid" in i for i in imgs) == 1 and all('width="90" height="160"' in i for i in imgs)
    assert any(o[0] == "cap" and "YouTube" in o[1] or o[0] == "cap" and "probado" in o[1] for o in st.out)
    st = _St(click=f"mini_{mp4.stem}_B")
    revisar.miniatura_row(st, mp4)
    assert ("rerun",) in st.out and json.loads((folder / "thumb.json").read_text())["chosen"] == "B"


def test_revisar_row_is_silent_for_a_video_without_thumbnails(tmp_path):
    from panel import revisar
    st = _St()
    revisar.miniatura_row(st, tmp_path / "none.mp4")
    assert st.out == []
