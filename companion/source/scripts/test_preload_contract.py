#!/usr/bin/env python3
"""Controlled-runtime contract for the persistent WCL preload database."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "companion" / "source" / "app"
sys.path.insert(0, str(APP_ROOT))

from keystonelens_companion.config import VALID_REGIONS, _normalize_config  # noqa: E402
from keystonelens_companion.preload import (  # noqa: E402
    ACTIVE_SEASON_KEY,
    DATASET_VERSION,
    MAX_DATASET_AGE_SECONDS,
    PreloadStore,
    record_key,
    render_lua_dataset,
)


def row(name="Alice-Draenor", spec=62, metric="DPS", pct=97.4, dungeon="Altar of Fangs", fetched=None):
    return {
        "full_name": name,
        "spec_id": spec,
        "dungeon": dungeon,
        "season": ACTIVE_SEASON_KEY,
        "metric": metric,
        "percentile": pct,
        "fetched_at": time.time() if fetched is None else fetched,
    }


def test_roundtrip_and_indexes():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "preload.json"
        store = PreloadStore(path)
        assert store.merge([row()], region="EU") >= 1
        assert store.save()
        loaded = PreloadStore(path)
        region, rows = loaded.snapshot()
        assert region == "EU"
        assert len(rows) == 1
        assert record_key("Alice-Draenor", 62, "Altar of Fangs") in loaded.records

        lua = render_lua_dataset(region, rows, now=time.time())
        assert "_G.KeystoneLensPreloadV4" in lua
        assert f"version = {DATASET_VERSION}" in lua
        assert 'season = "midnight-s2"' in lua
        assert '["alice-draenor|62|altaroffangs"]' in lua
        assert 'unitEntries = {' in lua
        assert '{"D",97.40,' in lua


def test_fail_closed_records_and_cross_realm():
    now = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        store = PreloadStore(Path(tmp) / "preload.json")
        bad = [
            row(name="NoRealm", fetched=now),
            row(spec=0, fetched=now),
            row(metric="NOPE", fetched=now),
            row(pct=101, fetched=now),
            row(dungeon="Magisters' Terrace", fetched=now),  # previous season
            row(fetched=now - MAX_DATASET_AGE_SECONDS - 1),
        ]
        assert store.merge(bad, region="EU") == 0
        assert store.merge([
            row(name="Alice-Draenor", pct=90, fetched=now),
            row(name="Alice-Kazzak", pct=80, fetched=now),
        ], region="EU") == 2
        assert len(store.records) == 2
        assert record_key("Alice-Draenor", 62, "Altar of Fangs") != record_key(
            "Alice-Kazzak", 62, "Altar of Fangs"
        )


def test_multi_spec_unit_index_fails_closed():
    now = time.time()
    lua = render_lua_dataset("EU", [
        row(spec=62, pct=90, fetched=now),
        row(spec=63, pct=91, fetched=now),
    ], now=now)
    assert '["alice-draenor|62|altaroffangs"]' in lua
    assert '["alice-draenor|63|altaroffangs"]' in lua
    assert '["alice-draenor|altaroffangs"]' not in lua


def test_thirty_plus_records_and_region_reset():
    now = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        store = PreloadStore(Path(tmp) / "preload.json")
        rows = [row(name=f"Player{i}-Draenor", fetched=now) for i in range(35)]
        assert store.merge(rows, region="EU") == 35
        assert len(store.snapshot()[1]) == 35
        store.merge([row(name="Usplayer-Illidan", fetched=now)], region="US")
        region, current = store.snapshot()
        assert region == "US"
        assert len(current) == 1
        assert current[0]["full_name"] == "Usplayer-Illidan"



def test_region_configuration_and_preferred_store():
    assert VALID_REGIONS == ("EU", "US", "KR", "TW", "CN")
    assert _normalize_config({}).region == "EU"
    assert _normalize_config({"region": "us"}).region == "US"
    assert _normalize_config({"region": "invalid"}).region == "EU"

    now = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "preload.json"
        store = PreloadStore(path, preferred_region="EU")
        assert store.merge([row(fetched=now)], region="EU") == 1
        assert store.save()

        switched = PreloadStore(path, preferred_region="US")
        region, rows = switched.snapshot()
        assert region == "US"
        assert rows == []


def test_backup_recovery_and_atomic_abort():
    now = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "preload.json"
        store = PreloadStore(path)
        store.merge([row(fetched=now)], region="EU")
        assert store.save()
        original = path.read_text(encoding="utf-8")
        assert json.loads(original)["version"] == DATASET_VERSION

        path.write_text("{corrupt", encoding="utf-8")
        recovered = PreloadStore(path)
        assert len(recovered.snapshot()[1]) == 1

        path.write_text(original, encoding="utf-8")
        store.merge([row(name="Bob-Draenor", fetched=now)], region="EU")
        real_replace = Path.replace

        def fail_primary_replace(self, target):
            if self.name == "preload.tmp":
                raise OSError("simulated atomic replace failure")
            return real_replace(self, target)

        with patch.object(Path, "replace", fail_primary_replace):
            assert not store.save()
        assert path.read_text(encoding="utf-8") == original


if __name__ == "__main__":
    test_roundtrip_and_indexes()
    test_fail_closed_records_and_cross_realm()
    test_multi_spec_unit_index_fails_closed()
    test_thirty_plus_records_and_region_reset()
    test_region_configuration_and_preferred_store()
    test_backup_recovery_and_atomic_abort()
    print("KeystoneLens preload database contract passed.")
