from __future__ import annotations

import inspect

from keystonelens_companion.ui import _ToggleSwitch


def test_settings_toggle_has_clear_visual_size() -> None:
    assert _ToggleSwitch.WIDTH >= 48
    assert _ToggleSwitch.HEIGHT >= 28
    assert _ToggleSwitch.TRACK_BOTTOM - _ToggleSwitch.TRACK_TOP >= 20
    assert _ToggleSwitch.THUMB_RADIUS >= 8


def test_settings_toggle_draws_high_contrast_state_and_focus() -> None:
    source = inspect.getsource(_ToggleSwitch)
    assert 'track = ACCENT if on else DIALOG_CONTROL_BORDER' in source
    assert 'outline = "#8fc5ff" if on else DIALOG_MUTED' in source
    assert 'self.bind("<FocusIn>", lambda _e: self._draw())' in source
    assert 'fill=TEXT, outline="#ffffff", width=1' in source
