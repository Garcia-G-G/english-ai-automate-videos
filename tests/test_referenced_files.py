"""Files the code cannot run without must exist.

2026-10-27: a cleanup deleted src/video/__main__.py from the working tree. pipeline.py renders
through `python -m video`, so every render would have failed while the suite stayed green.
These tests guard the render entry point and every repo file the code names by path.
"""
import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Repo paths the code names on purpose without shipping them, each with the reason.
OPTIONAL = {
    # First of several candidates; the system fonts after it are the real source.
    "assets/fonts/NotoSansCJKsc-Regular.otf",
}
#: Generated at run time, never in git.
GENERATED = ("output/", "logs/")
TOPS = ("assets/", "content/", "tests/fixtures/", "experiments/", "docs/", "src/", "tools/", "config")
FILE = re.compile(r"\.(py|ttf|otf|ttc|json|yaml|yml|png|jpg|mp3|wav|mp4|md|txt|svg|sh)$")
ROOT_NAMES = {"ROOT", "PROJECT_ROOT", "REPO", "REPO_ROOT", "BASE_DIR"}


def _root_chain(node):
    """`ROOT / "a" / "b.json"` -> "a/b.json" when every part is a string constant, else None."""
    parts = []
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        if not (isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)):
            return None
        parts.append(node.right.value)
        node = node.left
    if isinstance(node, ast.Name) and node.id in ROOT_NAMES and parts:
        return "/".join(reversed(parts))
    return None


def _code_references():
    sources = [*(ROOT / "src").rglob("*.py"), *(ROOT / "tools").glob("*.py"), ROOT / "main.py"]
    for f in sources:
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.BinOp):
                path = _root_chain(node)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith(TOPS):
                path = node.value
            else:
                continue
            if path and FILE.search(path):
                yield path, f"{f.relative_to(ROOT)}:{node.lineno}"


def _data_references():
    token = re.compile(r"""(?<![\w/])((?:assets|content|experiments|docs|tests/fixtures)/[^\s"'#,)]+)""")
    for f in [ROOT / "config.yaml", *(ROOT / "assets").rglob("*.json")]:
        for m in token.finditer(f.read_text(encoding="utf-8")):
            path = m.group(1).rstrip(".:;")                  # «…pronunciation.json. That file…»
            if FILE.search(path):
                yield path, str(f.relative_to(ROOT))


def test_every_file_the_code_names_exists():
    missing = sorted({(p, where) for p, where in [*_code_references(), *_data_references()]
                      if not any(c in p for c in "{}*<>\n ")
                      and not p.startswith(GENERATED) and p not in OPTIONAL
                      and not (ROOT / p).exists()})
    assert not missing, "named in code but missing on disk:\n" + "\n".join(f"  {p}  <- {w}" for p, w in missing)


def test_the_scan_sees_the_files_that_matter():
    """A scan that finds nothing passes nothing: it must see the brand font and the topics."""
    found = {p for p, _ in [*_code_references(), *_data_references()]}
    assert "assets/fonts/Fredoka-Bold.ttf" in found
    assert any(p.startswith("content/topics/") for p in found)


def test_the_render_entry_point_runs():
    """pipeline.py runs `python -m video` from src/; without src/video/__main__.py nothing renders."""
    run = subprocess.run([sys.executable, "-m", "video", "--help"], cwd=ROOT / "src",
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
    assert "--audio" in run.stdout
