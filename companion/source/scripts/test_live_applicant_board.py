#!/usr/bin/env python3
"""Controlled-runtime checks for the live Companion applicant board."""
from __future__ import annotations

from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "companion" / "source" / "app"
sys.path.insert(0, str(APP_ROOT))

from keystonelens_companion.metrics import applicant_board_rows, percentile_grade  # noqa: E402
from keystonelens_companion.models import (  # noqa: E402
    Applicant,
    ApplicantView,
    WCLBracket,
    WCLResult,
)


def view(name: str, percentile: float | None, *, spec_id: int = 62, status: str = "ready") -> ApplicantView:
    applicant = Applicant(
        applicant_id=1,
        member_idx=1,
        class_id=8,
        spec_id=spec_id,
        ilvl=0,
        rio_score=0,
        rio_main_score=0,
        role_byte=0,
        name=name,
    )
    result = None
    if percentile is not None:
        metric_key = "hps" if spec_id == 65 else "dps"
        bracket = WCLBracket(
            key_level=0,
            best_percentile=float(percentile),
            median_percentile=float(percentile),
            run_count=1,
            average_percentile=float(percentile),
        )
        result = WCLResult(
            name=name.split("-", 1)[0],
            realm=name.split("-", 1)[1],
            dungeon_name="Altar of Fangs",
            spec_id=spec_id,
            bracket=None,
            fetched_at=time.time(),
            metric_brackets={metric_key: bracket},
        )
    return ApplicantView(
        applicant=applicant,
        snapshot_listing=None,
        region="EU",
        wcl=result,
        wcl_status=status,
    )


def test_grade_boundaries():
    assert percentile_grade(99) == "S"
    assert percentile_grade(90) == "A"
    assert percentile_grade(80) == "B"
    assert percentile_grade(60) == "C"
    assert percentile_grade(30) == "D"
    assert percentile_grade(15) == "E"
    assert percentile_grade(5) == "F"
    assert percentile_grade(None) == "—"


def test_rows_sort_highest_first_and_keep_role_label():
    rows = applicant_board_rows([
        view("Middle-Draenor", 76),
        view("Top-Draenor", 98),
        view("Healer-Draenor", 91, spec_id=65),
        view("Loading-Draenor", None, status="loading"),
    ])
    assert rows[0] == ("Top-Draenor", "DPS 98%", "S")
    assert rows[1] == ("Healer-Draenor", "Healing 91%", "A")
    assert rows[2] == ("Middle-Draenor", "DPS 76%", "B")
    assert rows[3] == ("Loading-Draenor", "Laden…", "—")


def test_unavailable_rows_sort_after_valid_wcl():
    rows = applicant_board_rows([
        view("NoData-Draenor", None, status="none"),
        view("Ready-Draenor", 44),
        view("Error-Draenor", None, status="error"),
    ])
    assert rows[0] == ("Ready-Draenor", "DPS 44%", "D")
    assert rows[1][1] in {"Geen WCL-data", "WCL fout"}
    assert rows[2][1] in {"Geen WCL-data", "WCL fout"}


if __name__ == "__main__":
    test_grade_boundaries()
    test_rows_sort_highest_first_and_keep_role_label()
    test_unavailable_rows_sort_after_valid_wcl()
    print("KeystoneLens live applicant board contract passed.")
