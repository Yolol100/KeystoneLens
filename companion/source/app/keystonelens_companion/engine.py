from __future__ import annotations

import queue
import threading
import time
from typing import Callable

from .constants import ACTIVITY_TO_DUNGEON, REGION_NAMES
from .models import ApplicantView, EngineState, Listing, Snapshot, WCLResult
from .util import realm_slug, split_name_realm
from .wcl import WCLClient


class ApplicantEngine:
    """Small WCL-only mirror of the current Mythic+ applicant list."""

    def __init__(self, wcl: WCLClient | None, on_update: Callable[[EngineState], None]):
        self.wcl = wcl
        self.on_update = on_update
        self._lock = threading.Lock()
        self._views: dict[str, ApplicantView] = {}
        self._party = ()
        self._listing: Listing | None = None
        self._listing_generation = 0
        self._revision = 0
        self._region = "EU"
        self._default_realm = ""
        self._status = "Open a Mythic+ Group Finder listing"
        self._lfg_unavailable = False
        self._applicants_unavailable = False
        self._roster_unavailable = False
        self._queue: queue.Queue[tuple[str, int, str, str, int, str, int, str]] = queue.Queue()
        self._pending: set[tuple[str, str, int, int, str, int]] = set()
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run_worker, daemon=True, name="KL-WCLWorker")
        self._worker.start()

    def stop(self) -> None:
        self._stop.set()
        if self._worker.is_alive() and self._worker is not threading.current_thread():
            self._worker.join(timeout=3.0)

    def set_wcl(self, client: WCLClient | None) -> None:
        with self._lock:
            self.wcl = client
            for view in self._views.values():
                view.wcl = None
                view.wcl_status = "queued" if client else "disabled"
                view.updated_at = time.time()
                view.revision = self._revision
            if client:
                self._queue_missing_locked()
            self._emit_locked()

    def handle_snapshot(self, snapshot: Snapshot) -> bool:
        with self._lock:
            incoming_generation = max(0, min(255, int(snapshot.listing_generation or 0)))
            if self._listing_generation and incoming_generation and incoming_generation != self._listing_generation:
                if not _generation_is_newer(incoming_generation, self._listing_generation):
                    return False
                self._listing_generation = incoming_generation
                self._views.clear()
            elif incoming_generation:
                self._listing_generation = incoming_generation

            self._revision += 1
            revision = self._revision

            if snapshot.version:
                self._region = REGION_NAMES.get(int(snapshot.version.region_id or 0), self._region)
                _player_name, player_realm = split_name_realm(snapshot.version.player_name, self._default_realm)
                if player_realm:
                    self._default_realm = player_realm

            if snapshot.terminal_clear:
                self._listing = None
                self._views.clear()
                self._party = ()
                self._status = "Open a Mythic+ Group Finder listing"
                self._lfg_unavailable = False
                self._applicants_unavailable = False
                self._roster_unavailable = False
                self._emit_locked()
                return True

            self._lfg_unavailable = bool(snapshot.lfg_unavailable)
            self._applicants_unavailable = bool(snapshot.applicants_unavailable)
            self._roster_unavailable = bool(snapshot.roster_unavailable)

            incoming_listing = _normalized_listing(snapshot.listing)
            if not snapshot.lfg_unavailable:
                listing_changed = _listing_key(incoming_listing) != _listing_key(self._listing)
                self._listing = incoming_listing
                if listing_changed:
                    for view in self._views.values():
                        view.wcl = None
                        view.wcl_status = "queued" if self.wcl else "disabled"
                        view.revision = revision

            if not snapshot.roster_unavailable:
                self._party = snapshot.party

            if not snapshot.applicants_unavailable:
                new_views: dict[str, ApplicantView] = {}
                for applicant in snapshot.applicants:
                    old = self._views.get(applicant.identity)
                    same_context = bool(
                        old
                        and old.applicant.name == applicant.name
                        and old.applicant.spec_id == applicant.spec_id
                        and old.region == self._region
                        and _listing_key(old.snapshot_listing) == _listing_key(self._listing)
                    )
                    if same_context:
                        old.applicant = applicant
                        old.snapshot_listing = self._listing
                        old.updated_at = time.time()
                        new_views[applicant.identity] = old
                    else:
                        new_views[applicant.identity] = ApplicantView(
                            applicant=applicant,
                            snapshot_listing=self._listing,
                            region=self._region,
                            wcl=None,
                            wcl_status="queued" if self.wcl else "disabled",
                            updated_at=time.time(),
                            revision=revision,
                        )
                self._views = new_views

            if self._listing is None:
                self._status = "Open a Mythic+ Group Finder listing"
            elif not self._views:
                self._status = "Waiting for applicants"
            else:
                self._status = f"{len(self._views)} applicant(s) • {self._region}"

            if self.wcl:
                self._queue_missing_locked()
            self._emit_locked()
            return True

    def _queue_missing_locked(self) -> None:
        if not self.wcl or not self._listing:
            return
        dungeon = self._listing.dungeon_name
        target = self._listing.key_level
        if not dungeon:
            return

        for identity, view in self._views.items():
            if view.wcl is not None or view.wcl_status == "loading":
                continue
            name, realm = split_name_realm(view.applicant.name, self._default_realm)
            if not name or not realm:
                view.wcl_status = "none"
                continue
            key = (
                name.casefold() + "@" + realm.casefold(),
                dungeon.casefold(),
                int(view.applicant.spec_id),
                int(target),
                view.region,
                int(view.revision),
            )
            if key in self._pending:
                continue
            self._pending.add(key)
            view.wcl_status = "loading"
            self._queue.put((
                identity,
                view.revision,
                name,
                realm,
                int(view.applicant.spec_id),
                dungeon,
                int(target),
                view.region,
            ))

    def _run_worker(self) -> None:
        while not self._stop.is_set():
            try:
                first = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            batch = [first]
            deadline = time.time() + 0.18
            while len(batch) < 10 and time.time() < deadline:
                try:
                    batch.append(self._queue.get(timeout=max(0.0, deadline - time.time())))
                except queue.Empty:
                    break

            client = self.wcl
            if client is None:
                results: list[WCLResult | None] = [None] * len(batch)
            else:
                jobs = [
                    (name, realm_slug(realm), realm, region, spec_id, dungeon, target)
                    for _identity, _revision, name, realm, spec_id, dungeon, target, region in batch
                ]
                try:
                    results = list(client.fetch_batch_current_dungeon(jobs))
                except Exception as exc:
                    results = [
                        WCLResult(
                            name=name,
                            realm=realm,
                            dungeon_name=dungeon,
                            spec_id=spec_id,
                            bracket=None,
                            fetched_at=time.time(),
                            target_key=target,
                            error=str(exc),
                        )
                        for _identity, _revision, name, realm, spec_id, dungeon, target, _region in batch
                    ]
                if len(results) != len(batch):
                    normalized = list(results[:len(batch)])
                    for item in batch[len(normalized):]:
                        _identity, _revision, name, realm, spec_id, dungeon, target, _region = item
                        normalized.append(WCLResult(
                            name=name,
                            realm=realm,
                            dungeon_name=dungeon,
                            spec_id=spec_id,
                            bracket=None,
                            fetched_at=time.time(),
                            target_key=target,
                            error="WCL response incomplete",
                        ))
                    results = normalized

            if self._stop.is_set():
                for _ in batch:
                    self._queue.task_done()
                continue

            with self._lock:
                stale_client = client is not self.wcl
                for item, result in zip(batch, results):
                    identity, queued_revision, name, realm, spec_id, dungeon, target, region = item
                    self._pending.discard((
                        name.casefold() + "@" + realm.casefold(),
                        dungeon.casefold(), spec_id, target, region, queued_revision,
                    ))
                    if stale_client:
                        continue
                    view = self._views.get(identity)
                    if not view or view.revision != queued_revision:
                        continue
                    current_name, current_realm = split_name_realm(view.applicant.name, realm)
                    if current_name.casefold() != name.casefold() or current_realm.casefold() != realm.casefold():
                        continue
                    if view.applicant.spec_id != spec_id or view.region != region:
                        continue
                    if not view.snapshot_listing or view.snapshot_listing.dungeon_name != dungeon:
                        continue

                    view.wcl = result
                    if result is None:
                        view.wcl_status = "disabled"
                    elif result.error:
                        view.wcl_status = "error"
                    elif result.not_found or not result.metric_brackets:
                        view.wcl_status = "none"
                    else:
                        view.wcl_status = "ready"
                    view.updated_at = time.time()

                if self.wcl:
                    self._queue_missing_locked()
                self._emit_locked()

            for _ in batch:
                self._queue.task_done()

    def _emit_locked(self) -> None:
        rows = tuple(sorted(self._views.values(), key=lambda view: view.applicant.name.casefold()))
        self.on_update(EngineState(
            listing=self._listing,
            rows=rows,
            party=self._party,
            status=self._status,
            revision=self._revision,
            lfg_unavailable=self._lfg_unavailable,
            applicants_unavailable=self._applicants_unavailable,
            roster_unavailable=self._roster_unavailable,
        ))


def _normalized_listing(listing: Listing | None) -> Listing | None:
    if listing is None:
        return None
    dungeon = listing.dungeon_name or ACTIVITY_TO_DUNGEON.get(int(listing.activity_id or 0), "")
    if dungeon == listing.dungeon_name:
        return listing
    return Listing(
        activity_id=listing.activity_id,
        key_level=listing.key_level,
        dungeon_name=dungeon,
        listing_name=listing.listing_name,
        comment=listing.comment,
        category_id=listing.category_id,
        difficulty_id=listing.difficulty_id,
    )


def _listing_key(listing: Listing | None) -> tuple[int, int, str]:
    if listing is None:
        return (0, 0, "")
    return (int(listing.activity_id or 0), int(listing.key_level or 0), listing.dungeon_name)


def _generation_is_newer(candidate: int, current: int) -> bool:
    if candidate <= 0 or current <= 0 or candidate == current:
        return False
    delta = (candidate - current) % 255
    return 0 < delta <= 127
