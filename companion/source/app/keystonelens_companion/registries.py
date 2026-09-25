"""Minimal season/dungeon registry used by the Warcraft Logs client."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeasonDefinition:
    key: str
    name: str
    dungeons: tuple[str, ...]


MIDNIGHT_SEASON_1 = SeasonDefinition(
    key="midnight-s1",
    name="Midnight Season 1",
    dungeons=(
        "Magisters' Terrace",
        "Maisara Caverns",
        "Nexus-Point Xenas",
        "Windrunner Spire",
        "Algeth'ar Academy",
        "Pit of Saron",
        "Seat of the Triumvirate",
        "Skyreach",
    ),
)

MIDNIGHT_SEASON_2 = SeasonDefinition(
    key="midnight-s2",
    name="Midnight Season 2",
    dungeons=(
        "Altar of Fangs",
        "Murder Row",
        "Den of Nalorakk",
        "The Blinding Vale",
        "Voidscar Arena",
        "Kings' Rest",
        "Ruby Life Pools",
        "Temple of Sethraliss",
    ),
)

ACTIVE_SEASON_KEY = "midnight-s2"

SEASON_REGISTRY = {
    MIDNIGHT_SEASON_1.key: MIDNIGHT_SEASON_1,
    MIDNIGHT_SEASON_2.key: MIDNIGHT_SEASON_2,
}

DUNGEON_TO_SEASON = {
    dungeon: season.key
    for season in SEASON_REGISTRY.values()
    for dungeon in season.dungeons
}

WCL_ZONE_BY_SEASON = {
    MIDNIGHT_SEASON_1.key: 47,
    MIDNIGHT_SEASON_2.key: 55,
}

_DUNGEON_ALIASES = {
    "blinding vale": "The Blinding Vale",
    "the blinding vale": "The Blinding Vale",
    "king's rest": "Kings' Rest",
    "kings' rest": "Kings' Rest",
    "temple of sethraliss": "Temple of Sethraliss",
}


def canonical_dungeon_name(name: str) -> str:
    cleaned = " ".join(str(name or "").strip().split())
    if not cleaned:
        return ""
    lookup = cleaned.translate(
        str.maketrans({"\u2018": "'", "\u2019": "'", "\u02bc": "'", "\uff07": "'"})
    ).casefold()
    return _DUNGEON_ALIASES.get(lookup, cleaned)


def season_for_dungeon(name: str) -> SeasonDefinition | None:
    canonical = canonical_dungeon_name(name)
    return SEASON_REGISTRY.get(DUNGEON_TO_SEASON.get(canonical, ""))


def wcl_zone_for_dungeon(name: str) -> int | None:
    season = season_for_dungeon(name)
    return WCL_ZONE_BY_SEASON.get(season.key) if season else None
