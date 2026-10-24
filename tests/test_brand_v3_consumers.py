"""STEP 71 §3: nothing still shows the brand before v3."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_website_icon_is_the_brand_v3_app_icon():
    assert (ROOT / "docs" / "icon.png").read_bytes() == (ROOT / "assets" / "branding" / "app_icon.png").read_bytes()


def test_the_paid_icon_generator_will_not_replace_the_brand_icon():
    before = (ROOT / "assets" / "branding" / "app_icon.png").read_bytes()
    done = subprocess.run([sys.executable, "src/generate_app_icon.py"], cwd=ROOT, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "OPENAI_API_KEY": ""}, timeout=60)
    assert done.returncode != 0 and "brand v3 icon" in done.stderr
    assert (ROOT / "assets" / "branding" / "app_icon.png").read_bytes() == before


def test_the_icon_guard_holds_from_another_cwd(tmp_path):
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    before = (ROOT / "assets" / "branding" / "app_icon.png").read_bytes()
    done = subprocess.run([sys.executable, str(ROOT / "src" / "generate_app_icon.py")], cwd=cwd,
                          capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "OPENAI_API_KEY": ""},
                          timeout=60)
    assert done.returncode != 0 and "brand v3 icon" in done.stderr
    assert (ROOT / "assets" / "branding" / "app_icon.png").read_bytes() == before
    assert list(cwd.iterdir()) == []
