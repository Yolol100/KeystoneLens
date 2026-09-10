from __future__ import annotations

import inspect

from keystonelens_companion import ui
from keystonelens_companion.config import _normalize_config
from keystonelens_companion.filters import prepare_rows
from keystonelens_companion.models import Applicant, ApplicantView, Listing, ScoreBreakdown


def make_view(
    applicant_id: int,
    name: str,
    *,
    score: int,
    class_id: int,
    spec_id: int,
    role_byte: int,
    rio: int,
    wcl: float | None,
    wcl_error: bool = False,
    rio_error: bool = False,
) -> ApplicantView:
    applicant = Applicant(
        applicant_id=applicant_id,
        member_idx=1,
        class_id=class_id,
        spec_id=spec_id,
        ilvl=700,
        rio_score=rio,
        rio_main_score=0,
        role_byte=role_byte,
        name=name,
    )
    view = ApplicantView(
        applicant=applicant,
        snapshot_listing=Listing(key_level=16, dungeon_name="Skyreach"),
        region="EU",
        wcl_status="error" if wcl_error else "ready",
        rio_status="error" if rio_error else "ready",
    )
    view.score = ScoreBreakdown(
        score=score,
        label="Test",
        rio_score=float(score),
        wcl_score=wcl,
        wcl_weight=.5,
        confidence="test",
        reason="test",
        rio_effective=rio,
        target_key=16,
        same_dungeon_key=16,
        best_key=16,
        rio_weight=.5,
    )
    return view


def test_recruitment_filters_search_sort_and_unique_specs():
    rows = [
        make_view(1, "Alpha-Realm", score=90, class_id=8, spec_id=64, role_byte=2, rio=2800, wcl=91),
        make_view(2, "Bravo-Realm", score=89, class_id=8, spec_id=64, role_byte=2, rio=3100, wcl=88),
        make_view(3, "Cleric-Realm", score=92, class_id=5, spec_id=257, role_byte=1, rio=2950, wcl=95),
        make_view(4, "Guard-Realm", score=87, class_id=1, spec_id=73, role_byte=0, rio=3050, wcl=80),
    ]

    assert [v.applicant.name for v in prepare_rows(rows, role="HEALER", score_min=0)] == ["Cleric-Realm"]
    assert [v.applicant.name for v in prepare_rows(rows, spec_id=64, score_min=0)] == ["Alpha-Realm", "Bravo-Realm"]
    assert [v.applicant.name for v in prepare_rows(rows, search_query="mage", score_min=0)] == ["Alpha-Realm", "Bravo-Realm"]
    assert [v.applicant.name for v in prepare_rows(rows, sort_key="rio", sort_desc=True, score_min=0)] == [
        "Bravo-Realm", "Guard-Realm", "Cleric-Realm", "Alpha-Realm",
    ]
    assert [v.applicant.name for v in prepare_rows(
        rows, sort_key="rio", sort_desc=True, unique_specs=True, score_min=0,
    )] == ["Bravo-Realm", "Guard-Realm", "Cleric-Realm"]


def test_wcl_missing_sorts_last_and_source_errors_remain_visible_with_unique_specs():
    rows = [
        make_view(1, "Good-Realm", score=90, class_id=8, spec_id=64, role_byte=2, rio=3000, wcl=93),
        make_view(2, "Missing-Realm", score=89, class_id=2, spec_id=70, role_byte=2, rio=3100, wcl=None),
        make_view(3, "Error-Realm", score=40, class_id=8, spec_id=64, role_byte=2, rio=2900, wcl=None, wcl_error=True),
    ]
    ordered = prepare_rows(rows, score_min=0, sort_key="wcl", sort_desc=True, unique_specs=True)
    assert [v.applicant.name for v in ordered] == ["Good-Realm", "Missing-Realm", "Error-Realm"]


def test_every_visible_column_has_a_supported_sort_key():
    rows = [
        make_view(1, "Zulu-Realm", score=80, class_id=8, spec_id=64, role_byte=2, rio=2800, wcl=71),
        make_view(2, "Alpha-Realm", score=90, class_id=2, spec_id=65, role_byte=1, rio=3100, wcl=95),
    ]
    for sort_key in ("score", "role", "player", "class", "spec", "rio", "wcl"):
        ordered = prepare_rows(rows, score_min=0, sort_key=sort_key, sort_desc=False)
        assert sorted(v.applicant.identity for v in ordered) == sorted(v.applicant.identity for v in rows)


def test_config_normalizes_new_view_preferences():
    cfg = _normalize_config({
        "spec_filter_id": 64,
        "search_query": "  mage\n frost  ",
        "unique_specs": 1,
        "sort_key": "RIO",
        "sort_desc": 0,
    })
    assert cfg.spec_filter_id == 64
    assert cfg.search_query == "mage frost"
    assert cfg.unique_specs is True
    assert cfg.sort_key == "rio"
    assert cfg.sort_desc is False


def test_ui_recruitment_patch_is_installed():
    assert hasattr(ui.OverlayWindow, "_set_spec_filter")
    assert hasattr(ui.OverlayWindow, "_set_sort_key")
    assert "_set_sort_key" in inspect.getsource(ui.OverlayWindow._rebuild_headers)
    assert "prepare_rows" in inspect.getsource(ui.OverlayWindow._filtered)
    assert "score_min" in inspect.getsource(ui.OverlayWindow._notify_preferences)
