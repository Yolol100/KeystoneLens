from __future__ import annotations

from keystonelens_companion.registries import (
    MIDNIGHT_SEASON_2,
    canonical_dungeon_name,
    season_for_dungeon,
    wcl_zone_for_dungeon,
)


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


def test_midnight_season2_wcl_cache_context_is_bound_to_live_production_zone():
    from keystonelens_companion.wcl import WCL_CONTEXT_VERSION

    assert WCL_CONTEXT_VERSION.endswith(":prod-zone55")


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


def test_wcl_alias_resolves_against_canonical_zone_catalog():
    from unittest.mock import patch
    from keystonelens_companion.wcl import WCLClient

    client = object.__new__(WCLClient)
    with patch.object(client, "_fetch_zone_encounters", return_value={"theblindingvale": 424242}):
        assert client._resolve_encounter_id("Blinding Vale") == 424242
