"""STEP 71 §3: nothing still shows the brand before v3."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_website_icon_is_the_brand_v3_app_icon():
    assert (ROOT / "docs" / "icon.png").read_bytes() == (ROOT / "assets" / "branding" / "app_icon.png").read_bytes()
