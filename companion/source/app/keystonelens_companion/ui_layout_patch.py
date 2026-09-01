"""Adaptive layout fixes for KeystoneLens' borderless Tk windows.

Kept separate from the core UI so resize/alignment behavior stays easy to test
without changing ranking, filtering, or data semantics.
"""
from __future__ import annotations

import tkinter as tk

from . import ui as _ui

_SETTINGS_WIDTH = 640
_SETTINGS_MIN_WIDTH = 600


def _virtual_limits(widget: tk.Misc, min_width: int, min_height: int) -> tuple[int, int]:
    left, top, screen_width, screen_height = _ui._virtual_screen_bounds(widget)
    max_width = max(min_width, left + screen_width - widget.winfo_x())
    max_height = max(min_height, top + screen_height - widget.winfo_y())
    return max_width, max_height


def _settings_resize_start(self: _ui.SetupDialog, event) -> None:
    self._layout_resize_drag = (
        event.x_root, event.y_root, self.winfo_width(), self.winfo_height()
    )


def _settings_resize_move(self: _ui.SetupDialog, event) -> None:
    start_x, start_y, start_width, start_height = self._layout_resize_drag
    requested_width = start_width + (event.x_root - start_x)
    requested_height = start_height + (event.y_root - start_y)
    min_width = max(_SETTINGS_MIN_WIDTH, int(getattr(self, "_layout_min_width", 1)))
    min_height = max(1, int(getattr(self, "_layout_min_height", 1)))
    max_width, max_height = _virtual_limits(self, min_width, min_height)
    width = max(min_width, min(max_width, requested_width))
    height = max(min_height, min(max_height, requested_height))
    self.geometry(f"{int(width)}x{int(height)}")


def _install_settings_resize(self: _ui.SetupDialog) -> None:
    self.update_idletasks()
    self._layout_min_width = max(_SETTINGS_MIN_WIDTH, self.winfo_reqwidth())
    self._layout_min_height = self.winfo_reqheight()
    self._layout_resize_drag = (0, 0, self.winfo_width(), self.winfo_height())
    grip = tk.Canvas(
        self, width=16, height=16, bg=_ui.BG, highlightthickness=0, bd=0,
        cursor="sizing", takefocus=0,
    )
    grip.create_line(5, 13, 13, 5, fill=_ui.MUTED, width=1)
    grip.create_line(9, 13, 13, 9, fill=_ui.MUTED, width=1)
    grip.place(relx=1.0, rely=1.0, x=-2, y=-2, anchor="se")
    grip.bind("<ButtonPress-1>", self._layout_resize_start)
    grip.bind("<B1-Motion>", self._layout_resize_move)
    self.layout_resize_grip = grip


def _overlay_refresh_column_layout(self: _ui.OverlayWindow) -> None:
    keys = self._visible_columns_for_config()
    base = sum(_ui.COLUMN_WIDTH_BY_KEY[key] for key in keys)
    gaps = _ui.COLUMN_GAP * max(0, len(keys) - 1)
    natural = base + gaps + _ui.WINDOW_CHROME_WIDTH
    self.layout_minimum_width = max(_ui.MIN_WINDOW_WIDTH, natural)
    requested = getattr(self, "layout_user_width", None)
    self.width = max(self.layout_minimum_width, int(requested or self.layout_minimum_width))
    widths = {key: _ui.COLUMN_WIDTH_BY_KEY[key] for key in keys}
    if "player" in widths and self.width > natural:
        widths["player"] += self.width - natural
    self.visible_column_keys = keys
    self.column_widths = widths


def _overlay_set_user_width(self: _ui.OverlayWindow, width: int | None) -> None:
    if width is None:
        return
    try:
        requested = int(width)
    except (TypeError, ValueError):
        return
    self.layout_user_width = max(_ui.MIN_WINDOW_WIDTH, requested)
    self._refresh_column_layout()
    if hasattr(self, "cols"):
        self._rebuild_headers()
        if self.rows:
            self._render_rows()
        else:
            self.root.geometry(f"{self.width}x{self.current_height}")


def _overlay_resize_start(self: _ui.OverlayWindow, event) -> None:
    self._layout_resize_drag = (
        event.x_root, event.y_root, self.width, self.current_height
    )


def _overlay_resize_move(self: _ui.OverlayWindow, event) -> None:
    start_x, start_y, start_width, start_height = self._layout_resize_drag
    requested_width = start_width + (event.x_root - start_x)
    self.layout_user_width = max(self.layout_minimum_width, int(requested_width))
    self._refresh_column_layout()
    self._rebuild_headers()

    if self.rows:
        requested_height = start_height + (event.y_root - start_y)
        _chrome, minimum, maximum = self._height_bounds(
            len(self._filtered()), detail=bool(self.selected_identity)
        )
        self.user_height = max(minimum, min(maximum, requested_height))
        self._render_rows()
    else:
        self.root.geometry(f"{self.width}x{self.current_height}")


def _overlay_resize_end(self: _ui.OverlayWindow, _event) -> None:
    # Height already has a persistent callback in the core UI. Width intentionally
    # remains a session layout choice so no config/schema migration is required.
    if self.user_height is not None:
        self.on_resize(self.current_height)


def _overlay_header_cell(
    self: _ui.OverlayWindow,
    parent: tk.Misc,
    text: str,
    width: int,
    *,
    anchor: str = "w",
    offset_x: int = 0,
) -> None:
    box = tk.Frame(parent, bg=_ui.PANEL_ALT, width=width, height=27)
    box.pack(side="left", fill="y")
    box.pack_propagate(False)
    justify = "center" if anchor == "center" else "left"
    label = tk.Label(
        box, text=text, bg=_ui.PANEL_ALT, fg=_ui.MUTED,
        font=(_ui.FONT, 8, "bold"), anchor=anchor, justify=justify,
    )
    if anchor == "center":
        label.place(relx=0.5, rely=0.5, x=offset_x, anchor="center")
    else:
        label.place(x=6, rely=0.5, anchor="w")


def _center_row_widgets(self: _ui.OverlayWindow, row: tk.Frame) -> None:
    # Column frames and gap frames alternate. Re-place only the actual column
    # content so every word/icon shares one vertical center line.
    children = row.winfo_children()
    column_boxes = children[::2]
    for key, box in zip(self.visible_column_keys, column_boxes):
        box_children = box.winfo_children()
        if not box_children:
            continue
        widget = box_children[0]
        if key == "role":
            continue
        if not isinstance(widget, tk.Label):
            continue
        widget.pack_forget()
        if key == "score":
            widget.place(x=5, rely=0.5, anchor="w")
            continue
        if key in {"player", "rio", "wcl"}:
            widget.configure(font=(_ui.FONT, 9, "bold"))
        else:
            widget.configure(font=(_ui.FONT, 9))
        widget.place(x=6, rely=0.5, anchor="w")


def _install_overlay_post_init(self: _ui.OverlayWindow) -> None:
    self.layout_user_width = None
    self.layout_minimum_width = max(_ui.MIN_WINDOW_WIDTH, self.width)
    self._layout_resize_drag = (0, 0, self.width, self.current_height)
    if hasattr(self, "resize_grip"):
        try:
            self.resize_grip.configure(cursor="sizing")
        except tk.TclError:
            pass
        self.resize_grip.delete("all")
        self.resize_grip.create_line(5, 20, 13, 12, fill=_ui.MUTED, width=1)
        self.resize_grip.create_line(9, 20, 13, 16, fill=_ui.MUTED, width=1)


def install() -> None:
    if getattr(_ui, "_LAYOUT_PATCH_INSTALLED", False):
        return
    _ui._LAYOUT_PATCH_INSTALLED = True

    _ui.SetupDialog.WIDTH = _SETTINGS_WIDTH
    _ui.SetupDialog.MIN_WIDTH = _SETTINGS_MIN_WIDTH
    _ui.SetupDialog._layout_resize_start = _settings_resize_start
    _ui.SetupDialog._layout_resize_move = _settings_resize_move
    original_settings_init = _ui.SetupDialog.__init__

    def settings_init(self, *args, **kwargs):
        original_settings_init(self, *args, **kwargs)
        _install_settings_resize(self)

    _ui.SetupDialog.__init__ = settings_init

    original_overlay_init = _ui.OverlayWindow.__init__
    original_render_row = _ui.OverlayWindow._render_row

    def overlay_init(self, *args, **kwargs):
        self.layout_user_width = None
        self.layout_minimum_width = _ui.MIN_WINDOW_WIDTH
        original_overlay_init(self, *args, **kwargs)
        _install_overlay_post_init(self)

    def render_row(self, view, idx: int) -> None:
        original_render_row(self, view, idx)
        rows = self.list_frame.winfo_children()
        if rows:
            _center_row_widgets(self, rows[-1])

    _ui.OverlayWindow.__init__ = overlay_init
    _ui.OverlayWindow._refresh_column_layout = _overlay_refresh_column_layout
    _ui.OverlayWindow.set_user_width = _overlay_set_user_width
    _ui.OverlayWindow._resize_start = _overlay_resize_start
    _ui.OverlayWindow._resize_move = _overlay_resize_move
    _ui.OverlayWindow._resize_end = _overlay_resize_end
    _ui.OverlayWindow._header_cell = _overlay_header_cell
    _ui.OverlayWindow._render_row = render_row
