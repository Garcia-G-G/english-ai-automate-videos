"""Señal server: path resolution must never leave DIST (plus senal.json)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import senal  # noqa: E402
import senal_server  # noqa: E402


def test_the_json_route_points_at_senal_dir():
    assert senal_server.resolve("/senal.json") == senal.SENAL_DIR / "senal.json"


def test_index_resolves_inside_dist(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("x")
    monkeypatch.setattr(senal_server, "DIST", tmp_path)
    assert senal_server.resolve("/") == (tmp_path / "index.html").resolve()


@pytest.mark.parametrize("p", ["/../.env", "/%2e%2e/.env", "/..%2f..%2f.env", "//etc/passwd",
                               "/senal.json/../../.env", "/a%00b"])
def test_nothing_outside_dist_is_served(p, tmp_path, monkeypatch):
    (tmp_path / "dist").mkdir()
    (tmp_path / ".env").write_text("secret")
    monkeypatch.setattr(senal_server, "DIST", tmp_path / "dist")
    assert senal_server.resolve(p) is None
