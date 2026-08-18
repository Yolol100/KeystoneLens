from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Region-aware published Season 2 weekly windows.
replace_once(
    "companion/source/app/keystonelens_companion/registries.py",
    "from datetime import date\n",
    "from datetime import date, timedelta\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/registries.py",
    '''# Midnight Season 2 Mythic+ starts in the week of 19 August 2026. For the\n# first weekly lockout, fresh-season Raider.IO/WCL evidence is intentionally\n# treated as incomplete. On the second weekly reset we switch to Season 2 only.\nMIDNIGHT_SEASON_2_MYTHIC_PLUS_START = date(2026, 8, 19)\nMIDNIGHT_SEASON_2_WEEK2_START = date(2026, 8, 26)\n\n\ndef season2_transition_phase(on_date: date | None = None) -> str:\n    current = on_date or date.today()\n    if current < MIDNIGHT_SEASON_2_MYTHIC_PLUS_START:\n        return "preseason"\n    if current < MIDNIGHT_SEASON_2_WEEK2_START:\n        return "week1"\n    return "current"\n\n\ndef use_season1_carryover(on_date: date | None = None) -> bool:\n    return season2_transition_phase(on_date) == "week1"\n''',
    '''# Blizzard publishes Season 2 by regional weekly window. Keep EU aliases for\n# backwards-compatible tests/imports, but make runtime decisions from the actual\n# WoW region carried by the Bridge. This intentionally models the published day,\n# not an invented maintenance clock time.\nMIDNIGHT_SEASON_2_START_BY_REGION = {\n    "US": date(2026, 8, 18),\n    "EU": date(2026, 8, 19),\n    "KR": date(2026, 8, 20),\n    "TW": date(2026, 8, 20),\n    "CN": date(2026, 8, 20),\n}\nMIDNIGHT_SEASON_2_MYTHIC_PLUS_START = MIDNIGHT_SEASON_2_START_BY_REGION["EU"]\nMIDNIGHT_SEASON_2_WEEK2_START = MIDNIGHT_SEASON_2_MYTHIC_PLUS_START + timedelta(days=7)\n\n\ndef season2_start_for_region(region: str = "EU") -> date:\n    key = str(region or "EU").strip().upper()\n    return MIDNIGHT_SEASON_2_START_BY_REGION.get(key, MIDNIGHT_SEASON_2_MYTHIC_PLUS_START)\n\n\ndef season2_transition_phase(on_date: date | None = None, *, region: str = "EU") -> str:\n    current = on_date or date.today()\n    start = season2_start_for_region(region)\n    if current < start:\n        return "preseason"\n    if current < start + timedelta(days=7):\n        return "week1"\n    return "current"\n\n\ndef use_season1_carryover(on_date: date | None = None, *, region: str = "EU") -> bool:\n    return season2_transition_phase(on_date, region=region) == "week1"\n''',
)
replace_once(
    "companion/source/app/keystonelens_companion/registries.py",
    "def use_previous_wcl_for_dungeon(name: str, on_date: date | None = None) -> bool:\n",
    "def use_previous_wcl_for_dungeon(name: str, on_date: date | None = None, *, region: str = \"EU\") -> bool:\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/registries.py",
    "        and use_season1_carryover(on_date)\n",
    "        and use_season1_carryover(on_date, region=region)\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/registries.py",
    "def wcl_source_season_for_dungeon(name: str, on_date: date | None = None) -> str:\n",
    "def wcl_source_season_for_dungeon(name: str, on_date: date | None = None, *, region: str = \"EU\") -> str:\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/registries.py",
    "    if use_previous_wcl_for_dungeon(name, on_date):\n",
    "    if use_previous_wcl_for_dungeon(name, on_date, region=region):\n",
)

# Raider.IO caches must cross a new cache namespace when the season phase changes.
replace_once(
    "companion/source/app/keystonelens_companion/rio.py",
    "from .registries import canonical_dungeon_name, use_season1_carryover\n",
    "from .registries import canonical_dungeon_name, season2_transition_phase, use_season1_carryover\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/rio.py",
    "        self._profiles: dict[tuple[str, str, str, str, int, str], RIOResult] = {}\n",
    "        self._profiles: dict[tuple[str, str, str, str, int, str, str], RIOResult] = {}\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/rio.py",
    "        self._raw_profiles: dict[tuple[str, str, str], tuple[float, dict[str, Any] | None, bool]] = {}\n",
    "        self._raw_profiles: dict[tuple[str, str, str, str], tuple[float, dict[str, Any] | None, bool]] = {}\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/rio.py",
    '''    def _profile_key(region: str, realm: str, name: str, dungeon: str, target: int, role: str) -> tuple[str, str, str, str, int, str]:\n        dungeon = canonical_dungeon_name(dungeon)\n        return (region.casefold(), realm.casefold(), name.casefold(), dungeon.casefold(), int(target or 0), role.casefold())\n''',
    '''    def _profile_key(region: str, realm: str, name: str, dungeon: str, target: int, role: str) -> tuple[str, str, str, str, int, str, str]:\n        dungeon = canonical_dungeon_name(dungeon)\n        phase = season2_transition_phase(region=region)\n        return (region.casefold(), realm.casefold(), name.casefold(), dungeon.casefold(), int(target or 0), role.casefold(), phase)\n''',
)
replace_once(
    "companion/source/app/keystonelens_companion/rio.py",
    "        raw_key = (region.casefold(), realm.casefold(), name.casefold())\n",
    "        phase = season2_transition_phase(region=region)\n        raw_key = (region.casefold(), realm.casefold(), name.casefold(), phase)\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/rio.py",
    "            if use_season1_carryover():\n",
    "            if use_season1_carryover(region=region):\n",
)

# Keep WCL source identity fixed at request routing time; never relabel an in-flight S1 result as S2.
replace_once(
    "companion/source/app/keystonelens_companion/engine.py",
    "from .registries import canonical_dungeon_name, DUNGEON_TO_SEASON, use_previous_wcl_for_dungeon, wcl_source_season_for_dungeon\n",
    "from .registries import MIDNIGHT_SEASON_1, canonical_dungeon_name, DUNGEON_TO_SEASON, use_previous_wcl_for_dungeon, wcl_source_season_for_dungeon\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/engine.py",
    "def _result_matches_listing(result: WCLResult | RIOResult | None, listing: Listing | None) -> bool:\n",
    "def _result_matches_listing(result: WCLResult | RIOResult | None, listing: Listing | None, region: str = \"EU\") -> bool:\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/engine.py",
    "        return result.source_season == wcl_source_season_for_dungeon(listing.dungeon_name)\n",
    "        return result.source_season == wcl_source_season_for_dungeon(listing.dungeon_name, region=region)\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/engine.py",
    '''def _fetch_wcl_batch(client: WCLClient, jobs):\n    """Route WCL to S1 carry-over only during the first S2 weekly lockout."""\n    if not jobs:\n        return []\n    indexed_previous = []\n    indexed_current = []\n    for index, job in enumerate(jobs):\n        target = indexed_previous if use_previous_wcl_for_dungeon(job[5]) else indexed_current\n        target.append((index, job))\n\n    results: list[WCLResult | None] = [None] * len(jobs)\n    if indexed_previous:\n        fetched = client.fetch_batch_previous_season([job for _index, job in indexed_previous])\n        for (index, _job), result in zip(indexed_previous, fetched):\n            results[index] = result\n    if indexed_current:\n        fetched = client.fetch_batch_current_dungeon([job for _index, job in indexed_current])\n        for (index, _job), result in zip(indexed_current, fetched):\n            results[index] = result\n    return results\n''',
    '''def _with_wcl_source(result: WCLResult | None, expected_source: str) -> WCLResult | None:\n    """Stamp only source-less results; an explicit source is immutable evidence."""\n    if result is None or result.source_season or not expected_source:\n        return result\n    return replace(result, source_season=expected_source)\n\n\ndef _fetch_wcl_batch(client: WCLClient, jobs):\n    """Route WCL by region and bind source identity before network work returns."""\n    if not jobs:\n        return []\n    indexed_previous = []\n    indexed_current = []\n    for index, job in enumerate(jobs):\n        target = indexed_previous if use_previous_wcl_for_dungeon(job[5], region=job[3]) else indexed_current\n        target.append((index, job))\n\n    results: list[WCLResult | None] = [None] * len(jobs)\n    if indexed_previous:\n        fetched = client.fetch_batch_previous_season([job for _index, job in indexed_previous])\n        for (index, _job), result in zip(indexed_previous, fetched):\n            results[index] = _with_wcl_source(result, MIDNIGHT_SEASON_1.key)\n    if indexed_current:\n        fetched = client.fetch_batch_current_dungeon([job for _index, job in indexed_current])\n        for (index, job), result in zip(indexed_current, fetched):\n            expected = DUNGEON_TO_SEASON.get(canonical_dungeon_name(job[5]), "")\n            results[index] = _with_wcl_source(result, expected)\n    return results\n''',
)
replace_once(
    "companion/source/app/keystonelens_companion/engine.py",
    "                same_wcl_context = bool(same_character_context and _result_matches_listing(old.wcl, effective_listing))\n",
    "                same_wcl_context = bool(same_character_context and _result_matches_listing(old.wcl, effective_listing, region))\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/engine.py",
    "                same_rio_context = bool(same_character_context and _result_matches_listing(old.rio, effective_listing))\n",
    "                same_rio_context = bool(same_character_context and _result_matches_listing(old.rio, effective_listing, region))\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/engine.py",
    '''                    if result is not None:\n                        result = replace(\n                            result,\n                            source_season=wcl_source_season_for_dungeon(dungeon),\n                        )\n''',
    "",
)

# Persist and restore source identity, and invalidate pre-audit WCL cache semantics.
replace_once(
    "companion/source/app/keystonelens_companion/wcl.py",
    'WCL_CONTEXT_VERSION = "midnight-season-aware-v12:role-aware-ranking-average:parses2w"\n',
    'WCL_CONTEXT_VERSION = "midnight-season-aware-v13:source-season-bound:role-aware-ranking-average:parses2w"\n',
)
replace_once(
    "companion/source/app/keystonelens_companion/wcl.py",
    "                        metric_brackets=metric_brackets,\n                    )\n",
    "                        metric_brackets=metric_brackets,\n                        source_season=str(row.get(\"source_season\") or \"\"),\n                    )\n",
)

# Region-aware display, local-current fallback for API lag, and accurate S1 aggregate wording.
replace_once(
    "companion/source/app/keystonelens_companion/ui.py",
    "        current = max(0, live.role_score or live.score)\n        if use_season1_carryover():\n",
    "        current = max(0, live.role_score or live.score or view.applicant.rio_score)\n        if use_season1_carryover(region=view.region):\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/ui.py",
    '''            if context_bracket:\n                scope = "full dungeon" if context_bracket.key_level <= 0 else f"+{context_bracket.key_level}"\n                context_text = (\n                    f"  |  {scope}  |  {context_bracket.run_count} "\n                    f"parse{'s' if context_bracket.run_count != 1 else ''}"\n                )\n''',
    '''            if context_bracket:\n                if view.wcl and view.wcl.source_season == "midnight-s1":\n                    scope = "Season 1 aggregate"\n                else:\n                    scope = "full dungeon" if context_bracket.key_level <= 0 else f"+{context_bracket.key_level}"\n                context_text = (\n                    f"  |  {scope}  |  {context_bracket.run_count} "\n                    f"parse{'s' if context_bracket.run_count != 1 else ''}"\n                )\n''',
)
replace_once(
    "companion/source/app/keystonelens_companion/ui.py",
    "        rio_rating = score.rio_effective or 0\n",
    "        rio_rating = _rio_rating_text(view)\n",
)
replace_once(
    "companion/source/app/keystonelens_companion/ui.py",
    "        meta_text = f\"RIO half {score.rio_score:.0f}/100  |  rating {rio_rating or '—'}  |  dungeon +{score.same_dungeon_key or 0}{run_score_text}\"\n",
    "        meta_text = f\"RIO half {score.rio_score:.0f}/100  |  rating {rio_rating}  |  dungeon +{score.same_dungeon_key or 0}{run_score_text}\"\n",
)

# Region-aware previous-rating fallback in scoring metadata.
replace_once(
    "companion/source/app/keystonelens_companion/scoring.py",
    "    if _usable_rio(rio) and rio and use_season1_carryover():\n",
    "    if _usable_rio(rio) and rio and use_season1_carryover(region=rio.region):\n",
)

# Extend transition tests with region, cache-boundary, race and UI-lag regressions.
test_path = ROOT / "companion/source/app/tests/test_season_transition.py"
tests = test_path.read_text(encoding="utf-8")
marker = "\n\ndef test_real_season1_listing_is_not_mistaken_for_s2_carryover():\n"
if tests.count(marker) != 1:
    raise SystemExit("transition test insertion marker changed")
extra = r'''

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
'''
test_path.write_text(tests.replace(marker, extra + marker, 1), encoding="utf-8")

print("Season transition self-audit fixes applied")
