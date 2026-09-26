#!/usr/bin/env python3
"""Target-runtime end-to-end checks for the KeystoneLens applicant flow."""
from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
import zlib


def _package_paths(package_root: Path) -> tuple[Path, Path]:
    companion = package_root / "Windows-Companion"
    app = companion / "app"
    packages = companion / "packages"
    if not app.is_dir() or not packages.is_dir():
        raise AssertionError("complete package is missing Windows Companion app/packages")
    return app, packages


def _text(value: str) -> bytes:
    raw = value.encode("utf-8")
    if len(raw) > 255:
        raise AssertionError("APS1 test string too long")
    return bytes([len(raw)]) + raw


def _applicant(
    applicant_id: int,
    name: str,
    class_id: int,
    spec_id: int,
    role: int,
) -> bytes:
    return b"".join((
        struct.pack(">I", applicant_id),
        bytes([1, class_id]),
        struct.pack(">H", spec_id),
        struct.pack(">H", 639),
        struct.pack(">H", 2800),
        struct.pack(">H", 3000),
        bytes([1, 15, 14, 8, 4, 2, 7, 1]),
        bytes([role]),
        _text(name),
        bytes([1]),
        struct.pack(">H", 3000),
        bytes([14, 15]),
    ))


def build_snapshot_payload(
    applicants: list[tuple[int, str, int, int, int]],
    *,
    generation: int = 1,
    dungeon: str = "Altar of Fangs",
    key_level: int = 12,
) -> bytes:
    body = bytearray()
    body += b"\x01"
    body += struct.pack(">IHHB", 0, 2, 8, key_level)
    body += _text(dungeon)
    body += _text("KeystoneLens test")
    body += _text("phase 3")
    body += b"\x01"
    body += _text("0.15.1")
    body += _text("12.0.5")
    body += bytes([3])
    body += _text("Leader-Draenor")
    body += b"\x00"
    body += struct.pack(">H", len(applicants))
    for row in applicants:
        body += _applicant(*row)
    body += struct.pack(">H", 0)

    version = 13
    flags = 0
    total_len = 13 + len(body)
    if total_len > 65535:
        raise AssertionError("APS1 test payload unexpectedly large")
    head = b"APS1" + bytes([version]) + struct.pack(">H", total_len) + bytes([flags, generation])
    unsigned = head + bytes(body)
    return unsigned + struct.pack(">I", zlib.crc32(unsigned) & 0xFFFFFFFF)


def make_qr_screenshot(path: Path, payload: bytes) -> None:
    from PIL import Image
    import zxingcpp

    barcode = zxingcpp.create_barcode(
        payload.hex(),
        zxingcpp.BarcodeFormat.QRCode,
        ec_level="50%",
    )
    bitmap = barcode.to_image(scale=5)
    image = Image.fromarray(bitmap)
    try:
        image.save(path, format="PNG")
    finally:
        image.close()



def make_result(job, percentile: float | None = None, *, error: str = ""):
    from keystonelens_companion.constants import HEALER_SPECS
    from keystonelens_companion.models import WCLBracket, WCLResult

    name, _slug, realm, _region, spec_id, dungeon, target = job
    metric = "hps" if spec_id in HEALER_SPECS else "dps"
    metrics = {}
    if percentile is not None and not error:
        metrics[metric] = WCLBracket(
            key_level=0,
            best_percentile=float(percentile),
            median_percentile=float(percentile),
            run_count=1,
            average_percentile=float(percentile),
        )
    return WCLResult(
        name=name,
        realm=realm,
        dungeon_name=dungeon,
        spec_id=spec_id,
        bracket=None,
        fetched_at=time.time(),
        target_key=target,
        error=error,
        metric_brackets=metrics,
    )


class FakeWCL:
    def __init__(self, percentiles=None, *, error: str = ""):
        self.percentiles = percentiles or {}
        self.error = error
        self.calls = []

    def fetch_batch_current_dungeon(self, jobs, *, max_cache_age_seconds=None):
        self.calls.append((list(jobs), max_cache_age_seconds))
        out = []
        for job in jobs:
            percentile = self.percentiles.get(job[0])
            out.append(make_result(job, percentile, error=self.error))
        return out


class BlockingWCL:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = []

    def fetch_batch_current_dungeon(self, jobs, *, max_cache_age_seconds=None):
        call_index = len(self.calls)
        self.calls.append((list(jobs), max_cache_age_seconds))
        if call_index == 0:
            self.started.set()
            if not self.release.wait(5.0):
                raise AssertionError("stale-result test release timed out")
        out = []
        for job in jobs:
            percentile = 99.0 if job[0] == "Alice" else 80.0
            out.append(make_result(job, percentile))
        return out


def snapshot_for(name: str, applicant_id: int, generation: int):
    from keystonelens_companion.models import Applicant, Listing, Snapshot, VersionInfo

    return Snapshot(
        listing=Listing(key_level=12, dungeon_name="Altar of Fangs"),
        version=VersionInfo(
            addon_version="0.15.1",
            game_version="12.0.5",
            region_id=3,
            player_name="Leader-Draenor",
        ),
        applicants=(Applicant(
            applicant_id=applicant_id,
            member_idx=1,
            class_id=8,
            spec_id=62,
            ilvl=639,
            rio_score=2800,
            rio_main_score=3000,
            role_byte=2,
            name=name,
        ),),
        listing_generation=generation,
    )


def test_real_screenshot_qr_to_engine_and_ui(package_root: Path) -> None:
    from keystonelens_companion.engine import (
        ApplicantEngine,
        LIVE_APPLICANT_CACHE_MAX_AGE_SECONDS,
    )
    from keystonelens_companion.metrics import applicant_board_rows
    from keystonelens_companion.watcher import ScreenshotWatcher

    client = FakeWCL({"Top": 98.0, "Healer": 91.0, "Low": 30.0})
    states = []
    ready = threading.Event()

    def on_update(state):
        states.append(state)
        if len(state.rows) == 3 and all(row.wcl_status == "ready" for row in state.rows):
            ready.set()

    engine = ApplicantEngine(client, on_update)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            screenshot = folder / "WoWScrnShot_0001.png"
            payload = build_snapshot_payload([
                (101, "Low-Draenor", 8, 62, 2),
                (102, "Top-Draenor", 8, 62, 2),
                (103, "Healer-Kazzak", 2, 65, 3),
            ])
            make_qr_screenshot(screenshot, payload)

            statuses = []
            watcher = ScreenshotWatcher(folder, engine.handle_snapshot, statuses.append)
            sig = watcher.files.signature(screenshot)
            assert watcher._consume(screenshot, sig, backfill=False) is False
            assert not screenshot.exists(), "complete authoritative QR should be committed/deleted"
            assert any("complete snapshot received" in status for status in statuses)

            assert ready.wait(6.0), "WCL applicant batch did not become ready"
            final_state = states[-1]
            rows = applicant_board_rows(final_state.rows)
            assert rows == [
                ("Top-Draenor", "DPS 98%", "S"),
                ("Healer-Kazzak", "Healing 91%", "A"),
                ("Low-Draenor", "DPS 30%", "D"),
            ]
            assert client.calls
            jobs, max_age = client.calls[0]
            assert max_age == LIVE_APPLICANT_CACHE_MAX_AGE_SECONDS == 60 * 60
            assert len(jobs) == 3
            assert {job[3] for job in jobs} == {"EU"}
            assert {job[5] for job in jobs} == {"Altar of Fangs"}
            assert {job[6] for job in jobs} == {12}

            old_local = os.environ.get("LOCALAPPDATA")
            old_watchdog = os.environ.get("KEYSTONELENS_DISABLE_FORCE_EXIT_WATCHDOG")
            isolated = folder / "localappdata"
            os.environ["LOCALAPPDATA"] = str(isolated)
            os.environ["KEYSTONELENS_DISABLE_FORCE_EXIT_WATCHDOG"] = "1"
            app = None
            try:
                from keystonelens_companion.__main__ import App

                app = App()
                app.root.withdraw()
                app.root.update_idletasks()
                app._render_applicants(final_state)
                rendered = [
                    tuple(app.applicant_table.item(item, "values"))
                    for item in app.applicant_table.get_children()
                ]
                assert rendered == rows
            finally:
                if app is not None:
                    app.quit()
                    app._cleanup_after_ui()
                if old_local is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = old_local
                if old_watchdog is None:
                    os.environ.pop("KEYSTONELENS_DISABLE_FORCE_EXIT_WATCHDOG", None)
                else:
                    os.environ["KEYSTONELENS_DISABLE_FORCE_EXIT_WATCHDOG"] = old_watchdog
    finally:
        assert engine.stop(timeout=2.0)


def test_rate_limit_error_is_bounded_and_visible() -> None:
    from keystonelens_companion.engine import ApplicantEngine
    from keystonelens_companion.metrics import applicant_board_rows

    client = FakeWCL(error="WCL rate limit; waiting for reset")
    states = []
    done = threading.Event()

    def on_update(state):
        states.append(state)
        if state.rows and state.rows[0].wcl_status == "error":
            done.set()

    engine = ApplicantEngine(client, on_update)
    try:
        assert engine.handle_snapshot(snapshot_for("Rate-Draenor", 201, 20))
        assert done.wait(4.0)
        time.sleep(0.35)
        assert len(client.calls) == 1, "provider error must not spin/requeue immediately"
        rows = applicant_board_rows(states[-1].rows)
        assert rows == [("Rate-Draenor", "WCL fout", "—")]
    finally:
        assert engine.stop(timeout=2.0)


def test_rapid_listing_switch_rejects_stale_wcl_result() -> None:
    from keystonelens_companion.engine import ApplicantEngine
    from keystonelens_companion.metrics import applicant_board_rows

    client = BlockingWCL()
    states = []
    bob_ready = threading.Event()

    def on_update(state):
        states.append(state)
        if (
            len(state.rows) == 1
            and state.rows[0].applicant.name == "Bob-Draenor"
            and state.rows[0].wcl_status == "ready"
        ):
            bob_ready.set()

    engine = ApplicantEngine(client, on_update)
    try:
        assert engine.handle_snapshot(snapshot_for("Alice-Draenor", 301, 30))
        assert client.started.wait(3.0)
        assert engine.handle_snapshot(snapshot_for("Bob-Draenor", 302, 31))
        client.release.set()
        assert bob_ready.wait(6.0)
        final = states[-1]
        assert [row.applicant.name for row in final.rows] == ["Bob-Draenor"]
        assert applicant_board_rows(final.rows) == [("Bob-Draenor", "DPS 80%", "B")]
        assert len(client.calls) == 2
        assert client.calls[0][0][0][0] == "Alice"
        assert client.calls[1][0][0][0] == "Bob"
    finally:
        client.release.set()
        assert engine.stop(timeout=2.0)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_end_to_end_applicant_flow.py <extracted-complete-package-root>")

    package_root = Path(sys.argv[1]).resolve()
    app_root, packages_root = _package_paths(package_root)
    sys.path.insert(0, str(packages_root))
    sys.path.insert(0, str(app_root))

    test_real_screenshot_qr_to_engine_and_ui(package_root)
    test_rate_limit_error_is_bounded_and_visible()
    test_rapid_listing_switch_rejects_stale_wcl_result()
    print("KeystoneLens phase-3 applicant end-to-end flow passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
