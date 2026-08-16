from __future__ import annotations
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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


class _Files:
    def __init__(self):
        self.seen = []
        self.committed = []
        self.deleted = []
        self.fragments = []
        self.decode_failures_cleared = []

    def clear_decode_failure(self, path):
        self.decode_failures_cleared.append(str(path))

    def mark_seen(self, path, sig):
        self.seen.append((str(path), sig))

    def commit_snapshot(self, path, sig):
        self.committed.append((str(path), sig))

    def delete_if_unchanged(self, path, sig):
        self.deleted.append((str(path), sig))
        return True

    def retain_fragment(self, path, sig):
        self.fragments.append((str(path), sig))

    def mark_decode_failure(self, _path, _sig):
        return False


class _Assembler:
    def __init__(self, pending: bool = False):
        self.pending = pending

    def has_pending_streams(self):
        return self.pending


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

    def test_complete_snapshot_is_committed_after_successful_delivery(self):
        statuses = []
        snapshot = object()
        watcher = ScreenshotWatcher(Path('screenshots'), lambda value: value is snapshot, statuses.append)
        watcher.files = _Files()
        watcher.assembler = _Assembler(pending=False)
        sig = (123, 456)

        with patch(
            'keystonelens_companion.watcher.decode_image_result',
            return_value=(True, True, snapshot),
        ):
            should_stop_backfill = watcher._consume(Path('shot.png'), sig, backfill=False)

        self.assertFalse(should_stop_backfill)
        self.assertEqual(watcher.files.committed, [('shot.png', sig)])
        self.assertEqual(watcher.files.seen, [('shot.png', sig)])
        self.assertEqual(statuses[-1], 'Transport • complete snapshot received')

    def test_delivery_exception_keeps_frame_uncommitted_for_retry(self):
        statuses = []
        snapshot = object()

        def fail_delivery(_snapshot):
            raise RuntimeError('engine unavailable')

        watcher = ScreenshotWatcher(Path('screenshots'), fail_delivery, statuses.append)
        watcher.files = _Files()
        watcher.assembler = _Assembler(pending=False)
        sig = (123, 456)

        with patch(
            'keystonelens_companion.watcher.decode_image_result',
            return_value=(True, True, snapshot),
        ):
            should_stop_backfill = watcher._consume(Path('shot.png'), sig, backfill=False)

        self.assertFalse(should_stop_backfill)
        self.assertEqual(watcher.files.committed, [])
        self.assertEqual(watcher.files.seen, [])
        self.assertEqual(statuses[-1], 'Transport • snapshot processing: RuntimeError • retry')


if __name__ == '__main__':
    unittest.main()
