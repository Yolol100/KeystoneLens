from __future__ import annotations

from types import SimpleNamespace

from keystonelens_companion.addon_sync import render_tooltip_cache


def _view(*, activity_id: int = 777, key_level: int = 12, spec_id: int = 71):
    return SimpleNamespace(
        applicant=SimpleNamespace(name="Applicant-Realm", spec_id=spec_id),
        snapshot_listing=SimpleNamespace(activity_id=activity_id, key_level=key_level),
        score=SimpleNamespace(
            score=88,
            label="Strong",
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


def test_tooltip_cache_persists_exact_scoring_context():
    rendered = render_tooltip_cache([_view()], now=1_700_000_000)

    assert "version = 2" in rendered
    assert "activityID=777" in rendered
    assert "keyLevel=12" in rendered
    assert "specID=71" in rendered
    assert "score=88" in rendered


def test_tooltip_cache_rejects_rows_without_complete_context():
    rendered = render_tooltip_cache([
        _view(activity_id=0),
        _view(key_level=0),
        _view(spec_id=0),
    ], now=1_700_000_000)

    assert '["Applicant-Realm"]' not in rendered
