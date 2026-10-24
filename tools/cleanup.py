#!/usr/bin/env python3
"""Free disk space: old output, caches and intermediates (STEP 74).

    python3 tools/cleanup.py --dry-run     # make clean-dry: the table, writes nothing
    python3 tools/cleanup.py               # make clean: the table, «¿Borrar? [s/N]», then delete

Each rule is one function that returns what it would delete and what it keeps and why.
`delete()` refuses anything git tracks, anything a test reads, tests/ and NEVER, whatever a rule says.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parent.parent

DAY = 86400
ARTIFACT_MAX_AGE_DAYS = 14
CLIP_CACHE_MAX_AGE_DAYS = 30
CLIP_CACHE_CAP_BYTES = 1 << 30

#: Never deleted, whatever a rule says: they cost money, hold the record, or are the source.
NEVER = (".git", "content", "output/approved", "output/audio", "output/cache", "output/published",
         "output/costs", "output/scripts", "output/qa/design_proposals", "logs",
         "experiments/manim_voiceover_poc/audio", "experiments/manim_voiceover_poc/renders/ledger.jsonl",
         "experiments/manim_voiceover_poc/renders/reviews.jsonl", "experiments/manim_voiceover_poc/renders/jobs")
NEVER_NAME = re.compile(r"^(\.env.*|\.tokens.*|\.venv)$")    # at any depth

#: Statuses of an attempt that has not settled: the video may be live (publication_log).
OPEN_ATTEMPT = {"started", "session", "unknown"}
#: Artifact states that are approved but not (fully) published yet, and finished videos
#: waiting for a review the panel cannot show yet (ready_for_review, STEP 75 §3).
HELD_STATES = {"approved", "publishing", "partially_published", "ready_for_review"}


class RefusedPath(Exception):
    pass


# ── safety ───────────────────────────────────────────────────────────

def tracked_files(root: Path) -> set:
    """Every path git tracks under root. Raises when git cannot answer: no answer, no delete."""
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True)
    return {p for p in out.stdout.decode("utf-8").split("\0") if p}


TEST_PATH = re.compile(r"""(output/[^\s'"`{}()<>,;:*]+)""")


def test_references(root: Path) -> set:
    """Files under output/ that a test reads: `output/...` strings in tests/ that exist as files."""
    refs = set()
    for test in (root / "tests").rglob("*.py"):
        for ref in TEST_PATH.findall(test.read_text(encoding="utf-8", errors="replace")):
            if (root / ref).is_file():
                refs.add(ref)
    return refs


def guards(root: Path) -> Dict[str, set]:
    """What delete() refuses besides NEVER: git-tracked files and files the tests read."""
    return {"git": tracked_files(root), "tests": test_references(root)}


def protected_reason(path: Path, root: Path, guard: Dict[str, set]) -> Optional[str]:
    """Why `path` must not be deleted, or None."""
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return "fuera del repo"
    if rel in ("", "."):
        return "la raíz del repo"
    if rel == "tests" or rel.startswith("tests/"):
        return "nunca se borra (tests)"
    if any(NEVER_NAME.match(part) for part in rel.split("/")):
        return "nunca se borra (.env, .tokens, .venv)"
    for keep in NEVER:
        if rel == keep or rel.startswith(keep + "/"):
            return f"nunca se borra ({keep})"
    if rel.startswith("assets/") and not rel.startswith("assets/clips/_cache/"):
        return "nunca se borra (assets)"
    if rel in guard["git"] or any(t.startswith(rel + "/") for t in guard["git"]):
        return "git lo sigue"
    if rel in guard["tests"] or any(t.startswith(rel + "/") for t in guard["tests"]):
        return "un test lo usa"
    return None


def size_of(paths: Iterable[Path]) -> int:
    # shortcut: a hardlinked file is counted once per run; it frees nothing if a link outside the run survives.
    seen, total = set(), 0
    for p in paths:
        for f in ([p] if p.is_file() or p.is_symlink() else p.rglob("*")):
            try:
                st = f.lstat()
            except OSError:
                continue
            if f.is_dir() or (st.st_dev, st.st_ino) in seen:
                continue
            seen.add((st.st_dev, st.st_ino))
            total += st.st_size
    return total


def _plan(rule: str, paths: List[Path], kept: List[tuple], root: Path, tracked: set) -> Dict:
    """Move any protected path from `paths` to `kept`, then size what is left."""
    ok = []
    for p in paths:
        why = protected_reason(p, root, tracked)
        (kept.append((p, why)) if why else ok.append(p))
    return {"rule": rule, "paths": ok, "bytes": size_of(ok), "kept": kept}


def _children(folder: Path) -> List[Path]:
    return sorted(folder.iterdir()) if folder.is_dir() else []


def _newest_mtime(path: Path) -> float:
    times = [f.stat().st_mtime for f in path.rglob("*") if f.is_file()]
    return max(times) if times else path.stat().st_mtime


def _jsonl(path: Path) -> List[Dict]:
    rows = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


# ── rules ────────────────────────────────────────────────────────────

def rule_uploaded(root, tracked, now):
    return _plan("1 output/uploaded", _children(root / "output/uploaded"), [], root, tracked)


def rule_rejected(root, tracked, now):
    return _plan("2 output/rejected", _children(root / "output/rejected"), [], root, tracked)


def _still_needed(root: Path) -> Dict[str, str]:
    """{name: reason} of artifacts that must stay: approved, queued, or an attempt in doubt."""
    needed = {p.stem: "aprobado y sin subir a todo" for p in (root / "output/approved").glob("*/*.mp4")}
    queue = root / "output/published/meta_queue.json"
    if queue.is_file():
        try:
            for entry in json.loads(queue.read_text(encoding="utf-8")):
                needed.setdefault(entry.get("artifact", ""), "en la cola de Meta")
        except ValueError:
            needed["*"] = "meta_queue.json ilegible"
    latest = {}
    for row in _jsonl(root / "output/published/attempts.jsonl"):
        latest[(row.get("artifact"), row.get("platform"))] = row.get("status")
    for (artifact, _), status in latest.items():
        if status in OPEN_ATTEMPT:
            needed.setdefault(artifact or "", f"intento {status}, sin confirmar")
    return needed


def rule_artifacts(root, tracked, now):
    needed = _still_needed(root)
    paths, kept = [], []
    for folder in _children(root / "output/artifacts"):
        if not folder.is_dir() or now - _newest_mtime(folder) <= ARTIFACT_MAX_AGE_DAYS * DAY:
            continue
        names, why = {folder.name}, None
        meta = folder / "artifact.json"
        if meta.is_file():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                names |= {data.get("artifact_id") or "", Path((data.get("paths") or {}).get("video") or "").stem}
                if data.get("state") in HELD_STATES:
                    why = f"estado {data['state']}"
            except ValueError:
                why = "artifact.json ilegible"
        why = why or needed.get("*") or next((needed[n] for n in names if n in needed), None)
        (kept.append((folder, why)) if why else paths.append(folder))
    return _plan(f"3 output/artifacts > {ARTIFACT_MAX_AGE_DAYS} días", paths, kept, root, tracked)


def rule_intermediates(root, tracked, now):
    out = root / "output"
    folders = [out / "clips", out / "frames", out / "r1_verify", out / "step3_verify",
               *sorted(out.glob("voice_tests*"))]
    return _plan("4 output intermedios", [c for f in folders for c in _children(f)], [], root, tracked)


def rule_to_delete(root, tracked, now):
    return _plan("5 _to_delete", _children(root / "_to_delete"), [], root, tracked)


def rule_manim_media(root, tracked, now):
    return _plan("6 manim media/", _children(root / "experiments/manim_voiceover_poc/media"), [], root, tracked)


QUALITY = re.compile(r"^\d+p\d+$")


def _render_key(stem: str):
    """(theme, timestamp) of '20261019-131231_english-teacher_1080p30_sand'; None if not a render."""
    parts = stem.split("_")
    q = next((i for i, part in enumerate(parts) if QUALITY.match(part)), None)
    return None if q is None else ("_".join(parts[q + 1:]), parts[0])


def rule_manim_renders(root, tracked, now):
    renders = root / "experiments/manim_voiceover_poc/renders"
    published = {r.get("artifact") for r in _jsonl(root / "output/published/ledger.jsonl")}
    last_review = {}
    for line in _jsonl(renders / "reviews.jsonl"):
        if line.get("file"):
            last_review[line["file"]] = line
    paths, kept = [], []
    for lesson in _children(renders):
        if not lesson.is_dir() or lesson.name == "jobs":
            continue
        sets: Dict[str, List[Path]] = {}
        for f in lesson.iterdir():
            if f.is_file():
                sets.setdefault(f.name.split(".", 1)[0], []).append(f)
        newest = {}
        for stem in sets:
            key = _render_key(stem)
            if key and key[1] > newest.get(key[0], ""):
                newest[key[0]] = key[1]
        for stem, files in sorted(sets.items()):
            key = _render_key(stem)
            review = last_review.get(f"{lesson.name}/{stem}.mp4", {})
            why = ("no es un render" if key is None
                   else "el más nuevo de su lección y tema" if newest[key[0]] == key[1]
                   else "subido" if stem in published
                   else "aprobado" if review.get("status") == "aprobada"
                   else "reabierto" if review.get("reopen") else None)
            for f in files:
                (kept.append((f, why)) if why else paths.append(f))
    return _plan("7 manim renders antiguos", paths, kept, root, tracked)


def rule_clip_cache(root, tracked, now):
    """Pexels slots unused for 30 days, then the oldest until the cache is under 1 GB.
    Last use is max(atime, mtime): macOS may not update atime, and the newer of the two never deletes early."""
    slots = []
    for slot in _children(root / "assets/clips/_cache"):
        files = [f for f in slot.rglob("*") if f.is_file()] if slot.is_dir() else [slot]
        used = max((max(f.stat().st_atime, f.stat().st_mtime) for f in files), default=0)
        slots.append((used, slot))
    slots.sort()
    paths = [s for used, s in slots if now - used > CLIP_CACHE_MAX_AGE_DAYS * DAY]
    rest = [(used, s) for used, s in slots if s not in paths]
    total = size_of(s for _, s in rest)
    for _, slot in rest:                                   # oldest first
        if total <= CLIP_CACHE_CAP_BYTES:
            break
        total -= size_of([slot])
        paths.append(slot)
    return _plan("8 caché de Pexels", paths, [], root, tracked)


def rule_pycache(root, tracked, now):
    found = [root / ".pytest_cache"] if (root / ".pytest_cache").exists() else []
    for p in root.rglob("__pycache__"):
        rel = p.relative_to(root).parts
        if ".git" not in rel and not any(NEVER_NAME.match(part) for part in rel):
            found.append(p)
    return _plan("9 __pycache__ y .pytest_cache", sorted(found), [], root, tracked)


RULES = (rule_uploaded, rule_rejected, rule_artifacts, rule_intermediates, rule_to_delete,
         rule_manim_media, rule_manim_renders, rule_clip_cache, rule_pycache)


def plan(root: Path = ROOT, now: Optional[float] = None) -> List[Dict]:
    tracked = guards(root)
    now = time.time() if now is None else now
    return [rule(root, tracked, now) for rule in RULES]


def delete(paths: Iterable[Path], root: Path = ROOT) -> int:
    """Delete `paths`; refuses the whole call if any one is protected. Returns the bytes freed."""
    paths = list(paths)
    tracked = guards(root)
    for p in paths:
        why = protected_reason(p, root, tracked)
        if why:
            raise RefusedPath(f"{p}: {why}")
    freed = size_of(paths)
    for p in paths:
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
        elif p.exists() or p.is_symlink():
            p.unlink()
    return freed


# ── report ───────────────────────────────────────────────────────────

def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def table(plans: List[Dict]) -> str:
    lines = [f"{'regla':34} {'elementos':>9} {'tamaño':>10}"]
    for p in plans:
        lines.append(f"{p['rule']:34} {len(p['paths']):>9} {human(p['bytes']):>10}")
    lines.append(f"{'TOTAL':34} {sum(len(p['paths']) for p in plans):>9} "
                 f"{human(sum(p['bytes'] for p in plans)):>10}")
    reasons: Dict[str, int] = {}
    for p in plans:
        for _, why in p["kept"]:
            reasons[f"{p['rule']}: {why}"] = reasons.get(f"{p['rule']}: {why}", 0) + 1
    if reasons:
        lines.append("\nSe conservan:")
        lines += [f"  {n:>4} × {why}" for why, n in sorted(reasons.items())]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="show what would be deleted, delete nothing")
    args = ap.parse_args(argv)
    plans = plan()
    print(table(plans))
    if args.dry_run:
        return 0
    if input("¿Borrar? [s/N] ").strip().lower() != "s":
        print("No se borró nada.")
        return 1
    freed = delete([p for pl in plans for p in pl["paths"]])
    print(f"Liberado: {human(freed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
