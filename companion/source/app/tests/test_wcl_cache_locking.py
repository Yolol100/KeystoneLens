from __future__ import annotations

import threading
import time
from pathlib import Path

from keystonelens_companion.models import WCLResult
from keystonelens_companion.wcl import WCLCache


def test_wcl_cache_disk_write_does_not_hold_data_lock(tmp_path, monkeypatch):
    cache = WCLCache(tmp_path / "wcl-cache.json")
    started = threading.Event()
    release = threading.Event()
    original_write_text = Path.write_text

    def blocking_write(path, *args, **kwargs):
        if path.name == "wcl-cache.tmp":
            started.set()
            assert release.wait(2.0)
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", blocking_write)
    result = WCLResult(
        "Applicant", "Realm", "Dungeon", 250, None, time.time(),
        target_key=10, not_found=True,
    )
    worker = threading.Thread(target=lambda: cache.put("eu", result), daemon=True)
    worker.start()
    assert started.wait(2.0)
    acquired = cache._lock.acquire(timeout=0.5)
    try:
        assert acquired, "cache data lock remained held during filesystem I/O"
    finally:
        if acquired:
            cache._lock.release()
        release.set()
    worker.join(2.0)
    assert not worker.is_alive()


def test_wcl_backoff_uses_monotonic_clock():
    source = Path(__file__).parents[1] / "keystonelens_companion" / "wcl.py"
    text = source.read_text(encoding="utf-8")
    assert "time.time() < self._blocked_until" not in text
    assert "time.time() >= self._blocked_until" not in text
    assert "time.time() > self._blocked_until" not in text
    assert "time.time() <= self._blocked_until" not in text
    assert "self._blocked_until = time.time() +" not in text
    assert "time.monotonic() < self._blocked_until" in text
