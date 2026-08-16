from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from .aps1 import FragmentAssembler, decode_image_result
from .models import Snapshot
from .transport_pipeline import FileSignature, TransportFileLifecycle


LIVE_WINDOW = 30
INITIAL_BACKFILL_LIMIT = 2000
BACKFILL_BATCH_SIZE = 20
SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".tga"}
FILE_SETTLE_SECONDS = 0.08
POLL_SECONDS = 0.35
BACKFILL_STABLE_AGE_NS = 500_000_000

def _is_transient_decode_error(exc: Exception) -> bool:
    if isinstance(exc, BlockingIOError):
        return True
    # Windows sharing/lock violations are transient. Generic access-denied
    # failures (for example ACL error 5) stay on the bounded failure path.
    return isinstance(exc, OSError) and getattr(exc, "winerror", None) in {32, 33}


class ScreenshotWatcher:
    """Poll WoW screenshots and feed complete APS1 snapshots to the engine.

    Filesystem ownership/deletion lives in TransportFileLifecycle. Fragment
    assembly lives in APS1.FragmentAssembler. This class only coordinates the
    ordered pipeline and never deletes a frame before delivery is complete.
    """

    def __init__(
        self,
        folder: Path,
        on_snapshot: Callable[[Snapshot], bool | None],
        on_status: Callable[[str], None] | None = None,
    ):
        self.folder = folder
        self.on_snapshot = on_snapshot
        self.on_status = on_status or (lambda _status: None)
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.assembler = FragmentAssembler()
        self.files = TransportFileLifecycle(fragment_limit=INITIAL_BACKFILL_LIMIT)
        self._initial_backfill_pending = True

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run,
            name="KL-ScreenshotWatcher",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        thread = self.thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=3.0)
        if thread is None or not thread.is_alive():
            self.thread = None

    def _list_candidates(self) -> tuple[list[Path], bool]:
        # A screenshot can disappear between iterdir(), is_file() and stat()
        # (manual cleanup, sync tools, or our own committed transport cleanup).
        # Keep one racing file from aborting the complete polling pass.
        stamped: list[tuple[int, Path]] = []
        for path in self.folder.iterdir():
            try:
                if path.is_file() and path.suffix.casefold() in SUPPORTED_SUFFIXES:
                    stamped.append((path.stat().st_mtime_ns, path))
            except OSError:
                continue
        files = [path for _mtime, path in sorted(stamped, key=lambda item: item[0])]
        if self._initial_backfill_pending:
            # Newest-first recovery prevents an older terminal clear from
            # overwriting a newer complete snapshot after Companion startup.
            return list(reversed(files[-INITIAL_BACKFILL_LIMIT:])), True
        return files[-LIVE_WINDOW:], False

    def _settled_signature(self, path: Path, backfill: bool = False) -> FileSignature | None:
        try:
            first = self.files.signature(path)
        except OSError:
            return None
        # Historical files are already closed by WoW. Skipping the per-file
        # settle delay keeps a large Screenshots folder from blocking live QR
        # captures for minutes during startup. Very recent files still get the
        # normal two-stat stability check.
        if backfill and time.time_ns() - first[0] >= BACKFILL_STABLE_AGE_NS:
            return first
        if self.stop_event.wait(FILE_SETTLE_SECONDS):
            return None
        try:
            second = self.files.signature(path)
        except OSError:
            return None
        if first != second:
            self.files.clear_decode_failure(path)
            return None
        return second

    def _consume(self, path: Path, sig: FileSignature, backfill: bool) -> bool:
        """Return True when newest-first backfill may stop scanning older files."""
        if self.stop_event.is_set():
            return False
        try:
            owned, consumed, snapshot = decode_image_result(path, self.assembler)
        except Exception as exc:
            self.on_status(f"Transport • QR decode: {type(exc).__name__} • retry")
            if _is_transient_decode_error(exc):
                # Windows sharing violations and temporary permission locks are
                # recoverable. Never retire an otherwise unchanged screenshot
                # merely because WoW or another process still owns the handle.
                self.files.clear_decode_failure(path)
                return False
            if self.files.mark_decode_failure(path, sig):
                self.files.mark_seen(path, sig)
                self.files.clear_decode_failure(path)
            return False

        if self.stop_event.is_set():
            # Closing the Companion is a hard delivery boundary: do not mutate
            # engine state or delete a transport frame after shutdown started.
            return False

        self.files.clear_decode_failure(path)

        if not owned and not backfill:
            self.on_status("Transport • screenshot detected, but no KeystoneLens QR found")

        if snapshot is not None:
            # Delivery is the commit point. If the engine rejects/raises, keep
            # the screenshot unconsumed so the watcher can retry instead of
            # deleting the only authoritative transport frame.
            try:
                accepted = self.on_snapshot(snapshot)
            except Exception as exc:
                self.on_status(f"Transport • snapshot processing: {type(exc).__name__} • retry")
                return False
            if accepted is False:
                # A deliberately rejected stale snapshot is obsolete, not a
                # delivery commit. Retire only this frame; never clear pending
                # fragments that may belong to the newer listing generation.
                self.files.mark_seen(path, sig)
                if owned and consumed:
                    self.files.delete_if_unchanged(path, sig)
                self.on_status("Transport • stale snapshot ignored")
                return False

        self.files.mark_seen(path, sig)

        if owned and consumed:
            if snapshot is None:
                self.files.retain_fragment(path, sig)
                self.on_status("Transport • QR fragment received • waiting for the rest")
            else:
                if self.assembler.has_pending_streams():
                    # More than one fragment stream can coexist during startup
                    # recovery (for example across a Bridge reload). A complete
                    # snapshot from one stream must not delete the only on-disk
                    # fragments needed to recover another stream after a
                    # Companion restart. Retire only this completed frame; once
                    # all assembler streams are complete, commit_snapshot()
                    # clears the retained fragment batch normally.
                    self.files.delete_if_unchanged(path, sig)
                else:
                    self.files.commit_snapshot(path, sig)
                self.on_status("Transport • complete snapshot received")

        return backfill and snapshot is not None

    def _run(self) -> None:
        self.on_status(f"Transport • screenshots: {self.folder}")
        while not self.stop_event.is_set():
            self.files.retry_pending_deletes()
            if not self.folder.exists():
                self.on_status("Transport • Screenshots folder not found")
                self.stop_event.wait(2.0)
                continue

            try:
                candidates, backfill = self._list_candidates()
            except OSError:
                self.stop_event.wait(1.0)
                continue

            historical: dict[str, FileSignature] = {}
            backfill_processed = 0
            backfill_has_more = False
            recovered_snapshot = False

            for path in candidates:
                if self.stop_event.is_set():
                    break
                if backfill and backfill_processed >= BACKFILL_BATCH_SIZE:
                    backfill_has_more = True
                    continue

                sig = self._settled_signature(path, backfill=backfill)
                if sig is None:
                    if backfill:
                        backfill_has_more = True
                    continue
                key = str(path)
                historical[key] = sig
                if self.files.is_seen(path, sig):
                    continue

                if backfill:
                    backfill_processed += 1
                if self._consume(path, sig, backfill):
                    recovered_snapshot = True
                    break

            if backfill and recovered_snapshot:
                # A complete newest-first snapshot is authoritative. Mark older
                # startup files historical so a stale terminal clear cannot be
                # replayed on the next live pass.
                for path in candidates:
                    key = str(path)
                    if key in historical:
                        continue
                    try:
                        historical[key] = self.files.signature(path)
                    except OSError:
                        continue
                self.files.mark_historical(historical)
                self._initial_backfill_pending = False
            elif backfill and not backfill_has_more:
                # Exhausted the startup window without finding a complete frame.
                # Switch to live mode; any new screenshot is now handled on the
                # very next poll instead of waiting behind historical images.
                self._initial_backfill_pending = False

            self.files.bound_memory()
            self.stop_event.wait(POLL_SECONDS)
