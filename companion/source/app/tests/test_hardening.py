from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PIL import Image

from keystonelens_companion import aps1, config
from keystonelens_companion.addon_sync import render_data_addon_toc
from keystonelens_companion.config import Config, load_config, save_config
from keystonelens_companion.watcher import ScreenshotWatcher


def test_non_windows_config_never_persists_wcl_secret(tmp_path):
    target = tmp_path / "config.json"
    cfg = Config(client_id="client", client_secret="super-secret", screenshots_path="C:/WoW/Screenshots")
    with patch.object(config, "config_path", return_value=target), patch.object(config.os, "name", "posix"):
        save_config(cfg)
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert "client_secret" not in raw
    assert "client_secret_protected" not in raw
    assert "super-secret" not in target.read_text(encoding="utf-8")


def test_fragment_assembler_bounds_incomplete_streams():
    assembler = aps1.FragmentAssembler(max_streams=3)
    for stream_id in range(10):
        fragment = aps1.Fragment(
            stream_id=stream_id,
            generation=1,
            index=0,
            count=2,
            inner_len=640,
            inner_crc=0,
            chunk=b"x" * aps1.FRAGMENT_CHUNK_BYTES,
        )
        assert assembler.push(fragment) is None
    assert len(assembler._streams) == 3
    assert {key[0] for key in assembler._streams} == {7, 8, 9}


def test_decode_rejects_oversized_screenshot_before_opening():
    class HugePath:
        def stat(self):
            return SimpleNamespace(st_size=aps1.MAX_SCREENSHOT_BYTES + 1)

    fake_zxing = SimpleNamespace(BarcodeFormat=SimpleNamespace(QRCode="QR"), read_barcodes=lambda *_a, **_k: [])
    with patch.dict("sys.modules", {"zxingcpp": fake_zxing}):
        with pytest.raises(aps1.APS1Error, match="file size"):
            aps1.decode_image_result(HugePath(), aps1.FragmentAssembler())


def test_decode_rejects_excessive_image_dimension(tmp_path):
    path = tmp_path / "wide.png"
    Image.new("RGB", (aps1.MAX_IMAGE_DIMENSION + 1, 1), "white").save(path)
    fake_zxing = SimpleNamespace(BarcodeFormat=SimpleNamespace(QRCode="QR"), read_barcodes=lambda *_a, **_k: [])
    with patch.dict("sys.modules", {"zxingcpp": fake_zxing}):
        with pytest.raises(aps1.APS1Error, match="dimensions"):
            aps1.decode_image_result(path, aps1.FragmentAssembler())


def test_watcher_does_not_deliver_after_stop_boundary(tmp_path):
    delivered = []
    watcher = ScreenshotWatcher(tmp_path, delivered.append)
    path = tmp_path / "frame.png"
    path.write_bytes(b"x")
    sig = (1, 1)
    snapshot = object()

    def decode_and_stop(*_args, **_kwargs):
        watcher.stop_event.set()
        return True, True, snapshot

    with patch("keystonelens_companion.watcher.decode_image_result", side_effect=decode_and_stop), \
         patch.object(watcher.files, "mark_seen") as mark_seen, \
         patch.object(watcher.files, "commit_snapshot") as commit:
        assert watcher._consume(path, sig, False) is False
    assert delivered == []
    mark_seen.assert_not_called()
    commit.assert_not_called()


def test_generated_data_addon_targets_current_retail_interface():
    toc = render_data_addon_toc()
    assert "## Interface: 120007, 120100" in toc
    assert "120005" not in toc


def test_generated_data_addon_toc_does_not_reference_unmanaged_icon_asset():
    # TooltipCacheSync only materializes the TOC and Data.lua at runtime.
    # The generated TOC must therefore not reference an icon that is never copied.
    toc = render_data_addon_toc()
    assert "## IconTexture:" not in toc


def test_transport_bookkeeping_is_memory_bounded(tmp_path):
    from keystonelens_companion.transport_pipeline import (
        MAX_DECODE_FAILURES,
        MAX_PENDING_DELETES,
        TransportFileLifecycle,
    )

    lifecycle = TransportFileLifecycle()
    for i in range(MAX_DECODE_FAILURES + 100):
        lifecycle.mark_decode_failure(tmp_path / f"bad-{i}.png", (i, 1), retry_limit=99)
    assert len(lifecycle.decode_failures) == MAX_DECODE_FAILURES

    lifecycle.pending_deletes = {
        str(tmp_path / f"locked-{i}.png"): ((i, 1), 1, 0.0)
        for i in range(MAX_PENDING_DELETES + 100)
    }
    lifecycle.bound_memory()
    assert len(lifecycle.pending_deletes) == MAX_PENDING_DELETES


def test_oversized_config_is_ignored_without_loading_into_memory(tmp_path):
    target = tmp_path / "config.json"
    target.write_bytes(b"{" + b"x" * (config.MAX_CONFIG_FILE_BYTES + 1))
    with patch.object(config, "config_path", return_value=target), \
         patch.object(config, "autodetect_screenshots_path", return_value="AUTO"):
        cfg = load_config()
    assert cfg.screenshots_path == "AUTO"
    assert cfg.score_min == 84


def test_oversized_wcl_cache_is_ignored(tmp_path):
    from keystonelens_companion import wcl
    target = tmp_path / "wcl.json"
    target.write_bytes(b"{" + b"x" * (wcl.MAX_CACHE_FILE_BYTES + 1))
    cache = wcl.WCLCache(target)
    assert cache.count() == 0


def test_short_aps1_qr_is_rejected_without_index_error(tmp_path):
    import sys

    path = tmp_path / "short.png"
    Image.new("RGB", (64, 64), "white").save(path)
    fake_zxing = SimpleNamespace(
        BarcodeFormat=SimpleNamespace(QRCode="QR"),
        read_barcodes=lambda *_a, **_k: [SimpleNamespace(bytes=b"APS1")],
    )
    with patch.dict(sys.modules, {"zxingcpp": fake_zxing}):
        owned, consumed, snapshot = aps1.decode_image_result(path, aps1.FragmentAssembler())
    assert owned is True
    assert consumed is False
    assert snapshot is None


def test_rio_cache_is_ttl_and_size_bounded():
    from keystonelens_companion import rio

    client = rio.RIOClient()
    try:
        now = 10_000.0
        # Include expired/future entries plus more live rows than each cache permits.
        for i in range(rio.MAX_PROFILE_CACHE_ENTRIES + 50):
            fetched = now - (i % 100)
            key = ("eu", "realm", f"name{i}", "dungeon", 10, "dps")
            client._profiles[key] = rio.RIOResult(
                f"name{i}", "realm", "eu", "dungeon", 10, fetched_at=fetched
            )
        client._profiles[("eu", "realm", "expired", "dungeon", 10, "dps")] = rio.RIOResult(
            "expired", "realm", "eu", "dungeon", 10,
            fetched_at=now - rio.PROFILE_TTL_SECONDS - 1,
        )
        client._profiles[("eu", "realm", "future", "dungeon", 10, "dps")] = rio.RIOResult(
            "future", "realm", "eu", "dungeon", 10,
            fetched_at=now + rio.MAX_CACHE_FUTURE_SKEW_SECONDS + 1,
        )
        for i in range(rio.MAX_RAW_PROFILE_CACHE_ENTRIES + 50):
            client._raw_profiles[("eu", "realm", f"raw{i}")] = (now - (i % 100), {}, False)
        client._raw_profiles[("eu", "realm", "raw-expired")] = (
            now - rio.PROFILE_TTL_SECONDS - 1, {}, False
        )
        client._raw_profiles[("eu", "realm", "raw-future")] = (
            now + rio.MAX_CACHE_FUTURE_SKEW_SECONDS + 1, {}, False
        )

        with client._lock:
            client._prune_cache_locked(now)

        assert len(client._profiles) <= rio.MAX_PROFILE_CACHE_ENTRIES
        assert len(client._raw_profiles) <= rio.MAX_RAW_PROFILE_CACHE_ENTRIES
        assert all("expired" not in key and "future" not in key for key in client._profiles)
        assert all("expired" not in key and "future" not in key for key in client._raw_profiles)
    finally:
        client.close()


def test_wcl_cache_rejects_future_and_nonfinite_evidence(tmp_path):
    import time
    from keystonelens_companion import wcl

    target = tmp_path / "wcl.json"
    cache = wcl.WCLCache(target)
    key = cache._key("EU", "Realm", "Applicant", 71, "Altar of Fangs", 10)
    now = time.time()

    cache._data[key] = {
        "name": "Applicant",
        "realm": "Realm",
        "dungeon_name": "Altar of Fangs",
        "spec_id": 71,
        "fetched_at": now,
        "bracket": {
            "key_level": 0,
            "best_percentile": float("nan"),
            "median_percentile": 50.0,
            "average_percentile": 50.0,
            "run_count": 2,
        },
        "metric_brackets": {},
        "not_found": False,
        "error": "",
    }
    assert cache.get("EU", "Realm", "Applicant", 71, "Altar of Fangs", 10) is None
    assert key not in cache._data

    cache._data[key] = {
        "name": "Applicant",
        "realm": "Realm",
        "dungeon_name": "Altar of Fangs",
        "spec_id": 71,
        "fetched_at": now + wcl.MAX_CACHE_FUTURE_SKEW_SECONDS + 1,
        "bracket": None,
        "metric_brackets": {},
        "not_found": True,
        "error": "",
    }
    assert cache.get("EU", "Realm", "Applicant", 71, "Altar of Fangs", 10) is None
    assert key not in cache._data


def test_scoring_clamp_never_promotes_nonfinite_values():
    from keystonelens_companion.scoring import _clamp

    assert _clamp(float("nan")) == 0.0
    assert _clamp(float("inf")) == 0.0
    assert _clamp(float("-inf")) == 0.0


def test_wcl_cache_prunes_invalid_nonfinite_rows_on_load(tmp_path):
    import time
    from keystonelens_companion import wcl

    target = tmp_path / "wcl.json"
    target.write_text(json.dumps({
        "bad": {
            "name": "Applicant",
            "realm": "Realm",
            "dungeon_name": "Altar of Fangs",
            "spec_id": 71,
            "fetched_at": time.time(),
            "bracket": {
                "key_level": 10,
                "best_percentile": float("nan"),
                "median_percentile": 50.0,
                "average_percentile": 50.0,
                "run_count": 2,
            },
            "metric_brackets": {},
            "not_found": False,
            "error": "",
        }
    }), encoding="utf-8")
    cache = wcl.WCLCache(target)
    assert cache.count() == 0
    persisted = json.loads(target.read_text(encoding="utf-8"))
    assert persisted == {}


def test_incomplete_fragment_does_not_mask_complete_qr_in_same_image(tmp_path):
    import sys

    path = tmp_path / "mixed.png"
    Image.new("RGB", (64, 64), "white").save(path)
    fragment_raw = b"APS1" + bytes([aps1.FRAGMENT_VERSION]) + b"fragment"
    complete_raw = b"APS1\x0ccomplete"
    fake_zxing = SimpleNamespace(
        BarcodeFormat=SimpleNamespace(QRCode="QR"),
        read_barcodes=lambda *_a, **_k: [
            SimpleNamespace(bytes=fragment_raw),
            SimpleNamespace(bytes=complete_raw),
        ],
    )
    expected = object()
    assembler = aps1.FragmentAssembler()
    with patch.dict(sys.modules, {"zxingcpp": fake_zxing}), \
         patch.object(aps1, "parse_fragment", return_value=object()), \
         patch.object(assembler, "push", return_value=None) as push, \
         patch.object(aps1, "parse_snapshot", return_value=expected) as parse_snapshot:
        owned, consumed, snapshot = aps1.decode_image_result(path, assembler)

    assert owned is True
    assert consumed is True
    assert snapshot is expected
    push.assert_called_once()
    parse_snapshot.assert_called_once_with(complete_raw)


def test_incomplete_fragment_in_crop_does_not_mask_complete_qr_elsewhere(tmp_path):
    import sys

    path = tmp_path / "large.png"
    Image.new("RGB", (900, 900), "white").save(path)
    fragment_raw = b"APS1" + bytes([aps1.FRAGMENT_VERSION]) + b"fragment"
    complete_raw = b"APS1\x0ccomplete"
    batches = iter([
        [SimpleNamespace(bytes=fragment_raw)],  # raw crop
        [],                                      # enlarged crop
        [SimpleNamespace(bytes=complete_raw)],   # full image fallback
    ])
    fake_zxing = SimpleNamespace(
        BarcodeFormat=SimpleNamespace(QRCode="QR"),
        read_barcodes=lambda *_a, **_k: next(batches),
    )
    expected = object()
    assembler = aps1.FragmentAssembler()
    with patch.dict(sys.modules, {"zxingcpp": fake_zxing}), \
         patch.object(aps1, "parse_fragment", return_value=object()), \
         patch.object(assembler, "push", return_value=None), \
         patch.object(aps1, "parse_snapshot", return_value=expected):
        owned, consumed, snapshot = aps1.decode_image_result(path, assembler)

    assert owned is True
    assert consumed is True
    assert snapshot is expected


def test_app_quit_signals_network_clients_before_joining_engine_workers():
    from keystonelens_companion.__main__ import App

    calls: list[str] = []

    class Stopper:
        def __init__(self, name: str):
            self.name = name
        def stop(self):
            calls.append(self.name)

    class Closer:
        def __init__(self, name: str):
            self.name = name
        def close(self):
            calls.append(self.name)

    class Root:
        def destroy(self):
            calls.append("root")

    app = App.__new__(App)
    app._preferences_save_job = None
    app.watcher = Stopper("watcher")
    app.wcl = Closer("wcl")
    app.rio = Closer("rio")
    app.engine = Stopper("engine")
    app.root = Root()

    app.quit()

    assert calls == ["watcher", "wcl", "rio", "engine", "root"]
    assert app.watcher is None
    assert app.wcl is None


def test_rio_invalid_200_json_is_transient_error_not_cached_zero_score():
    from unittest.mock import Mock
    from keystonelens_companion import rio

    class Response:
        status_code = 200
        headers = {}
        def json(self):
            raise ValueError("broken json")

    client = rio.RIOClient()
    try:
        client._get = Mock(return_value=Response())
        result = client.fetch_character("Applicant", "Realm", "EU", "Altar of Fangs", 10, "dps")
        assert result.error == "Raider.IO returned invalid JSON"
        assert result.score == 0
        assert client._profiles == {}
        assert client._raw_profiles == {}
    finally:
        client.close()


def test_rio_200_without_character_identity_is_rejected_as_malformed():
    from unittest.mock import Mock
    from keystonelens_companion import rio

    class Response:
        status_code = 200
        headers = {}
        def json(self):
            return {"mythic_plus_scores_by_season": []}

    client = rio.RIOClient()
    try:
        client._get = Mock(return_value=Response())
        result = client.fetch_character("Applicant", "Realm", "EU", "Altar of Fangs", 10, "dps")
        assert result.error == "Raider.IO returned malformed character data"
        assert client._profiles == {}
        assert client._raw_profiles == {}
    finally:
        client.close()


def test_crash_log_records_version_component_severity_and_bounds_growth(tmp_path):
    from unittest.mock import patch
    from keystonelens_companion import __version__
    from keystonelens_companion import __main__ as app_main

    target = tmp_path / "keystonelens.log"
    target.write_bytes(b"x" * (app_main.MAX_CRASH_LOG_BYTES + 128))
    try:
        raise RuntimeError("controlled crash marker")
    except RuntimeError as exc:
        with patch.object(app_main, "log_path", return_value=target):
            app_main._write_crash_log(type(exc), exc, exc.__traceback__)

    text = target.read_text(encoding="utf-8")
    assert "[FATAL]" in text
    assert f"KeystoneLens {__version__} Companion" in text
    assert "controlled crash marker" in text
    assert target.stat().st_size < app_main.CRASH_LOG_TAIL_BYTES + 16_384


def test_wow_autodetect_refuses_ambiguous_known_retail_installations(tmp_path, monkeypatch):
    from keystonelens_companion import config

    pf = tmp_path / "Program Files"
    pfx86 = tmp_path / "Program Files (x86)"
    first = pf / "World of Warcraft" / "_retail_" / "Screenshots"
    second = pfx86 / "World of Warcraft" / "_retail_" / "Screenshots"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    monkeypatch.setenv("ProgramFiles", str(pf))
    monkeypatch.setenv("ProgramFiles(x86)", str(pfx86))

    assert config.autodetect_screenshots_path() == ""


def test_wow_autodetect_accepts_exactly_one_known_retail_installation(tmp_path, monkeypatch):
    from keystonelens_companion import config

    pf = tmp_path / "Program Files"
    only = pf / "World of Warcraft" / "_retail_" / "Screenshots"
    only.mkdir(parents=True)
    monkeypatch.setenv("ProgramFiles", str(pf))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "missing-x86"))

    assert config.autodetect_screenshots_path() == str(only)


@pytest.mark.parametrize("path", [
    r"D:\\Games & Apps\\World of Warcraft\\_retail_\\Screenshots",
    r"E:\\Spellen\\Wörld of Warcraft\\_retail_\\Screenshots",
])
def test_manual_wow_screenshot_path_accepts_custom_drives_spaces_and_unicode(path):
    from keystonelens_companion.ui import validate_settings_values
    assert validate_settings_values("", "", path) == ""


def test_manual_wow_screenshot_path_rejects_wrong_client_variant():
    from keystonelens_companion.ui import validate_settings_values
    error = validate_settings_values("", "", r"D:\\World of Warcraft\\_classic_\\Screenshots")
    assert "_retail_" in error
