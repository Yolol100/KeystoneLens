from __future__ import annotations

import time
from pathlib import Path

FileSignature = tuple[int, int]
MAX_SEEN_ENTRIES = 3000
SEEN_TRIM_TARGET = 1000
MAX_DECODE_FAILURES = 256
MAX_PENDING_DELETES = 512


class TransportFileLifecycle:
    """Owns filesystem state for the screenshot transport.

    The watcher detects files; this class decides when a transport frame is
    considered seen, retained for fragment recovery, or safe to delete.
    Keeping these decisions outside the polling loop makes the delivery order
    explicit: detect -> decode -> assemble -> deliver -> delete.
    """

    def __init__(self, fragment_limit: int = 2000):
        self.fragment_limit = fragment_limit
        self.seen: dict[str, FileSignature] = {}
        self.decode_failures: dict[str, tuple[FileSignature, int]] = {}
        self.pending_deletes: dict[str, tuple[FileSignature, int, float]] = {}
        self.pending_fragment_files: dict[str, FileSignature] = {}

    @staticmethod
    def signature(path: Path) -> FileSignature:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size

    def is_seen(self, path: Path, sig: FileSignature) -> bool:
        return self.seen.get(str(path)) == sig

    def mark_seen(self, path: Path, sig: FileSignature) -> None:
        self.seen[str(path)] = sig

    def clear_decode_failure(self, path: Path) -> None:
        self.decode_failures.pop(str(path), None)

    def mark_decode_failure(self, path: Path, sig: FileSignature, retry_limit: int = 3) -> bool:
        """Return True once this unchanged file reached the decode retry limit."""
        key = str(path)
        prior_sig, prior_count = self.decode_failures.get(key, (sig, 0))
        count = prior_count + 1 if prior_sig == sig else 1
        self.decode_failures[key] = (sig, count)
        self._bound_mapping(self.decode_failures, MAX_DECODE_FAILURES)
        return count >= retry_limit

    def retain_fragment(self, path: Path, sig: FileSignature) -> None:
        self.pending_fragment_files[str(path)] = sig
        self._bound_fragments()

    def commit_snapshot(self, path: Path, sig: FileSignature) -> None:
        """Delete transport frames only after a full snapshot was delivered."""
        self.pending_fragment_files[str(path)] = sig
        batch = list(self.pending_fragment_files.items())
        self.pending_fragment_files.clear()
        for key, expected_sig in batch:
            self.delete_if_unchanged(Path(key), expected_sig)

    def delete_if_unchanged(self, path: Path, sig: FileSignature) -> None:
        try:
            current = self.signature(path)
        except OSError:
            return
        if current != sig:
            return
        self._delete_or_queue(path, sig)

    def _delete_or_queue(self, path: Path, sig: FileSignature) -> None:
        key = str(path)
        try:
            path.unlink()
        except FileNotFoundError:
            self.pending_deletes.pop(key, None)
        except OSError:
            self.pending_deletes[key] = (sig, 1, time.monotonic() + 0.25)
            self._bound_mapping(self.pending_deletes, MAX_PENDING_DELETES)
        else:
            self.pending_deletes.pop(key, None)

    def retry_pending_deletes(self) -> None:
        if not self.pending_deletes:
            return
        now = time.monotonic()
        for key, (expected_sig, attempts, retry_at) in list(self.pending_deletes.items()):
            if now < retry_at:
                continue
            path = Path(key)
            try:
                current_sig = self.signature(path)
            except FileNotFoundError:
                self.pending_deletes.pop(key, None)
                continue
            except OSError:
                self._reschedule_delete(key, expected_sig, attempts, now)
                continue

            if current_sig != expected_sig:
                # Never delete a new screenshot that reused the same path.
                self.pending_deletes.pop(key, None)
                continue

            try:
                path.unlink()
            except FileNotFoundError:
                self.pending_deletes.pop(key, None)
            except OSError:
                self._reschedule_delete(key, expected_sig, attempts, now)
            else:
                self.pending_deletes.pop(key, None)

    def mark_historical(self, signatures: dict[str, FileSignature]) -> None:
        self.seen.update(signatures)
        self.bound_memory()

    @staticmethod
    def _bound_mapping(mapping: dict, limit: int) -> None:
        if len(mapping) <= limit:
            return
        # dict preserves insertion order. Keep the newest bookkeeping only;
        # dropping an old retry record leaves the user's file untouched.
        for key in list(mapping)[:len(mapping) - limit]:
            mapping.pop(key, None)

    def bound_memory(self) -> None:
        if len(self.seen) > MAX_SEEN_ENTRIES:
            self.seen = dict(list(self.seen.items())[-SEEN_TRIM_TARGET:])
        self._bound_mapping(self.decode_failures, MAX_DECODE_FAILURES)
        self._bound_mapping(self.pending_deletes, MAX_PENDING_DELETES)
        self._bound_fragments()

    def _bound_fragments(self) -> None:
        if len(self.pending_fragment_files) <= self.fragment_limit:
            return
        # Old files stay on disk and can still be recovered after a restart.
        self.pending_fragment_files = dict(
            list(self.pending_fragment_files.items())[-self.fragment_limit:]
        )

    def _reschedule_delete(
        self,
        key: str,
        expected_sig: FileSignature,
        attempts: int,
        now: float,
    ) -> None:
        delay = min(5.0, 0.25 * (2 ** min(attempts, 5)))
        self.pending_deletes[key] = (expected_sig, attempts + 1, now + delay)
