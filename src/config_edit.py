"""Change single keys of config.yaml without touching the rest of the file (STEP 75 §1).

The panel used to yaml.dump() a dict it had rebuilt from a few widgets, which deleted
every section it did not know about and every comment. Here ruamel.yaml only finds
WHERE a scalar sits; the new value is spliced into that line, so every other byte of
the file stays as it was. The result is re-parsed before it replaces the file.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml
from ruamel.yaml import YAML

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

KeyPath = Tuple[str, ...]


def _scalar_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(round(value, 6) if isinstance(value, float) else value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)    # a double-quoted YAML scalar
    raise TypeError(f"only scalars can be patched, not {type(value).__name__}")


def _locate(tree, key_path: KeyPath) -> Tuple[int, int]:
    """(line, column) of the value at key_path, 0-based."""
    node = tree
    for key in key_path[:-1]:
        node = node[key]
    last = key_path[-1]
    if last not in node:
        raise KeyError(".".join(key_path))
    if isinstance(node[last], (dict, list)):
        raise TypeError(f"{'.'.join(key_path)} is not a scalar")
    return node.lc.value(last)


def _get(tree, key_path: KeyPath):
    for key in key_path:
        tree = tree[key]
    return tree


def _splice(line: str, col: int, new_text: str) -> str:
    """Replace the scalar that starts at `col`, keeping any trailing « # comment»."""
    rest = line[col:]
    if rest[:1] in ("'", '"'):
        end = rest.index(rest[0], 1) + 1
    else:
        hash_at = rest.find(" #")
        end = len(rest.rstrip("\n")) if hash_at < 0 else hash_at
        end = len(rest[:end].rstrip())
    return line[:col] + new_text + rest[end:]


def patch_config(updates: Dict[KeyPath, Any], path: Path = CONFIG_PATH, backup: bool = True) -> Path:
    """Set each key path to its value; returns the backup's path (or the file when backup=False)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    tree = YAML().load(text)
    lines = io.StringIO(text).readlines()
    for key_path, value in updates.items():
        line, col = _locate(tree, key_path)
        old = _get(tree, key_path)
        if old == value and isinstance(old, bool) == isinstance(value, bool):
            continue                                     # 0.50 stays 0.50 when 0.5 is saved
        lines[line] = _splice(lines[line], col, _scalar_text(value))
    new_text = "".join(lines)

    parsed = yaml.safe_load(new_text)                    # the file must still parse, with the new values
    for key_path, value in updates.items():
        node = _get(parsed, key_path)
        if node != value:
            raise ValueError(f"{'.'.join(key_path)} reads back as {node!r}, not {value!r}")

    saved = path
    if backup:
        saved = path.with_name(f"{path.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, saved)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return saved
