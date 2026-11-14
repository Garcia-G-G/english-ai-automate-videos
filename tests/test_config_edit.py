"""STEP 75 §1: saving one key of config.yaml leaves every other byte as it was."""
import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import config_edit as CE  # noqa: E402


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "cfg" / "config.yaml"
    path.parent.mkdir()
    shutil.copy(ROOT / "config.yaml", path)
    return path


def test_one_key_changes_and_every_other_byte_stays(cfg):
    before = cfg.read_text(encoding="utf-8").splitlines(keepends=True)
    backup = CE.patch_config({("audio", "stability"): 0.65}, path=cfg)
    after = cfg.read_text(encoding="utf-8").splitlines(keepends=True)
    changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert len(before) == len(after) and len(changed) == 1
    line = after[changed[0]]
    assert line.startswith("  stability: 0.65") and "# Balanced" in line
    assert before[changed[0]] == "  stability: 0.50             # Balanced: human but no hallucinated artifacts\n"
    assert backup.read_text(encoding="utf-8") == "".join(before)
    assert yaml.safe_load(cfg.read_text())["audio"]["stability"] == 0.65


def test_quoted_strings_bools_and_several_keys(cfg):
    CE.patch_config({("audio", "narration_lang"): "es", ("audio", "global_speed"): 1.05,
                     ("audio", "speaker_boost"): False}, path=cfg, backup=False)
    audio = yaml.safe_load(cfg.read_text())["audio"]
    assert (audio["narration_lang"], audio["global_speed"], audio["speaker_boost"]) == ("es", 1.05, False)
    assert '  narration_lang: "es"          # native' in cfg.read_text()


def test_a_missing_key_or_a_section_is_refused_and_the_file_is_untouched(cfg):
    before = cfg.read_bytes()
    with pytest.raises(KeyError):
        CE.patch_config({("audio", "nope"): 1}, path=cfg)
    with pytest.raises(TypeError):
        CE.patch_config({("audio",): 1}, path=cfg)
    assert cfg.read_bytes() == before
    assert list(cfg.parent.iterdir()) == [cfg]          # no backup, no temp file left


def test_the_panel_saves_through_patch_config_only():
    src = (ROOT / "src" / "admin.py").read_text(encoding="utf-8")
    assert "yaml.dump(config, f" not in src and "save_config(new_config)" not in src
    assert "patch_config(" in src


def test_saving_the_values_already_there_changes_nothing(cfg):
    before = cfg.read_bytes()
    CE.patch_config({("audio", "stability"): 0.5, ("audio", "style"): 0.05}, path=cfg, backup=False)
    assert cfg.read_bytes() == before
