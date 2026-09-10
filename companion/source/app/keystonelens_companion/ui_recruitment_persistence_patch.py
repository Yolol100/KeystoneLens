"""Persistence bridge for recruitment view preferences.

The legacy App callback allowlists the original filter fields. This adapter
synchronizes the expanded Config first, then reuses the existing debounced and
atomic persistence callback without changing runtime/network ownership.
"""
from __future__ import annotations

from dataclasses import replace

from . import ui as _ui


def _notify_preferences(self: _ui.OverlayWindow, **changes: object) -> None:
    if not changes:
        return
    try:
        self.cfg = replace(self.cfg, **changes)
    except TypeError:
        return

    owner = getattr(self.on_preferences, "__self__", None)
    if owner is not None and hasattr(owner, "cfg"):
        try:
            owner.cfg = replace(owner.cfg, **changes)
        except TypeError:
            pass

    # App.save_preferences already owns debounce + atomic save. Include the
    # current score floor so its legacy allowlist schedules persistence even
    # when this event changes only a new recruitment-view preference.
    payload = dict(changes)
    payload.setdefault("score_min", self.score_min)
    self.on_preferences(payload)


def install() -> None:
    if getattr(_ui, "_RECRUITMENT_PERSISTENCE_PATCH_INSTALLED", False):
        return
    _ui._RECRUITMENT_PERSISTENCE_PATCH_INSTALLED = True
    _ui.OverlayWindow._notify_preferences = _notify_preferences
