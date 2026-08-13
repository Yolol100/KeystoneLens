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


def test_first_generated_addon_data_failure_does_not_publish_incomplete_toc(tmp_path, monkeypatch):
    screenshots = tmp_path / "World of Warcraft" / "_retail_" / "Screenshots"
    screenshots.mkdir(parents=True)

    sync = TooltipCacheSync(str(screenshots))
    assert sync.path is not None
    assert sync.toc_path is not None
    data_tmp = sync.path.with_suffix(".tmp")
    original_replace = Path.replace

    def fail_first_data_replace(self: Path, target: Path):
        if self == data_tmp and Path(target) == sync.path:
            raise OSError("simulated first Data.lua replace failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_first_data_replace)
    assert sync.write([]) is False
    assert "simulated first Data.lua replace failure" in sync.last_error
    assert not sync.path.exists()
    assert not sync.toc_path.exists(), "Do not expose a generated addon that references missing Data.lua"


def test_poll_surfaces_tooltip_sync_failure_instead_of_normal_runtime_status():
    import queue

    from keystonelens_companion.__main__ import App
    from keystonelens_companion.config import Config
    from keystonelens_companion.models import EngineState

    class FakeRoot:
        def __init__(self):
            self.after_calls = []

        def after(self, delay, callback):
            self.after_calls.append((delay, callback))
            return "after-id"

    class FakeUI:
        def __init__(self):
            self.state = None

        def update_state(self, state):
            self.state = state

        def set_status(self, status):
            raise AssertionError(f"Unexpected direct status update: {status}")

    class FailingTooltipSync:
        last_written_at = 0.0
        last_error = "simulated locked Data.lua"

        def write(self, rows):
            return False

    app = App.__new__(App)
    app.cfg = Config()
    app.root = FakeRoot()
    app.q = queue.Queue()
    app.wcl = None
    app._wcl_pending = False
    app._transport_status = ""
    app._tooltip_notice_until = 0.0
    app._tooltip_notice_generation = 0
    app.tooltip_sync = FailingTooltipSync()
    app.ui = FakeUI()

    app.q.put(("state", EngineState(None, (), (), "Ready", revision=1)))
    app._poll()

    assert app.ui.state is not None
    status = app.ui.state.status.casefold()
    assert "tooltip" in status and "failed" in status
    assert "simulated locked data.lua" in status
    assert app._tooltip_notice_until == 0.0


def test_generated_addon_noop_sync_repairs_missing_toc(tmp_path):
    screenshots = tmp_path / "World of Warcraft" / "_retail_" / "Screenshots"
    screenshots.mkdir(parents=True)

    sync = TooltipCacheSync(str(screenshots))
    assert sync.write([]) is True
    assert sync.path is not None and sync.toc_path is not None
    assert sync.path.exists() and sync.toc_path.exists()

    sync.toc_path.unlink()
    assert not sync.toc_path.exists()

    # A semantic no-op is only successful when the complete generated addon is
    # loadable. Missing metadata must be healed even when Data.lua is unchanged.
    assert sync.write([]) is True
    assert sync.toc_path.exists()
