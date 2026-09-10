"""Applicant-list search, spec filtering, unique-spec view and sortable columns.

Kept separate from the core Tk window for the same reason as ui_layout_patch:
the presentation behavior stays easy to test without changing enrichment or
scoring semantics.
"""
from __future__ import annotations

import tkinter as tk

from . import ui as _ui
from .filters import (
    DEFAULT_SCORE_MAX,
    DEFAULT_SCORE_MIN,
    DEFAULT_SORT_DESC,
    DEFAULT_SORT_KEY,
    normalize_search_query,
    normalize_sort_key,
    prepare_rows,
)

_ADVANCED_FILTER_HEIGHT = 34
_EXTRA_CHROME_HEIGHT = 42
_NUMERIC_SORT_KEYS = frozenset({"score", "rio", "wcl"})

_SPEC_CLASS_BY_ID = {
    250: 6, 251: 6, 252: 6,
    577: 12, 581: 12, 1480: 12,
    102: 11, 103: 11, 104: 11, 105: 11,
    1467: 13, 1468: 13, 1473: 13,
    253: 3, 254: 3, 255: 3,
    62: 8, 63: 8, 64: 8,
    268: 10, 269: 10, 270: 10,
    65: 2, 66: 2, 70: 2,
    256: 5, 257: 5, 258: 5,
    259: 4, 260: 4, 261: 4,
    262: 7, 263: 7, 264: 7,
    265: 9, 266: 9, 267: 9,
    71: 1, 72: 1, 73: 1,
}


def _spec_options(class_id: int | None = None) -> list[tuple[object | None, str]]:
    options: list[tuple[object | None, str]] = [(None, "All specs")]
    rows: list[tuple[str, int, str]] = []
    for spec_id, spec_name in _ui.SPEC_NAMES.items():
        owner_class = _SPEC_CLASS_BY_ID.get(spec_id)
        if class_id is not None and owner_class != class_id:
            continue
        class_name = _ui.CLASS_NAMES.get(owner_class or 0, "Unknown")
        label = spec_name if class_id is not None else f"{class_name} · {spec_name}"
        rows.append((label.casefold(), spec_id, label))
    rows.sort()
    options.extend((spec_id, label) for _sort, spec_id, label in rows)
    return options


def _sync_unique_button(self: _ui.OverlayWindow) -> None:
    if not hasattr(self, "unique_specs_button"):
        return
    enabled = bool(getattr(self, "unique_specs", False))
    self.unique_specs_button.configure(
        text="Unique specs: ON" if enabled else "Unique specs: OFF",
        fg=_ui.TEXT if enabled else _ui.MUTED,
        bg=_ui.PANEL if enabled else _ui.PANEL_ALT,
    )


def _sync_spec_options(self: _ui.OverlayWindow) -> None:
    if not hasattr(self, "spec_filter_dropdown"):
        return
    selected_class = self.class_filter_id if self.cfg.show_class else None
    selected_spec = self.spec_filter_id if self.cfg.show_spec else None
    if selected_spec is not None and selected_class is not None:
        if _SPEC_CLASS_BY_ID.get(selected_spec) != selected_class:
            selected_spec = None
            self.spec_filter_id = None
    selected = self.spec_filter_dropdown.set_options(
        _spec_options(selected_class), selected_spec
    )
    self.spec_filter_id = int(selected) if isinstance(selected, int) else None


def _overlay_build(self: _ui.OverlayWindow) -> None:
    _ORIGINAL_BUILD(self)
    advanced = tk.Frame(self.data, bg=_ui.BG, height=_ADVANCED_FILTER_HEIGHT)
    advanced.pack(fill="x", padx=12, pady=(0, 8), before=self.normal_panel)
    advanced.pack_propagate(False)
    self.advanced_filter_bar = advanced

    tk.Label(
        advanced, text="Search", bg=_ui.BG, fg=_ui.MUTED,
        font=(_ui.FONT, 8, "bold"),
    ).pack(side="left", padx=(0, 5))
    self.search_var = tk.StringVar(value=self.search_query)
    self.search_entry = tk.Entry(
        advanced, textvariable=self.search_var, bg=_ui.PANEL_ALT, fg=_ui.TEXT,
        insertbackground=_ui.TEXT, selectbackground=_ui.ACCENT,
        selectforeground="#07101c", relief="flat", bd=0,
        highlightthickness=1, highlightbackground=_ui.BORDER,
        highlightcolor=_ui.ACCENT, font=(_ui.FONT, 9),
    )
    self.search_entry.pack(side="left", fill="y", ipadx=7, ipady=3)
    self.search_entry.configure(width=18)
    self.search_var.trace_add("write", lambda *_args: self._set_search_query(self.search_var.get()))

    self.spec_filter_dropdown = _ui._FilterDropdown(
        advanced, "Specs", _spec_options(self.class_filter_id),
        self._set_spec_filter, width=185,
    )
    self.spec_filter_dropdown.pack(side="left", padx=(8, 0))
    self.spec_filter_dropdown.set_value(self.spec_filter_id)

    self.unique_specs_button = tk.Button(
        advanced, text="", command=self._toggle_unique_specs,
        bg=_ui.PANEL_ALT, fg=_ui.MUTED,
        activebackground=_ui.PANEL, activeforeground=_ui.TEXT,
        relief="flat", bd=0, highlightthickness=1,
        highlightbackground=_ui.BORDER, highlightcolor=_ui.ACCENT,
        padx=9, pady=2, font=(_ui.FONT, 8, "bold"),
        cursor="hand2", takefocus=1,
    )
    self.unique_specs_button.pack(side="left", padx=(8, 0))
    _sync_unique_button(self)

    self.sort_hint = tk.Label(
        advanced, text="Click a column header to sort",
        bg=_ui.BG, fg=_ui.MUTED, font=(_ui.FONT, 8),
    )
    self.sort_hint.pack(side="right")
    self._sync_filter_visibility()


def _overlay_init(self: _ui.OverlayWindow, *args, **kwargs) -> None:
    cfg = kwargs.get("cfg")
    if cfg is None and len(args) >= 6:
        cfg = args[5]
    self.spec_filter_id = getattr(cfg, "spec_filter_id", None)
    self.search_query = normalize_search_query(getattr(cfg, "search_query", ""))
    self.unique_specs = bool(getattr(cfg, "unique_specs", False))
    self.sort_key = normalize_sort_key(getattr(cfg, "sort_key", DEFAULT_SORT_KEY))
    self.sort_desc = bool(getattr(cfg, "sort_desc", DEFAULT_SORT_DESC))
    self._recruitment_syncing = False
    _ORIGINAL_INIT(self, *args, **kwargs)


def _overlay_apply_config(self: _ui.OverlayWindow, cfg) -> None:
    self.spec_filter_id = getattr(cfg, "spec_filter_id", None)
    self.search_query = normalize_search_query(getattr(cfg, "search_query", ""))
    self.unique_specs = bool(getattr(cfg, "unique_specs", False))
    self.sort_key = normalize_sort_key(getattr(cfg, "sort_key", DEFAULT_SORT_KEY))
    self.sort_desc = bool(getattr(cfg, "sort_desc", DEFAULT_SORT_DESC))
    self._recruitment_syncing = True
    try:
        _ORIGINAL_APPLY_CONFIG(self, cfg)
        if hasattr(self, "search_var"):
            self.search_var.set(self.search_query)
        _sync_spec_options(self)
        _sync_unique_button(self)
        self._sync_filter_visibility()
        self._rebuild_headers()
    finally:
        self._recruitment_syncing = False
    if self.rows:
        self._render_rows()


def _overlay_sync_filter_visibility(self: _ui.OverlayWindow) -> None:
    _ORIGINAL_SYNC_FILTER_VISIBILITY(self)
    if not hasattr(self, "spec_filter_dropdown"):
        return
    if self.cfg.show_spec:
        if not self.spec_filter_dropdown.winfo_manager():
            self.spec_filter_dropdown.pack(side="left", padx=(8, 0))
        if not self.unique_specs_button.winfo_manager():
            self.unique_specs_button.pack(side="left", padx=(8, 0))
    else:
        if self.spec_filter_dropdown.winfo_manager():
            self.spec_filter_dropdown.pack_forget()
        if self.unique_specs_button.winfo_manager():
            self.unique_specs_button.pack_forget()


def _overlay_active_filter_count(self: _ui.OverlayWindow) -> int:
    count = _ORIGINAL_ACTIVE_FILTER_COUNT(self)
    count += int(self.cfg.show_spec and self.spec_filter_id is not None)
    count += int(bool(self.search_query))
    count += int(self.cfg.show_spec and bool(self.unique_specs))
    return count


def _overlay_reset_filters(self: _ui.OverlayWindow) -> None:
    self.score_min, self.score_max = DEFAULT_SCORE_MIN, DEFAULT_SCORE_MAX
    self.class_filter_id = None
    self.role_filter = ""
    self.spec_filter_id = None
    self.search_query = ""
    self.unique_specs = False
    self.score_filter.set_range(DEFAULT_SCORE_MIN, DEFAULT_SCORE_MAX)
    self.class_filter.set_value(None)
    self.role_filter_dropdown.set_value(None)
    self._recruitment_syncing = True
    try:
        if hasattr(self, "search_var"):
            self.search_var.set("")
        _sync_spec_options(self)
        self.spec_filter_dropdown.set_value(None)
        _sync_unique_button(self)
    finally:
        self._recruitment_syncing = False
    self.canvas.yview_moveto(0.0)
    self._notify_preferences(
        score_min=DEFAULT_SCORE_MIN,
        score_max=DEFAULT_SCORE_MAX,
        class_filter_id=None,
        role_filter="",
        spec_filter_id=None,
        search_query="",
        unique_specs=False,
    )
    self._render_rows()


def _overlay_filtered(self: _ui.OverlayWindow):
    return prepare_rows(
        self.rows,
        score_min=self.score_min,
        score_max=self.score_max,
        class_id=self.class_filter_id if self.cfg.show_class else None,
        role=self.role_filter if self.cfg.show_role else "",
        spec_id=self.spec_filter_id if self.cfg.show_spec else None,
        search_query=self.search_query,
        sort_key=self.sort_key,
        sort_desc=self.sort_desc,
        unique_specs=self.unique_specs if self.cfg.show_spec else False,
    )


def _overlay_set_class_filter(self: _ui.OverlayWindow, class_id: object | None) -> None:
    self.class_filter_id = int(class_id) if isinstance(class_id, int) and class_id in _ui.CLASS_NAMES else None
    previous_spec = self.spec_filter_id
    _sync_spec_options(self)
    self.canvas.yview_moveto(0.0)
    changes: dict[str, object] = {"class_filter_id": self.class_filter_id}
    if self.spec_filter_id != previous_spec:
        changes["spec_filter_id"] = self.spec_filter_id
    self._notify_preferences(**changes)
    self._render_rows()


def _overlay_set_spec_filter(self: _ui.OverlayWindow, spec_id: object | None) -> None:
    if isinstance(spec_id, int) and spec_id in _ui.SPEC_NAMES:
        if self.class_filter_id is None or _SPEC_CLASS_BY_ID.get(spec_id) == self.class_filter_id:
            self.spec_filter_id = spec_id
        else:
            self.spec_filter_id = None
    else:
        self.spec_filter_id = None
    self.canvas.yview_moveto(0.0)
    self._notify_preferences(spec_filter_id=self.spec_filter_id)
    self._render_rows()


def _overlay_set_search_query(self: _ui.OverlayWindow, value: object) -> None:
    query = normalize_search_query(value)
    if query == self.search_query:
        return
    self.search_query = query
    if getattr(self, "_recruitment_syncing", False):
        return
    self.canvas.yview_moveto(0.0)
    self._notify_preferences(search_query=query)
    self._render_rows()


def _overlay_toggle_unique_specs(self: _ui.OverlayWindow) -> None:
    self.unique_specs = not bool(self.unique_specs)
    _sync_unique_button(self)
    self.canvas.yview_moveto(0.0)
    self._notify_preferences(unique_specs=self.unique_specs)
    self._render_rows()


def _overlay_set_sort_key(self: _ui.OverlayWindow, key: object) -> None:
    normalized = normalize_sort_key(key)
    if normalized == self.sort_key:
        self.sort_desc = not bool(self.sort_desc)
    else:
        self.sort_key = normalized
        self.sort_desc = normalized in _NUMERIC_SORT_KEYS
    self.canvas.yview_moveto(0.0)
    self._notify_preferences(sort_key=self.sort_key, sort_desc=self.sort_desc)
    self._rebuild_headers()
    self._render_rows()


def _overlay_rebuild_headers(self: _ui.OverlayWindow) -> None:
    if not hasattr(self, "cols"):
        return
    for child in self.cols.winfo_children():
        child.destroy()
    visible_specs = [spec for spec in _ui.COLUMN_SPECS if spec[0] in self.visible_column_keys]
    for idx, (key, label, _base_width, anchor) in enumerate(visible_specs):
        base_label = label.replace(" ↓", "").replace(" ↑", "")
        if key == self.sort_key:
            base_label += " ↓" if self.sort_desc else " ↑"
        box = tk.Frame(
            self.cols, bg=_ui.PANEL_ALT,
            width=self.column_widths[key], height=27,
        )
        box.pack(side="left", fill="y")
        box.pack_propagate(False)
        button = tk.Button(
            box, text=base_label, command=lambda column=key: self._set_sort_key(column),
            bg=_ui.PANEL_ALT, fg=_ui.TEXT if key == self.sort_key else _ui.MUTED,
            activebackground=_ui.PANEL, activeforeground=_ui.TEXT,
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground=_ui.PANEL_ALT, highlightcolor=_ui.ACCENT,
            font=(_ui.FONT, 8, "bold"), cursor="hand2", takefocus=1,
            anchor=anchor,
        )
        if anchor == "center":
            button.place(
                relx=0.5, rely=0.5,
                x=_ui.ROLE_OFFSET_X if key == "role" else 0,
                anchor="center", width=max(1, self.column_widths[key] - 4), height=25,
            )
        else:
            button.pack(fill="both", expand=True, padx=(4, 0))
        if idx < len(visible_specs) - 1:
            self._column_gap(self.cols, _ui.PANEL_ALT)


def _overlay_height_bounds(self: _ui.OverlayWindow, shown: int, *, detail: bool):
    chrome, minimum, maximum = _ORIGINAL_HEIGHT_BOUNDS(self, shown, detail=detail)
    if not hasattr(self, "advanced_filter_bar"):
        return chrome, minimum, maximum
    _left, top, _screen_width, screen_height = _ui._virtual_screen_bounds(self.root)
    available = max(self.MIN_DATA_HEIGHT, top + screen_height - max(top, self.root.winfo_y()) - 20)
    extra = _EXTRA_CHROME_HEIGHT
    return (
        chrome + extra,
        min(available, minimum + extra),
        min(available, maximum + extra),
    )


def install() -> None:
    if getattr(_ui, "_RECRUITMENT_PATCH_INSTALLED", False):
        return
    _ui._RECRUITMENT_PATCH_INSTALLED = True

    global _ORIGINAL_BUILD, _ORIGINAL_INIT, _ORIGINAL_APPLY_CONFIG
    global _ORIGINAL_SYNC_FILTER_VISIBILITY, _ORIGINAL_ACTIVE_FILTER_COUNT
    global _ORIGINAL_HEIGHT_BOUNDS

    _ORIGINAL_BUILD = _ui.OverlayWindow._build
    _ORIGINAL_INIT = _ui.OverlayWindow.__init__
    _ORIGINAL_APPLY_CONFIG = _ui.OverlayWindow.apply_config
    _ORIGINAL_SYNC_FILTER_VISIBILITY = _ui.OverlayWindow._sync_filter_visibility
    _ORIGINAL_ACTIVE_FILTER_COUNT = _ui.OverlayWindow._active_filter_count
    _ORIGINAL_HEIGHT_BOUNDS = _ui.OverlayWindow._height_bounds

    _ui.OverlayWindow.__init__ = _overlay_init
    _ui.OverlayWindow._build = _overlay_build
    _ui.OverlayWindow.apply_config = _overlay_apply_config
    _ui.OverlayWindow._sync_filter_visibility = _overlay_sync_filter_visibility
    _ui.OverlayWindow._active_filter_count = _overlay_active_filter_count
    _ui.OverlayWindow._reset_filters = _overlay_reset_filters
    _ui.OverlayWindow._filtered = _overlay_filtered
    _ui.OverlayWindow._set_class_filter = _overlay_set_class_filter
    _ui.OverlayWindow._set_spec_filter = _overlay_set_spec_filter
    _ui.OverlayWindow._set_search_query = _overlay_set_search_query
    _ui.OverlayWindow._toggle_unique_specs = _overlay_toggle_unique_specs
    _ui.OverlayWindow._set_sort_key = _overlay_set_sort_key
    _ui.OverlayWindow._rebuild_headers = _overlay_rebuild_headers
    _ui.OverlayWindow._height_bounds = _overlay_height_bounds
