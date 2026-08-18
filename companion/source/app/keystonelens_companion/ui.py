from __future__ import annotations
from dataclasses import replace
import ctypes
import os
import re
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
from typing import Callable

from .config import Config
from .constants import (
    ACCENT, BG, BORDER, CLASS_NAMES, GREEN, MUTED, ORANGE, PANEL, PANEL_ALT, PURPLE,
    RED, ROLE_NAMES, SPEC_NAMES, TEXT, YELLOW,
)
from .filters import (
    DEFAULT_SCORE_MAX, DEFAULT_SCORE_MIN, ROLE_FILTERS, filter_rows, has_final_score,
    normalize_score_range,
)
from .models import ApplicantView, EngineState
from .scoring import wcl_metric_scores
from .registries import use_season1_carryover

FONT = "Segoe UI"
RAIDER_IO_URL = "https://raider.io"


def open_raider_io() -> bool:
    """Open the fixed Raider.IO attribution URL without accepting user input."""
    try:
        return bool(webbrowser.open_new_tab(RAIDER_IO_URL))
    except Exception:
        return False


# Settings-only text roles keep the overlay palette intact while improving form legibility.
DIALOG_MUTED = "#aab3c0"
DIALOG_LABEL = "#c5ccd6"
DIALOG_ACCENT_HOVER = "#74b7ff"
DIALOG_TITLE_SIZE = 11
DIALOG_PARENT_ALPHA = 0.72
DIALOG_CONTROL_BORDER = "#56647b"

# The visible table uses one shared spacing contract in both the header and rows.
COLUMN_GAP = 14
ROLE_OFFSET_X = -11
SETTINGS_TEXT_OFFSET_X = -4
COLUMN_SPECS = (
    ("score", "Score ↓", 66, "w"),
    ("role", "Role", 60, "center"),
    ("player", "Applicant", 110, "w"),
    ("class", "Class", 110, "w"),
    ("spec", "Spec", 110, "w"),
    ("rio", "Raider.IO", 170, "w"),
    ("wcl", "WCL", 93, "w"),
)
COLUMN_WIDTH_BY_KEY = {key: width for key, _label, width, _anchor in COLUMN_SPECS}
WINDOW_CHROME_WIDTH = 39  # table padding, outer border and scrollbar reserve
DEFAULT_TABLE_WIDTH = sum(width for _key, _label, width, _anchor in COLUMN_SPECS) + COLUMN_GAP * (len(COLUMN_SPECS) - 1)
WINDOW_WIDTH = DEFAULT_TABLE_WIDTH + WINDOW_CHROME_WIDTH
MIN_WINDOW_WIDTH = 640
FILTER_HEIGHT = 26


def score_colour(score: int) -> str:
    if score >= 85:
        return PURPLE
    if score >= 70:
        return GREEN
    if score >= 55:
        return YELLOW
    return RED


def pct_colour(pct: float | None) -> str:
    if pct is None:
        return MUTED
    if pct >= 95:
        return ORANGE
    if pct >= 75:
        return PURPLE
    if pct >= 50:
        return ACCENT
    if pct >= 25:
        return GREEN
    return MUTED


def _rio_rating_text(view: ApplicantView) -> str:
    """Format the visible Raider.IO rating without changing KL score semantics."""
    live = view.rio if view.rio and not view.rio.error and not view.rio.not_found else None
    main_rio = max(0, view.applicant.rio_main_score)
    if live is not None:
        current = max(0, live.role_score or live.score or view.applicant.rio_score)
        if use_season1_carryover(region=view.region):
            previous = max(0, live.previous_role_score or live.previous_score)
            return f"{current} / {previous}" if previous else f"{current} / —"
        return str(current)
    local_rio = max(0, view.applicant.rio_score)
    if local_rio:
        return str(local_rio)
    return f"M {main_rio}" if main_rio else "—"


def validate_settings_values(client_id: str, client_secret: str, screenshots_path: str) -> str:
    raw_path = screenshots_path.strip()
    if not raw_path:
        return "Select your WoW Screenshots folder."
    path = Path(raw_path).expanduser()
    if path.exists() and not path.is_dir():
        return "Select a valid Screenshots folder."

    # Validate the path shape even when the WoW drive is temporarily offline.
    # Path() cannot parse Windows backslashes on non-Windows test hosts, so use
    # separator-agnostic components for this contract check.
    parts = [part for part in re.split(r"[\\/]+", raw_path.rstrip("\\/")) if part]
    if len(parts) < 2 or parts[-1].casefold() != "screenshots" or parts[-2].casefold() != "_retail_":
        return r"Choose the World of Warcraft\_retail_\Screenshots folder."
    if bool(client_id.strip()) != bool(client_secret.strip()):
        return "Enter both Warcraft Logs credentials, or leave both fields empty."
    return ""


def _virtual_screen_bounds(root: tk.Misc) -> tuple[int, int, int, int]:
    """Return virtual desktop bounds, including monitors left of the primary one."""
    if os.name == "nt":
        try:
            user32 = ctypes.windll.user32
            return (
                int(user32.GetSystemMetrics(76)),  # SM_XVIRTUALSCREEN
                int(user32.GetSystemMetrics(77)),  # SM_YVIRTUALSCREEN
                int(user32.GetSystemMetrics(78)),  # SM_CXVIRTUALSCREEN
                int(user32.GetSystemMetrics(79)),  # SM_CYVIRTUALSCREEN
            )
        except (AttributeError, OSError):
            pass
    return 0, 0, int(root.winfo_screenwidth()), int(root.winfo_screenheight())


class _CaptionButton(tk.Canvas):
    """Pixel-drawn caption button so minimize/close have identical geometry."""

    def __init__(self, parent: tk.Misc, kind: str, command: Callable[[], None]):
        self.kind = kind
        self.command = command
        self._hover = False
        self._pressed = False
        super().__init__(
            parent, width=40, height=42, bg=PANEL, highlightthickness=0, bd=0,
            cursor="arrow", takefocus=1,
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Key-Return>", self._on_key_invoke)
        self.bind("<Key-space>", self._on_key_invoke)
        self.bind("<FocusIn>", lambda _e: self._draw())
        self.bind("<FocusOut>", lambda _e: self._draw())
        self._draw()

    def _on_enter(self, _event=None) -> None:
        self._hover = True
        self._draw()

    def _on_leave(self, _event=None) -> None:
        self._hover = False
        self._pressed = False
        self._draw()

    def _on_press(self, _event=None) -> None:
        self._pressed = True
        self._draw()

    def _on_release(self, event) -> None:
        inside = 0 <= event.x < 40 and 0 <= event.y < 42
        was_pressed = self._pressed
        self._pressed = False
        self._draw()
        if was_pressed and inside:
            self.command()

    def _on_key_invoke(self, _event=None) -> str:
        self.command()
        return "break"

    def _draw(self) -> None:
        self.delete("all")
        if self.kind == "close" and (self._hover or self._pressed):
            background = RED
        elif self._hover or self._pressed or self.focus_get() is self:
            background = PANEL_ALT
        else:
            background = PANEL
        self.configure(bg=background)
        colour = TEXT if self._hover or self._pressed or self.focus_get() is self else MUTED
        # Both glyphs use the same compact 9 px footprint and 40x42 hit target.
        # Minimize intentionally draws exactly one canvas item/one horizontal stroke.
        if self.kind == "minimize":
            self.create_line(16, 21, 24, 21, fill=colour, width=1)
        elif self.kind == "close":
            self.create_line(16, 17, 24, 25, fill=colour, width=1)
            self.create_line(24, 17, 16, 25, fill=colour, width=1)


class _HeaderTextButton(tk.Frame):
    """Native header button with a fixed hit target and optical text offset."""

    WIDTH = 72
    HEIGHT = 42

    def __init__(self, parent: tk.Misc, text: str, command: Callable[[], None], *, text_offset_x: int = 0):
        self.text_offset_x = int(text_offset_x)
        super().__init__(parent, width=self.WIDTH, height=self.HEIGHT, bg=PANEL)
        self.pack_propagate(False)

        # Keep the visible hit target at 72x42 while shifting only the text.
        # The slightly wider native Button is clipped by this frame, preserving
        # normal keyboard/button semantics instead of replacing it with a Canvas.
        inner_x = min(0, self.text_offset_x * 2)
        inner_width = self.WIDTH - inner_x
        self.button = tk.Button(
            self, text=text, command=command, bg=PANEL, fg=MUTED,
            activebackground=PANEL_ALT, activeforeground=TEXT, relief="flat", bd=0,
            highlightthickness=0, font=(FONT, 9), cursor="hand2", takefocus=1,
        )
        self.button.place(x=inner_x, y=0, width=inner_width, height=self.HEIGHT)
        self.button.bind("<FocusIn>", lambda _e: self.button.configure(bg=PANEL_ALT, fg=TEXT), add="+")
        self.button.bind("<FocusOut>", lambda _e: self.button.configure(bg=PANEL, fg=MUTED), add="+")


class _FilterDropdown(tk.Frame):
    """Compact overlay-native dropdown with deterministic keyboard/button behavior."""

    def __init__(
        self,
        parent: tk.Misc,
        label: str,
        options: list[tuple[object | None, str]],
        on_change: Callable[[object | None], None],
        *,
        width: int = 126,
    ):
        super().__init__(parent, bg=BORDER, width=width, height=FILTER_HEIGHT, padx=1, pady=1)
        self.pack_propagate(False)
        self.label = label
        self.on_change = on_change
        self.selected_value: object | None = None
        self._menu_options: list[tuple[object | None, str]] = []
        self.button = tk.Menubutton(
            self, text=f"All {label.lower()}  ▾", bg=PANEL_ALT, fg=TEXT,
            activebackground=PANEL, activeforeground=TEXT, relief="flat", bd=0,
            highlightthickness=0, font=(FONT, 8, "bold"), anchor="w",
            cursor="hand2", takefocus=1, padx=9, disabledforeground=MUTED,
        )
        self.button.pack(fill="both", expand=True)
        self.menu = tk.Menu(
            self.button, tearoff=False, bg=PANEL_ALT, fg=TEXT,
            activebackground=ACCENT, activeforeground="#07101c",
            relief="flat", bd=1, font=(FONT, 9),
        )
        self.button.configure(menu=self.menu)
        self.set_options(options, None)

    def set_options(
        self,
        options: list[tuple[object | None, str]],
        selected_value: object | None,
    ) -> object | None:
        if not options or options[0][0] is not None:
            options = [(None, f"All {self.label.lower()}"), *options]
        values = {value for value, _label in options}
        if selected_value not in values:
            selected_value = None
        if options != self._menu_options:
            self.menu.delete(0, "end")
            for value, label in options:
                self.menu.add_command(label=label, command=lambda v=value: self._choose(v))
            self._menu_options = list(options)
        self.selected_value = selected_value
        label = next((text for value, text in options if value == selected_value), options[0][1])
        self.button.configure(text=f"{label}  ▾", state="normal", cursor="hand2")
        return selected_value

    def set_value(self, value: object | None) -> object | None:
        return self.set_options(self._menu_options, value)

    def _choose(self, value: object | None) -> None:
        if value == self.selected_value:
            return
        self.selected_value = value
        label = next((text for option, text in self._menu_options if option == value), self._menu_options[0][1])
        self.button.configure(text=f"{label}  ▾")
        self.on_change(value)


class _ScoreRangeFilter(tk.Frame):
    """Small dual-handle KL score range slider (0..100)."""

    TRACK_WIDTH = 118
    TRACK_HEIGHT = 26
    TRACK_LEFT = 8
    TRACK_RIGHT = 110
    TRACK_Y = 13
    HANDLE_RADIUS = 5

    def __init__(self, parent: tk.Misc, on_change: Callable[[int, int], None]):
        super().__init__(parent, bg=BG)
        self.on_change = on_change
        self.low, self.high = 0, 100
        self._drag_handle = "low"
        self.value = tk.Label(self, text="Score 0–100", bg=BG, fg=TEXT, font=(FONT, 8, "bold"))
        self.value.pack(side="left", padx=(0, 5))
        self.canvas = tk.Canvas(
            self, width=self.TRACK_WIDTH, height=self.TRACK_HEIGHT, bg=BG,
            highlightthickness=1, highlightbackground=BG, highlightcolor=ACCENT,
            bd=0, cursor="hand2", takefocus=1,
        )
        self.canvas.pack(side="left")
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Key-Left>", lambda _e: self._nudge(-1))
        self.canvas.bind("<Key-Right>", lambda _e: self._nudge(1))
        self.canvas.bind("<Key-Up>", self._switch_handle)
        self.canvas.bind("<Key-Down>", self._switch_handle)
        self._draw()

    def set_range(self, low: int, high: int, *, notify: bool = False) -> tuple[int, int]:
        self.low, self.high = normalize_score_range(low, high)
        self._draw()
        if notify:
            self.on_change(self.low, self.high)
        return self.low, self.high

    def _x_for(self, value: int) -> float:
        span = self.TRACK_RIGHT - self.TRACK_LEFT
        return self.TRACK_LEFT + span * (value / 100.0)

    def _value_for(self, x: float) -> int:
        span = self.TRACK_RIGHT - self.TRACK_LEFT
        value = round(100 * (x - self.TRACK_LEFT) / max(1, span))
        return max(0, min(100, value))

    def _draw(self) -> None:
        self.canvas.delete("all")
        x1, x2 = self._x_for(self.low), self._x_for(self.high)
        self.canvas.create_line(self.TRACK_LEFT, self.TRACK_Y, self.TRACK_RIGHT, self.TRACK_Y, fill=BORDER, width=4)
        self.canvas.create_line(x1, self.TRACK_Y, x2, self.TRACK_Y, fill=ACCENT, width=4)
        for name, x in (("low", x1), ("high", x2)):
            active = name == self._drag_handle and self.canvas.focus_get() is self.canvas
            radius = self.HANDLE_RADIUS + (1 if active else 0)
            self.canvas.create_oval(
                x - radius, self.TRACK_Y - radius, x + radius, self.TRACK_Y + radius,
                fill=TEXT if active else ACCENT, outline=BG, width=1,
            )
        self.value.configure(text=f"Score {self.low}–{self.high}")

    def _nearest_handle(self, x: float) -> str:
        return "low" if abs(x - self._x_for(self.low)) <= abs(x - self._x_for(self.high)) else "high"

    def _press(self, event) -> None:
        self.canvas.focus_set()
        self._drag_handle = self._nearest_handle(event.x)
        self._apply_x(event.x)

    def _drag(self, event) -> None:
        self._apply_x(event.x)

    def _release(self, event) -> None:
        self._apply_x(event.x)
        self.on_change(self.low, self.high)

    def _apply_x(self, x: float) -> None:
        value = self._value_for(x)
        if self._drag_handle == "low":
            self.low = min(value, self.high)
        else:
            self.high = max(value, self.low)
        self._draw()

    def _nudge(self, delta: int) -> str:
        if self._drag_handle == "low":
            self.low = max(0, min(self.high, self.low + delta))
        else:
            self.high = min(100, max(self.low, self.high + delta))
        self._draw()
        self.on_change(self.low, self.high)
        return "break"

    def _switch_handle(self, _event=None) -> str:
        self._drag_handle = "high" if self._drag_handle == "low" else "low"
        self._draw()
        return "break"


class _ToggleSwitch(tk.Canvas):
    WIDTH = 38
    HEIGHT = 20

    def __init__(self, parent: tk.Misc, variable: tk.BooleanVar):
        super().__init__(
            parent, width=self.WIDTH, height=self.HEIGHT, bg=str(parent.cget("bg")),
            highlightthickness=1, highlightbackground=str(parent.cget("bg")), highlightcolor=ACCENT,
            bd=0, cursor="hand2", takefocus=1,
        )
        self.variable = variable
        self.bind("<Button-1>", self._toggle)
        self.bind("<Key-space>", self._toggle)
        self.bind("<Key-Return>", self._toggle)
        self.variable.trace_add("write", lambda *_args: self._draw())
        self._draw()

    def _toggle(self, _event=None) -> str:
        self.variable.set(not self.variable.get())
        return "break"

    def _draw(self) -> None:
        self.delete("all")
        on = bool(self.variable.get())
        track = ACCENT if on else DIALOG_CONTROL_BORDER
        self.create_oval(2, 3, 16, 17, fill=track, outline=track)
        self.create_oval(22, 3, 36, 17, fill=track, outline=track)
        self.create_rectangle(9, 3, 29, 17, fill=track, outline=track)
        cx = 28 if on else 10
        self.create_oval(cx - 6, 4, cx + 6, 16, fill=TEXT, outline="")


class SetupDialog(tk.Toplevel):
    WIDTH = 520

    def __init__(self, parent: tk.Misc, cfg: Config, on_save: Callable[[Config], bool | None]):
        super().__init__(parent)
        self.title("Settings")
        self.configure(bg=BORDER)
        self.resizable(False, False)
        self.transient(parent)
        self.overrideredirect(True)
        self.on_save = on_save
        self.cfg = cfg
        self._parent = parent
        self._parent_alpha: float | None = None
        try:
            self._parent_alpha = float(parent.attributes("-alpha"))
            parent.attributes("-alpha", DIALOG_PARENT_ALPHA)
        except (tk.TclError, TypeError, ValueError):
            self._parent_alpha = None
        self._drag = (0, 0)
        self._secret_visible = False
        self.vars = {
            "client_id": tk.StringVar(value=cfg.client_id),
            "client_secret": tk.StringVar(value=cfg.client_secret),
            "screenshots_path": tk.StringVar(value=cfg.screenshots_path),
        }
        self.column_vars = {
            "show_role": tk.BooleanVar(value=cfg.show_role),
            "show_class": tk.BooleanVar(value=cfg.show_class),
            "show_spec": tk.BooleanVar(value=cfg.show_spec),
            "show_rio": tk.BooleanVar(value=cfg.show_rio),
            "show_wcl": tk.BooleanVar(value=cfg.show_wcl),
        }
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", self._on_return)

        outer = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        body = tk.Frame(outer, bg=BG)
        body.pack(fill="both", expand=True)

        # Use the dialog task as the single title, styled like the overlay brand.
        titlebar = tk.Frame(body, bg=PANEL, height=42)
        titlebar.pack(fill="x")
        titlebar.pack_propagate(False)
        title = tk.Label(titlebar, text="Settings", bg=PANEL, fg=TEXT,
                         font=(FONT, DIALOG_TITLE_SIZE, "bold"))
        title.pack(side="left", padx=(14, 0))
        _CaptionButton(titlebar, "close", self.destroy).pack(side="right")
        for widget in (titlebar, title):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)

        # Keep the body flat and quiet. Sections are separated by spacing/a single rule,
        # rather than nesting bordered cards inside the dialog.
        content = tk.Frame(body, bg=BG, padx=18, pady=12)
        content.pack(fill="both", expand=True)

        wow = tk.Frame(content, bg=BG)
        wow.pack(fill="x")
        tk.Label(wow, text="World of Warcraft", bg=BG, fg=TEXT,
                 font=(FONT, 9, "bold"), anchor="w").grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Label(wow, text="Screenshots folder", bg=BG, fg=DIALOG_LABEL,
                 font=(FONT, 8), anchor="w").grid(row=1, column=0, columnspan=2, sticky="w", pady=(9, 4))
        self.path_entry = self._entry(wow, self.vars["screenshots_path"])
        self.path_entry.grid(row=2, column=0, sticky="ew", ipady=4)
        self.browse_button = self._button(wow, "Browse", self._browse)
        self.browse_button.grid(row=2, column=1, padx=(8, 0), sticky="ns")
        wow.grid_columnconfigure(0, weight=1)

        tk.Frame(content, bg=BORDER, height=1).pack(fill="x", pady=(13, 12))

        wcl = tk.Frame(content, bg=BG)
        wcl.pack(fill="x")
        heading = tk.Frame(wcl, bg=BG)
        heading.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(heading, text="Warcraft Logs", bg=BG, fg=TEXT,
                 font=(FONT, 9, "bold")).pack(side="left")
        tk.Label(heading, text="Optional", bg=PANEL_ALT, fg=DIALOG_MUTED,
                 font=(FONT, 7), padx=6, pady=1).pack(side="right")
        tk.Label(
            wcl, text="Public Warcraft Logs data contributes 50% of the KL Score.",
            bg=BG, fg=DIALOG_MUTED, font=(FONT, 8), anchor="w",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 7))

        tk.Label(wcl, text="Client ID", bg=BG, fg=DIALOG_LABEL,
                 font=(FONT, 8), anchor="w").grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.client_id_entry = self._entry(wcl, self.vars["client_id"])
        self.client_id_entry.grid(row=3, column=0, columnspan=2, sticky="ew", ipady=4)

        tk.Label(wcl, text="Client Secret", bg=BG, fg=DIALOG_LABEL,
                 font=(FONT, 8), anchor="w").grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 4))
        self.secret_entry = self._entry(wcl, self.vars["client_secret"], show="•")
        self.secret_entry.grid(row=5, column=0, sticky="ew", ipady=4)
        self.secret_toggle = self._button(wcl, "Show", self._toggle_secret)
        self.secret_toggle.grid(row=5, column=1, padx=(8, 0), sticky="ns")
        tk.Label(
            wcl,
            text="Client Secret is protected by Windows.",
            bg=BG, fg=DIALOG_MUTED, font=(FONT, 8), wraplength=440,
            justify="left", anchor="w",
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))
        wcl.grid_columnconfigure(0, weight=1)

        tk.Frame(content, bg=BORDER, height=1).pack(fill="x", pady=(13, 12))

        display = tk.Frame(content, bg=BG)
        display.pack(fill="x")
        tk.Label(display, text="Visible columns", bg=BG, fg=TEXT,
                 font=(FONT, 9, "bold"), anchor="w").pack(fill="x")
        tk.Label(
            display, text="Show or hide columns without changing the KL Score.",
            bg=BG, fg=DIALOG_MUTED, font=(FONT, 8), anchor="w",
        ).pack(fill="x", pady=(2, 7))
        toggle_grid = tk.Frame(display, bg=BG)
        toggle_grid.pack(fill="x")
        toggles = (
            ("show_role", "Role", "Show the Role column and filter"),
            ("show_class", "Class", "Show the Class column and filter"),
            ("show_spec", "Spec", "Show the Specialization column"),
            ("show_rio", "Raider.IO", "Show Raider.IO details"),
            ("show_wcl", "Warcraft Logs", "Show Warcraft Logs details"),
        )
        for index, (key, label, description) in enumerate(toggles):
            row = self._setting_toggle(toggle_grid, label, description, self.column_vars[key])
            row.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0, 10) if index % 2 == 0 else (10, 0), pady=2)
        toggle_grid.grid_columnconfigure(0, weight=1, uniform="column")
        toggle_grid.grid_columnconfigure(1, weight=1, uniform="column")

        self.error_label = tk.Label(
            content, text="", bg=BG, fg=RED, font=(FONT, 8),
            anchor="w", justify="left", wraplength=440,
        )
        self.error_label.pack(fill="x", pady=(6, 0))

        attribution = tk.Label(
            content, text="Data by Raider.IO • raider.io", bg=BG, fg=ACCENT,
            font=(FONT, 8, "underline"), cursor="hand2", anchor="w",
        )
        attribution.pack(fill="x", pady=(7, 0))
        attribution.bind("<Button-1>", lambda _event: open_raider_io())

        # Footer is outside the scrollable/content area so the primary action can never
        # be pushed below the visible dialog on short desktops.
        tk.Frame(body, bg=BORDER, height=1).pack(fill="x")
        actions = tk.Frame(body, bg=BG, padx=18, pady=9)
        actions.pack(fill="x")
        # Create controls in visual/tab order (Cancel -> Save), then pack Save first
        # so it remains the rightmost primary action while keyboard focus stays logical.
        self.cancel_button = self._button(actions, "Cancel", self.destroy)
        self.save_button = self._button(actions, "Save", self._save, primary=True)
        self.save_button.pack(side="right")
        self.cancel_button.pack(side="right", padx=(0, 8))

        self.update_idletasks()
        self._center_over_parent(parent)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.grab_set()
        self.after_idle(self.path_entry.focus_set)

    def destroy(self) -> None:
        # Keep modal focus visually clear while open, then restore the overlay exactly.
        parent = getattr(self, "_parent", None)
        parent_alpha = getattr(self, "_parent_alpha", None)
        self._parent_alpha = None
        if parent is not None and parent_alpha is not None:
            try:
                if parent.winfo_exists():
                    parent.attributes("-alpha", parent_alpha)
            except tk.TclError:
                pass
        super().destroy()

    @staticmethod
    def _button(parent: tk.Misc, text: str, command: Callable[[], None], *, primary: bool = False) -> tk.Button:
        bg = ACCENT if primary else PANEL_ALT
        fg = "#07101c" if primary else TEXT
        hover_bg = DIALOG_ACCENT_HOVER if primary else PANEL
        button = tk.Button(
            parent, text=text, command=command, bg=bg, fg=fg,
            activebackground=hover_bg, activeforeground=fg,
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground=BG, highlightcolor=ACCENT,
            padx=11, pady=4, font=(FONT, 8, "bold" if primary else "normal"),
            cursor="hand2", takefocus=1,
        )
        button.bind("<Enter>", lambda _e, b=button, c=hover_bg: b.configure(bg=c), add="+")
        button.bind("<Leave>", lambda _e, b=button, c=bg: b.configure(bg=c), add="+")
        return button

    @staticmethod
    def _entry(parent: tk.Misc, variable: tk.StringVar, *, show: str | None = None) -> tk.Entry:
        return tk.Entry(
            parent, textvariable=variable, show=show, bg=PANEL_ALT, fg=TEXT,
            insertbackground=TEXT, selectbackground=ACCENT, selectforeground="#07101c",
            relief="flat", bd=0, highlightthickness=1, font=(FONT, 9),
            highlightbackground=DIALOG_CONTROL_BORDER, highlightcolor=ACCENT,
        )

    @staticmethod
    def _setting_toggle(parent: tk.Misc, label: str, description: str, variable: tk.BooleanVar) -> tk.Frame:
        row = tk.Frame(parent, bg=PANEL_ALT, padx=10, pady=7, highlightthickness=1, highlightbackground=BORDER)
        copy = tk.Frame(row, bg=PANEL_ALT)
        copy.pack(side="left", fill="x", expand=True)
        title = tk.Label(copy, text=label, bg=PANEL_ALT, fg=TEXT, font=(FONT, 8, "bold"), anchor="w")
        title.pack(fill="x")
        detail = tk.Label(copy, text=description, bg=PANEL_ALT, fg=DIALOG_MUTED, font=(FONT, 7), anchor="w")
        detail.pack(fill="x", pady=(1, 0))
        switch = _ToggleSwitch(row, variable)
        switch.pack(side="right", padx=(8, 0))
        for widget in (row, copy, title, detail):
            widget.bind("<Button-1>", lambda _e, v=variable: v.set(not v.get()))
        return row

    def _center_over_parent(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        width = self.WIDTH
        height = self.winfo_reqheight()
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + max(0, (pw - width) // 2)
            y = py + max(0, (ph - height) // 2)
        except tk.TclError:
            x, y = 80, 80
        left, top, sw, sh = _virtual_screen_bounds(self)
        x = max(left, min(x, left + max(0, sw - width)))
        y = max(top, min(y, top + max(0, sh - height)))
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _drag_start(self, event) -> None:
        self._drag = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _drag_move(self, event) -> None:
        x = event.x_root - self._drag[0]
        y = event.y_root - self._drag[1]
        left, top, sw, sh = _virtual_screen_bounds(self)
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        x = max(left, min(x, left + max(0, sw - width)))
        y = max(top, min(y, top + max(0, sh - height)))
        self.geometry(f"+{x}+{y}")

    def _toggle_secret(self) -> None:
        self._secret_visible = not self._secret_visible
        self.secret_entry.configure(show="" if self._secret_visible else "•")
        self.secret_toggle.configure(text="Hide" if self._secret_visible else "Show")
        self.secret_entry.focus_set()

    def _browse(self) -> None:
        path = filedialog.askdirectory(title=r"Choose World of Warcraft _retail_\Screenshots", parent=self)
        if path:
            self.vars["screenshots_path"].set(path)
            self.error_label.configure(text="")

    def _on_return(self, _event=None) -> str:
        """Use Enter as the dialog default without hijacking focused secondary buttons."""
        focused = self.focus_get()
        if focused is self.browse_button:
            self._browse()
        elif focused is self.secret_toggle:
            self._toggle_secret()
        elif focused is self.cancel_button:
            self.destroy()
        else:
            self._save()
        return "break"

    def _save(self) -> None:
        cid = self.vars["client_id"].get().strip()
        secret = self.vars["client_secret"].get().strip()
        path = self.vars["screenshots_path"].get().strip()
        error = validate_settings_values(cid, secret, path)
        if error:
            self.error_label.configure(text=error)
            if not path:
                self.path_entry.focus_set()
            elif bool(cid) != bool(secret):
                (self.client_id_entry if not cid else self.secret_entry).focus_set()
            return
        self.error_label.configure(text="")
        # Do not require the folder to exist here: a WoW install can be on a
        # temporarily disconnected drive. The watcher reports that state clearly.
        out = replace(
            self.cfg,
            client_id=cid,
            client_secret=secret,
            screenshots_path=path,
            show_role=self.column_vars["show_role"].get(),
            show_class=self.column_vars["show_class"].get(),
            show_spec=self.column_vars["show_spec"].get(),
            show_rio=self.column_vars["show_rio"].get(),
            show_wcl=self.column_vars["show_wcl"].get(),
        )
        if self.on_save(out) is False:
            self.error_label.configure(text="Couldn’t save settings. Check the main window status, then try again.")
            return
        self.destroy()


class OverlayWindow:
    """Compact always-on-top applicant ranking window.

    The custom chrome remains visually consistent with the overlay, while the
    minimize button behaves like a normal Windows primary window: it minimizes
    to the taskbar. Only the close button/normal close protocol quits the app.
    """

    MAX_VISIBLE_ROWS = 6
    ROW_HEIGHT = 38
    MIN_DATA_HEIGHT = 250

    def __init__(self, root: tk.Tk, on_settings: Callable[[], None], on_qoff: Callable[[], None],
                 on_move: Callable[[int, int], None],
                 on_resize: Callable[[int], None] | None = None,
                 cfg: Config | None = None,
                 on_preferences: Callable[[dict[str, object]], None] | None = None):
        self.root = root
        self.on_settings = on_settings
        self.on_qoff = on_qoff
        self.on_move = on_move
        self.on_resize = on_resize or (lambda _height: None)
        self.on_preferences = on_preferences or (lambda _changes: None)
        self.cfg = cfg or Config()
        root.configure(bg=BG)
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.protocol("WM_DELETE_WINDOW", self.on_qoff)
        try:
            root.attributes("-alpha", 0.985)
        except tk.TclError:
            pass

        self.score_min, self.score_max = normalize_score_range(self.cfg.score_min, self.cfg.score_max)
        self.class_filter_id: int | None = self.cfg.class_filter_id
        self.role_filter: str = self.cfg.role_filter
        self.visible_column_keys: tuple[str, ...] = ()
        self.column_widths: dict[str, int] = {}
        self.width = WINDOW_WIDTH
        self._refresh_column_layout()
        self.empty_height = 214
        self.current_height = self.empty_height
        self.user_height: int | None = None
        self._resize_drag = (0, self.empty_height)
        root.geometry(f"{self.width}x{self.empty_height}+1180+80")
        self.rows: list[ApplicantView] = []
        self.state: EngineState | None = None
        self.selected_identity = ""
        self._drag = (0, 0)
        self._restore_borderless_after_map = False
        self._build()
        self.root.after_idle(self._ensure_windows_taskbar_presence)
        self.root.bind("<Map>", self._on_root_map, add="+")

    def _visible_columns_for_config(self) -> tuple[str, ...]:
        enabled = {
            "score": True,
            "role": self.cfg.show_role,
            "player": True,
            "class": self.cfg.show_class,
            "spec": self.cfg.show_spec,
            "rio": self.cfg.show_rio,
            "wcl": self.cfg.show_wcl,
        }
        return tuple(key for key, _label, _width, _anchor in COLUMN_SPECS if enabled.get(key, False))

    def _refresh_column_layout(self) -> None:
        keys = self._visible_columns_for_config()
        base = sum(COLUMN_WIDTH_BY_KEY[key] for key in keys)
        gaps = COLUMN_GAP * max(0, len(keys) - 1)
        natural = base + gaps + WINDOW_CHROME_WIDTH
        self.width = max(MIN_WINDOW_WIDTH, natural)
        widths = {key: COLUMN_WIDTH_BY_KEY[key] for key in keys}
        if "player" in widths and self.width > natural:
            widths["player"] += self.width - natural
        self.visible_column_keys = keys
        self.column_widths = widths

    def _notify_preferences(self, **changes: object) -> None:
        if changes:
            self.on_preferences(changes)

    def apply_config(self, cfg: Config) -> None:
        self.cfg = cfg
        self.score_min, self.score_max = normalize_score_range(cfg.score_min, cfg.score_max)
        self.class_filter_id = cfg.class_filter_id
        self.role_filter = cfg.role_filter
        self._refresh_column_layout()
        if hasattr(self, "score_filter"):
            self.score_filter.set_range(self.score_min, self.score_max)
            self.class_filter.set_value(self.class_filter_id)
            self.role_filter_dropdown.set_value(self.role_filter or None)
            self._sync_filter_visibility()
            self._rebuild_headers()
            if self.rows:
                self._render_rows()
            else:
                self.root.geometry(f"{self.width}x{self.current_height}")
            try:
                x, y = self._clamp_position(self.root.winfo_x(), self.root.winfo_y())
                self.root.geometry(f"+{x}+{y}")
            except tk.TclError:
                pass

    def _native_hwnd(self) -> int:
        if os.name != "nt":
            return 0
        try:
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            user32.GetParent.argtypes = [wintypes.HWND]
            user32.GetParent.restype = wintypes.HWND
            hwnd = wintypes.HWND(int(self.root.winfo_id()))
            parent = user32.GetParent(hwnd)
            parent_value = int(parent) if isinstance(parent, int) else int(getattr(parent, "value", 0) or 0)
            return parent_value or int(hwnd.value or 0)
        except (AttributeError, OSError, tk.TclError, ValueError):
            return 0

    def _ensure_windows_taskbar_presence(self) -> None:
        """Keep the borderless primary window represented on the Windows taskbar."""
        if os.name != "nt" or not self.root.winfo_exists():
            return
        hwnd = self._native_hwnd()
        if not hwnd:
            return
        try:
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000
            SW_HIDE = 0
            SW_SHOWNA = 8
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            SWP_FRAMECHANGED = 0x0020

            get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            get_long.argtypes = [wintypes.HWND, ctypes.c_int]
            get_long.restype = ctypes.c_ssize_t
            set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
            set_long.restype = ctypes.c_ssize_t
            user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.ShowWindow.restype = wintypes.BOOL
            user32.SetWindowPos.argtypes = [
                wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, wintypes.UINT,
            ]
            user32.SetWindowPos.restype = wintypes.BOOL

            native = wintypes.HWND(hwnd)
            style = int(get_long(native, GWL_EXSTYLE))
            wanted = (style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
            if wanted != style:
                # Microsoft documents hide -> style change -> show for dynamic
                # taskbar-button style changes. This prevents a stale tool-window
                # classification on borderless Tk windows.
                user32.ShowWindow(native, SW_HIDE)
                set_long(native, GWL_EXSTYLE, wanted)
                user32.SetWindowPos(
                    native, wintypes.HWND(0), 0, 0, 0, 0,
                    SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
                )
                user32.ShowWindow(native, SW_SHOWNA)
        except (AttributeError, OSError, tk.TclError, ValueError):
            # Tk's normal iconify path remains a safe fallback.
            return

    def _on_root_map(self, _event=None) -> None:
        # A borderless Tk window is temporarily changed to a normal top-level
        # before minimizing. A taskbar click maps that normal window again; this
        # callback then restores KeystoneLens' custom chrome immediately.
        if self._restore_borderless_after_map:
            self._restore_borderless_after_map = False
            self.root.after_idle(self._restore_borderless_window)
        else:
            self.root.after_idle(self._ensure_windows_taskbar_presence)

    def _restore_borderless_window(self) -> None:
        try:
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", True)
        except tk.TclError:
            return
        self._ensure_windows_taskbar_presence()

    def minimize_to_taskbar(self) -> None:
        """Minimize without stopping watcher, engine, WCL or other runtime work."""
        try:
            if os.name == "nt":
                # A normal top-level is reliably restored by clicking its taskbar
                # button. <Map> switches it back to borderless after restoration.
                self._restore_borderless_after_map = True
                self.root.attributes("-topmost", False)
                self.root.overrideredirect(False)
                self.root.update_idletasks()
                self._ensure_windows_taskbar_presence()
            self.root.iconify()
        except tk.TclError:
            self._restore_borderless_after_map = False
            try:
                self.root.overrideredirect(True)
                self.root.attributes("-topmost", True)
            except tk.TclError:
                pass

    def _clamp_position(self, x: int, y: int) -> tuple[int, int]:
        left, top, width, height = _virtual_screen_bounds(self.root)
        right = left + max(1, width)
        bottom = top + max(1, height)
        visible_x = min(80, self.width)
        visible_y = min(46, self.current_height)
        x = max(left - self.width + visible_x, min(int(x), right - visible_x))
        y = max(top, min(int(y), bottom - visible_y))
        return x, y

    def set_position(self, x: int | None, y: int | None) -> tuple[int, int] | None:
        if x is None or y is None:
            return None
        x, y = self._clamp_position(x, y)
        self.root.geometry(f"+{x}+{y}")
        return x, y

    @staticmethod
    def _column_gap(parent: tk.Misc, bg: str) -> None:
        gap = tk.Frame(parent, bg=bg, width=COLUMN_GAP)
        gap.pack(side="left", fill="y")
        gap.pack_propagate(False)

    def _header_cell(self, parent: tk.Misc, text: str, width: int, *, anchor: str = "w", offset_x: int = 0) -> None:
        box = tk.Frame(parent, bg=PANEL_ALT, width=width, height=27)
        box.pack(side="left", fill="y")
        box.pack_propagate(False)
        justify = "center" if anchor == "center" else "left"
        label = tk.Label(box, text=text, bg=PANEL_ALT, fg=MUTED, font=(FONT, 8, "bold"),
                         anchor=anchor, justify=justify)
        if anchor == "center" and offset_x:
            label.place(relx=0.5, rely=0.5, x=offset_x, anchor="center")
        else:
            padx = 0 if anchor == "center" else (6, 0)
            label.pack(fill="both", padx=padx)

    def _rebuild_headers(self) -> None:
        if not hasattr(self, "cols"):
            return
        for child in self.cols.winfo_children():
            child.destroy()
        visible_specs = [spec for spec in COLUMN_SPECS if spec[0] in self.visible_column_keys]
        for idx, (key, label, _base_width, anchor) in enumerate(visible_specs):
            self._header_cell(
                self.cols, label, self.column_widths[key], anchor=anchor,
                offset_x=ROLE_OFFSET_X if key == "role" else 0,
            )
            if idx < len(visible_specs) - 1:
                self._column_gap(self.cols, PANEL_ALT)

    def _sync_filter_visibility(self) -> None:
        if self.cfg.show_class:
            if not self.class_filter.winfo_manager():
                self.class_filter.pack(side="left", padx=(8, 0))
        elif self.class_filter.winfo_manager():
            self.class_filter.pack_forget()
        if self.cfg.show_role:
            if not self.role_filter_dropdown.winfo_manager():
                self.role_filter_dropdown.pack(side="left", padx=(8, 0))
        elif self.role_filter_dropdown.winfo_manager():
            self.role_filter_dropdown.pack_forget()

    def _active_filter_count(self) -> int:
        count = int((self.score_min, self.score_max) != (DEFAULT_SCORE_MIN, DEFAULT_SCORE_MAX))
        count += int(self.cfg.show_class and self.class_filter_id is not None)
        count += int(self.cfg.show_role and bool(self.role_filter))
        return count

    def _refresh_filter_meta(self) -> None:
        active = self._active_filter_count()
        self.filter_badge.configure(text=f"{active} active" if active else "")
        if active:
            if not self.reset_filters_button.winfo_manager():
                self.reset_filters_button.pack(side="right", padx=(8, 0))
        elif self.reset_filters_button.winfo_manager():
            self.reset_filters_button.pack_forget()

    def _reset_filters(self) -> None:
        self.score_min, self.score_max = DEFAULT_SCORE_MIN, DEFAULT_SCORE_MAX
        self.class_filter_id = None
        self.role_filter = ""
        self.score_filter.set_range(DEFAULT_SCORE_MIN, DEFAULT_SCORE_MAX)
        self.class_filter.set_value(None)
        self.role_filter_dropdown.set_value(None)
        self.canvas.yview_moveto(0.0)
        self._notify_preferences(
            score_min=DEFAULT_SCORE_MIN, score_max=DEFAULT_SCORE_MAX,
            class_filter_id=None, role_filter="",
        )
        self._render_rows()

    def _build(self) -> None:
        outer = tk.Frame(self.root, bg=BORDER, padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        self.body = tk.Frame(outer, bg=BG)
        self.body.pack(fill="both", expand=True)

        head = tk.Frame(self.body, bg=PANEL, height=44)
        head.pack(fill="x")
        head.pack_propagate(False)
        self.title = tk.Label(head, text="KeystoneLens", bg=PANEL, fg=TEXT, font=(FONT, 12, "bold"))
        self.title.pack(side="left", padx=(14, 8))
        self.context = tk.Label(head, text="Mythic+", bg=PANEL, fg=MUTED, font=(FONT, 9))
        # Optical correction requested for dungeon/key context: exactly 1 px lower.
        self.context.pack(side="left", pady=(1, 0))
        for widget in (head, self.title, self.context):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)
            widget.bind("<ButtonRelease-1>", self._drag_end)

        # Pack rightmost first so the visual order is Settings | Minimize | Close.
        _CaptionButton(head, "close", self.on_qoff).pack(side="right")
        _CaptionButton(head, "minimize", self.minimize_to_taskbar).pack(side="right")
        self.settings_button = _HeaderTextButton(
            head, "Settings", self.on_settings, text_offset_x=SETTINGS_TEXT_OFFSET_X,
        )
        self.settings_button.pack(side="right", padx=(2, 4))

        self.content = tk.Frame(self.body, bg=BG)
        self.content.pack(fill="both", expand=True)
        self.main_area = tk.Frame(self.content, bg=BG)
        self.main_area.pack(fill="both", expand=True)

        self.empty = tk.Frame(self.main_area, bg=BG)
        tk.Label(self.empty, text="Open a Mythic+ Group Finder listing", bg=BG, fg=TEXT,
                 font=(FONT, 12, "bold")).pack(pady=(28, 8))
        tk.Label(self.empty,
                 text="Applicants appear automatically as they apply.",
                 bg=BG, fg=MUTED, font=(FONT, 9), justify="center").pack()

        self.data = tk.Frame(self.main_area, bg=BG)
        summary = tk.Frame(self.data, bg=BG, pady=8)
        summary.pack(fill="x", padx=12)
        self.score_filter = _ScoreRangeFilter(summary, self._set_score_range)
        self.score_filter.pack(side="left")
        self.score_filter.set_range(self.score_min, self.score_max)

        class_options: list[tuple[object | None, str]] = [(None, "All classes")]
        class_options.extend((class_id, CLASS_NAMES[class_id]) for class_id in sorted(CLASS_NAMES, key=lambda cid: CLASS_NAMES[cid].casefold()))
        self.class_filter = _FilterDropdown(summary, "Classes", class_options, self._set_class_filter, width=132)
        self.class_filter.set_value(self.class_filter_id)

        role_options: list[tuple[object | None, str]] = [(None, "All roles")]
        role_options.extend((role, role.title()) for role in ROLE_FILTERS)
        self.role_filter_dropdown = _FilterDropdown(summary, "Roles", role_options, self._set_role_filter, width=110)
        self.role_filter_dropdown.set_value(self.role_filter or None)
        self._sync_filter_visibility()

        self.count = tk.Label(summary, text="", bg=BG, fg=MUTED, font=(FONT, 9))
        self.count.pack(side="right")
        self.reset_filters_button = tk.Button(
            summary, text="Reset filters", command=self._reset_filters, bg=PANEL_ALT, fg=MUTED,
            activebackground=PANEL, activeforeground=TEXT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BG, highlightcolor=ACCENT,
            padx=8, pady=2, font=(FONT, 8), cursor="hand2", takefocus=1,
        )
        self.filter_badge = tk.Label(summary, text="", bg=BG, fg=ACCENT, font=(FONT, 8, "bold"))
        self.filter_badge.pack(side="right", padx=(8, 0))

        self.normal_panel = tk.Frame(self.data, bg=BG)
        self.normal_panel.pack(fill="both", expand=True)

        self.cols = tk.Frame(self.normal_panel, bg=PANEL_ALT, height=27)
        self.cols.pack(fill="x", padx=12)
        self.cols.pack_propagate(False)
        self._rebuild_headers()

        self.list_area = tk.Frame(self.normal_panel, bg=BG)
        self.list_area.pack(fill="both", expand=True, padx=12)
        self.canvas = tk.Canvas(
            self.list_area, bg=BG, highlightthickness=0,
            height=self.ROW_HEIGHT, yscrollincrement=self.ROW_HEIGHT,
        )
        self.scrollbar = tk.Scrollbar(
            self.list_area, orient="vertical", command=self.canvas.yview, width=12,
            bg=PANEL, troughcolor=PANEL_ALT, activebackground=ACCENT, relief="flat", bd=0,
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.list_frame = tk.Frame(self.canvas, bg=BG)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.canvas_window, width=e.width))
        self.list_frame.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)

        self.detail = tk.Frame(self.normal_panel, bg=PANEL, padx=12, pady=8, height=96)
        self.detail.pack_propagate(False)
        detail_head = tk.Frame(self.detail, bg=PANEL)
        detail_head.pack(fill="x")
        self.detail_title = tk.Label(detail_head, text="", bg=PANEL, fg=TEXT,
                                     font=(FONT, 10, "bold"), anchor="w")
        self.detail_title.pack(side="left", fill="x", expand=True)
        self.detail_close = tk.Button(
            detail_head, text="×", command=self._clear_selection, bg=PANEL, fg=MUTED,
            activebackground=PANEL_ALT, activeforeground=TEXT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=PANEL, highlightcolor=ACCENT,
            cursor="hand2", takefocus=1, width=2,
        )
        self.detail_close.pack(side="right")
        self.detail_line1 = tk.Label(self.detail, text="", bg=PANEL, fg=MUTED, font=(FONT, 9), anchor="w")
        self.detail_line1.pack(fill="x", pady=(5, 0))
        self.detail_line2 = tk.Label(self.detail, text="", bg=PANEL, fg=MUTED, font=(FONT, 9), anchor="w")
        self.detail_line2.pack(fill="x", pady=(3, 0))
        self.detail_line3 = tk.Label(self.detail, text="", bg=PANEL, fg=MUTED, font=(FONT, 8), anchor="w")
        self.detail_line3.pack(fill="x", pady=(3, 0))

        foot = tk.Frame(self.content, bg=BG, height=28)
        foot.pack(fill="x", padx=12, pady=(0, 4))
        foot.pack_propagate(False)
        self.status_dot = tk.Label(foot, text="●", bg=BG, fg=MUTED, font=(FONT, 8), anchor="w")
        self.status_dot.pack(side="left")
        self.resize_grip = tk.Canvas(
            foot, width=18, height=24, bg=BG, highlightthickness=0, bd=0,
            cursor="sb_v_double_arrow", takefocus=0,
        )
        self.resize_grip.pack(side="right")
        self.resize_grip.create_line(5, 17, 13, 17, fill=MUTED, width=1)
        self.resize_grip.create_line(7, 20, 13, 20, fill=MUTED, width=1)
        self.resize_grip.bind("<ButtonPress-1>", self._resize_start)
        self.resize_grip.bind("<B1-Motion>", self._resize_move)
        self.resize_grip.bind("<ButtonRelease-1>", self._resize_end)
        self.status = tk.Label(foot, text="Waiting for Group Finder", bg=BG, fg=MUTED,
                               font=(FONT, 8), anchor="w")
        self.status.pack(side="left", fill="both", expand=True, padx=(5, 0))

        self.root.bind("<Up>", lambda _e: self._move_selection(-1))
        self.root.bind("<Down>", lambda _e: self._move_selection(1))
        self.root.bind("<Home>", lambda _e: self._select_edge(0))
        self.root.bind("<End>", lambda _e: self._select_edge(-1))
        self.root.bind("<Escape>", lambda _e: self._clear_selection())
        self._show_empty_state()

    def _show_empty_state(self) -> None:
        if self.data.winfo_manager():
            self.data.pack_forget()
        if not self.empty.winfo_manager():
            self.empty.pack(fill="both", expand=True)
        self.current_height = self.empty_height
        self.root.geometry(f"{self.width}x{self.current_height}")

    def _show_data_state(self) -> None:
        if self.empty.winfo_manager():
            self.empty.pack_forget()
        if not self.data.winfo_manager():
            self.data.pack(fill="both", expand=True)

    def _height_bounds(self, shown: int, *, detail: bool) -> tuple[int, int, int]:
        # Fixed chrome around the scrolling applicant viewport. The user-resize
        # handle changes only viewport height, so column geometry never drifts.
        chrome = 44 + 34 + 27 + 34 + 18 + (94 if detail else 0)
        minimum_canvas = 58 if shown == 0 else self.ROW_HEIGHT
        content_canvas = max(minimum_canvas, max(shown, 1) * self.ROW_HEIGHT)
        _left, top, _screen_width, screen_height = _virtual_screen_bounds(self.root)
        available_screen = max(self.MIN_DATA_HEIGHT, top + screen_height - max(top, self.root.winfo_y()) - 20)
        maximum = min(chrome + content_canvas, available_screen)
        minimum = min(maximum, max(self.MIN_DATA_HEIGHT, chrome + minimum_canvas))
        return chrome, minimum, maximum

    def set_user_height(self, height: int | None) -> None:
        if height is None:
            return
        try:
            requested = int(height)
        except (TypeError, ValueError):
            return
        self.user_height = max(self.MIN_DATA_HEIGHT, requested)
        if self.rows:
            self._resize_for_rows(len(self._filtered()), detail=bool(self.selected_identity))

    def _resize_for_rows(self, shown: int, *, detail: bool) -> None:
        chrome, minimum, maximum = self._height_bounds(shown, detail=detail)
        if self.user_height is None:
            visible = min(max(shown, 1), self.MAX_VISIBLE_ROWS)
            natural_canvas = 58 if shown == 0 else visible * self.ROW_HEIGHT
            target = chrome + natural_canvas
        else:
            target = self.user_height
        target = max(minimum, min(maximum, target))
        canvas_height = max(1, target - chrome)
        self.canvas.configure(height=canvas_height)

        content_height = max(58 if shown == 0 else 0, shown * self.ROW_HEIGHT)
        if content_height > canvas_height + 1:
            if not self.scrollbar.winfo_manager():
                self.scrollbar.pack(side="right", fill="y", padx=(4, 0))
        elif self.scrollbar.winfo_manager():
            self.scrollbar.pack_forget()

        self.current_height = target
        self.root.geometry(f"{self.width}x{self.current_height}")

    def _resize_start(self, event) -> None:
        self._resize_drag = (event.y_root, self.current_height)

    def _resize_move(self, event) -> None:
        if not self.rows:
            return
        start_y, start_height = self._resize_drag
        requested = start_height + (event.y_root - start_y)
        _chrome, minimum, maximum = self._height_bounds(
            len(self._filtered()), detail=bool(self.selected_identity)
        )
        self.user_height = max(minimum, min(maximum, requested))
        self._resize_for_rows(len(self._filtered()), detail=bool(self.selected_identity))

    def _resize_end(self, _event) -> None:
        if self.user_height is not None:
            self.on_resize(self.current_height)

    def _drag_start(self, event) -> None:
        self._drag = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag_move(self, event) -> None:
        self.root.geometry(f"+{event.x_root - self._drag[0]}+{event.y_root - self._drag[1]}")

    def _drag_end(self, _event) -> None:
        x, y = self._clamp_position(self.root.winfo_x(), self.root.winfo_y())
        self.root.geometry(f"+{x}+{y}")
        self.on_move(x, y)

    def set_status(self, text: str) -> None:
        lower = text.casefold()
        if any(token in lower for token in ("error", "failed", "not found", "could not", "invalid", "mislukt", "niet gevonden", "kon niet", "ongeldig")):
            colour = RED
        elif any(token in lower for token in ("loading", "waiting", "temporary", "temporarily", "retry", "laden", "wacht", "tijdelijk")):
            colour = YELLOW
        else:
            colour = GREEN
        self.status_dot.configure(fg=colour)
        self.status.configure(text=text)

    def update_state(self, state: EngineState) -> None:
        self.state = state
        self.rows = list(state.rows)
        listing = state.listing
        context = f"{listing.dungeon_name} +{listing.key_level}" if listing and listing.key_level else "Mythic+"
        self.context.configure(text=context)

        if not listing:
            self.selected_identity = ""
            self.empty.winfo_children()[0].configure(text="Open a Mythic+ Group Finder listing")
            self.empty.winfo_children()[1].configure(
                text="Applicants appear automatically as they apply."
            )
            self._show_empty_state()
        elif not self.rows and (state.lfg_unavailable or state.applicants_unavailable):
            self.selected_identity = ""
            self.empty.winfo_children()[0].configure(text="Group Finder data temporarily unavailable")
            self.empty.winfo_children()[1].configure(
                text="KeystoneLens is waiting for complete Group Finder data.\nThe last valid applicant list stays visible."
            )
            self._show_empty_state()
        elif not self.rows:
            self.selected_identity = ""
            self.empty.winfo_children()[0].configure(text="Waiting for applicants")
            self.empty.winfo_children()[1].configure(
                text=f"{context} is open.\nNew applicants appear automatically."
            )
            self._show_empty_state()
        else:
            self._show_data_state()
            self._render_rows()
        self.set_status(state.status)

    def update_rows(self, rows: list[ApplicantView], status: str) -> None:
        # Backwards-compatible demo/test helper. Runtime uses EngineState.
        listing = rows[0].snapshot_listing if rows else None
        self.update_state(EngineState(
            listing=listing, rows=tuple(rows), party=(), status=status
        ))

    def _on_mousewheel(self, event) -> str:
        delta = int(-1 * (event.delta / 120)) if getattr(event, "delta", 0) else 0
        if delta:
            self.canvas.yview_scroll(delta, "units")
        return "break"

    def _select_edge(self, index: int) -> None:
        rows = self._filtered()
        if not rows:
            return
        self.selected_identity = rows[index].applicant.identity
        self._render_rows()

    def _ensure_selected_visible(self) -> None:
        widget = getattr(self, "_selected_row_widget", None)
        if not widget or not widget.winfo_exists():
            return
        self.root.update_idletasks()
        content_height = max(1, self.list_frame.winfo_height())
        viewport_height = max(1, self.canvas.winfo_height())
        row_top = widget.winfo_y()
        row_bottom = row_top + widget.winfo_height()
        top_fraction = self.canvas.yview()[0] if self.canvas.yview() else 0.0
        view_top = top_fraction * content_height
        view_bottom = view_top + viewport_height
        if row_top < view_top:
            self.canvas.yview_moveto(max(0.0, row_top / content_height))
        elif row_bottom > view_bottom:
            target = max(0.0, (row_bottom - viewport_height) / content_height)
            self.canvas.yview_moveto(min(1.0, target))

    def _move_selection(self, delta: int) -> None:
        rows = self._filtered()
        if not rows:
            return
        identities = [view.applicant.identity for view in rows]
        try:
            current = identities.index(self.selected_identity)
        except ValueError:
            current = -1 if delta > 0 else 0
        current = max(0, min(len(rows) - 1, current + delta))
        self.selected_identity = identities[current]
        self._render_rows()

    @staticmethod
    def _has_final_score(view: ApplicantView) -> bool:
        return has_final_score(view)

    def _eligible_rows(self) -> list[ApplicantView]:
        return [view for view in self.rows if has_final_score(view)]

    def _filtered(self) -> list[ApplicantView]:
        return filter_rows(
            self.rows,
            score_min=self.score_min,
            score_max=self.score_max,
            class_id=self.class_filter_id if self.cfg.show_class else None,
            role=self.role_filter if self.cfg.show_role else "",
        )

    def _set_score_range(self, low: int, high: int) -> None:
        self.score_min, self.score_max = normalize_score_range(low, high)
        self.canvas.yview_moveto(0.0)
        self._notify_preferences(score_min=self.score_min, score_max=self.score_max)
        self._render_rows()

    def _set_class_filter(self, class_id: object | None) -> None:
        self.class_filter_id = int(class_id) if isinstance(class_id, int) and class_id in CLASS_NAMES else None
        self.canvas.yview_moveto(0.0)
        self._notify_preferences(class_filter_id=self.class_filter_id)
        self._render_rows()

    def _set_role_filter(self, role: object | None) -> None:
        normalized = str(role or "").upper()
        self.role_filter = normalized if normalized in ROLE_FILTERS else ""
        self.canvas.yview_moveto(0.0)
        self._notify_preferences(role_filter=self.role_filter)
        self._render_rows()

    def _clear_selection(self) -> None:
        self.selected_identity = ""
        if self.rows:
            self._render_rows()

    def _render_rows(self) -> None:
        for child in self.list_frame.winfo_children():
            child.destroy()
        rows = self._filtered()
        shown = len(rows)
        eligible_total = len(self._eligible_rows())
        active_filters = self._active_filter_count()
        if active_filters:
            count_text = f"{shown} / {eligible_total} applicants"
        else:
            count_text = f"{eligible_total} applicant{'s' if eligible_total != 1 else ''}"
        self.count.configure(text=count_text)
        self._refresh_filter_meta()
        self._selected_row_widget = None
        if self.selected_identity and not any(v.applicant.identity == self.selected_identity for v in rows):
            self.selected_identity = ""

        if not rows:
            empty_text = "No applicants match these filters" if eligible_total else "Calculating KL scores…"
            tk.Label(self.list_frame, text=empty_text, bg=BG, fg=MUTED,
                     font=(FONT, 9)).pack(pady=18)
        else:
            for idx, view in enumerate(rows):
                self._render_row(view, idx)

        selected = next((v for v in rows if v.applicant.identity == self.selected_identity), None)
        if selected:
            if not self.detail.winfo_manager():
                self.detail.pack(fill="x", padx=12, pady=(6, 0))
            self._show_detail(selected)
            self._ensure_selected_visible()
        elif self.detail.winfo_manager():
            self.detail.pack_forget()
        self._resize_for_rows(shown, detail=selected is not None)

    def _render_row(self, view: ApplicantView, idx: int) -> None:
        selected = view.applicant.identity == self.selected_identity
        bg = PANEL if selected else (PANEL_ALT if idx % 2 else BG)
        row = tk.Frame(self.list_frame, bg=bg, height=self.ROW_HEIGHT, cursor="hand2")
        row.pack(fill="x", pady=(0, 1))
        row.pack_propagate(False)
        if selected:
            self._selected_row_widget = row

        score = view.score.score if view.score else 0
        score_resolved = self._has_final_score(view)
        class_name = CLASS_NAMES.get(view.applicant.class_id, "?")
        spec_name = SPEC_NAMES.get(view.applicant.spec_id, "?")
        player_name = view.applicant.name.split("-", 1)[0]

        rio_raw = _rio_rating_text(view)
        same = view.score.same_dungeon_key if view.score else view.applicant.rio_best_dungeon_key
        rio_text = rio_raw + (f" · dungeon +{same}" if same else "")

        if view.score and view.score.wcl_score is not None:
            average = view.score.wcl_score
            source = "S1 " if view.wcl and view.wcl.source_season == "midnight-s1" else ""
            wtext, wfg = f"{source}{int(round(average))}/100", pct_colour(average)
        elif view.wcl_status == "loading":
            wtext, wfg = "loading…", MUTED
        elif view.wcl_status == "error":
            error_text = (view.wcl.error if view.wcl else "").casefold()
            if "rate limit" in error_text:
                wtext = "rate limit"
            elif "oauth" in error_text or "login" in error_text or "401" in error_text or "403" in error_text:
                wtext = "auth error"
            elif "server" in error_text or "realm" in error_text:
                wtext = "realm error"
            elif "graphql" in error_text:
                wtext = "API error"
            else:
                wtext = "error"
            wfg = RED
        elif view.wcl_status == "disabled":
            wtext, wfg = "off", MUTED
        else:
            wtext, wfg = "no data", MUTED

        visible = list(self.visible_column_keys)
        for position, key in enumerate(visible):
            if position:
                self._column_gap(row, bg)
            width = self.column_widths[key]
            box = tk.Frame(row, bg=bg, width=width, height=self.ROW_HEIGHT)
            box.pack(side="left", fill="y")
            box.pack_propagate(False)

            if key == "score":
                tk.Label(
                    box,
                    text=str(score) if score_resolved else "…",
                    bg=score_colour(score) if score_resolved else PANEL,
                    fg="#07101c" if score_resolved else MUTED,
                    font=(FONT, 10, "bold"), width=4,
                ).pack(side="left", padx=(5, 0), pady=6)
            elif key == "role":
                self._draw_role_icon(box, view.applicant.role_byte, bg)
            elif key == "player":
                tk.Label(box, text=player_name, bg=bg, fg=TEXT, font=(FONT, 9, "bold"),
                         anchor="w").pack(fill="both", padx=(6, 4))
            elif key == "class":
                tk.Label(box, text=class_name, bg=bg, fg=TEXT, font=(FONT, 8),
                         anchor="w").pack(fill="both", padx=(6, 2))
            elif key == "spec":
                tk.Label(box, text=spec_name, bg=bg, fg=TEXT, font=(FONT, 8),
                         anchor="w").pack(fill="both", padx=(6, 2))
            elif key == "rio":
                tk.Label(box, text=rio_text, bg=bg, fg=TEXT, font=(FONT, 9, "bold"),
                         anchor="w").pack(fill="both", padx=(6, 0))
            elif key == "wcl":
                tk.Label(box, text=wtext, bg=bg, fg=wfg, font=(FONT, 9, "bold"),
                         anchor="w").pack(fill="both", padx=(6, 0))

        for widget in [row, *row.winfo_children()]:
            widget.bind("<Button-1>", lambda _event, v=view: self._select(v))
            widget.bind("<MouseWheel>", self._on_mousewheel)
            for child in widget.winfo_children():
                child.bind("<Button-1>", lambda _event, v=view: self._select(v))
                child.bind("<MouseWheel>", self._on_mousewheel)


    def _draw_role_icon(self, parent: tk.Misc, role_byte: int, bg: str) -> None:
        """Draw a dependency-free tank/healer/DPS icon.

        Canvas primitives avoid emoji/font differences on Windows and keep the
        single-list role column compact. The icon is intentionally the only
        role indicator; class/spec remains plain text as requested.
        """
        canvas = tk.Canvas(parent, width=22, height=20, bg=bg, highlightthickness=0, bd=0)
        canvas.place(relx=0.5, rely=0.5, x=ROLE_OFFSET_X, anchor="center")
        role = ROLE_NAMES.get(role_byte, "DPS")
        if role == "TANK":
            # Compact shield.
            canvas.create_polygon(11, 2, 17, 5, 16, 13, 11, 18, 6, 13, 5, 5,
                                  fill=ACCENT, outline=TEXT, width=1)
            canvas.create_line(11, 5, 11, 15, fill=BG, width=1)
        elif role == "HEALER":
            # Compact medical cross.
            canvas.create_rectangle(9, 3, 13, 17, fill=GREEN, outline="")
            canvas.create_rectangle(4, 8, 18, 12, fill=GREEN, outline="")
        else:
            # Compact crossed swords.
            canvas.create_line(6, 15, 16, 5, fill=YELLOW, width=2)
            canvas.create_line(6, 5, 16, 15, fill=YELLOW, width=2)
            canvas.create_line(4, 14, 7, 17, fill=TEXT, width=1)
            canvas.create_line(15, 17, 18, 14, fill=TEXT, width=1)
        canvas.bind("<Button-1>", lambda event: parent.event_generate("<Button-1>", x=event.x, y=event.y))
        canvas.bind("<MouseWheel>", self._on_mousewheel)

    def _select(self, view: ApplicantView) -> None:
        self.selected_identity = view.applicant.identity
        self._render_rows()

    def _show_detail(self, view: ApplicantView) -> None:
        score = view.score
        if not score:
            return
        unresolved = (
            view.rio_status in {"queued", "loading"}
            or view.wcl_status in {"queued", "loading"}
        )
        if unresolved:
            rio_text = "Raider.IO loading…" if view.rio_status in {"queued", "loading"} else "Raider.IO ready"
            wcl_text = "Warcraft Logs loading…" if view.wcl_status in {"queued", "loading"} else "Warcraft Logs ready"
            self.detail_title.configure(text=f"{view.applicant.name}   KL … · loading", fg=MUTED)
            self.detail_line1.configure(text=f"{rio_text}  |  {wcl_text}", fg=MUTED)
            self.detail_line2.configure(text="KL Score appears when Raider.IO and Warcraft Logs finish loading.", fg=MUTED)
            self.detail_line3.configure(text="", fg=MUTED)
            return
        self.detail_title.configure(
            text=f"{view.applicant.name}   KL {score.score}/100 · {score.label.title()} · {score.confidence.title()} confidence",
            fg=score_colour(score.score),
        )

        wcl_source_label = "Warcraft Logs S1 carry-over" if view.wcl and view.wcl.source_season == "midnight-s1" else "Warcraft Logs"
        components = [
            f"Raider.IO {score.rio_score:.0f}/100 · 50%",
            (f"{wcl_source_label} {score.wcl_score:.0f}/100 · 50%"
             if score.wcl_score is not None else f"{wcl_source_label} 0/100 · 50% · No public data"),
        ]
        self.detail_line1.configure(text="  |  ".join(components), fg=TEXT)

        metric_scores = wcl_metric_scores(view.applicant, view.wcl)
        if score.wcl_score is not None and metric_scores:
            labels = {
                "playerscore": "Score", "playerspeed": "Speed", "wdps": "WDPS",
                "hps": "HPS", "tankhps": "Tank HPS", "dps": "DPS",
                "bossdps": "Boss DPS",
            }
            metric_text = "  |  ".join(
                f"{labels.get(name, name.upper())} {int(round(value))}/100"
                for name, value in metric_scores
            )
            average_text = f"WCL average {score.wcl_score:.0f}/100"
            context_bracket = score.wcl_bracket
            if not context_bracket and view.wcl:
                context_bracket = next(iter(view.wcl.metric_brackets.values()), None)
            context_text = ""
            if context_bracket:
                if view.wcl and view.wcl.source_season == "midnight-s1":
                    scope = "Season 1 aggregate"
                else:
                    scope = "full dungeon" if context_bracket.key_level <= 0 else f"+{context_bracket.key_level}"
                context_text = (
                    f"  |  {scope}  |  {context_bracket.run_count} "
                    f"parse{'s' if context_bracket.run_count != 1 else ''}"
                )
            line = f"{average_text}  |  {metric_text}{context_text}"
        elif view.wcl_status == "disabled":
            line = "Warcraft Logs is off. Its fixed 50% share remains 0/100."
        elif view.wcl and view.wcl.error:
            line = f"WCL: {view.wcl.error}"
        else:
            line = "Warcraft Logs: no usable public ranking; its fixed 50% share is 0/100."
        self.detail_line2.configure(text=line, fg=MUTED)

        source = "Raider.IO live" if view.rio and not view.rio.error and not view.rio.not_found else "Raider.IO local addon data"
        rio_rating = _rio_rating_text(view)
        run_score_text = ""
        if view.rio and not view.rio.error and not view.rio.not_found and view.rio.best_dungeon_run_score > 0:
            run_key = view.rio.best_dungeon_score_key or score.same_dungeon_key
            run_score_text = f"  |  Best run: +{run_key}"
        meta_text = f"RIO half {score.rio_score:.0f}/100  |  rating {rio_rating}  |  dungeon +{score.same_dungeon_key or 0}{run_score_text}"
        self.detail_line3.configure(
            text=f"{source}: {meta_text}",
            fg=MUTED,
        )
