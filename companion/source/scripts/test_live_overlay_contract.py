#!/usr/bin/env python3
"""Pure live-overlay contracts that do not require a Windows desktop."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "companion" / "source" / "app"
sys.path.insert(0, str(APP_ROOT))

from keystonelens_companion.live_overlay import (  # noqa: E402
    LiveTooltipOverlay,
    _generation16_is_newer,
    _normalized_rect_to_screen,
    _point_in_rect,
)
from keystonelens_companion.models import (  # noqa: E402
    Applicant,
    ApplicantView,
    EngineState,
    Listing,
    LiveHover,
    WCLBracket,
    WCLResult,
)


def applicant(spec_id: int = 62) -> Applicant:
    return Applicant(
        applicant_id=42,
        member_idx=1,
        class_id=8,
        spec_id=spec_id,
        ilvl=700,
        rio_score=0,
        rio_main_score=0,
        role_byte=3,
        name="Alice-Draenor",
    )


def hover(generation: int = 5, spec_id: int = 62, activity_id: int = 777) -> LiveHover:
    return LiveHover(
        generation=generation,
        applicant_id=42,
        member_idx=1,
        name="Alice-Draenor",
        spec_id=spec_id,
        activity_id=activity_id,
        value_x=32768,
        value_y=16384,
        value_w=8192,
        value_h=2048,
        owner_x=20000,
        owner_y=12000,
        owner_w=10000,
        owner_h=3000,
    )


def state(
    *,
    spec_id: int = 62,
    metric: str = "dps",
    percentile: float = 97.4,
    generation: int = 5,
    activity_id: int = 777,
) -> EngineState:
    bracket = WCLBracket(
        key_level=12,
        best_percentile=percentile,
        median_percentile=percentile,
        run_count=3,
        average_percentile=percentile,
    )
    result = WCLResult(
        name="Alice",
        realm="Draenor",
        dungeon_name="Test Dungeon",
        spec_id=spec_id,
        bracket=None,
        fetched_at=time.time(),
        metric_brackets={metric: bracket},
    )
    view = ApplicantView(
        applicant=applicant(spec_id),
        snapshot_listing=Listing(activity_id=777, key_level=12, dungeon_name="Test Dungeon"),
        region="EU",
        wcl=result,
        wcl_status="ready",
    )
    return EngineState(
        listing=Listing(activity_id=activity_id, key_level=12, dungeon_name="Test Dungeon"),
        rows=(view,),
        party=(),
        status="ready",
        live_hover=hover(generation, spec_id, activity_id),
    )


def fake_overlay():
    overlay = LiveTooltipOverlay.__new__(LiveTooltipOverlay)
    overlay.enabled = True
    overlay.current_generation = 0
    overlay.visible = False
    shown = []
    hidden = []
    overlay._show_value = lambda live, text, color: shown.append((live, text, color))
    overlay.hide = lambda: hidden.append(True)
    return overlay, shown, hidden


def test_dps_and_healing_labels() -> None:
    overlay, shown, _ = fake_overlay()
    overlay.update_from_state(state())
    assert shown[-1][1] == "DPS 97%"

    overlay, shown, _ = fake_overlay()
    overlay.update_from_state(state(spec_id=65, metric="hps", percentile=94.2))
    assert shown[-1][1] == "Healing 94%"


def test_identity_and_activity_fail_closed() -> None:
    overlay, shown, hidden = fake_overlay()
    bad = state(activity_id=778)
    # Listing and hover both say 778, but row still belongs to its captured 777 listing.
    overlay.update_from_state(bad)
    assert not shown
    assert hidden

    overlay, shown, hidden = fake_overlay()
    wrong_hover = hover()
    wrong_hover = LiveHover(**{**wrong_hover.__dict__, "applicant_id": 99})
    s = state()
    s = EngineState(**{**s.__dict__, "live_hover": wrong_hover})
    overlay.update_from_state(s)
    assert not shown
    assert hidden


def test_stale_generation_is_ignored() -> None:
    overlay, shown, hidden = fake_overlay()
    overlay.current_generation = 10
    overlay.update_from_state(state(generation=9))
    assert not shown
    assert not hidden


def test_geometry_mapping() -> None:
    rect = _normalized_rect_to_screen(
        0,
        0,
        32768,
        32768,
        (100, 200, 1000, 800),
    )
    assert rect == (100, 600, 500, 400)
    assert _point_in_rect((110, 610), rect)
    assert not _point_in_rect((50, 50), rect)
    assert _generation16_is_newer(1, 65535)
    assert not _generation16_is_newer(65535, 1)


if __name__ == "__main__":
    test_dps_and_healing_labels()
    test_identity_and_activity_fail_closed()
    test_stale_generation_is_ignored()
    test_geometry_mapping()
    print("KeystoneLens live overlay contract passed.")
