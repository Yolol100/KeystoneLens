from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import time
import tkinter as tk

from .metrics import percentile_hex, role_metric
from .models import EngineState, LiveHover


TRANSPARENT_KEY = "#010203"
CURSOR_MARGIN_PX = 6
POLL_MS = 100

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class LiveTooltipOverlay:
    """Mouse-transparent WCL value painted over KeystoneLens' reserved tooltip cell.

    WoW addons cannot receive arbitrary HTTP responses while the client is running.
    The in-game addon therefore sends only hover identity + normalized screen geometry
    through the existing QR transport. The Companion already owns the WCL lookup and
    paints the right-hand value into that reserved row without input injection.
    """

    def __init__(self, root: tk.Misc):
        self.root = root
        self.enabled = os.name == "nt"
        self.window: tk.Toplevel | None = None
        self.label: tk.Label | None = None
        self.current_generation = 0
        self.owner_rect: tuple[int, int, int, int] | None = None
        self.visible = False

        if self.enabled:
            self._create_window()
        self._schedule_cursor_watch()

    def _create_window(self) -> None:
        window = tk.Toplevel(self.root)
        window.withdraw()
        window.overrideredirect(True)
        window.configure(bg=TRANSPARENT_KEY)
        window.attributes("-topmost", True)
        try:
            window.wm_attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError:
            pass

        label = tk.Label(
            window,
            text="",
            anchor="e",
            justify="right",
            padx=0,
            pady=0,
            borderwidth=0,
            highlightthickness=0,
            bg=TRANSPARENT_KEY,
            fg="#ffffff",
            font=("Arial", 10, "bold"),
        )
        label.pack(fill="both", expand=True)

        self.window = window
        self.label = label
        window.update_idletasks()
        self._apply_window_styles()

    def _apply_window_styles(self) -> None:
        if not self.enabled or self.window is None:
            return
        try:
            hwnd = int(self.window.winfo_id())
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            get_long = user32.GetWindowLongW
            set_long = user32.SetWindowLongW
            get_long.argtypes = [wintypes.HWND, ctypes.c_int]
            get_long.restype = ctypes.c_long
            set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
            set_long.restype = ctypes.c_long
            style = int(get_long(hwnd, GWL_EXSTYLE))
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            set_long(hwnd, GWL_EXSTYLE, style)

            set_long_ptr = getattr(user32, "SetWindowLongPtrW", None)
            if set_long_ptr is not None:
                set_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
                set_long_ptr.restype = ctypes.c_void_p
                set_long_ptr(hwnd, GWLP_HWNDPARENT, None)
            else:
                set_long(hwnd, GWLP_HWNDPARENT, 0)

            user32.SetWindowPos.argtypes = [
                wintypes.HWND,
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.UINT,
            ]
            user32.SetWindowPos(
                hwnd,
                wintypes.HWND(HWND_TOPMOST),
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
        except (AttributeError, OSError, tk.TclError):
            pass

    def update_from_state(self, state: EngineState) -> None:
        if not self.enabled:
            return

        hover = state.live_hover
        if hover is None:
            return
        if self.current_generation and not _generation16_is_newer(
            hover.generation, self.current_generation
        ) and hover.generation != self.current_generation:
            return

        identity = f"{hover.applicant_id}:{hover.member_idx}"
        view = next((row for row in state.rows if row.applicant.identity == identity), None)
        if view is None or view.applicant.name != hover.name or view.applicant.spec_id != hover.spec_id:
            self.hide()
            return
        if not state.listing or int(state.listing.activity_id or 0) != int(hover.activity_id or 0):
            self.hide()
            return

        metric = role_metric(view)
        if metric is None:
            if view.wcl_status in {"none", "error", "disabled"}:
                self._show_value(hover, "N/R", "#777777")
            return

        metric_name, percentile = metric
        label = "Healing" if metric_name == "HPS" else "DPS"
        text = f"{label} {int(percentile + 0.5)}%"
        self._show_value(hover, text, percentile_hex(percentile))

    def _show_value(self, hover: LiveHover, text: str, color: str) -> None:
        client = _wow_client_rect()
        if client is None or self.window is None or self.label is None:
            self.hide()
            return

        value_rect = _normalized_rect_to_screen(
            hover.value_x,
            hover.value_y,
            hover.value_w,
            hover.value_h,
            client,
        )
        owner_rect = _normalized_rect_to_screen(
            hover.owner_x,
            hover.owner_y,
            hover.owner_w,
            hover.owner_h,
            client,
        )
        if value_rect is None or owner_rect is None:
            self.hide()
            return

        x, y, width, height = value_rect
        width = max(width, 56)
        height = max(height, 14)
        font_size = max(8, min(14, int(height * 0.72)))

        self.current_generation = int(hover.generation)
        self.owner_rect = owner_rect
        self.label.configure(text=text, fg=color, font=("Arial", font_size, "bold"))
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.deiconify()
        self.window.lift()
        self._apply_window_styles()
        self.visible = True

    def hide(self) -> None:
        if self.window is not None and self.visible:
            try:
                self.window.withdraw()
            except tk.TclError:
                pass
        self.visible = False
        self.owner_rect = None

    def close(self) -> None:
        self.hide()
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None
            self.label = None

    def _schedule_cursor_watch(self) -> None:
        try:
            self.root.after(POLL_MS, self._cursor_watch)
        except tk.TclError:
            pass

    def _cursor_watch(self) -> None:
        try:
            if self.visible and self.owner_rect is not None:
                if _wow_client_rect() is None:
                    self.hide()
                else:
                    point = _cursor_position()
                    if point is None or not _point_in_rect(point, self.owner_rect, CURSOR_MARGIN_PX):
                        self.hide()
            self._schedule_cursor_watch()
        except tk.TclError:
            return


def _generation16_is_newer(candidate: int, current: int) -> bool:
    if candidate <= 0 or current <= 0 or candidate == current:
        return False
    delta = (candidate - current) % 65535
    return 0 < delta <= 32767


def _window_title(user32, hwnd) -> str:
    length = int(user32.GetWindowTextLengthW(hwnd))
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _wow_window() -> int | None:
    """Return WoW only while it is the foreground application.

    The live value must never float over a browser/desktop after Alt-Tab.
    """
    if os.name != "nt":
        return None
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetForegroundWindow.restype = wintypes.HWND
        foreground = user32.GetForegroundWindow()
        if not foreground:
            return None
        title = _window_title(user32, foreground).casefold()
        return int(foreground) if "world of warcraft" in title else None
    except (AttributeError, OSError):
        return None


def _wow_client_rect() -> tuple[int, int, int, int] | None:
    hwnd = _wow_window()
    if hwnd is None:
        return None
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        rect = RECT()
        if not user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            return None
        origin = POINT(0, 0)
        if not user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(origin)):
            return None
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width <= 0 or height <= 0:
            return None
        return int(origin.x), int(origin.y), width, height
    except (AttributeError, OSError):
        return None


def _normalized_rect_to_screen(
    x: int,
    y: int,
    width: int,
    height: int,
    client: tuple[int, int, int, int],
) -> tuple[int, int, int, int] | None:
    left, top, client_w, client_h = client
    if client_w <= 0 or client_h <= 0:
        return None

    nx = max(0, min(65535, int(x))) / 65535.0
    ny = max(0, min(65535, int(y))) / 65535.0
    nw = max(0, min(65535, int(width))) / 65535.0
    nh = max(0, min(65535, int(height))) / 65535.0

    px = left + int(round(nx * client_w))
    pw = max(1, int(round(nw * client_w)))
    ph = max(1, int(round(nh * client_h)))
    py = top + client_h - int(round((ny + nh) * client_h))
    return px, py, pw, ph


def _cursor_position() -> tuple[int, int] | None:
    if os.name != "nt":
        return None
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        point = POINT()
        if not user32.GetCursorPos(ctypes.byref(point)):
            return None
        return int(point.x), int(point.y)
    except (AttributeError, OSError):
        return None


def _point_in_rect(
    point: tuple[int, int],
    rect: tuple[int, int, int, int],
    margin: int = 0,
) -> bool:
    x, y = point
    left, top, width, height = rect
    return (
        left - margin <= x <= left + width + margin
        and top - margin <= y <= top + height + margin
    )
