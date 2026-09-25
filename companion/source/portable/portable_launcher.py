from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import importlib
import json
import os
from pathlib import Path
import time
import runpy
import sys
import traceback


ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
PACKAGES_DIR = ROOT / "packages"
RUNTIME_DIR = ROOT / "runtime"
RUNTIME_CONTRACT = ROOT / "RUNTIME.json"
STARTUP_LOG = ROOT / "portable-startup.log"
MUTEX_NAME = "KeystoneLens.Companion.Singleton"
ERROR_ALREADY_EXISTS = 183


def configure_runtime_environment() -> None:
    sys.path[:0] = [str(APP_DIR), str(PACKAGES_DIR)]

    # A private Python install is relocated when the portable ZIP is extracted.
    # Point Tcl/Tk explicitly at the bundled runtime so Tk() never inherits a
    # stale system-Python or installer path from the user's environment.
    tcl_dir = RUNTIME_DIR / "tcl" / "tcl8.6"
    tk_dir = RUNTIME_DIR / "tcl" / "tk8.6"
    if tcl_dir.is_dir():
        os.environ["TCL_LIBRARY"] = str(tcl_dir)
    if tk_dir.is_dir():
        os.environ["TK_LIBRARY"] = str(tk_dir)


def expected_python_version() -> tuple[int, int, int]:
    try:
        contract = json.loads(RUNTIME_CONTRACT.read_text(encoding="utf-8"))
        raw = str(contract["python_version"])
        version = tuple(int(part) for part in raw.split("."))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"The bundled runtime contract is invalid: {exc}") from exc
    if len(version) != 3:
        raise RuntimeError("The bundled runtime contract must contain a three-part Python version.")
    return version


def verify_runtime(*, import_full_app: bool) -> None:
    if os.name != "nt":
        raise RuntimeError("KeystoneLens Portable is a Windows x64 package.")
    expected = expected_python_version()
    if sys.version_info[:3] != expected:
        raise RuntimeError(
            "Portable runtime mismatch: expected Python "
            + ".".join(str(part) for part in expected)
            + ", got "
            + ".".join(str(part) for part in sys.version_info[:3])
        )
    if not (RUNTIME_DIR / "python.exe").is_file() or not (RUNTIME_DIR / "pythonw.exe").is_file():
        raise RuntimeError("The bundled KeystoneLens Python runtime is incomplete.")

    import tkinter  # noqa: F401
    import requests  # noqa: F401
    import PIL  # noqa: F401
    import zxingcpp  # noqa: F401
    if import_full_app:
        importlib.import_module("keystonelens_companion.__main__")


def _find_top_level_window(title_prefix: str) -> int | None:
    if os.name != "nt":
        return None

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    user32.EnumWindows.argtypes = [enum_proc_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int

    found: list[int] = []

    @enum_proc_type
    def callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if buffer.value.startswith(title_prefix):
            found.append(int(hwnd))
            return False
        return True

    try:
        user32.EnumWindows(callback, 0)
    except OSError:
        return None
    return found[0] if found else None


def restore_existing_window(title_prefix: str = "KeystoneLens ") -> bool:
    """Restore and foreground an existing KeystoneLens top-level window."""
    hwnd_value = _find_top_level_window(title_prefix)
    if hwnd_value is None:
        return False

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL

    hwnd = wintypes.HWND(hwnd_value)
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    return True


def verify_ui_runtime() -> None:
    import tkinter as tk
    from keystonelens_companion.live_overlay import LiveTooltipOverlay

    root = tk.Tk()
    overlay = None
    try:
        root.title("KeystoneLens Verification")
        root.update_idletasks()
        root.deiconify()
        root.update()

        overlay = LiveTooltipOverlay(root)
        root.update_idletasks()
        root.update()
        if overlay.window is None:
            raise RuntimeError("Live tooltip overlay window could not be created.")

        overlay.window.geometry("24x18+0+0")
        overlay.window.deiconify()
        root.update()

        root.iconify()
        root.update()
        if overlay.window.state() != "normal":
            raise RuntimeError("Live tooltip overlay followed the Companion into the minimized state.")

        if not restore_existing_window("KeystoneLens Verification"):
            raise RuntimeError("Could not find the verification window through Win32.")

        # Tk's cached state can lag ShowWindow(SW_RESTORE) on Windows CI even
        # after the native HWND has already left the iconic state. Verify the
        # actual Win32 state with a short bounded retry instead of treating that
        # Tk bookkeeping lag as a portable-runtime failure.
        hwnd_value = _find_top_level_window("KeystoneLens Verification")
        if hwnd_value is None:
            raise RuntimeError("Verification top-level HWND disappeared after restore.")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        hwnd = wintypes.HWND(hwnd_value)
        restored = False
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            root.update()
            if not user32.IsIconic(hwnd) and user32.IsWindowVisible(hwnd):
                restored = True
                break
            time.sleep(0.02)
        if not restored:
            raise RuntimeError("Win32 restore left the Tk window iconic.")
    finally:
        if overlay is not None:
            overlay.close()
        root.destroy()


def show_message(text: str, flags: int) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, text, "KeystoneLens", flags)
    except (AttributeError, OSError):
        pass


def show_startup_error(message: str) -> None:
    try:
        STARTUP_LOG.write_text(message, encoding="utf-8")
    except OSError:
        pass

    summary = ""
    for line in reversed(message.splitlines()):
        if line.strip():
            summary = line.strip()
            break
    if len(summary) > 180:
        summary = summary[:177] + "..."

    popup = (
        "KeystoneLens Portable could not start.\n\n"
        f"Details were written to:\n{STARTUP_LOG}"
    )
    if summary:
        popup += f"\n\nError: {summary}"
    show_message(popup, 0x10)


def acquire_single_instance_mutex():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return kernel32, handle


def close_mutex(mutex) -> None:
    if mutex is None:
        return
    kernel32, handle = mutex
    kernel32.CloseHandle(handle)


def system_exit_code(exc: SystemExit) -> int:
    if exc.code is None:
        return 0
    if isinstance(exc.code, int):
        return exc.code
    return 1


def app_crash_detail(exit_code: int) -> str:
    local = os.environ.get("LOCALAPPDATA", "")
    app_log = Path(local) / "KeystoneLens" / "keystonelens.log" if local else None
    if app_log is not None:
        try:
            if app_log.is_file():
                detail = app_log.read_text(encoding="utf-8", errors="replace").strip()
                if detail:
                    return detail
        except OSError:
            pass
    return f"KeystoneLens application exited during startup with code {exit_code}."


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--verify-ui", action="store_true")
    args, passthrough = parser.parse_known_args()

    configure_runtime_environment()
    mutex = None
    verification = args.verify or args.verify_ui

    try:
        verify_runtime(import_full_app=verification)
        if args.verify_ui:
            verify_ui_runtime()
            print("KeystoneLens portable GUI runtime verification passed.")
            return 0
        if args.verify:
            print("KeystoneLens portable runtime verification passed.")
            return 0

        mutex = acquire_single_instance_mutex()
        if mutex is None:
            if restore_existing_window():
                return 0
            show_message(
                "KeystoneLens is already running, but its window could not be restored. "
                "Close the old pythonw.exe process in Task Manager and start KeystoneLens again.",
                0x30,
            )
            return 0

        sys.argv = [str(APP_DIR / "keystonelens_companion" / "__main__.py"), *passthrough]
        runpy.run_module("keystonelens_companion.__main__", run_name="__main__")
        return 0
    except SystemExit as exc:
        code = system_exit_code(exc)
        if code != 0 and not verification:
            show_startup_error(app_crash_detail(code))
        return code
    except Exception:
        detail = traceback.format_exc()
        if verification:
            stream = sys.stderr
            if stream is not None:
                stream.write(detail)
        else:
            show_startup_error(detail)
        return 1
    finally:
        close_mutex(mutex)


if __name__ == "__main__":
    raise SystemExit(main())
