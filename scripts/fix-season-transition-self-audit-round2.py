from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Sample the transition phase exactly once per Raider.IO lookup, so a request
# crossing midnight/reset-date boundaries cannot derive mismatched cache keys.
replace_once(
    "companion/source/app/keystonelens_companion/rio.py",
    '''    @staticmethod\n    def _profile_key(region: str, realm: str, name: str, dungeon: str, target: int, role: str) -> tuple[str, str, str, str, int, str, str]:\n        dungeon = canonical_dungeon_name(dungeon)\n        phase = season2_transition_phase(region=region)\n        return (region.casefold(), realm.casefold(), name.casefold(), dungeon.casefold(), int(target or 0), role.casefold(), phase)\n''',
    '''    @staticmethod\n    def _profile_key(\n        region: str, realm: str, name: str, dungeon: str, target: int, role: str, phase: str\n    ) -> tuple[str, str, str, str, int, str, str]:\n        dungeon = canonical_dungeon_name(dungeon)\n        return (region.casefold(), realm.casefold(), name.casefold(), dungeon.casefold(), int(target or 0), role.casefold(), phase)\n''',
)
replace_once(
    "companion/source/app/keystonelens_companion/rio.py",
    '''        role = role.casefold().strip()\n        key = self._profile_key(region, realm, name, dungeon, target_key, role)\n        phase = season2_transition_phase(region=region)\n        raw_key = (region.casefold(), realm.casefold(), name.casefold(), phase)\n''',
    '''        role = role.casefold().strip()\n        phase = season2_transition_phase(region=region)\n        key = self._profile_key(region, realm, name, dungeon, target_key, role, phase)\n        raw_key = (region.casefold(), realm.casefold(), name.casefold(), phase)\n''',
)

# The cache test must use fresh evidence. fetched_at=1.0 is intentionally stale
# and WCLCache correctly rejects it, so use the real current timestamp instead.
replace_once(
    "companion/source/app/tests/test_season_transition.py",
    "from dataclasses import replace\nfrom datetime import date\n",
    "from dataclasses import replace\nfrom datetime import date\nimport time\n",
)
replace_once(
    "companion/source/app/tests/test_season_transition.py",
    '''def test_wcl_cache_roundtrip_preserves_source_season(tmp_path):\n    cache = WCLCache(tmp_path / "wcl.json")\n    result = WCLResult(\n        "Applicant", "Realm", "Altar of Fangs", 71,\n        WCLBracket(10, 55, 55, 1, 55), 1.0, target_key=10,\n        source_season="midnight-s2",\n    )\n''',
    '''def test_wcl_cache_roundtrip_preserves_source_season(tmp_path):\n    cache = WCLCache(tmp_path / "wcl.json")\n    result = WCLResult(\n        "Applicant", "Realm", "Altar of Fangs", 71,\n        WCLBracket(10, 55, 55, 1, 55), time.time(), target_key=10,\n        source_season="midnight-s2",\n    )\n''',
)

# Strengthen the phase-cache regression: two fetches must sample the transition
# state exactly twice, once per lookup, not once for profile and once for raw key.
replace_once(
    "companion/source/app/tests/test_season_transition.py",
    '''        with patch.object(rio, "season2_transition_phase", side_effect=lambda **_kw: phase["value"]), \\\n             patch.object(rio, "use_season1_carryover", side_effect=lambda **_kw: phase["value"] == "week1"), \\\n             patch.object(client, "_get", side_effect=[current, current, previous]) as get:\n''',
    '''        with patch.object(rio, "season2_transition_phase", side_effect=lambda **_kw: phase["value"]) as phase_lookup, \\\n             patch.object(rio, "use_season1_carryover", side_effect=lambda **_kw: phase["value"] == "week1"), \\\n             patch.object(client, "_get", side_effect=[current, current, previous]) as get:\n''',
)
replace_once(
    "companion/source/app/tests/test_season_transition.py",
    '''        assert second.previous_score == 2784\n        assert get.call_count == 3\n''',
    '''        assert second.previous_score == 2784\n        assert get.call_count == 3\n        assert phase_lookup.call_count == 2\n''',
)

print("Self-audit round two corrections applied")
