from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "companion/source/app/keystonelens_companion/registries.py",
    "from datetime import date, timedelta\n",
    "from datetime import date, datetime, timedelta, timezone\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/registries.py",
    '''MIDNIGHT_SEASON_2_MYTHIC_PLUS_START = MIDNIGHT_SEASON_2_START_BY_REGION["EU"]\nMIDNIGHT_SEASON_2_WEEK2_START = MIDNIGHT_SEASON_2_MYTHIC_PLUS_START + timedelta(days=7)\n\n\ndef season2_start_for_region(region: str = "EU") -> date:\n''',
    '''MIDNIGHT_SEASON_2_MYTHIC_PLUS_START = MIDNIGHT_SEASON_2_START_BY_REGION["EU"]\nMIDNIGHT_SEASON_2_WEEK2_START = MIDNIGHT_SEASON_2_MYTHIC_PLUS_START + timedelta(days=7)\n# Blizzard's published EU weekly reset is permanently 05:00 CET, i.e. 04:00 UTC\n# year-round (06:00 local CEST during August). This exact boundary avoids the\n# calendar-day implementation switching Dutch/EU users roughly six hours early.\nMIDNIGHT_SEASON_2_EU_START_UTC = datetime(2026, 8, 19, 4, 0, tzinfo=timezone.utc)\nMIDNIGHT_SEASON_2_EU_WEEK2_UTC = MIDNIGHT_SEASON_2_EU_START_UTC + timedelta(days=7)\n\n\ndef season2_start_for_region(region: str = "EU") -> date:\n''',
)
replace_once(
    "companion/source/app/keystonelens_companion/registries.py",
    '''def season2_transition_phase(on_date: date | None = None, *, region: str = "EU") -> str:\n    current = on_date or date.today()\n    start = season2_start_for_region(region)\n    if current < start:\n        return "preseason"\n    if current < start + timedelta(days=7):\n        return "week1"\n    return "current"\n''',
    '''def season2_transition_phase_at(moment: datetime, *, region: str = "EU") -> str:\n    """Resolve the transition at an exact instant where a verified reset exists."""\n    if moment.tzinfo is None:\n        raise ValueError("season transition moment must be timezone-aware")\n    key = str(region or "EU").strip().upper()\n    if key == "EU":\n        current_utc = moment.astimezone(timezone.utc)\n        if current_utc < MIDNIGHT_SEASON_2_EU_START_UTC:\n            return "preseason"\n        if current_utc < MIDNIGHT_SEASON_2_EU_WEEK2_UTC:\n            return "week1"\n        return "current"\n    return season2_transition_phase(moment.date(), region=key)\n\n\ndef season2_transition_phase(on_date: date | None = None, *, region: str = "EU") -> str:\n    key = str(region or "EU").strip().upper()\n    if on_date is None and key == "EU":\n        return season2_transition_phase_at(datetime.now(timezone.utc), region=key)\n    current = on_date or date.today()\n    start = season2_start_for_region(key)\n    if current < start:\n        return "preseason"\n    if current < start + timedelta(days=7):\n        return "week1"\n    return "current"\n''',
)

# Add exact EU reset-boundary tests while preserving the date-based regional matrix.
test_path = ROOT / "companion/source/app/tests/test_season_transition.py"
text = test_path.read_text(encoding="utf-8")
old_import = "from datetime import date\nimport time\n"
new_import = "from datetime import date, datetime, timezone\nimport time\n"
if text.count(old_import) != 1:
    raise SystemExit("datetime test import marker changed")
text = text.replace(old_import, new_import, 1)
old_registry = '''    season2_transition_phase,\n    use_season1_carryover,\n'''
new_registry = '''    season2_transition_phase,\n    season2_transition_phase_at,\n    use_season1_carryover,\n'''
if text.count(old_registry) != 1:
    raise SystemExit("registry test import marker changed")
text = text.replace(old_registry, new_registry, 1)
marker = "\n\ndef test_unknown_region_falls_back_to_eu_window():\n"
if text.count(marker) != 1:
    raise SystemExit("EU reset test insertion marker changed")
extra = r'''


def test_eu_transition_uses_exact_weekly_reset_instant_not_midnight():
    assert season2_transition_phase_at(
        datetime(2026, 8, 19, 3, 59, 59, tzinfo=timezone.utc), region="EU"
    ) == "preseason"
    assert season2_transition_phase_at(
        datetime(2026, 8, 19, 4, 0, 0, tzinfo=timezone.utc), region="EU"
    ) == "week1"
    assert season2_transition_phase_at(
        datetime(2026, 8, 26, 3, 59, 59, tzinfo=timezone.utc), region="EU"
    ) == "week1"
    assert season2_transition_phase_at(
        datetime(2026, 8, 26, 4, 0, 0, tzinfo=timezone.utc), region="EU"
    ) == "current"


def test_transition_instant_must_be_timezone_aware():
    with pytest.raises(ValueError, match="timezone-aware"):
        season2_transition_phase_at(datetime(2026, 8, 19, 4, 0), region="EU")
'''
test_path.write_text(text.replace(marker, extra + marker, 1), encoding="utf-8")

print("Exact EU weekly reset boundary applied")
