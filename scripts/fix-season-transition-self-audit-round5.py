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
    '''def wcl_source_season_for_dungeon(name: str, on_date: date | None = None, *, region: str = "EU") -> str:\n    """Return the WCL season whose evidence should score this listing today."""\n    season = season_for_dungeon(name)\n    if not season:\n        return ""\n    if use_previous_wcl_for_dungeon(name, on_date, region=region):\n        return MIDNIGHT_SEASON_1.key\n    return season.key\n''',
    '''def wcl_source_season_for_dungeon(name: str, on_date: date | None = None, *, region: str = "EU") -> str:\n    """Return the WCL season whose evidence should score this listing today."""\n    season = season_for_dungeon(name)\n    if not season:\n        return ""\n    if use_previous_wcl_for_dungeon(name, on_date, region=region):\n        return MIDNIGHT_SEASON_1.key\n    return season.key\n\n\ndef is_season1_carryover_source(name: str, source_season: str) -> bool:\n    """True only when Season 1 evidence stands in for a Season 2 listing."""\n    season = season_for_dungeon(name)\n    return bool(\n        season\n        and season.key == MIDNIGHT_SEASON_2.key\n        and source_season == MIDNIGHT_SEASON_1.key\n    )\n''',
)

replace_once(
    "companion/source/app/keystonelens_companion/scoring.py",
    "from .registries import use_season1_carryover\n",
    "from .registries import is_season1_carryover_source, use_season1_carryover\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/scoring.py",
    '''        context = (\n            " from Midnight Season 1 carry-over"\n            if wcl and wcl.source_season == "midnight-s1"\n            else " in this dungeon" if context_bracket else ""\n        )\n''',
    '''        carryover = bool(\n            wcl\n            and listing\n            and is_season1_carryover_source(listing.dungeon_name, wcl.source_season)\n        )\n        context = (\n            " from Midnight Season 1 carry-over"\n            if carryover\n            else " in this dungeon" if context_bracket else ""\n        )\n''',
)

replace_once(
    "companion/source/app/keystonelens_companion/ui.py",
    "from .registries import use_season1_carryover\n",
    "from .registries import is_season1_carryover_source, use_season1_carryover\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/ui.py",
    '''            source = "S1 " if view.wcl and view.wcl.source_season == "midnight-s1" else ""\n''',
    '''            source = (\n                "S1 "\n                if view.wcl\n                and view.snapshot_listing\n                and is_season1_carryover_source(\n                    view.snapshot_listing.dungeon_name, view.wcl.source_season\n                )\n                else ""\n            )\n''',
)
replace_once(
    "companion/source/app/keystonelens_companion/ui.py",
    '''                if view.wcl and view.wcl.source_season == "midnight-s1":\n                    scope = "Season 1 aggregate"\n''',
    '''                if (\n                    view.wcl\n                    and view.snapshot_listing\n                    and is_season1_carryover_source(\n                        view.snapshot_listing.dungeon_name, view.wcl.source_season\n                    )\n                ):\n                    scope = "Season 1 aggregate"\n''',
)

# Strengthen the existing edge-case test so source identity and carry-over meaning
# cannot be conflated again.
test_path = ROOT / "companion/source/app/tests/test_season_transition.py"
text = test_path.read_text(encoding="utf-8")
replace_old = '''    MIDNIGHT_SEASON_1,\n    season2_transition_phase,\n'''
replace_new = '''    MIDNIGHT_SEASON_1,\n    is_season1_carryover_source,\n    season2_transition_phase,\n'''
if text.count(replace_old) != 1:
    raise SystemExit("registry import marker changed")
text = text.replace(replace_old, replace_new, 1)
old = '''    assert use_previous_wcl_for_dungeon("Magisters' Terrace", date(2026, 8, 25)) is False\n    assert wcl_source_season_for_dungeon("Magisters' Terrace", date(2026, 8, 25)) == "midnight-s1"\n'''
new = '''    assert use_previous_wcl_for_dungeon("Magisters' Terrace", date(2026, 8, 25)) is False\n    assert wcl_source_season_for_dungeon("Magisters' Terrace", date(2026, 8, 25)) == "midnight-s1"\n    assert is_season1_carryover_source("Magisters' Terrace", "midnight-s1") is False\n    assert is_season1_carryover_source("Altar of Fangs", "midnight-s1") is True\n'''
if text.count(old) != 1:
    raise SystemExit("real Season 1 edge-case marker changed")
test_path.write_text(text.replace(old, new, 1), encoding="utf-8")

print("Carry-over label semantics corrected")
