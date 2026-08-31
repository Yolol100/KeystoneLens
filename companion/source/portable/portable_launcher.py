from __future__ import annotations

import argparse
import ctypes
import os
from pathlib import Path
import runpy
import sys
import traceback


ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
PACKAGES_DIR = ROOT / "packages"
RUNTIME_DIR = ROOT / "runtime"
STARTUP_LOG = ROOT / "portable-startup.log"


def configure_import_path() -> None:
    sys.path[:0] = [str(APP_DIR), str(PACKAGES_DIR)]


def verify_runtime() -> None:
    if os.name != "nt":
        raise RuntimeError("KeystoneLens Portable is a Windows x64 package.")
    if sys.version_info[:3] != (3, 13, 15):
        raise RuntimeError(
            "Portable runtime mismatch: expected Python 3.13.15, got "
            + ".".join(str(part) for part in sys.version_info[:3])
        )
    if not (RUNTIME_DIR / "python.exe").is_file() or not (RUNTIME_DIR / "pythonw.exe").is_file():
        raise RuntimeError("The bundled KeystoneLens Python runtime is incomplete.")

    import tkinter  # noqa: F401
    import requests  # noqa: F401
    import PIL  # noqa: F401
    import zxingcpp  # noqa: F401
    import keystonelens_companion.__main__  # noqa: F401


def show_startup_error(message: str) -> None:
    try:
        STARTUP_LOG.write_text(message, encoding="utf-8")
    except OSError:
        pass
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            "KeystoneLens Portable could not start.\n\n"
            f"Details were written to:\n{STARTUP_LOG}",
            "KeystoneLens",
            0x10,
        )
    except (AttributeError, OSError):
        pass


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--verify", action="store_true")
    args, passthrough = parser.parse_known_args()
    configure_import_path()

    try:
        verify_runtime()
        if args.verify:
            print("KeystoneLens portable runtime verification passed.")
            return 0

        sys.argv = [str(APP_DIR / "keystonelens_companion" / "__main__.py"), *passthrough]
        runpy.run_module("keystonelens_companion.__main__", run_name="__main__")
        return 0
    except BaseException:
        detail = traceback.format_exc()
        if args.verify:
            print(detail, file=sys.stderr)
        else:
            show_startup_error(detail)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
