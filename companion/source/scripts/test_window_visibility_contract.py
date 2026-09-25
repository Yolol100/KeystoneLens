#!/usr/bin/env python3
"""Controlled-runtime checks for the single restorable Companion window."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "companion" / "source" / "app"
sys.path.insert(0, str(APP_ROOT))
os.environ["KEYSTONELENS_DISABLE_FORCE_EXIT_WATCHDOG"] = "1"

requests_stub = types.ModuleType("requests")
requests_stub.RequestException = RuntimeError
requests_stub.Session = object
sys.modules.setdefault("requests", requests_stub)

import keystonelens_companion.__main__ as app_module  # noqa: E402


class FakeRoot:
    def __init__(self):
        self.state_value = "iconic"
        self.deiconify_count = 0
        self.lift_count = 0
        self.focus_count = 0
        self.after_idle_count = 0
        self.update_count = 0

    def state(self, value=None):
        if value is not None:
            self.state_value = value
        return self.state_value

    def deiconify(self):
        self.deiconify_count += 1
        self.state_value = "normal"

    def update_idletasks(self):
        self.update_count += 1

    def lift(self):
        self.lift_count += 1

    def focus_force(self):
        self.focus_count += 1

    def after_idle(self, callback):
        self.after_idle_count += 1
        callback()


class Event:
    def __init__(self, widget):
        self.widget = widget


def make_app():
    app = app_module.App.__new__(app_module.App)
    app._shutdown_started = False
    app.root = FakeRoot()
    return app


def test_iconic_window_restores():
    app = make_app()
    app._show_main_window()

    assert app.root.state_value == "normal"
    assert app.root.deiconify_count == 1
    assert app.root.lift_count == 1


def test_user_requested_restore_gets_focus():
    app = make_app()
    app._show_main_window(force_foreground=True)

    assert app.root.state_value == "normal"
    assert app.root.focus_count == 1


def test_taskbar_map_reasserts_window():
    app = make_app()
    app.root.state_value = "normal"
    app._on_root_mapped(Event(app.root))

    assert app.root.after_idle_count == 1
    assert app.root.lift_count == 1


if __name__ == "__main__":
    test_iconic_window_restores()
    test_user_requested_restore_gets_focus()
    test_taskbar_map_reasserts_window()
    print("KeystoneLens window visibility contract passed.")
