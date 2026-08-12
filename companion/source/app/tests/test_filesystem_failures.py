from __future__ import annotations

from pathlib import Path

import pytest

from keystonelens_companion import config as config_mod
from keystonelens_companion.addon_sync import TooltipCacheSync


def test_config_atomic_replace_failure_preserves_last_valid_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text('{"screenshots_path":"C:/old"}', encoding="utf-8")
    monkeypatch.setattr(config_mod, "config_path", lambda: path)

    original_replace = Path.replace

    def fail_config_replace(self: Path, target: Path):
        if self == path.with_suffix(".tmp") and Path(target) == path:
            raise OSError("simulated locked config")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_config_replace)
    with pytest.raises(OSError, match="simulated locked config"):
        config_mod.save_config(config_mod.Config(screenshots_path="C:/new"))

    assert path.read_text(encoding="utf-8") == '{"screenshots_path":"C:/old"}'


def test_generated_addon_atomic_replace_failure_preserves_last_valid_data(tmp_path, monkeypatch):
    screenshots = tmp_path / "World of Warcraft" / "_retail_" / "Screenshots"
    screenshots.mkdir(parents=True)

    initial = TooltipCacheSync(str(screenshots))
    assert initial.write([]) is True
    assert initial.path is not None
    old_data = initial.path.read_text(encoding="utf-8")

    retry = TooltipCacheSync(str(screenshots))
    assert retry.path is not None
    data_tmp = retry.path.with_suffix(".tmp")
    original_replace = Path.replace

    def fail_data_replace(self: Path, target: Path):
        if self == data_tmp and Path(target) == retry.path:
            raise OSError("simulated locked Data.lua")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_data_replace)
    assert retry.write([]) is False
    assert "simulated locked Data.lua" in retry.last_error
    assert retry.path.read_text(encoding="utf-8") == old_data
