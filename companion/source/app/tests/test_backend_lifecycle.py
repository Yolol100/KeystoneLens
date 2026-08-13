from __future__ import annotations

import struct
import time
import zlib

from keystonelens_companion.aps1 import MAGIC, parse_snapshot
from keystonelens_companion.models import Applicant, Listing, Snapshot
from keystonelens_companion.rio import RIOClient
from keystonelens_companion.wcl import WCLCache, WCLClient, _reduce_ranks
from keystonelens_companion.engine import ApplicantEngine, _generation_is_newer


def _minimal_packet(version: int = 12, *, generation: int = 1, flags: int = 0) -> bytes:
    body = bytes([0, 0, 0]) + struct.pack(">H", 0) + struct.pack(">H", 0)
    total = 4 + 1 + 2 + 1 + 1 + len(body) + 4
    prefix = MAGIC + bytes([version]) + struct.pack(">H", total) + bytes([flags, generation]) + body
    return prefix + struct.pack(">I", zlib.crc32(prefix) & 0xFFFFFFFF)


def test_minimal_current_aps1_snapshot_round_trip():
    snapshot = parse_snapshot(_minimal_packet(12, generation=7))
    assert snapshot.listing is None
    assert snapshot.applicants == ()
    assert snapshot.party == ()
    assert snapshot.listing_generation == 7


def test_closed_rio_client_never_starts_a_later_lookup():
    client = RIOClient()
    called = []
    client._http.get = lambda *a, **k: called.append((a, k))  # type: ignore[method-assign]
    client.close()
    result = client.fetch_character("A", "Realm", "EU", "Dungeon", 10, "DPS")
    assert result.error == "Raider.IO client closed"
    assert called == []


def test_closed_wcl_client_forgets_secret_and_returns_without_network(tmp_path):
    client = WCLClient("id", "top-secret", WCLCache(tmp_path / "wcl.json"))
    called = []
    client._http.post = lambda *a, **k: called.append((a, k))  # type: ignore[method-assign]
    client.close()
    result = client.fetch_batch_current_dungeon([
        ("A", "realm", "Realm", "EU", 71, "Dungeon", 10),
    ])
    assert len(result) == 1 and result[0].error == "WCL client closed"
    assert client.client_secret == ""
    assert called == []


def test_wcl_rank_reduction_uses_only_matching_finite_percentiles():
    bracket = _reduce_ranks([
        {"spec": "Arms", "rankPercent": 80},
        {"spec": "Arms", "rankPercent": 60},
        {"spec": "Fury", "rankPercent": 100},
        {"spec": "Arms", "rankPercent": 150},
    ], "Arms")
    assert bracket is not None
    assert bracket.run_count == 2
    assert bracket.best_percentile == 80
    assert bracket.average_percentile == 70


def test_engine_rejects_stale_listing_generation_and_wraps_forward():
    updates = []
    engine = ApplicantEngine(None, updates.append, rio=None)
    try:
        listing = Listing(activity_id=1, key_level=10, dungeon_name="Dungeon")
        a1 = Applicant(1, 1, 1, 71, 600, 0, 0, 2, "One-Realm")
        a2 = Applicant(2, 1, 1, 71, 600, 0, 0, 2, "Two-Realm")
        engine.handle_snapshot(Snapshot(listing, None, (a1,), listing_generation=255))
        assert [r.applicant.name for r in updates[-1].rows] == ["One-Realm"]

        # 1 is the next generation after 255 on the Bridge's 1..255 ring.
        assert _generation_is_newer(1, 255)
        engine.handle_snapshot(Snapshot(listing, None, (a2,), listing_generation=1))
        assert [r.applicant.name for r in updates[-1].rows] == ["Two-Realm"]

        count = len(updates)
        engine.handle_snapshot(Snapshot(listing, None, (a1,), listing_generation=255))
        assert len(updates) == count
        assert [r.applicant.name for r in updates[-1].rows] == ["Two-Realm"]
    finally:
        engine.stop()


def _current_packet_with_one_applicant(*, version: int = 12, generation: int = 9) -> bytes:
    assert version in (12, 13)
    body = bytearray()
    body += b"\x00"  # no listing
    body += b"\x00"  # no version block
    body += b"\x00"  # no leader-key block
    body += struct.pack(">H", 1)
    body += struct.pack(">I", 0x01020304)  # applicant id
    body += b"\x02"  # member index
    body += b"\x08"  # class id
    body += struct.pack(">H", 71)  # spec id
    body += struct.pack(">H", 639)  # item level
    body += struct.pack(">H", 2468)  # Raider.IO current score
    body += struct.pack(">H", 2501)  # Raider.IO main score
    body += b"\x01"  # RIO profile present
    body += bytes([14, 13, 4, 5, 6, 7, 8])
    body += b"\x02"  # role byte (DPS)
    name = b"Applicant-Realm"
    body += bytes([len(name)]) + name
    body += b"\x03"  # application has 3 members
    body += struct.pack(">H", 3123)  # Blizzard M+ score
    body += bytes([12, 15])  # Blizzard dungeon/best keys
    body += struct.pack(">H", 0)  # roster count
    total = 4 + 1 + 2 + 1 + 1 + len(body) + 4
    prefix = MAGIC + bytes([version]) + struct.pack(">H", total) + bytes([0, generation]) + bytes(body)
    return prefix + struct.pack(">I", zlib.crc32(prefix) & 0xFFFFFFFF)


def test_current_v12_applicant_layout_matches_lua_writer_exactly():
    snapshot = parse_snapshot(_current_packet_with_one_applicant(version=12))
    assert len(snapshot.applicants) == 1
    applicant = snapshot.applicants[0]
    assert applicant.applicant_id == 0x01020304
    assert applicant.member_idx == 2
    assert applicant.class_id == 8
    assert applicant.spec_id == 71
    assert applicant.ilvl == 639
    assert applicant.rio_score == 2468
    assert applicant.rio_main_score == 2501
    assert applicant.rio_profile is True
    assert applicant.rio_best_key == 14
    assert applicant.rio_best_dungeon_key == 13
    assert applicant.rio_timed_at_or_above == 4
    assert applicant.rio_timed_at_or_above_minus1 == 5
    assert applicant.rio_timed_at_or_above_minus2 == 6
    assert applicant.rio_completed_at_or_above_minus1 == 7
    assert applicant.rio_dungeon_count == 8
    assert applicant.role_byte == 2
    assert applicant.name == "Applicant-Realm"
    assert applicant.application_member_count == 3
    assert applicant.blizzard_score == 3123
    assert applicant.blizzard_best_dungeon_key == 12
    assert applicant.blizzard_best_key == 15


def test_current_v13_partial_layout_uses_same_applicant_record_shape():
    snapshot = parse_snapshot(_current_packet_with_one_applicant(version=13, generation=10))
    applicant = snapshot.applicants[0]
    assert applicant.application_member_count == 3
    assert applicant.blizzard_score == 3123
    assert applicant.name == "Applicant-Realm"


def test_rio_current_profile_shape_preserves_dungeon_role_and_recent_evidence():
    from keystonelens_companion.rio import _parse_profile

    payload = {
        "name": "Applicant",
        "mythic_plus_scores_by_season": [{"scores": {"all": 2500, "dps": 2400, "tank": 900}}],
        "mythic_plus_best_runs": [
            {
                "dungeon": "Skyreach",
                "mythic_level": 12,
                "score": 275.5,
                "clear_time_ms": 1_000_000,
                "keystone_time_ms": 1_100_000,
                "num_chests": 1,
            },
            {
                "dungeon": "Other Dungeon",
                "mythic_level": 15,
                "score": 300.0,
                "clear_time_ms": 1_200_000,
                "keystone_time_ms": 1_100_000,
                "num_chests": 0,
            },
        ],
        "mythic_plus_recent_runs": [
            {"dungeon": "Skyreach", "mythic_level": 10, "num_chests": 1},
            {"dungeon": "Skyreach", "mythic_level": 8, "num_chests": 0, "clear_time_ms": 900, "keystone_time_ms": 1000},
            {"dungeon": "Other Dungeon", "mythic_level": 14, "num_chests": 1},
        ],
    }
    result = _parse_profile(payload, "Applicant", "Realm", "EU", "Skyreach", 10, 1234.0, "dps")
    assert result.score == 2500
    assert result.role_score == 2400
    assert result.role_score_available is True
    assert result.best_key == 15
    assert result.best_dungeon_key == 12
    assert result.best_dungeon_run_score == 275.5
    assert result.best_dungeon_score_key == 12
    assert result.recent_runs == 3
    assert result.recent_dungeon_runs == 2
    assert result.recent_dungeon_timed == 2
    assert result.recent_dungeon_targetish == 2


class _FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload


def test_wcl_graphql_character_shape_reduces_current_metrics_without_network(tmp_path):
    client = WCLClient("id", "secret", WCLCache(tmp_path / "wcl.json"))
    captured = []
    payload = {
        "data": {
            "rateLimitData": {"limitPerHour": 3600, "pointsSpentThisHour": 12, "pointsResetIn": 600},
            "characterData": {
                "c0": {
                    "name": "Applicant",
                    "run": {"ranks": [
                        {"spec": "Arms", "rankPercent": 80.0},
                        {"spec": "Arms", "rankPercent": 90.0},
                    ]},
                    "speed": {"ranks": [{"spec": "Arms", "rankPercent": 70.0}]},
                    "throughput": {"ranks": [{"spec": "Arms", "rankPercent": 75.0}]},
                    "damage": {"ranks": [{"spec": "Arms", "rankPercent": 73.0}]},
                    "bossdamage": {"ranks": [{"spec": "Arms", "rankPercent": 77.0}]},
                }
            },
        }
    }

    def fake_post(body):
        captured.append(body)
        return _FakeResponse(payload)

    client._post_graphql = fake_post  # type: ignore[method-assign]
    results = client.fetch_batch_current_dungeon([
        ("Applicant", "realm", "Realm", "EU", 71, "Skyreach", 10),
    ])
    client.close()
    assert len(captured) == 1
    assert "metric:playerscore" in captured[0]["query"]
    assert "metric:playerspeed" in captured[0]["query"]
    assert "metric:wdps" in captured[0]["query"]
    assert len(results) == 1
    result = results[0]
    assert result.error == ""
    assert result.not_found is False
    assert result.bracket is not None
    assert result.bracket.run_count == 2
    assert result.bracket.best_percentile == 90.0
    assert result.bracket.average_percentile == 85.0
    assert set(result.metric_brackets) == {"playerspeed", "wdps", "dps", "bossdps"}


def test_partial_snapshot_keeps_missing_applicants_when_listing_context_changes():
    from keystonelens_companion.models import WCLBracket, WCLResult
    from keystonelens_companion.rio import RIOResult

    updates = []
    engine = ApplicantEngine(None, updates.append, rio=None)
    try:
        old_listing = Listing(activity_id=1, key_level=10, dungeon_name="Dungeon A", listing_name="Old")
        new_listing = Listing(activity_id=2, key_level=11, dungeon_name="Dungeon B", listing_name="Edited")
        a = Applicant(1, 1, 1, 71, 600, 0, 0, 2, "One-Realm")
        b = Applicant(2, 1, 1, 71, 600, 0, 0, 2, "Two-Realm")
        engine.handle_snapshot(Snapshot(old_listing, None, (a, b), listing_generation=9))

        old_b_revision = engine._views[b.identity].revision
        engine._views[b.identity].wcl = WCLResult(
            name="Two", realm="Realm", dungeon_name="Dungeon A", spec_id=71,
            bracket=WCLBracket(10, 80.0, 75.0, 3, 77.0), fetched_at=time.time(), target_key=10,
        )
        engine._views[b.identity].wcl_status = "ready"
        engine._views[b.identity].rio = RIOResult(
            name="Two", realm="Realm", region="EU", dungeon_name="Dungeon A", target_key=10,
            score=2500, fetched_at=time.time(),
        )
        engine._views[b.identity].rio_status = "ready"

        # Blizzard could read only applicant A in this v13/partial frame while
        # the listing itself changed. B must remain until a complete snapshot
        # authoritatively removes it, but old Dungeon A enrichment is stale.
        engine.handle_snapshot(Snapshot(
            new_listing, None, (a,), listing_generation=9, applicants_unavailable=True,
        ))

        state = updates[-1]
        assert {row.applicant.name for row in state.rows} == {"One-Realm", "Two-Realm"}
        preserved_b = engine._views[b.identity]
        assert preserved_b.snapshot_listing == new_listing
        assert preserved_b.wcl is None and preserved_b.rio is None
        assert preserved_b.wcl_status == "disabled"
        assert preserved_b.rio_status == "disabled"
        assert preserved_b.revision > old_b_revision
    finally:
        engine.stop()


def test_partial_snapshot_with_missing_listing_keeps_last_listing_and_rows():
    updates = []
    engine = ApplicantEngine(None, updates.append, rio=None)
    try:
        listing = Listing(activity_id=1, key_level=10, dungeon_name="Dungeon A")
        a = Applicant(1, 1, 1, 71, 600, 0, 0, 2, "One-Realm")
        engine.handle_snapshot(Snapshot(listing, None, (a,), listing_generation=4))
        engine.handle_snapshot(Snapshot(
            None, None, (), listing_generation=4, applicants_unavailable=True,
        ))
        state = updates[-1]
        assert state.listing == listing
        assert [row.applicant.name for row in state.rows] == ["One-Realm"]
        assert "keeping last valid list" in state.status
    finally:
        engine.stop()


def test_partial_snapshot_without_version_preserves_confirmed_region_and_realm():
    from keystonelens_companion.models import VersionInfo

    updates = []
    engine = ApplicantEngine(None, updates.append, rio=None)
    try:
        listing = Listing(activity_id=1, key_level=10, dungeon_name="Dungeon A")
        a = Applicant(1, 1, 1, 71, 600, 0, 0, 2, "One")
        version = VersionInfo(addon_version="x", game_version="x", region_id=1, player_name="Leader-Illidan")
        engine.handle_snapshot(Snapshot(listing, version, (a,), listing_generation=5))
        assert engine._region == "US"
        assert engine._default_realm == "Illidan"

        engine.handle_snapshot(Snapshot(
            None, None, (), listing_generation=5, applicants_unavailable=True,
        ))
        assert engine._region == "US"
        assert engine._default_realm == "Illidan"
        assert updates[-1].rows[0].region == "US"
    finally:
        engine.stop()


def test_listing_title_edit_does_not_invalidate_same_dungeon_enrichment_context():
    from keystonelens_companion.models import WCLBracket, WCLResult
    from keystonelens_companion.rio import RIOResult

    updates = []
    engine = ApplicantEngine(None, updates.append, rio=None)
    try:
        old_listing = Listing(activity_id=1, key_level=10, dungeon_name="Dungeon A", listing_name="Old")
        edited_listing = Listing(activity_id=1, key_level=10, dungeon_name="Dungeon A", listing_name="New title")
        a = Applicant(1, 1, 1, 71, 600, 0, 0, 2, "One-Realm")
        engine.handle_snapshot(Snapshot(old_listing, None, (a,), listing_generation=7))
        view = engine._views[a.identity]
        revision = view.revision
        view.wcl = WCLResult(
            "One", "Realm", "Dungeon A", 71, WCLBracket(10, 80.0, 75.0, 2, 77.0),
            time.time(), target_key=10,
        )
        view.wcl_status = "ready"
        view.rio = RIOResult("One", "Realm", "EU", "Dungeon A", 10, score=2500, fetched_at=time.time())
        view.rio_status = "ready"

        engine.handle_snapshot(Snapshot(edited_listing, None, (a,), listing_generation=7))
        updated = engine._views[a.identity]
        assert updated.snapshot_listing == edited_listing
        assert updated.revision == revision
        assert updated.wcl is not None and updated.rio is not None
    finally:
        engine.stop()


def test_stale_snapshot_rejection_preserves_newer_pending_fragments(tmp_path, monkeypatch):
    from keystonelens_companion import watcher as watcher_module
    from keystonelens_companion.watcher import ScreenshotWatcher

    updates = []
    engine = ApplicantEngine(None, updates.append, rio=None)
    try:
        listing = Listing(activity_id=1, key_level=10, dungeon_name="Dungeon")
        current = Applicant(2, 1, 1, 71, 600, 0, 0, 2, "Current-Realm")
        stale = Applicant(1, 1, 1, 71, 600, 0, 0, 2, "Stale-Realm")
        engine.handle_snapshot(Snapshot(listing, None, (current,), listing_generation=2))

        pending = tmp_path / "newer-fragment.png"
        pending.write_bytes(b"newer fragment")
        stale_file = tmp_path / "stale-complete.png"
        stale_file.write_bytes(b"stale complete")

        watcher = ScreenshotWatcher(tmp_path, engine.handle_snapshot)
        pending_sig = watcher.files.signature(pending)
        stale_sig = watcher.files.signature(stale_file)
        watcher.files.retain_fragment(pending, pending_sig)

        stale_snapshot = Snapshot(listing, None, (stale,), listing_generation=1)
        monkeypatch.setattr(
            watcher_module,
            "decode_image_result",
            lambda _path, _assembler: (True, True, stale_snapshot),
        )

        watcher._consume(stale_file, stale_sig, backfill=False)

        assert [row.applicant.name for row in updates[-1].rows] == ["Current-Realm"]
        assert pending.exists(), "rejecting a stale snapshot must not delete newer fragments"
        assert str(pending) in watcher.files.pending_fragment_files
    finally:
        engine.stop()


def test_completed_snapshot_does_not_delete_another_pending_fragment_stream(tmp_path, monkeypatch):
    """A complete stream must not consume recovery files owned by another stream."""
    from keystonelens_companion import watcher as watcher_module
    from keystonelens_companion.watcher import ScreenshotWatcher

    newer_fragment = tmp_path / "newer-stream-fragment.png"
    newer_fragment.write_bytes(b"newer fragment")
    completed_frame = tmp_path / "older-stream-complete.png"
    completed_frame.write_bytes(b"older complete")

    watcher = ScreenshotWatcher(tmp_path, lambda _snapshot: True)
    newer_sig = watcher.files.signature(newer_fragment)
    completed_sig = watcher.files.signature(completed_frame)
    watcher.files.retain_fragment(newer_fragment, newer_sig)
    # Model a second, still-incomplete FragmentAssembler stream. The complete
    # snapshot returned below belongs to another stream.
    watcher.assembler._streams[(99, 1)] = (time.time(), object(), {})  # type: ignore[assignment]

    snapshot = Snapshot(None, None, (), listing_generation=7)
    monkeypatch.setattr(
        watcher_module,
        "decode_image_result",
        lambda _path, _assembler: (True, True, snapshot),
    )

    watcher._consume(completed_frame, completed_sig, backfill=True)

    assert newer_fragment.exists(), "another incomplete stream must remain restart-recoverable"
    assert str(newer_fragment) in watcher.files.pending_fragment_files
