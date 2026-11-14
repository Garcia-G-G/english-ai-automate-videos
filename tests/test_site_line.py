"""STEP 61 Part C: every Short's description names learningroutes.com, after the body and
before the hashtags. Plain line, no tracking parameters.

    python3 -m pytest tests/test_site_line.py
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import metadata_generator as MG  # noqa: E402
import video_types  # noqa: E402


def test_the_line_is_plain():
    assert MG.SITE_LINE == "Más lecciones en https://learningroutes.com"


@pytest.mark.parametrize("vtype", video_types.VIDEO_TYPES)
def test_every_type_gets_the_line_between_body_and_hashtags(vtype):
    meta = MG.generate_metadata({"video_description": "Cuerpo del vídeo 🧠", "items": [], "theme": "x"}, vtype)
    assert meta["description"] == "Cuerpo del vídeo 🧠\n\n" + MG.SITE_LINE
    youtube = MG.adapt_for_platform(meta, "youtube")["description"]
    body, site, tags = youtube.split("\n\n")[:3]
    assert (body, site) == ("Cuerpo del vídeo 🧠", MG.SITE_LINE) and tags.startswith("#")


def test_the_line_is_added_once():
    once = MG.with_site_line("Hola")
    assert MG.with_site_line(once) == once and once.count("learningroutes") == 1
    assert MG.with_site_line("") == MG.SITE_LINE
