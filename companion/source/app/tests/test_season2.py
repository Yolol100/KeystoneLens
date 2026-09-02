from __future__ import annotations

from keystonelens_companion.constants import DUNGEONS
from keystonelens_companion.registries import (
    MIDNIGHT_SEASON_2,
    canonical_dungeon_name,
    season_for_dungeon,
    wcl_zone_for_dungeon,
)


SEASON2_WCL_ENCOUNTERS = {
    "Altar of Fangs": 62993,
    "Murder Row": 62813,
    "Den of Nalorakk": 62825,
    "The Blinding Vale": 62859,
    "Voidscar Arena": 62923,
    "Kings' Rest": 61762,
    "Ruby Life Pools": 162521,
    "Temple of Sethraliss": 111877,
}


def test_midnight_season2_registry_is_release_ready_and_complete():
    assert MIDNIGHT_SEASON_2.ruleset == "retail-12.1-season2"
    assert MIDNIGHT_SEASON_2.verified_date == "2026-08-19"
    assert MIDNIGHT_SEASON_2.dungeons == (
        "Altar of Fangs",
        "Murder Row",
        "Den of Nalorakk",
        "The Blinding Vale",
        "Voidscar Arena",
        "Kings' Rest",
        "Ruby Life Pools",
        "Temple of Sethraliss",
    )
    assert all(wcl_zone_for_dungeon(name) == 55 for name in MIDNIGHT_SEASON_2.dungeons)


def test_all_verified_season2_encounter_ids_bypass_zone_catalog_outages():
    from unittest.mock import patch
    from keystonelens_companion.wcl import WCLClient

    assert {name: DUNGEONS.get(name) for name in MIDNIGHT_SEASON_2.dungeons} == SEASON2_WCL_ENCOUNTERS
    # Regression guard for the production-breaking typo that used 12825.
    assert DUNGEONS["Den of Nalorakk"] == 62825

    client = object.__new__(WCLClient)
    with patch.object(client, "_fetch_zone_encounters", side_effect=AssertionError("catalog should not be queried")):
        for dungeon, encounter_id in SEASON2_WCL_ENCOUNTERS.items():
            assert client._resolve_encounter_id(dungeon) == encounter_id


def test_midnight_season2_wcl_cache_is_migrated_off_ptr_evidence():
    from keystonelens_companion.config import cache_path

    assert cache_path().name == "wcl-cache-prod55.json"


def test_season2_name_variants_are_canonicalized():
    aliases = {
        "Blinding Vale": "The Blinding Vale",
        "The Blinding Vale": "The Blinding Vale",
        "King's Rest": "Kings' Rest",
        "King’s Rest": "Kings' Rest",
        "King‘s Rest": "Kings' Rest",
        "Kingʼs Rest": "Kings' Rest",
        "Kings’ Rest": "Kings' Rest",
        "Kings' Rest": "Kings' Rest",
    }
    for raw, expected in aliases.items():
        assert canonical_dungeon_name(raw) == expected
        season = season_for_dungeon(raw)
        assert season is not None and season.key == "midnight-s2"
        assert wcl_zone_for_dungeon(raw) == 55


def test_raiderio_run_names_use_same_season2_canonicalization():
    from keystonelens_companion.rio import _run_dungeon_name
    assert _run_dungeon_name({"dungeon": "Blinding Vale"}) == "The Blinding Vale"
    assert _run_dungeon_name({"dungeon": {"name": "King's Rest"}}) == "Kings' Rest"
    assert _run_dungeon_name({"dungeon": {"name": "King’s Rest"}}) == "Kings' Rest"


def test_wcl_alias_resolves_against_verified_encounter_registry():
    from unittest.mock import patch
    from keystonelens_companion.wcl import WCLClient

    client = object.__new__(WCLClient)
    with patch.object(client, "_fetch_zone_encounters", side_effect=AssertionError("catalog should not be queried")):
        assert client._resolve_encounter_id("Blinding Vale") == SEASON2_WCL_ENCOUNTERS["The Blinding Vale"]
        assert client._resolve_encounter_id("King’s Rest") == SEASON2_WCL_ENCOUNTERS["Kings' Rest"]
