#!/usr/bin/env python3
"""Controlled-runtime checks for quota-bounded preload discovery."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import time
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "companion" / "source" / "app"
sys.path.insert(0, str(APP_ROOT))

requests_stub = types.ModuleType("requests")
requests_stub.RequestException = RuntimeError
requests_stub.Session = object
sys.modules.setdefault("requests", requests_stub)

from keystonelens_companion.models import WCLBracket, WCLResult  # noqa: E402
from keystonelens_companion.preload_refresh import PreloadRefresher  # noqa: E402
from keystonelens_companion.wcl import WCLCache, WCLClient  # noqa: E402


class FakeSync:
    def __init__(self):
        self.region = "EU"
        self.rows = []
        self.publish_count = 0

    @property
    def record_count(self):
        return len(self.rows)

    def merge_external(self, rows, *, region=None):
        assert region == self.region
        self.rows.extend(rows)
        return len(rows)

    def publish(self):
        self.publish_count += 1
        return True


class FakeClient:
    def __init__(self, *, quota=0.0, offline=False):
        self.quota = quota
        self.offline = offline
        self.discovery_calls = []
        self.batch_calls = []

    def quota_fraction(self):
        return self.quota

    def discover_ranked_characters(self, region, dungeon, spec_id, *, page=1, limit=20):
        self.discovery_calls.append((region, dungeon, spec_id, page, limit))
        if self.offline:
            return []
        return [("Alice", "Draenor"), ("Bob", "Kazzak")]

    def fetch_batch_current_dungeon(self, jobs):
        self.batch_calls.append(list(jobs))
        results = []
        for name, _slug, realm, _region, spec_id, dungeon, target in jobs:
            metric = "hps" if spec_id == 65 else "dps"
            bracket = WCLBracket(
                key_level=0,
                best_percentile=95.0,
                median_percentile=90.0,
                run_count=2,
                average_percentile=92.5,
            )
            results.append(WCLResult(
                name=name,
                realm=realm,
                dungeon_name=dungeon,
                spec_id=spec_id,
                bracket=None,
                fetched_at=time.time(),
                target_key=target,
                metric_brackets={metric: bracket},
            ))
        return results


def test_provider_json_parser_is_fail_closed():
    rows = WCLClient._ranking_rows({"rankings": [
        {"name": "Alice", "serverName": "Draenor"},
        "bad",
    ]})
    assert len(rows) == 1
    assert WCLClient._ranking_identity(rows[0]) == ("Alice", "Draenor")
    assert WCLClient._ranking_identity({"character": {
        "name": "Bob", "server": {"name": "Kazzak"}
    }}) == ("Bob", "Kazzak")
    assert WCLClient._ranking_identity({"name": "NoRealm"}) is None
    assert WCLClient._ranking_rows({"unknown": []}) == []


def test_incremental_refresh_and_role_metric():
    with tempfile.TemporaryDirectory() as tmp:
        sync = FakeSync()
        client = FakeClient()
        refresher = PreloadRefresher(client, sync, Path(tmp) / "cursor.json")
        summary = refresher.run_once()

        assert summary["slices"] == 4
        assert summary["seeds"] == 8
        assert summary["added"] == 8
        assert sync.publish_count == 1
        assert len(client.discovery_calls) == 4
        assert all(len(batch) <= 10 for batch in client.batch_calls)
        metrics = {row["metric"] for row in sync.rows}
        assert metrics == {"DPS"}
        assert all(row["season"] == "midnight-s2" for row in sync.rows)

        healer_bracket = WCLBracket(
            key_level=0,
            best_percentile=94.0,
            median_percentile=91.0,
            run_count=2,
            average_percentile=92.0,
        )
        healer = WCLResult(
            name="Healer",
            realm="Draenor",
            dungeon_name="Altar of Fangs",
            spec_id=65,
            bracket=None,
            fetched_at=time.time(),
            metric_brackets={"hps": healer_bracket},
        )
        healer_record = PreloadRefresher._record_from_result(
            healer, 65, "Altar of Fangs"
        )
        assert healer_record is not None
        assert healer_record["metric"] == "HPS"


def test_discovery_cursor_advances_to_next_ranking_page():
    with tempfile.TemporaryDirectory() as tmp:
        sync = FakeSync()
        client = FakeClient()
        cursor = Path(tmp) / "cursor.json"
        refresher = PreloadRefresher(client, sync, cursor)
        slices = refresher._slices()
        cursor.write_text(json.dumps({
            "version": 2,
            "index": len(slices) - 1,
            "page": 1,
        }), encoding="utf-8")

        refresher.run_once()
        pages = [call[3] for call in client.discovery_calls]
        assert pages[0] == 1
        assert pages[1:] == [2, 2, 2]

        saved = json.loads(cursor.read_text(encoding="utf-8"))
        assert saved["version"] == 2
        assert saved["page"] == 2


def test_wcl_quota_snapshot_expires_after_provider_reset():
    client = WCLClient.__new__(WCLClient)
    client.last_quota = (80.0, 100.0, 60.0)
    client._last_quota_observed_at = 100.0

    with patch("keystonelens_companion.wcl.time.monotonic", return_value=130.0):
        assert client.quota_fraction() == 0.8

    with patch("keystonelens_companion.wcl.time.monotonic", return_value=161.0):
        assert client.quota_fraction() == 0.0
        assert client.last_quota is None


def test_live_cache_freshness_miss_keeps_longer_cached_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        cache = WCLCache(Path(tmp) / "wcl.json", ttl=12 * 60 * 60)
        bracket = WCLBracket(
            key_level=0,
            best_percentile=91.0,
            median_percentile=90.0,
            run_count=2,
            average_percentile=90.5,
        )
        cached = WCLResult(
            name="Alice",
            realm="Draenor",
            dungeon_name="Altar of Fangs",
            spec_id=62,
            bracket=None,
            fetched_at=time.time() - (2 * 60 * 60),
            metric_brackets={"dps": bracket},
        )
        cache.put("EU", cached)

        assert cache.get(
            "EU", "Draenor", "Alice", 62, "Altar of Fangs", 0,
            max_age_seconds=60 * 60,
        ) is None
        assert cache.get(
            "EU", "Draenor", "Alice", 62, "Altar of Fangs", 0
        ) is not None


def test_quota_exhaustion_and_offline_are_safe():
    with tempfile.TemporaryDirectory() as tmp:
        sync = FakeSync()
        blocked = FakeClient(quota=0.81)
        result = PreloadRefresher(blocked, sync, Path(tmp) / "blocked.json").run_once()
        assert result["slices"] == 0
        assert result["added"] == 0
        assert not blocked.discovery_calls

        offline = FakeClient(offline=True)
        result = PreloadRefresher(offline, sync, Path(tmp) / "offline.json").run_once()
        assert result["slices"] == 4
        assert result["added"] == 0
        assert sync.publish_count == 0


if __name__ == "__main__":
    test_provider_json_parser_is_fail_closed()
    test_incremental_refresh_and_role_metric()
    test_discovery_cursor_advances_to_next_ranking_page()
    test_wcl_quota_snapshot_expires_after_provider_reset()
    test_live_cache_freshness_miss_keeps_longer_cached_evidence()
    test_quota_exhaustion_and_offline_are_safe()
    print("KeystoneLens preload refresh contract passed.")
