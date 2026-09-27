#!/usr/bin/env python3
"""Controlled-runtime stale-work regressions for screenshot and engine lifecycle."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import threading
import time
import types

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "companion" / "source" / "app"
sys.path.insert(0, str(APP_ROOT))

requests_stub = types.ModuleType("requests")
requests_stub.RequestException = RuntimeError
requests_stub.Session = object
sys.modules.setdefault("requests", requests_stub)

import keystonelens_companion.watcher as watcher_module  # noqa: E402
from keystonelens_companion.engine import ApplicantEngine  # noqa: E402
from keystonelens_companion.models import Applicant, Listing, Snapshot  # noqa: E402


def _snapshot(name: str, generation: int) -> Snapshot:
    return Snapshot(
        listing=Listing(key_level=12, dungeon_name="Altar of Fangs"),
        version=None,
        applicants=(Applicant(
            applicant_id=generation,
            member_idx=1,
            class_id=8,
            spec_id=62,
            ilvl=639,
            rio_score=0,
            rio_main_score=0,
            role_byte=2,
            name=name,
        ),),
        listing_generation=generation,
    )


def test_watcher_stop_during_decode_drops_result_without_delivery() -> None:
    started = threading.Event()
    release = threading.Event()
    delivered = []
    original_decode = watcher_module.decode_image_result

    def blocking_decode(_path, _assembler):
        started.set()
        assert release.wait(timeout=2.0)
        return True, True, object()

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        screenshot = folder / "WoWScrnShot_0001.png"
        screenshot.write_bytes(b"fixture")
        watcher = watcher_module.ScreenshotWatcher(folder, delivered.append)
        sig = watcher.files.signature(screenshot)
        watcher_module.decode_image_result = blocking_decode
        try:
            worker = threading.Thread(
                target=watcher._consume,
                args=(screenshot, sig, False),
            )
            worker.start()
            assert started.wait(timeout=1.0)
            watcher.request_stop()
            release.set()
            worker.join(timeout=1.0)
            assert not worker.is_alive()
            assert delivered == [], "stopped watcher published a late decoded snapshot"
            assert screenshot.exists(), "stopped watcher deleted an uncommitted transport frame"
            assert not watcher.files.is_seen(screenshot, sig)
        finally:
            watcher_module.decode_image_result = original_decode
            release.set()


class BlockingWCL:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def fetch_batch_current_dungeon(self, jobs, *, max_cache_age_seconds=None):
        self.started.set()
        assert self.release.wait(timeout=2.0)
        return [None for _ in jobs]


def test_engine_stop_during_inflight_wcl_drops_late_result() -> None:
    client = BlockingWCL()
    states = []
    engine = ApplicantEngine(client, states.append)
    try:
        assert engine.handle_snapshot(_snapshot("Alice-Draenor", 40))
        assert client.started.wait(timeout=2.0)
        before_stop = len(states)
        engine.request_stop()
        client.release.set()
        assert engine.stop(timeout=2.0)
        time.sleep(0.05)
        assert len(states) == before_stop, "engine emitted state after shutdown started"
    finally:
        client.release.set()
        engine.stop(timeout=1.0)


def test_older_listing_generation_is_rejected_without_replacing_state() -> None:
    states = []
    engine = ApplicantEngine(None, states.append)
    try:
        assert engine.handle_snapshot(_snapshot("Bob-Draenor", 31))
        before = states[-1]
        assert engine.handle_snapshot(_snapshot("Alice-Draenor", 30)) is False
        after = states[-1]
        assert after is before
        assert [row.applicant.name for row in after.rows] == ["Bob-Draenor"]
    finally:
        assert engine.stop(timeout=2.0)


class _CandidatePath:
    def __init__(self, index: int):
        self.index = index
        self.suffix = ".png"

    def is_file(self) -> bool:
        return True

    def stat(self):
        return types.SimpleNamespace(st_mtime_ns=self.index)


class _CandidateFolder:
    def __init__(self, count: int):
        self.paths = [_CandidatePath(index) for index in range(count)]

    def iterdir(self):
        return iter(self.paths)


def test_candidate_selection_does_not_sort_unbounded_screenshot_history() -> None:
    watcher = watcher_module.ScreenshotWatcher(_CandidateFolder(5000), lambda _snapshot: None)
    original_sorted = getattr(watcher_module, "sorted", None)
    had_override = hasattr(watcher_module, "sorted")
    builtin_sorted = sorted

    def bounded_sorted(iterable, *args, **kwargs):
        materialized = list(iterable)
        assert len(materialized) <= watcher_module.INITIAL_BACKFILL_LIMIT, (
            "watcher sorted the full unbounded screenshot history before applying its backfill limit"
        )
        return builtin_sorted(materialized, *args, **kwargs)

    watcher_module.sorted = bounded_sorted
    try:
        backfill, is_backfill = watcher._list_candidates()
        assert is_backfill is True
        assert len(backfill) == watcher_module.INITIAL_BACKFILL_LIMIT
        assert [item.index for item in backfill[:3]] == [4999, 4998, 4997]

        watcher._initial_backfill_pending = False
        live, is_backfill = watcher._list_candidates()
        assert is_backfill is False
        assert len(live) == watcher_module.LIVE_WINDOW
        assert [item.index for item in live[:3]] == [4970, 4971, 4972]
    finally:
        if had_override:
            watcher_module.sorted = original_sorted
        else:
            delattr(watcher_module, "sorted")


if __name__ == "__main__":
    test_watcher_stop_during_decode_drops_result_without_delivery()
    test_engine_stop_during_inflight_wcl_drops_late_result()
    test_older_listing_generation_is_rejected_without_replacing_state()
    test_candidate_selection_does_not_sort_unbounded_screenshot_history()
    print("KeystoneLens transport lifecycle contract passed.")
