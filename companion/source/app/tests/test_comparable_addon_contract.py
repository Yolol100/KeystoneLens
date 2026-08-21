from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from keystonelens_companion.addon_sync import render_data_addon_toc, render_tooltip_cache


# Use the canonical companion/source root so this regression works both in the
# repository checkout and when BUILD-RELEASE.sh re-tests the extracted source ZIP.
ROOT = Path(__file__).resolve().parents[2]
LOCALES = ("deDE", "esES", "esMX", "frFR", "itIT", "koKR", "ptBR", "ruRU", "zhCN", "zhTW")


def _view(confidence: str = "high"):
    return SimpleNamespace(
        applicant=SimpleNamespace(name="Applicant-Realm", spec_id=71),
        snapshot_listing=SimpleNamespace(activity_id=777, key_level=12),
        score=SimpleNamespace(
            score=88,
            label="STRONG",
            confidence=confidence,
            rio_score=84.0,
            rio_weight=0.5,
            wcl_score=92.0,
            wcl_weight=0.5,
            wcl_bracket=None,
        ),
        rio_status="ready",
        wcl_status="ready",
        rio=None,
        wcl=None,
    )


def _assert_grouped_dungeon_metadata(toc: str) -> None:
    assert toc.count("## Group: KeystoneLensBridge") == 1
    assert toc.count("## Category: Dungeons & Raids") == 1
    for locale in LOCALES:
        assert toc.count(f"## Category-{locale}:") == 1


def test_tooltip_cache_exports_explainable_confidence():
    rendered = render_tooltip_cache([_view("high")], now=1_700_000_000)
    assert 'confidence="high"' in rendered

    malformed = render_tooltip_cache([_view("impossible")], now=1_700_000_000)
    assert 'confidence="low"' in malformed


def test_tooltip_freshness_uses_oldest_contributing_online_evidence():
    view = _view()
    view.rio = SimpleNamespace(fetched_at=1_700_000_000)
    view.wcl = SimpleNamespace(fetched_at=1_699_990_000, metric_brackets={})
    rendered = render_tooltip_cache([view], now=1_700_000_100)
    assert "fetchedAt=1699990000" in rendered


def test_generated_addon_uses_shared_group_and_localized_category():
    _assert_grouped_dungeon_metadata(render_data_addon_toc())


def test_bridge_and_checked_in_data_addon_share_group_and_category():
    bridge_toc = (ROOT / "addon/KeystoneLensBridge/KeystoneLensBridge.toc").read_text(encoding="utf-8")
    data_toc = (ROOT / "data-addon/KeystoneLensCompanionData/KeystoneLensCompanionData.toc").read_text(encoding="utf-8")

    _assert_grouped_dungeon_metadata(bridge_toc)
    _assert_grouped_dungeon_metadata(data_toc)


def test_bridge_tooltip_surface_exposes_evidence_age():
    tooltip = (ROOT / "addon/KeystoneLensBridge/Core/Tooltip.lua").read_text(encoding="utf-8")
    audit = (ROOT / "docs/COMPARABLE-ADDON-AUDIT-2026-08-21.md").read_text(encoding="utf-8")

    assert 'local function FormatEvidence(entry)' in tooltip
    assert '"KL evidence"' in tooltip
    assert 'ageText = string.format("%dm old"' in tooltip
    assert "oldest contributing" in audit
    assert "context-specific Mythic+ evidence" in audit
    assert "Premade Applicants Filter" in audit
    assert "Pinta Group Finder" in audit
