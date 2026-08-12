"""Season and dungeon registry used by Raider.IO/WCL enrichment."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeasonDefinition:
    key: str
    name: str
    dungeons: tuple[str, ...]
    verified_date: str
    ruleset: str


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
    verified_date="2026-08-11",
    ruleset="retail-12.x",
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
    verified_date="2026-08-12",
    ruleset="retail-12.1-season2",
)

SEASON_REGISTRY = {
    MIDNIGHT_SEASON_1.key: MIDNIGHT_SEASON_1,
    MIDNIGHT_SEASON_2.key: MIDNIGHT_SEASON_2,
}
DUNGEON_TO_SEASON = {
    dungeon: season.key
    for season in SEASON_REGISTRY.values()
    for dungeon in season.dungeons
}

# Current Warcraft Logs dungeon-zone IDs. Encounter IDs remain hard-coded for
# known dungeons and this mapping provides a dynamic fallback for unknown/new IDs.
WCL_ZONE_BY_SEASON = {
    MIDNIGHT_SEASON_1.key: 47,
    MIDNIGHT_SEASON_2.key: 56,
}


# Names can differ slightly between Blizzard's LFG short names and external
# services. Canonicalize the known Season 2 variants before enrichment so WCL,
# Raider.IO and local listing context always refer to the same dungeon.
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
    # Blizzard/external services can use typographic apostrophes while WCL uses
    # an ASCII apostrophe for Kings' Rest. Normalize common Unicode variants
    # only for lookup; unknown dungeon names keep their original display form.
    lookup = cleaned.translate(str.maketrans({"\u2018": "'", "\u2019": "'", "\u02bc": "'", "\uff07": "'"})).casefold()
    return _DUNGEON_ALIASES.get(lookup, cleaned)


def season_for_dungeon(name: str) -> SeasonDefinition | None:
    canonical = canonical_dungeon_name(name)
    return SEASON_REGISTRY.get(DUNGEON_TO_SEASON.get(canonical, ""))


def wcl_zone_for_dungeon(name: str) -> int | None:
    season = season_for_dungeon(name)
    return WCL_ZONE_BY_SEASON.get(season.key) if season else None
