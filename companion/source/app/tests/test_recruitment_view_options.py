from __future__ import annotations

import inspect

from keystonelens_companion import ui, ui_recruitment_patch
from keystonelens_companion.config import Config, _config_payload, _normalize_config
from keystonelens_companion.constants import CLASS_NAMES, SPEC_NAMES
from keystonelens_companion.filters import (
    MAX_SEARCH_CHARS,
    SORT_KEYS,
    normalize_search_query,
    prepare_rows,
)
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


def _sample_rows() -> list[ApplicantView]:
    return [
        make_view(1, "Alpha-Realm", score=90, class_id=8, spec_id=64, role_byte=2, rio=2800, wcl=91),
        make_view(2, "Bravo-Realm", score=89, class_id=8, spec_id=64, role_byte=2, rio=3100, wcl=88),
        make_view(3, "Cleric-Realm", score=92, class_id=5, spec_id=257, role_byte=1, rio=2950, wcl=95),
        make_view(4, "Guard-Realm", score=87, class_id=1, spec_id=73, role_byte=0, rio=3050, wcl=80),
    ]


def _names(rows: list[ApplicantView]) -> list[str]:
    return [view.applicant.name for view in rows]


def test_recruitment_role_class_spec_and_combined_filters():
    rows = _sample_rows()
    assert _names(prepare_rows(rows, role="HEALER", score_min=0)) == ["Cleric-Realm"]
    assert _names(prepare_rows(rows, class_id=8, score_min=0)) == ["Alpha-Realm", "Bravo-Realm"]
    assert _names(prepare_rows(rows, spec_id=64, score_min=0)) == ["Alpha-Realm", "Bravo-Realm"]
    assert _names(prepare_rows(
        rows,
        class_id=8,
        spec_id=64,
        role=" dps ",
        search_query="alpha",
        score_min=0,
    )) == ["Alpha-Realm"]


def test_search_matches_player_class_spec_and_role_case_insensitively():
    rows = _sample_rows()
    assert _names(prepare_rows(rows, search_query="BRAVO", score_min=0)) == ["Bravo-Realm"]
    assert _names(prepare_rows(rows, search_query="mage", score_min=0)) == ["Alpha-Realm", "Bravo-Realm"]
    assert _names(prepare_rows(rows, search_query="fRoSt", score_min=0)) == ["Alpha-Realm", "Bravo-Realm"]
    assert _names(prepare_rows(rows, search_query="tank", score_min=0)) == ["Guard-Realm"]


def test_search_input_is_bounded_and_control_whitespace_is_collapsed():
    assert normalize_search_query("  Mage\n\tFrost  ") == "Mage Frost"
    assert normalize_search_query(1234) == ""
    assert normalize_search_query("x" * (MAX_SEARCH_CHARS + 50)) == "x" * MAX_SEARCH_CHARS


def test_rio_sort_and_unique_specs_follow_active_sort():
    rows = _sample_rows()
    assert _names(prepare_rows(rows, sort_key="rio", sort_desc=True, score_min=0)) == [
        "Bravo-Realm", "Guard-Realm", "Cleric-Realm", "Alpha-Realm",
    ]
    assert _names(prepare_rows(
        rows, sort_key="rio", sort_desc=True, unique_specs=True, score_min=0,
    )) == ["Bravo-Realm", "Guard-Realm", "Cleric-Realm"]
    assert _names(prepare_rows(
        rows, sort_key="rio", sort_desc=False, unique_specs=True, score_min=0,
    )) == ["Alpha-Realm", "Cleric-Realm", "Guard-Realm"]


def test_every_visible_column_sorts_in_both_directions():
    rows = [
        make_view(1, "Charlie-Realm", score=80, class_id=8, spec_id=64, role_byte=2, rio=2800, wcl=71),
        make_view(2, "Alpha-Realm", score=90, class_id=2, spec_id=65, role_byte=1, rio=3100, wcl=95),
        make_view(3, "Bravo-Realm", score=85, class_id=1, spec_id=73, role_byte=0, rio=2950, wcl=83),
    ]
    expected_ascending = {
        "score": ["Charlie-Realm", "Bravo-Realm", "Alpha-Realm"],
        "role": ["Charlie-Realm", "Alpha-Realm", "Bravo-Realm"],
        "player": ["Alpha-Realm", "Bravo-Realm", "Charlie-Realm"],
        "class": ["Charlie-Realm", "Alpha-Realm", "Bravo-Realm"],
        "spec": ["Charlie-Realm", "Alpha-Realm", "Bravo-Realm"],
        "rio": ["Charlie-Realm", "Bravo-Realm", "Alpha-Realm"],
        "wcl": ["Charlie-Realm", "Bravo-Realm", "Alpha-Realm"],
    }
    assert set(expected_ascending) == set(SORT_KEYS)
    for sort_key, ascending in expected_ascending.items():
        assert _names(prepare_rows(rows, score_min=0, sort_key=sort_key, sort_desc=False)) == ascending
        assert _names(prepare_rows(rows, score_min=0, sort_key=sort_key, sort_desc=True)) == list(reversed(ascending))


def test_sort_is_stable_on_ties_and_invalid_key_falls_back_to_score():
    tied = [
        make_view(1, "Bravo-Realm", score=80, class_id=8, spec_id=64, role_byte=2, rio=3000, wcl=80),
        make_view(2, "Alpha-Realm", score=90, class_id=2, spec_id=65, role_byte=1, rio=3000, wcl=90),
    ]
    assert _names(prepare_rows(tied, score_min=0, sort_key="rio", sort_desc=False)) == ["Bravo-Realm", "Alpha-Realm"]
    assert _names(prepare_rows(tied, score_min=0, sort_key="rio", sort_desc=True)) == ["Bravo-Realm", "Alpha-Realm"]
    assert _names(prepare_rows(tied, score_min=0, sort_key="not-a-column", sort_desc=True)) == ["Alpha-Realm", "Bravo-Realm"]


def test_missing_wcl_values_sort_last_in_both_directions():
    rows = [
        make_view(1, "High-Realm", score=90, class_id=8, spec_id=64, role_byte=2, rio=3000, wcl=93),
        make_view(2, "Missing-Realm", score=89, class_id=2, spec_id=70, role_byte=2, rio=3100, wcl=None),
        make_view(3, "Low-Realm", score=88, class_id=5, spec_id=258, role_byte=2, rio=2900, wcl=50),
    ]
    assert _names(prepare_rows(rows, score_min=0, sort_key="wcl", sort_desc=True)) == [
        "High-Realm", "Low-Realm", "Missing-Realm",
    ]
    assert _names(prepare_rows(rows, score_min=0, sort_key="wcl", sort_desc=False)) == [
        "Low-Realm", "High-Realm", "Missing-Realm",
    ]


def test_unique_specs_is_strict_even_when_provider_error_shares_a_spec():
    rows = [
        make_view(1, "Error-Realm", score=99, class_id=8, spec_id=64, role_byte=2, rio=2900, wcl=None, wcl_error=True),
        make_view(2, "Good-Realm", score=90, class_id=8, spec_id=64, role_byte=2, rio=3000, wcl=93),
        make_view(3, "Other-Realm", score=89, class_id=2, spec_id=70, role_byte=2, rio=3100, wcl=85),
    ]
    by_score = prepare_rows(rows, score_min=0, sort_key="score", sort_desc=True, unique_specs=True)
    assert _names(by_score) == ["Error-Realm", "Other-Realm"]
    assert len({view.applicant.spec_id for view in by_score}) == len(by_score)

    by_wcl = prepare_rows(rows, score_min=0, sort_key="wcl", sort_desc=True, unique_specs=True)
    assert _names(by_wcl) == ["Good-Realm", "Other-Realm"]
    assert len({view.applicant.spec_id for view in by_wcl}) == len(by_wcl)


def test_unique_specs_does_not_merge_unknown_spec_ids():
    rows = [
        make_view(1, "Unknown-A", score=95, class_id=8, spec_id=9999, role_byte=2, rio=3000, wcl=90),
        make_view(2, "Unknown-B", score=90, class_id=8, spec_id=9999, role_byte=2, rio=2900, wcl=85),
    ]
    assert _names(prepare_rows(rows, score_min=0, unique_specs=True)) == ["Unknown-A", "Unknown-B"]


def test_provider_errors_stay_fail_visible_but_pending_rows_do_not_render():
    failed = make_view(1, "Failed-Realm", score=20, class_id=8, spec_id=64, role_byte=2, rio=2500, wcl=None, wcl_error=True)
    healthy_low = make_view(2, "Low-Realm", score=20, class_id=2, spec_id=70, role_byte=2, rio=2500, wcl=20)
    pending = make_view(3, "Pending-Realm", score=99, class_id=1, spec_id=73, role_byte=0, rio=3500, wcl=99)
    pending.rio_status = "loading"
    assert _names(prepare_rows([failed, healthy_low, pending])) == ["Failed-Realm"]


def test_config_normalizes_new_view_preferences_and_invalid_inputs():
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

    invalid = _normalize_config({
        "spec_filter_id": True,
        "search_query": ["mage"],
        "unique_specs": "yes",
        "sort_key": "unknown",
        "sort_desc": "no",
    })
    assert invalid.spec_filter_id is None
    assert invalid.search_query == ""
    assert invalid.unique_specs is False
    assert invalid.sort_key == "score"
    assert invalid.sort_desc is True


def test_config_payload_preserves_all_recruitment_preferences():
    cfg = Config(
        score_min=70,
        score_max=98,
        class_filter_id=8,
        role_filter="DPS",
        spec_filter_id=64,
        search_query="frost mage",
        unique_specs=True,
        sort_key="rio",
        sort_desc=False,
    )
    payload = _config_payload(cfg)
    for key in (
        "score_min", "score_max", "class_filter_id", "role_filter",
        "spec_filter_id", "search_query", "unique_specs", "sort_key", "sort_desc",
    ):
        assert payload[key] == getattr(cfg, key)


def test_ui_preference_bridge_updates_overlay_and_app_owner_before_debounced_save():
    class Owner:
        def __init__(self) -> None:
            self.cfg = Config(score_min=73)
            self.calls: list[dict[str, object]] = []

        def save_preferences(self, changes: dict[str, object]) -> None:
            self.calls.append(dict(changes))

    owner = Owner()
    overlay = object.__new__(ui.OverlayWindow)
    overlay.cfg = Config(score_min=73)
    overlay.score_min = 73
    overlay.on_preferences = owner.save_preferences

    overlay._notify_preferences(
        spec_filter_id=64,
        search_query="mage",
        unique_specs=True,
        sort_key="rio",
        sort_desc=False,
    )

    assert overlay.cfg.spec_filter_id == 64
    assert overlay.cfg.search_query == "mage"
    assert overlay.cfg.unique_specs is True
    assert overlay.cfg.sort_key == "rio"
    assert overlay.cfg.sort_desc is False
    assert owner.cfg == overlay.cfg
    assert owner.calls == [{
        "spec_filter_id": 64,
        "search_query": "mage",
        "unique_specs": True,
        "sort_key": "rio",
        "sort_desc": False,
        "score_min": 73,
    }]


def test_spec_to_class_mapping_covers_every_supported_spec():
    mapping = ui_recruitment_patch._SPEC_CLASS_BY_ID
    assert set(mapping) == set(SPEC_NAMES)
    assert all(class_id in CLASS_NAMES for class_id in mapping.values())


def test_ui_recruitment_patch_is_installed_and_sort_headers_are_keyboard_focusable():
    assert hasattr(ui.OverlayWindow, "_set_spec_filter")
    assert hasattr(ui.OverlayWindow, "_set_sort_key")
    header_source = inspect.getsource(ui.OverlayWindow._rebuild_headers)
    assert "_set_sort_key" in header_source
    assert "tk.Button" in header_source
    assert "takefocus=1" in header_source
    assert "prepare_rows" in inspect.getsource(ui.OverlayWindow._filtered)
    assert "score_min" in inspect.getsource(ui.OverlayWindow._notify_preferences)
