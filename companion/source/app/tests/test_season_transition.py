from __future__ import annotations

from datetime import date
from unittest.mock import Mock, patch

import pytest

from keystonelens_companion import engine, rio, ui
from keystonelens_companion.models import Applicant, ApplicantView, Listing, WCLBracket, WCLResult
from keystonelens_companion.registries import (
    MIDNIGHT_SEASON_1,
    season2_transition_phase,
    use_season1_carryover,
    wcl_source_season_for_dungeon,
)
from keystonelens_companion.wcl import WCLCache, WCLClient


def _applicant() -> Applicant:
    return Applicant(
        applicant_id=1,
        member_idx=1,
        class_id=1,
        spec_id=71,
        ilvl=300,
        rio_score=0,
        rio_main_score=0,
        role_byte=2,
        name="Applicant-Realm",
    )


def test_transition_is_week1_from_august_19_through_25_and_current_on_26():
    assert season2_transition_phase(date(2026, 8, 18)) == "preseason"
    assert season2_transition_phase(date(2026, 8, 19)) == "week1"
    assert season2_transition_phase(date(2026, 8, 25)) == "week1"
    assert season2_transition_phase(date(2026, 8, 26)) == "current"
    assert use_season1_carryover(date(2026, 8, 25)) is True
    assert use_season1_carryover(date(2026, 8, 26)) is False
    assert wcl_source_season_for_dungeon("Altar of Fangs", date(2026, 8, 25)) == "midnight-s1"
    assert wcl_source_season_for_dungeon("Altar of Fangs", date(2026, 8, 26)) == "midnight-s2"


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.headers = {}

    def json(self):
        return self._payload


def test_raiderio_week1_keeps_current_zero_and_loads_previous_score():
    current = _Response({
        "name": "Applicant",
        "mythic_plus_scores_by_season": [{"scores": {"all": 0, "dps": 0}}],
        "mythic_plus_best_runs": [],
        "mythic_plus_recent_runs": [],
    })
    previous = _Response({
        "name": "Applicant",
        "mythic_plus_scores_by_season": [{"scores": {"all": 2784, "dps": 2601}}],
    })
    client = rio.RIOClient()
    try:
        with patch.object(rio, "use_season1_carryover", return_value=True), \
             patch.object(client, "_get", side_effect=[current, previous]) as get:
            result = client.fetch_character("Applicant", "realm", "EU", "Altar of Fangs", 10, "dps")
        assert result.score == 0
        assert result.previous_score == 2784
        assert result.previous_role_score == 2601
        assert result.previous_role_score_available is True
        assert get.call_count == 2
        assert get.call_args_list[1].kwargs["params"]["fields"] == "mythic_plus_scores_by_season:previous"
    finally:
        client.close()


def test_raiderio_week2_stops_requesting_previous_season():
    current = _Response({
        "name": "Applicant",
        "mythic_plus_scores_by_season": [{"scores": {"all": 814, "dps": 814}}],
        "mythic_plus_best_runs": [],
        "mythic_plus_recent_runs": [],
    })
    client = rio.RIOClient()
    try:
        with patch.object(rio, "use_season1_carryover", return_value=False), \
             patch.object(client, "_get", return_value=current) as get:
            result = client.fetch_character("Applicant", "realm", "EU", "Altar of Fangs", 10, "dps")
        assert result.score == 814
        assert result.previous_score == 0
        assert get.call_count == 1
    finally:
        client.close()


def test_raiderio_previous_lookup_failure_does_not_break_current_score():
    current = _Response({
        "name": "Applicant",
        "mythic_plus_scores_by_season": [{"scores": {"all": 125, "dps": 125}}],
        "mythic_plus_best_runs": [],
        "mythic_plus_recent_runs": [],
    })
    previous_failure = _Response({}, status_code=500)
    client = rio.RIOClient()
    try:
        with patch.object(rio, "use_season1_carryover", return_value=True), \
             patch.object(client, "_get", side_effect=[current, previous_failure]):
            result = client.fetch_character("Applicant", "realm", "EU", "Altar of Fangs", 10, "dps")
        assert result.error == ""
        assert result.score == 125
        assert result.previous_score == 0
    finally:
        client.close()


def test_ui_shows_current_slash_previous_only_in_week1():
    view = ApplicantView(
        applicant=_applicant(),
        snapshot_listing=Listing(key_level=10, dungeon_name="Altar of Fangs"),
        region="EU",
        rio=rio.RIOResult(
            "Applicant", "realm", "EU", "Altar of Fangs", 10,
            score=0, previous_score=2784,
        ),
    )
    with patch.object(ui, "use_season1_carryover", return_value=True):
        assert ui._rio_rating_text(view) == "0 / 2784"
    with patch.object(ui, "use_season1_carryover", return_value=False):
        assert ui._rio_rating_text(view) == "0"

    view.rio = rio.RIOResult(
        "Applicant", "realm", "EU", "Altar of Fangs", 10,
        score=814, previous_score=2784,
    )
    with patch.object(ui, "use_season1_carryover", return_value=True):
        assert ui._rio_rating_text(view) == "814 / 2784"
    with patch.object(ui, "use_season1_carryover", return_value=False):
        assert ui._rio_rating_text(view) == "814"


def test_week1_wcl_aggregates_previous_season_without_persisting_in_s2_cache(tmp_path):
    cache = WCLCache(tmp_path / "wcl.json")
    client = WCLClient("id", "secret", cache)
    payload = {
        "data": {
            "rateLimitData": {"limitPerHour": 1000, "pointsSpentThisHour": 10, "pointsResetIn": 300},
            "characterData": {
                "c0": {
                    "name": "Applicant",
                    "s0": {"ranks": [{"spec": "Arms", "rankPercent": 70.0}]},
                    "s1": {"ranks": [{"spec": "Arms", "rankPercent": 80.0}]},
                    "s2": {"ranks": [{"spec": "Arms", "rankPercent": 90.0}]},
                }
            },
        }
    }
    try:
        with patch.object(client, "_post_graphql", return_value=_Response(payload)) as post:
            result = client.fetch_batch_previous_season([
                ("Applicant", "realm", "Realm", "EU", 71, "Altar of Fangs", 10),
            ])[0]
        assert result.source_season == MIDNIGHT_SEASON_1.key
        assert result.dungeon_name == "Altar of Fangs"
        assert result.target_key == 10
        assert result.bracket is not None
        assert result.bracket.run_count == 3
        assert result.bracket.average_percentile == pytest.approx(80.0)
        query = post.call_args.args[0]["query"]
        assert query.count("encounterRankings(") == len(MIDNIGHT_SEASON_1.dungeons)
        assert cache.count() == 0
    finally:
        client.close()


def test_engine_routes_week1_to_previous_wcl_and_week2_to_current():
    previous = WCLResult(
        "Applicant", "Realm", "Altar of Fangs", 71,
        WCLBracket(0, 80, 80, 1, 80), 1.0, target_key=10,
        source_season="midnight-s1",
    )
    current = WCLResult(
        "Applicant", "Realm", "Altar of Fangs", 71,
        WCLBracket(0, 55, 55, 1, 55), 1.0, target_key=10,
        source_season="midnight-s2",
    )

    class Client:
        def __init__(self):
            self.previous_calls = 0
            self.current_calls = 0
        def fetch_batch_previous_season(self, jobs):
            self.previous_calls += 1
            return [previous for _ in jobs]
        def fetch_batch_current_dungeon(self, jobs):
            self.current_calls += 1
            return [current for _ in jobs]

    jobs = [("Applicant", "realm", "Realm", "EU", 71, "Altar of Fangs", 10)]
    client = Client()
    with patch.object(engine, "use_previous_wcl_for_dungeon", return_value=True):
        assert engine._fetch_wcl_batch(client, jobs)[0] is previous
    assert client.previous_calls == 1
    assert client.current_calls == 0

    with patch.object(engine, "use_previous_wcl_for_dungeon", return_value=False):
        assert engine._fetch_wcl_batch(client, jobs)[0] is current
    assert client.current_calls == 1


def test_wcl_source_mismatch_is_invalidated_at_week2_cutover():
    listing = Listing(key_level=10, dungeon_name="Altar of Fangs")
    carryover = WCLResult(
        "Applicant", "Realm", "Altar of Fangs", 71,
        WCLBracket(0, 80, 80, 1, 80), 1.0, target_key=10,
        source_season="midnight-s1",
    )
    with patch.object(engine, "wcl_source_season_for_dungeon", return_value="midnight-s1"):
        assert engine._result_matches_listing(carryover, listing) is True
    with patch.object(engine, "wcl_source_season_for_dungeon", return_value="midnight-s2"):
        assert engine._result_matches_listing(carryover, listing) is False


@pytest.mark.parametrize(
    ("region", "pre", "start", "last_week1", "week2"),
    [
        ("US", date(2026, 8, 17), date(2026, 8, 18), date(2026, 8, 24), date(2026, 8, 25)),
        ("EU", date(2026, 8, 18), date(2026, 8, 19), date(2026, 8, 25), date(2026, 8, 26)),
        ("KR", date(2026, 8, 19), date(2026, 8, 20), date(2026, 8, 26), date(2026, 8, 27)),
        ("TW", date(2026, 8, 19), date(2026, 8, 20), date(2026, 8, 26), date(2026, 8, 27)),
        ("CN", date(2026, 8, 19), date(2026, 8, 20), date(2026, 8, 26), date(2026, 8, 27)),
    ],
)
def test_transition_uses_published_region_windows(region, pre, start, last_week1, week2):
    assert season2_transition_phase(pre, region=region) == "preseason"
    assert season2_transition_phase(start, region=region) == "week1"
    assert season2_transition_phase(last_week1, region=region) == "week1"
    assert season2_transition_phase(week2, region=region) == "current"


def test_unknown_region_falls_back_to_eu_window():
    assert season2_transition_phase(date(2026, 8, 18), region="UNKNOWN") == "preseason"
    assert season2_transition_phase(date(2026, 8, 19), region="UNKNOWN") == "week1"


def test_ui_uses_local_current_score_when_raiderio_api_lags_in_week1():
    applicant = _applicant()
    applicant.rio_score = 375
    view = ApplicantView(
        applicant=applicant,
        snapshot_listing=Listing(key_level=10, dungeon_name="Altar of Fangs"),
        region="EU",
        rio=rio.RIOResult(
            "Applicant", "realm", "EU", "Altar of Fangs", 10,
            score=0, previous_score=2784,
        ),
    )
    with patch.object(ui, "use_season1_carryover", return_value=True):
        assert ui._rio_rating_text(view) == "375 / 2784"


def test_raiderio_phase_change_invalidates_raw_profile_cache():
    current = _Response({
        "name": "Applicant",
        "mythic_plus_scores_by_season": [{"scores": {"all": 0, "dps": 0}}],
        "mythic_plus_best_runs": [],
        "mythic_plus_recent_runs": [],
    })
    previous = _Response({
        "name": "Applicant",
        "mythic_plus_scores_by_season": [{"scores": {"all": 2784, "dps": 2601}}],
    })
    phase = {"value": "preseason"}
    client = rio.RIOClient()
    try:
        with patch.object(rio, "season2_transition_phase", side_effect=lambda **_kw: phase["value"]), \
             patch.object(rio, "use_season1_carryover", side_effect=lambda **_kw: phase["value"] == "week1"), \
             patch.object(client, "_get", side_effect=[current, current, previous]) as get:
            first = client.fetch_character("Applicant", "realm", "EU", "Altar of Fangs", 10, "dps")
            assert first.previous_score == 0
            phase["value"] = "week1"
            second = client.fetch_character("Applicant", "realm", "EU", "Altar of Fangs", 10, "dps")
        assert second.previous_score == 2784
        assert get.call_count == 3
    finally:
        client.close()


def test_wcl_explicit_source_is_never_relabelled_after_request_boundary():
    previous = WCLResult(
        "Applicant", "Realm", "Altar of Fangs", 71,
        WCLBracket(0, 80, 80, 1, 80), 1.0, target_key=10,
        source_season="midnight-s1",
    )
    assert engine._with_wcl_source(previous, "midnight-s2").source_season == "midnight-s1"


def test_wcl_current_result_gets_source_bound_at_routing_time():
    current = WCLResult(
        "Applicant", "Realm", "Altar of Fangs", 71,
        WCLBracket(10, 55, 55, 1, 55), 1.0, target_key=10,
    )

    class Client:
        def fetch_batch_previous_season(self, jobs):
            raise AssertionError("previous season should not be queried")
        def fetch_batch_current_dungeon(self, jobs):
            return [current for _ in jobs]

    jobs = [("Applicant", "realm", "Realm", "EU", 71, "Altar of Fangs", 10)]
    with patch.object(engine, "use_previous_wcl_for_dungeon", return_value=False):
        result = engine._fetch_wcl_batch(Client(), jobs)[0]
    assert result.source_season == "midnight-s2"


def test_wcl_cache_roundtrip_preserves_source_season(tmp_path):
    cache = WCLCache(tmp_path / "wcl.json")
    result = WCLResult(
        "Applicant", "Realm", "Altar of Fangs", 71,
        WCLBracket(10, 55, 55, 1, 55), 1.0, target_key=10,
        source_season="midnight-s2",
    )
    cache.put("EU", result)
    loaded = cache.get("EU", "Realm", "Applicant", 71, "Altar of Fangs", 10)
    assert loaded is not None
    assert loaded.source_season == "midnight-s2"


def test_same_calendar_date_can_be_different_transition_phase_by_region():
    day = date(2026, 8, 19)
    assert season2_transition_phase(day, region="US") == "week1"
    assert season2_transition_phase(day, region="EU") == "week1"
    assert season2_transition_phase(day, region="KR") == "preseason"
    assert season2_transition_phase(day, region="TW") == "preseason"
    assert season2_transition_phase(day, region="CN") == "preseason"


def test_real_season1_listing_is_not_mistaken_for_s2_carryover():
    from keystonelens_companion.registries import use_previous_wcl_for_dungeon

    assert use_previous_wcl_for_dungeon("Magisters' Terrace", date(2026, 8, 25)) is False
    assert wcl_source_season_for_dungeon("Magisters' Terrace", date(2026, 8, 25)) == "midnight-s1"
