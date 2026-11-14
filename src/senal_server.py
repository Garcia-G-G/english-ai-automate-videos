"""Señal's local server: the built page plus senal.json, on 127.0.0.1 only."""
import socket
import subprocess
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import senal

ROOT = Path(__file__).resolve().parent.parent
PORT = 8766  # 8765 belongs to the panel's own tests on this machine
DIST = ROOT / "senal" / "dist"


def resolve(path: str) -> Path | None:
    """Map a URL path to a file under DIST (or senal.json); None for anything else."""
    p = unquote(urlsplit(path).path)
    if p == "/senal.json":
        return senal.SENAL_DIR / "senal.json"
    if "\0" in p:
        return None
    root = DIST.resolve()
    target = (root / (p.lstrip("/") or "index.html")).resolve()
    if target.is_dir():
        target = target / "index.html"
    if root not in target.parents or not target.is_file():
        return None
    return target


class _Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".woff2": "font/woff2"}

    def do_GET(self):
        f = resolve(self.path)
        if f is None or not f.is_file():
            return self.send_error(404)
        self._file = f
        super().do_GET()

    do_HEAD = do_GET

    def translate_path(self, path):
        return str(self._file)

    def log_message(self, *a):
        pass


def serve() -> None:
    ThreadingHTTPServer(("127.0.0.1", PORT), _Handler).serve_forever()


def _open() -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def ensure_running() -> str:
    if not _open():
        subprocess.Popen([sys.executable, "-m", "senal_server"], cwd=ROOT / "src", start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(20):
            if _open():
                break
            time.sleep(0.1)
    return f"http://127.0.0.1:{PORT}/"


if __name__ == "__main__":
    serve()
