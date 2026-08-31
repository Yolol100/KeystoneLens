from __future__ import annotations

import argparse
import ctypes
import importlib
import os
from pathlib import Path
import runpy
import sys
import tempfile
import traceback


ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
PACKAGES_DIR = ROOT / "packages"
RUNTIME_DIR = ROOT / "runtime"
RUNTIME_VERSION_FILE = RUNTIME_DIR / "python-version.txt"
PRIMARY_STARTUP_LOG = ROOT / "portable-startup.log"
FALLBACK_STARTUP_LOG = Path(tempfile.gettempdir()) / "keystonelens-portable-startup.log"
SINGLE_INSTANCE_NAME = r"Local\KeystoneLens.Companion.Singleton"
ERROR_ALREADY_EXISTS = 183


def configure_import_path() -> None:
    sys.path[:0] = [str(APP_DIR), str(PACKAGES_DIR)]


def expected_runtime_version() -> tuple[int, int, int]:
    try:
        raw = RUNTIME_VERSION_FILE.read_text(encoding="ascii").strip()
        parts = tuple(int(part) for part in raw.split("."))
    except (OSError, UnicodeError, ValueError) as exc:
        raise RuntimeError("The bundled KeystoneLens runtime version metadata is invalid.") from exc
    if len(parts) != 3 or any(part < 0 for part in parts):
        raise RuntimeError("The bundled KeystoneLens runtime version metadata is invalid.")
    return parts


def verify_runtime(*, import_full_app: bool) -> None:
    if os.name != "nt":
        raise RuntimeError("KeystoneLens Portable is a Windows x64 package.")
    expected = expected_runtime_version()
    if sys.version_info[:3] != expected:
        raise RuntimeError(
            "Portable runtime mismatch: expected "
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


def message_box(message: str, *, error: bool = False) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, message, "KeystoneLens", 0x10 if error else 0x40)
    except (AttributeError, OSError):
        pass


def write_startup_log(message: str) -> Path:
    for path in (PRIMARY_STARTUP_LOG, FALLBACK_STARTUP_LOG):
        try:
            path.write_text(message, encoding="utf-8")
            return path
        except OSError:
            continue
    return PRIMARY_STARTUP_LOG


def clear_stale_startup_logs() -> None:
    for path in (PRIMARY_STARTUP_LOG, FALLBACK_STARTUP_LOG):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def show_startup_error(message: str) -> None:
    log_path = write_startup_log(message)
    message_box(
        "KeystoneLens Portable could not start.\n\n"
        f"Details were written to:\n{log_path}",
        error=True,
    )


def acquire_single_instance() -> int | None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
    create_mutex.restype = ctypes.c_void_p
    ctypes.set_last_error(0)
    raw_handle = create_mutex(None, 0, SINGLE_INSTANCE_NAME)
    if not raw_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(ctypes.c_void_p(raw_handle))
        message_box("KeystoneLens Companion is already running.")
        return None
    return int(raw_handle)


def close_handle(handle: int | None) -> None:
    if handle is None:
        return
    try:
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(handle))
    except (AttributeError, OSError):
        pass


def system_exit_code(exc: SystemExit) -> int:
    if exc.code is None:
        return 0
    if isinstance(exc.code, int):
        return exc.code
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--verify", action="store_true")
    args, passthrough = parser.parse_known_args()
    configure_import_path()
    mutex: int | None = None

    try:
        verify_runtime(import_full_app=args.verify)
        if args.verify:
            print("KeystoneLens portable runtime verification passed.")
            return 0

        clear_stale_startup_logs()
        mutex = acquire_single_instance()
        if mutex is None:
            return 0

        sys.argv = [str(APP_DIR / "keystonelens_companion" / "__main__.py"), *passthrough]
        runpy.run_module("keystonelens_companion.__main__", run_name="__main__")
        return 0
    except SystemExit as exc:
        code = system_exit_code(exc)
        if code != 0 and not args.verify:
            show_startup_error(f"KeystoneLens Companion exited with code {code}.\n\n{traceback.format_exc()}")
        return code
    except Exception:
        detail = traceback.format_exc()
        if args.verify:
            print(detail, file=sys.stderr)
        else:
            show_startup_error(detail)
        return 1
    finally:
        close_handle(mutex)


if __name__ == "__main__":
    raise SystemExit(main())
