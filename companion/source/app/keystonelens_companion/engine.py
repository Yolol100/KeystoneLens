from __future__ import annotations

from dataclasses import replace
import queue
import threading
import time
from typing import Callable

from .constants import ACTIVITY_TO_DUNGEON, REGION_NAMES
from .registries import canonical_dungeon_name, DUNGEON_TO_SEASON
from .models import ApplicantView, EngineState, Listing, PartyMember, Snapshot, WCLResult
from .rio import RIOClient, RIOResult
from .scoring import calculate_score
from .util import realm_slug, split_name_realm
from .wcl import WCLClient


def _listing_context(value: Listing | None) -> tuple[str, int]:
    """Return the stable enrichment identity for a listing."""
    if value is None:
        return ("", 0)
    return (value.dungeon_name.casefold(), int(value.key_level or 0))


def _same_character_context(old: ApplicantView | None, applicant, listing: Listing | None, region: str) -> bool:
    """Keep enrichment only when character and listing context are unchanged."""
    return bool(
        old
        and old.applicant.name == applicant.name
        and old.applicant.spec_id == applicant.spec_id
        and old.applicant.role_byte == applicant.role_byte
        and _listing_context(old.snapshot_listing) == _listing_context(listing)
        and old.region == region
    )


def _result_matches_listing(result: WCLResult | RIOResult | None, listing: Listing | None) -> bool:
    """Validate cached online evidence against the current listing context."""
    return bool(
        result
        and not result.error
        and listing is not None
        and result.dungeon_name == listing.dungeon_name
        and result.target_key == int(listing.key_level or 0)
    )


class ApplicantEngine:
    """Authoritative LFG mirror with asynchronous Raider.IO/WCL enrichment.

    WoW remains source-of-truth for who is actually in the applicant pool and
    party. Online services enrich only currently visible identities and can never
    resurrect a player removed by a later APS1 snapshot.
    """

    def __init__(
        self,
        wcl: WCLClient | None,
        on_update: Callable[[EngineState], None],
        rio: RIOClient | None = None,
    ):
        self.wcl = wcl
        self.rio = rio
        self.on_update = on_update
        self._lock = threading.Lock()
        self._views: dict[str, ApplicantView] = {}
        self._party: tuple[PartyMember, ...] = ()
        self._listing: Listing | None = None
        self._listing_generation = 0
        self._listing_closed = False
        self._revision = 0

        self._queue: queue.Queue[tuple[str, int, str, str, int, str, int, str]] = queue.Queue()
        self._pending: set[tuple[str, str, int, int, str, int]] = set()
        self._rio_queue: queue.Queue[tuple[str, int, str, str, str, str, int, str]] = queue.Queue()
        self._rio_pending: set[tuple[str, str, int, str, str, int]] = set()

        self._default_realm = ""
        self._region = "EU"
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run_worker, daemon=True, name="KL-WCLWorker")
        self._rio_worker = threading.Thread(target=self._run_rio_worker, daemon=True, name="KL-RIOWorker")
        self._worker.start()
        self._rio_worker.start()
        self._status = "Open a Mythic+ Group Finder listing"
        self._lfg_unavailable = False
        self._applicants_unavailable = False
        self._roster_unavailable = False

    def stop(self) -> None:
        self._stop.set()
        self._worker.join(timeout=1.0)
        self._rio_worker.join(timeout=1.0)

    def _clear_enrichment_queues_locked(self) -> None:
        """Drop queued online lookups when the WoW bridge ends a session.

        A request already in flight cannot be cancelled safely, but its result is
        revision-checked and ignored. This prevents a large old applicant queue
        from continuing to hit Raider.IO/WCL after `/kl off`.
        """
        for work_queue in (self._queue, self._rio_queue):
            while True:
                try:
                    work_queue.get_nowait()
                except queue.Empty:
                    break
                else:
                    work_queue.task_done()
        self._pending.clear()
        self._rio_pending.clear()

    def set_wcl(self, client: WCLClient | None) -> None:
        with self._lock:
            self.wcl = client
            if client is None:
                for view in self._views.values():
                    view.wcl = None
                    view.wcl_status = "disabled"
                    view.score = calculate_score(
                        view.applicant, view.snapshot_listing, None, view.rio,
                    )
            else:
                for view in self._views.values():
                    if view.wcl is None:
                        view.wcl_status = "queued"
                self._queue_missing_wcl_locked()
            self._emit_locked()

    def handle_snapshot(self, snapshot: Snapshot) -> bool:
        with self._lock:
            incoming_generation = max(0, min(255, int(snapshot.listing_generation or 0)))

            # New Bridges stamp each LFG listing instance into the formerly
            # reserved header byte. This is deliberately separate from the
            # listing fields: a re-queue can use the exact same dungeon, key,
            # title and comment but must still start with an empty applicant
            # list. Older Bridges emit 0 and keep the legacy behavior.
            if incoming_generation and self._listing_generation:
                if incoming_generation != self._listing_generation:
                    if not _generation_is_newer(incoming_generation, self._listing_generation):
                        # A late screenshot from the previous queue must never
                        # resurrect old applicants after a re-queue.
                        return False
                    self._clear_enrichment_queues_locked()
                    self._views.clear()
                    self._listing = None
                    self._listing_generation = incoming_generation
                    self._listing_closed = False
                elif self._listing_closed and snapshot.listing is not None and not snapshot.terminal_clear:
                    # We already observed this generation end. A delayed full
                    # frame from the same generation is stale; wait for the
                    # next listing generation instead of restoring its rows.
                    return False
            elif incoming_generation:
                self._listing_generation = incoming_generation

            if snapshot.terminal_clear:
                self._clear_enrichment_queues_locked()
                self._views.clear()
                self._party = ()
                self._listing = None
                if incoming_generation:
                    self._listing_generation = incoming_generation
                    self._listing_closed = True
                else:
                    self._listing_generation = 0
                    self._listing_closed = False
                self._revision += 1
                self._status = "Open a Mythic+ Group Finder listing"
                self._lfg_unavailable = False
                self._applicants_unavailable = False
                self._roster_unavailable = False
                self._emit_locked()
                return True

            # If Blizzard temporarily blocks all LFG reads we cannot trust any
            # applicant state. Preserve the last known-good list unchanged.
            if snapshot.lfg_unavailable:
                self._lfg_unavailable = True
                self._applicants_unavailable = snapshot.applicants_unavailable
                self._roster_unavailable = snapshot.roster_unavailable
                self._status = "Group Finder data temporarily unavailable • keeping last valid list"
                self._emit_locked()
                return True

            listing = snapshot.listing
            if listing:
                canonical_name = canonical_dungeon_name(listing.dungeon_name)
                if canonical_name in DUNGEON_TO_SEASON:
                    if canonical_name != listing.dungeon_name:
                        listing = replace(listing, dungeon_name=canonical_name)
                else:
                    # Legacy activity IDs are only a defensive fallback. New
                    # season activities are resolved live by WoW's
                    # C_LFGList.GetActivityInfoTable and then canonicalized above.
                    mapped = ACTIVITY_TO_DUNGEON.get(listing.activity_id)
                    if mapped:
                        listing = replace(listing, dungeon_name=mapped)

            old_region = self._region
            if snapshot.version:
                region = REGION_NAMES.get(snapshot.version.region_id, self._region)
                _, default_realm = split_name_realm(snapshot.version.player_name, self._default_realm)
                self._region = region
                self._default_realm = default_realm
            else:
                # Version/player context is an independent transport domain. A
                # partial frame may omit it, so never silently turn a US/KR/TW
                # session into EU or forget the last confirmed default realm.
                region = self._region
                default_realm = self._default_realm

            self._revision += 1
            revision = self._revision
            old_listing = self._listing
            partial_applicants = snapshot.applicants_unavailable
            listing_missing_partial = partial_applicants and listing is None and old_listing is not None
            effective_listing = old_listing if listing_missing_partial else listing
            self._listing = effective_listing

            new_enrichment_context = _listing_context(effective_listing)
            if (_listing_context(old_listing), old_region) != (new_enrichment_context, region):
                # Old queued requests cannot enrich the new dungeon/key/region.
                # Drop them immediately; any request already in flight is still
                # rejected by the per-view revision/context checks.
                self._clear_enrichment_queues_locked()

            def view_for_context(applicant, old: ApplicantView | None) -> ApplicantView:
                same_character_context = _same_character_context(old, applicant, effective_listing, region)
                same_wcl_context = bool(same_character_context and _result_matches_listing(old.wcl, effective_listing))
                same_rio_context = bool(same_character_context and _result_matches_listing(old.rio, effective_listing))
                view = ApplicantView(
                    applicant=applicant,
                    snapshot_listing=effective_listing,
                    region=region,
                    wcl=old.wcl if same_wcl_context else None,
                    wcl_status=(
                        old.wcl_status if same_wcl_context else ("queued" if self.wcl else "disabled")
                    ),
                    updated_at=time.time(),
                    revision=old.revision if same_character_context else revision,
                    rio=old.rio if same_rio_context else None,
                    rio_status=(
                        old.rio_status if same_rio_context else ("queued" if self.rio else "disabled")
                    ),
                )
                view.score = calculate_score(applicant, effective_listing, view.wcl, view.rio)
                return view

            # A v13/partial snapshot can contain every applicant Blizzard could
            # read in this frame. Merge those rows into the last authoritative
            # list instead of discarding the entire snapshot. Missing rows are
            # never deleted until a later complete snapshot proves they are gone.
            # If the listing context changed in the same generation, retain the
            # missing identities but re-contextualize them and invalidate stale
            # online enrichment before re-queueing it.
            new_views: dict[str, ApplicantView] = {}
            if partial_applicants:
                for identity, old in self._views.items():
                    new_views[identity] = view_for_context(old.applicant, old)

            for applicant in snapshot.applicants:
                old = self._views.get(applicant.identity)
                new_views[applicant.identity] = view_for_context(applicant, old)
            self._views = new_views

            if not snapshot.roster_unavailable:
                self._party = snapshot.party
            self._roster_unavailable = snapshot.roster_unavailable
            self._lfg_unavailable = False
            self._applicants_unavailable = partial_applicants

            if snapshot.listing is None:
                # A partial/no-listing frame is not authoritative enough to
                # clear a healthy list. Terminal-clear owns that transition.
                if not partial_applicants:
                    self._views.clear()
                    if incoming_generation:
                        self._listing_closed = True
                self._status = (
                    "Group Finder data temporarily unavailable • keeping last valid list"
                    if partial_applicants else "Open a Mythic+ Group Finder listing"
                )
            elif partial_applicants:
                if incoming_generation:
                    self._listing_closed = False
                self._status = f"{len(self._views)} applicants • partial data • {region}"
            elif snapshot.roster_unavailable:
                if incoming_generation:
                    self._listing_closed = False
                self._status = "Party temporarily unreadable • applicants are kept"
            else:
                if incoming_generation:
                    self._listing_closed = False
                self._status = "Waiting for applicants" if not new_views else f"{len(new_views)} applicants • {region}"

            self._emit_locked()
            queued = False
            if self.rio and self._views:
                self._queue_missing_rio_locked(default_realm=default_realm)
                queued = True
            if self.wcl and self._views:
                self._queue_missing_wcl_locked(default_realm=default_realm)
                queued = True
            if queued:
                self._emit_locked()
            return True

    def _queue_missing_rio_locked(self, default_realm: str | None = None) -> None:
        if default_realm is not None:
            self._default_realm = default_realm
        if not self.rio:
            return
        for identity, view in self._views.items():
            if view.rio is not None or not view.snapshot_listing:
                continue
            dungeon = view.snapshot_listing.dungeon_name
            target = view.snapshot_listing.key_level
            name, realm = split_name_realm(view.applicant.name, self._default_realm)
            if not name or not realm or not dungeon:
                continue
            role = "tank" if view.applicant.role_byte == 0 else "healer" if view.applicant.role_byte == 1 else "dps"
            key = (name.casefold() + "@" + realm.casefold(), dungeon.casefold(), target, view.region, role, view.revision)
            if key in self._rio_pending:
                continue
            self._rio_pending.add(key)
            view.rio_status = "loading"
            self._rio_queue.put((identity, view.revision, name, realm, view.region, dungeon, target, role))

    def _queue_missing_wcl_locked(self, default_realm: str | None = None) -> None:
        if default_realm is not None:
            self._default_realm = default_realm
        if not self.wcl:
            return
        for identity, view in self._views.items():
            if view.wcl is not None or not view.snapshot_listing:
                continue
            dungeon = view.snapshot_listing.dungeon_name
            target = view.snapshot_listing.key_level
            if not dungeon:
                continue
            name, realm = split_name_realm(view.applicant.name, self._default_realm)
            if not name or not realm:
                continue
            key = (
                name.casefold() + "@" + realm.casefold(), dungeon.casefold(),
                view.applicant.spec_id, target, view.region, view.revision,
            )
            if key in self._pending:
                continue
            self._pending.add(key)
            view.wcl_status = "loading"
            self._queue.put((
                identity, view.revision, name, realm, view.applicant.spec_id,
                dungeon, target, view.region,
            ))

    def _run_rio_worker(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._rio_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            identity, queued_revision, name, realm, region, dungeon, target, role = item
            client = self.rio
            if client is None:
                result: RIOResult | None = None
            else:
                try:
                    result = client.fetch_character(
                        name, realm_slug(realm), region, dungeon, target, role,
                    )
                except Exception as exc:
                    result = RIOResult(
                        name, realm, region, dungeon, target,
                        fetched_at=time.time(), error=str(exc),
                    )
            if self._stop.is_set():
                self._rio_queue.task_done()
                continue
            with self._lock:
                self._rio_pending.discard((
                    name.casefold() + "@" + realm.casefold(), dungeon.casefold(), target, region, role, queued_revision,
                ))
                stale_client = client is not self.rio
                view = self._views.get(identity)
                same_context = bool(
                    view
                    and view.revision == queued_revision
                    and view.snapshot_listing
                    and view.snapshot_listing.dungeon_name == dungeon
                    and view.snapshot_listing.key_level == target
                    and view.region == region
                )
                current_name, current_realm = split_name_realm(view.applicant.name, realm) if view else ("", "")
                same_character = bool(
                    current_name.casefold() == name.casefold()
                    and current_realm.casefold() == realm.casefold()
                )
                if not stale_client and view and same_context and same_character:
                    view.rio = result
                    if result is None:
                        view.rio_status = "disabled"
                    elif result.error:
                        view.rio_status = "error"
                    elif result.not_found:
                        view.rio_status = "none"
                    else:
                        view.rio_status = "ready"
                    view.score = calculate_score(
                        view.applicant, view.snapshot_listing, view.wcl, result,
                    )
                    view.updated_at = time.time()
                if self.rio is not None:
                    self._queue_missing_rio_locked()
                self._emit_locked()
            self._rio_queue.task_done()

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
                    fetched = client.fetch_batch_current_dungeon(jobs)
                    results = list(fetched) if isinstance(fetched, (list, tuple)) else []
                except Exception as exc:
                    results = [
                        WCLResult(name, realm, dungeon, spec_id, None, time.time(), target_key=target, error=str(exc))
                        for _identity, _revision, name, realm, spec_id, dungeon, target, _region in batch
                    ]
                if len(results) != len(batch):
                    normalized = list(results[:len(batch)])
                    for item in batch[len(normalized):]:
                        _identity, _revision, name, realm, spec_id, dungeon, target, _region = item
                        normalized.append(WCLResult(
                            name, realm, dungeon, spec_id, None, time.time(),
                            target_key=target, error="WCL antwoord incompleet",
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
                        name.casefold() + "@" + realm.casefold(), dungeon.casefold(),
                        spec_id, target, region, queued_revision,
                    ))
                    if stale_client:
                        continue
                    view = self._views.get(identity)
                    same_context = bool(
                        view
                        and view.revision == queued_revision
                        and view.snapshot_listing
                        and view.snapshot_listing.dungeon_name == dungeon
                        and view.snapshot_listing.key_level == target
                    )
                    current_name, current_realm = split_name_realm(view.applicant.name, realm) if view else ("", "")
                    same_character = bool(
                        current_name.casefold() == name.casefold()
                        and current_realm.casefold() == realm.casefold()
                    )
                    same_spec = bool(view and view.applicant.spec_id == spec_id)
                    if view and same_context and same_character and same_spec:
                        view.wcl = result
                        if result is None:
                            view.wcl_status = "disabled"
                        elif result.error:
                            view.wcl_status = "error"
                        elif result.not_found or (
                            not result.bracket
                            and not result.metric_brackets
                        ):
                            view.wcl_status = "none"
                        else:
                            view.wcl_status = "ready"
                        view.score = calculate_score(
                            view.applicant, view.snapshot_listing, result, view.rio,
                        )
                        view.updated_at = time.time()
                if self.wcl is not None:
                    self._queue_missing_wcl_locked()
                self._emit_locked()
            for _ in batch:
                self._queue.task_done()

    def _emit_locked(self) -> None:
        rows = tuple(sorted(self._views.values(), key=ranking_key))
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


def ranking_key(view: ApplicantView) -> tuple:
    """Deterministic order using only the two visible scoring pillars.

    Rows still loading online evidence stay below resolved rows so an interim
    half-score is never presented as if it were the finished ranking.
    """
    unresolved = (
        view.rio_status in {"queued", "loading"}
        or view.wcl_status in {"queued", "loading"}
    )
    score = view.score.score if view.score else -1
    rio_component = view.score.rio_score if view.score else -1.0
    wcl_component = view.score.wcl_score if view.score and view.score.wcl_score is not None else -1.0
    return (
        1 if unresolved else 0,
        -score,
        -rio_component,
        -wcl_component,
        view.applicant.name.casefold(),
        view.applicant.identity,
    )


def _generation_is_newer(candidate: int, current: int) -> bool:
    """Return whether an 8-bit non-zero listing generation is forward.

    The Bridge cycles 1..255. Treat a forward distance below half the ring as
    newer; the opposite direction is a delayed/stale screenshot.
    """
    if candidate <= 0 or current <= 0 or candidate == current:
        return False
    delta = (candidate - current) % 255
    return 0 < delta <= 127
