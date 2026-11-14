"""STEP 70 §1: no tracked text file names a home folder (a user name and a machine layout)."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Built in pieces so this file does not match itself.
HOME = re.compile("/" + "Users/" + r"|/" + "home/" + r"[a-z_][\w.-]*/")
ALLOW = set()                                   # test fixtures that need a home path go here


def test_no_tracked_text_file_contains_a_home_path():
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    hits = []
    for name in filter(None, files.decode().split("\0")):
        path = ROOT / name
        if name in ALLOW or not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:8192]:                # binary
            continue
        for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            if HOME.search(line):
                hits.append(f"{name}:{n}")
    assert not hits, hits
