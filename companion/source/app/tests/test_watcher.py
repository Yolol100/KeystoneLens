from __future__ import annotations
import unittest
from types import SimpleNamespace
from keystonelens_companion.watcher import ScreenshotWatcher


class _RacingPath:
    def __init__(self, name: str, mtime: int, fail: bool = False):
        self.name = name
        self.suffix = '.png'
        self._mtime = mtime
        self._fail = fail
    def is_file(self): return True
    def stat(self):
        if self._fail:
            raise FileNotFoundError(self.name)
        return SimpleNamespace(st_mtime_ns=self._mtime)
    def __str__(self): return self.name


class _Folder:
    def __init__(self, paths): self.paths = paths
    def iterdir(self): return iter(self.paths)


class WatcherTests(unittest.TestCase):
    def test_candidate_scan_survives_file_disappearing_during_stat(self):
        folder = _Folder([
            _RacingPath('old.png', 1),
            _RacingPath('gone.png', 2, fail=True),
            _RacingPath('new.png', 3),
        ])
        watcher = ScreenshotWatcher(folder, lambda _snapshot: None)
        watcher._initial_backfill_pending = False
        files, backfill = watcher._list_candidates()
        self.assertFalse(backfill)
        self.assertEqual([str(path) for path in files], ['old.png', 'new.png'])


if __name__ == '__main__':
    unittest.main()
