#!/usr/bin/env python3
"""Controlled-runtime regression checks for Companion shutdown behavior."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "companion" / "source" / "app"
sys.path.insert(0, str(APP_ROOT))
os.environ["KEYSTONELENS_DISABLE_FORCE_EXIT_WATCHDOG"] = "1"

# The source CI job intentionally does not install Windows runtime packages.
# Stub only the HTTP package needed while importing the app graph; this test
# exercises shutdown lifecycle, not Warcraft Logs transport.
requests_stub = types.ModuleType("requests")
requests_stub.RequestException = RuntimeError
requests_stub.Session = object
sys.modules.setdefault("requests", requests_stub)

import keystonelens_companion.__main__ as app_module  # noqa: E402


class FakeRoot:
    def __init__(self):
        self.destroy_count = 0
        self.mainloop_count = 0
        self.app = None

    def destroy(self):
        self.destroy_count += 1

    def mainloop(self):
        self.mainloop_count += 1
        if self.app is not None:
            self.app.quit()


class FakeWatcher:
    def __init__(self):
        self.request_count = 0
        self.stop_count = 0

    def request_stop(self):
        self.request_count += 1

    def stop(self, timeout=1.0):
        self.stop_count += 1
        return True


class FakeEngine:
    def __init__(self):
        self.request_count = 0
        self.stop_count = 0

    def request_stop(self):
        self.request_count += 1

    def stop(self, timeout=1.0):
        self.stop_count += 1
        return True


class FakeWCL:
    def __init__(self, delay=0.0):
        self.close_count = 0
        self.delay = delay

    def close(self):
        self.close_count += 1
        if self.delay:
            time.sleep(self.delay)


def make_app(*, wcl_delay=0.0):
    app = app_module.App.__new__(app_module.App)
    app._shutdown_started = False
    app._shutdown_cleaned = False
    app._shutdown_watchdog_started = False
    app._shutdown_step_timeout = 0.05
    app._shutdown_warnings = []
    app.root = FakeRoot()
    app.root.app = app
    app.watcher = FakeWatcher()
    app.wcl = FakeWCL(delay=wcl_delay)
    app.engine = FakeEngine()
    return app


def test_close_path_is_idempotent():
    app = make_app()
    app.run()

    assert app.root.mainloop_count == 1
    assert app.root.destroy_count == 1
    assert app.watcher is None
    assert app.wcl is None
    assert app.engine.request_count >= 1
    assert app.engine.stop_count == 1

    app.quit()
    app._cleanup_after_ui()
    assert app.root.destroy_count == 1
    assert app.engine.stop_count == 1


def test_cleanup_is_bounded():
    with tempfile.TemporaryDirectory() as tmp:
        app_module.log_path = lambda: Path(tmp) / "shutdown.log"
        app = make_app(wcl_delay=0.5)

        started = time.monotonic()
        app.quit()
        app._cleanup_after_ui()
        elapsed = time.monotonic() - started

        assert elapsed < 0.25, f"shutdown cleanup took too long: {elapsed:.3f}s"
        assert any("wcl: cleanup timed out" in item for item in app._shutdown_warnings)


def test_wcl_close_waits_for_inflight_http_boundary():
    """Closing the shared HTTP session must not race an active WCL request."""
    client = app_module.WCLClient.__new__(app_module.WCLClient)
    client._closed = threading.Event()
    client._token = "token"
    client._token_expires = time.time() + 60
    client.client_secret = "secret"
    client._http_lock = threading.Lock()

    in_flight = threading.Event()
    release = threading.Event()
    close_done = threading.Event()

    class FakeHTTP:
        def __init__(self):
            self.closed_during_inflight = False

        def close(self):
            self.closed_during_inflight = in_flight.is_set()

    http = FakeHTTP()
    client._http = http

    def hold_http_boundary():
        with client._http_lock:
            in_flight.set()
            assert release.wait(timeout=2.0)
            in_flight.clear()

    worker = threading.Thread(target=hold_http_boundary)
    worker.start()
    assert in_flight.wait(timeout=1.0)

    def close_client():
        client.close()
        close_done.set()

    closer = threading.Thread(target=close_client)
    closer.start()
    time.sleep(0.02)
    assert not close_done.is_set(), "WCL close raced an active HTTP operation"

    release.set()
    worker.join(timeout=1.0)
    closer.join(timeout=1.0)
    assert not worker.is_alive()
    assert not closer.is_alive()
    assert close_done.is_set()
    assert not http.closed_during_inflight


if __name__ == "__main__":
    test_close_path_is_idempotent()
    test_cleanup_is_bounded()
    test_wcl_close_waits_for_inflight_http_boundary()
    print("KeystoneLens shutdown contract passed.")
