#!/usr/bin/env python3
"""Controlled-runtime checks for quota-bounded preload discovery."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import time
import types

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "companion" / "source" / "app"
sys.path.insert(0, str(APP_ROOT))

requests_stub = types.ModuleType("requests")
requests_stub.RequestException = RuntimeError
requests_stub.Session = object
sys.modules.setdefault("requests", requests_stub)

from keystonelens_companion.models import WCLBracket, WCLResult  # noqa: E402
from keystonelens_companion.preload_refresh import PreloadRefresher  # noqa: E402
from keystonelens_companion.wcl import WCLClient  # noqa: E402


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
        assert "DPS" in metrics
        assert "HPS" in metrics  # fourth sorted spec is Holy Paladin (65)
        assert all(row["season"] == "midnight-s2" for row in sync.rows)


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
    test_quota_exhaustion_and_offline_are_safe()
    print("KeystoneLens preload refresh contract passed.")
