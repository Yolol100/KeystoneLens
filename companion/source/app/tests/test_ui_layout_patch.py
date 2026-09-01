from __future__ import annotations

import inspect

from keystonelens_companion import ui


def test_settings_dialog_is_roomy_and_has_resize_patch() -> None:
    assert ui.SetupDialog.WIDTH >= 640
    assert ui.SetupDialog.MIN_WIDTH >= 600
    assert hasattr(ui.SetupDialog, "_layout_resize_start")
    assert hasattr(ui.SetupDialog, "_layout_resize_move")


def test_overlay_has_width_resize_and_centered_header_contract() -> None:
    assert hasattr(ui.OverlayWindow, "set_user_width")
    assert "layout_user_width" in inspect.getsource(ui.OverlayWindow._refresh_column_layout)
    assert "rely=0.5" in inspect.getsource(ui.OverlayWindow._header_cell)
    assert "render_row" in ui.OverlayWindow._render_row.__name__
