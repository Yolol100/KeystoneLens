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
    "companion/source/app/keystonelens_companion/engine.py",
    '''def _with_wcl_source(result: WCLResult | None, expected_source: str) -> WCLResult | None:\n    """Stamp only source-less results; an explicit source is immutable evidence."""\n    if result is None or result.source_season or not expected_source:\n        return result\n    return replace(result, source_season=expected_source)\n\n\ndef _fetch_wcl_batch(client: WCLClient, jobs):\n''',
    '''def _with_wcl_source(result: WCLResult | None, expected_source: str) -> WCLResult | None:\n    """Stamp only source-less results; an explicit source is immutable evidence."""\n    if result is None or result.source_season or not expected_source:\n        return result\n    return replace(result, source_season=expected_source)\n\n\ndef _wcl_result_assignable(\n    result: WCLResult | None, listing: Listing | None, region: str\n) -> bool:\n    """Reject successful evidence that became stale while its request was in flight."""\n    if result is None or result.error:\n        return True\n    return _result_matches_listing(result, listing, region)\n\n\ndef _fetch_wcl_batch(client: WCLClient, jobs):\n''',
)
replace_once(
    "companion/source/app/keystonelens_companion/engine.py",
    '''                    if view and same_context and same_character and same_spec:\n                        view.wcl = result\n''',
    '''                    source_is_current = bool(\n                        view and _wcl_result_assignable(result, view.snapshot_listing, region)\n                    )\n                    if view and same_context and same_character and same_spec and source_is_current:\n                        view.wcl = result\n''',
)

# Add a direct regression for the exact in-flight cutover invariant used by the worker.
test_path = ROOT / "companion/source/app/tests/test_season_transition.py"
text = test_path.read_text(encoding="utf-8")
marker = "\n\ndef test_wcl_current_result_gets_source_bound_at_routing_time():\n"
if text.count(marker) != 1:
    raise SystemExit("test insertion marker changed")
extra = r'''


def test_wcl_success_from_prior_phase_is_rejected_when_it_arrives_after_cutover():
    listing = Listing(key_level=10, dungeon_name="Altar of Fangs")
    stale = WCLResult(
        "Applicant", "Realm", "Altar of Fangs", 71,
        WCLBracket(0, 80, 80, 1, 80), time.time(), target_key=10,
        source_season="midnight-s1",
    )
    with patch.object(engine, "wcl_source_season_for_dungeon", return_value="midnight-s2"):
        assert engine._wcl_result_assignable(stale, listing, "EU") is False


def test_wcl_current_phase_result_is_assignable():
    listing = Listing(key_level=10, dungeon_name="Altar of Fangs")
    current = WCLResult(
        "Applicant", "Realm", "Altar of Fangs", 71,
        WCLBracket(10, 55, 55, 1, 55), time.time(), target_key=10,
        source_season="midnight-s2",
    )
    with patch.object(engine, "wcl_source_season_for_dungeon", return_value="midnight-s2"):
        assert engine._wcl_result_assignable(current, listing, "EU") is True
'''
test_path.write_text(text.replace(marker, extra + marker, 1), encoding="utf-8")

print("WCL cutover race correction applied")
