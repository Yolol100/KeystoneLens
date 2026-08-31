from __future__ import annotations

import argparse
import ctypes
import importlib
import json
import os
from pathlib import Path
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


def configure_import_path() -> None:
    sys.path[:0] = [str(APP_DIR), str(PACKAGES_DIR)]


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
    show_message(
        "KeystoneLens Portable could not start.\n\n"
        f"Details were written to:\n{STARTUP_LOG}",
        0x10,
    )


def acquire_single_instance_mutex():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_bool
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


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--verify", action="store_true")
    args, passthrough = parser.parse_known_args()
    configure_import_path()
    mutex = None

    try:
        verify_runtime(import_full_app=args.verify)
        if args.verify:
            print("KeystoneLens portable runtime verification passed.")
            return 0

        mutex = acquire_single_instance_mutex()
        if mutex is None:
            show_message("KeystoneLens is already running.", 0x40)
            return 0

        sys.argv = [str(APP_DIR / "keystonelens_companion" / "__main__.py"), *passthrough]
        runpy.run_module("keystonelens_companion.__main__", run_name="__main__")
        return 0
    except SystemExit as exc:
        return system_exit_code(exc)
    except Exception:
        detail = traceback.format_exc()
        if args.verify:
            print(detail, file=sys.stderr)
        else:
            show_startup_error(detail)
        return 1
    finally:
        close_mutex(mutex)


if __name__ == "__main__":
    raise SystemExit(main())
