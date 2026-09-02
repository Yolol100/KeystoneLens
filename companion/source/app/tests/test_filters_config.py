from __future__ import annotations

import unittest

from keystonelens_companion.config import _normalize_config
from keystonelens_companion.filters import filter_rows, normalize_score_range
from keystonelens_companion.models import Applicant, ApplicantView, Listing, ScoreBreakdown


def make_view(
    score: int,
    class_id: int,
    role_byte: int,
    *,
    loading: bool = False,
    wcl_error: bool = False,
    rio_error: bool = False,
) -> ApplicantView:
    applicant = Applicant(
        applicant_id=score + class_id + role_byte + 1,
        member_idx=1,
        class_id=class_id,
        spec_id=64,
        ilvl=680,
        rio_score=3000,
        rio_main_score=0,
        role_byte=role_byte,
        name=f"Player{score}-Realm",
    )
    listing = Listing(key_level=16, dungeon_name="Skyreach")
    view = ApplicantView(
        applicant=applicant,
        snapshot_listing=listing,
        region="EU",
        wcl_status="loading" if loading else ("error" if wcl_error else "ready"),
        rio_status="error" if rio_error else "ready",
    )
    view.score = ScoreBreakdown(
        score=score,
        label="Test",
        rio_score=float(score),
        wcl_score=float(score),
        wcl_weight=.5,
        confidence="test",
        reason="test",
        rio_effective=3000,
        target_key=16,
        same_dungeon_key=16,
        best_key=16,
        rio_weight=.5,
    )
    return view


class FilterTests(unittest.TestCase):
    def test_score_range_supports_both_halves(self):
        rows = [make_view(25, 8, 2), make_view(50, 2, 0), make_view(88, 8, 2)]
        self.assertEqual([v.score.score for v in filter_rows(rows, score_min=0, score_max=50)], [25, 50])
        self.assertEqual([v.score.score for v in filter_rows(rows, score_min=50, score_max=100)], [50, 88])

    def test_default_filter_keeps_original_84_floor(self):
        rows = [make_view(83, 8, 2), make_view(84, 8, 2), make_view(100, 8, 2)]
        self.assertEqual([v.score.score for v in filter_rows(rows)], [84, 100])

    def test_filters_compose_without_reordering(self):
        rows = [make_view(88, 8, 2), make_view(91, 2, 0), make_view(85, 8, 2)]
        out = filter_rows(rows, score_min=80, score_max=90, class_id=8, role="DPS")
        self.assertEqual([v.score.score for v in out], [88, 85])

    def test_loading_score_is_hidden(self):
        self.assertEqual(filter_rows([make_view(99, 8, 2, loading=True)]), [])

    def test_wcl_error_is_not_hidden_by_score_filter(self):
        rows = [make_view(42, 8, 2, wcl_error=True), make_view(42, 2, 0)]
        out = filter_rows(rows, score_min=84, score_max=100)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].applicant.class_id, 8)
        self.assertEqual(out[0].wcl_status, "error")

    def test_rio_error_is_not_hidden_by_score_filter_but_class_role_still_apply(self):
        rows = [
            make_view(40, 8, 2, rio_error=True),
            make_view(40, 2, 0, rio_error=True),
        ]
        out = filter_rows(rows, score_min=84, score_max=100, class_id=8, role="DPS")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].applicant.class_id, 8)
        self.assertEqual(out[0].rio_status, "error")

    def test_range_normalizes(self):
        self.assertEqual(normalize_score_range(90, 10), (10, 90))
        self.assertEqual(normalize_score_range(-10, 140), (0, 100))


class ConfigTests(unittest.TestCase):
    def test_new_settings_have_safe_defaults(self):
        cfg = _normalize_config({})
        self.assertEqual((cfg.score_min, cfg.score_max), (84, 100))
        self.assertTrue(cfg.show_role and cfg.show_class and cfg.show_spec and cfg.show_rio and cfg.show_wcl)

    def test_config_clamps_and_normalizes(self):
        cfg = _normalize_config({
            "score_min": 90,
            "score_max": 30,
            "class_filter_id": 99,
            "role_filter": "dps",
            "show_wcl": False,
        })
        self.assertEqual((cfg.score_min, cfg.score_max), (30, 90))
        self.assertIsNone(cfg.class_filter_id)
        self.assertEqual(cfg.role_filter, "DPS")
        self.assertFalse(cfg.show_wcl)


if __name__ == "__main__":
    unittest.main()
