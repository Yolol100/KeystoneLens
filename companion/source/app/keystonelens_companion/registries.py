"""Season and dungeon registry used by Raider.IO/WCL enrichment."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone


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
    verified_date="2026-08-19",
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

# Current Warcraft Logs production dungeon-zone IDs. Encounter IDs remain
# hard-coded for known dungeons and this mapping provides a dynamic fallback for
# unknown/new IDs. Midnight Season 2 live is zone 55; zone 56 is the PTR and
# must never be used as production scoring evidence.
WCL_ZONE_BY_SEASON = {
    MIDNIGHT_SEASON_1.key: 47,
    MIDNIGHT_SEASON_2.key: 55,
}

# Public Warcraft Logs character/ranking surfaces were rechecked on 2026-08-20
# and expose live Midnight Mythic+ Season 2 scores. Keep this source-verification
# date separate from Blizzard's regional season window: Raider.IO can still show
# previous-season context during week one, while WCL should stop forcing Season 1
# as soon as current Season 2 evidence is independently visible in production.
MIDNIGHT_SEASON_2_WCL_PRODUCTION_VERIFIED_ON = date(2026, 8, 20)

# Blizzard publishes Season 2 by regional weekly window. Keep EU aliases for
# backwards-compatible tests/imports, but make runtime decisions from the actual
# WoW region carried by the Bridge. This intentionally models the published day,
# not an invented maintenance clock time.
MIDNIGHT_SEASON_2_START_BY_REGION = {
    "US": date(2026, 8, 18),
    "EU": date(2026, 8, 19),
    "KR": date(2026, 8, 20),
    "TW": date(2026, 8, 20),
    "CN": date(2026, 8, 20),
}
MIDNIGHT_SEASON_2_MYTHIC_PLUS_START = MIDNIGHT_SEASON_2_START_BY_REGION["EU"]
MIDNIGHT_SEASON_2_WEEK2_START = MIDNIGHT_SEASON_2_MYTHIC_PLUS_START + timedelta(days=7)
# Blizzard's published EU weekly reset is permanently 05:00 CET, i.e. 04:00 UTC
# year-round (06:00 local CEST during August). This exact boundary avoids the
# calendar-day implementation switching Dutch/EU users roughly six hours early.
MIDNIGHT_SEASON_2_EU_START_UTC = datetime(2026, 8, 19, 4, 0, tzinfo=timezone.utc)
MIDNIGHT_SEASON_2_EU_WEEK2_UTC = MIDNIGHT_SEASON_2_EU_START_UTC + timedelta(days=7)


def season2_start_for_region(region: str = "EU") -> date:
    key = str(region or "EU").strip().upper()
    return MIDNIGHT_SEASON_2_START_BY_REGION.get(key, MIDNIGHT_SEASON_2_MYTHIC_PLUS_START)


def season2_transition_phase_at(moment: datetime, *, region: str = "EU") -> str:
    """Resolve the transition at an exact instant where a verified reset exists."""
    if moment.tzinfo is None:
        raise ValueError("season transition moment must be timezone-aware")
    key = str(region or "EU").strip().upper()
    if key == "EU":
        current_utc = moment.astimezone(timezone.utc)
        if current_utc < MIDNIGHT_SEASON_2_EU_START_UTC:
            return "preseason"
        if current_utc < MIDNIGHT_SEASON_2_EU_WEEK2_UTC:
            return "week1"
        return "current"
    return season2_transition_phase(moment.date(), region=key)


def season2_transition_phase(on_date: date | None = None, *, region: str = "EU") -> str:
    key = str(region or "EU").strip().upper()
    if on_date is None and key == "EU":
        return season2_transition_phase_at(datetime.now(timezone.utc), region=key)
    current = on_date or date.today()
    start = season2_start_for_region(key)
    if current < start:
        return "preseason"
    if current < start + timedelta(days=7):
        return "week1"
    return "current"


def use_season1_carryover(on_date: date | None = None, *, region: str = "EU") -> bool:
    return season2_transition_phase(on_date, region=region) == "week1"


def wcl_season2_production_verified(on_date: date | None = None) -> bool:
    current = on_date or date.today()
    return current >= MIDNIGHT_SEASON_2_WCL_PRODUCTION_VERIFIED_ON


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


def use_previous_wcl_for_dungeon(name: str, on_date: date | None = None, *, region: str = "EU") -> bool:
    season = season_for_dungeon(name)
    return bool(
        season
        and season.key == MIDNIGHT_SEASON_2.key
        and use_season1_carryover(on_date, region=region)
        and not wcl_season2_production_verified(on_date)
    )


def wcl_source_season_for_dungeon(name: str, on_date: date | None = None, *, region: str = "EU") -> str:
    """Return the WCL season whose evidence should score this listing today."""
    season = season_for_dungeon(name)
    if not season:
        return ""
    if use_previous_wcl_for_dungeon(name, on_date, region=region):
        return MIDNIGHT_SEASON_1.key
    return season.key


def is_season1_carryover_source(name: str, source_season: str) -> bool:
    """True only when Season 1 evidence stands in for a Season 2 listing."""
    season = season_for_dungeon(name)
    return bool(
        season
        and season.key == MIDNIGHT_SEASON_2.key
        and source_season == MIDNIGHT_SEASON_1.key
    )
