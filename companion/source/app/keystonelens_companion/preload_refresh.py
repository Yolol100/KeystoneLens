from __future__ import annotations

import json
from pathlib import Path
import time

from .addon_sync import TooltipCacheSync
from .config import local_app_dir
from .constants import HEALER_SPECS, SPEC_NAMES
from .metrics import safe_percentile
from .preload import MAX_RECORDS
from .registries import ACTIVE_SEASON_KEY, SEASON_REGISTRY
from .util import realm_slug
from .wcl import WCLClient

CURSOR_PATH = local_app_dir() / "wcl-preload-cursor-v1.json"
MAX_SLICES_PER_RUN = 4
SEEDS_PER_SLICE = 20
QUOTA_STOP_FRACTION = 0.80


class PreloadRefresher:
    """Grow the local preload set in small, quota-bounded increments."""

    def __init__(self, client: WCLClient, sync: TooltipCacheSync, cursor_path: Path | None = None):
        self.client = client
        self.sync = sync
        self.cursor_path = cursor_path or CURSOR_PATH

    def _slices(self) -> list[tuple[str, int]]:
        season = SEASON_REGISTRY[ACTIVE_SEASON_KEY]
        specs = sorted(SPEC_NAMES)
        return [(dungeon, spec_id) for dungeon in season.dungeons for spec_id in specs]

    def _load_cursor(self) -> int:
        try:
            raw = json.loads(self.cursor_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and int(raw.get("version", 0)) == 1:
                return max(0, int(raw.get("index", 0)))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return 0

    def _save_cursor(self, index: int) -> None:
        payload = {"version": 1, "index": max(0, int(index)), "saved_at": int(time.time())}
        try:
            self.cursor_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cursor_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            tmp.replace(self.cursor_path)
        except OSError:
            pass

    @staticmethod
    def _record_from_result(result, spec_id: int, dungeon: str) -> dict[str, object] | None:
        if result is None or result.error or result.not_found:
            return None
        metric_key = "hps" if spec_id in HEALER_SPECS else "dps"
        bracket = result.metric_brackets.get(metric_key)
        if bracket is None:
            return None
        percentile = bracket.average_percentile if bracket.run_count >= 2 else bracket.best_percentile
        percentile = safe_percentile(percentile)
        if percentile is None:
            return None
        metric = "HPS" if metric_key == "hps" else "DPS"
        return {
            "full_name": f"{result.name}-{''.join(str(result.realm).split())}",
            "spec_id": int(spec_id),
            "dungeon": dungeon,
            "season": ACTIVE_SEASON_KEY,
            "metric": metric,
            "percentile": percentile,
            "fetched_at": float(result.fetched_at or time.time()),
        }

    def run_once(self) -> dict[str, int | float | str]:
        slices = self._slices()
        if not slices:
            return {"records": self.sync.record_count, "added": 0, "seeds": 0, "slices": 0}

        region = self.sync.region
        index = self._load_cursor() % len(slices)
        records: list[dict[str, object]] = []
        seed_count = 0
        slices_done = 0

        for _ in range(MAX_SLICES_PER_RUN):
            if self.client.quota_fraction() >= QUOTA_STOP_FRACTION:
                break
            dungeon, spec_id = slices[index]
            seeds = self.client.discover_ranked_characters(
                region, dungeon, spec_id, page=1, limit=SEEDS_PER_SLICE
            )
            seed_count += len(seeds)
            slices_done += 1
            index = (index + 1) % len(slices)

            jobs = [
                (name, realm_slug(realm), realm, region, spec_id, dungeon, 0)
                for name, realm in seeds
                if name and realm and realm_slug(realm)
            ]
            for offset in range(0, len(jobs), 10):
                if self.client.quota_fraction() >= QUOTA_STOP_FRACTION:
                    break
                batch = jobs[offset:offset + 10]
                results = self.client.fetch_batch_current_dungeon(batch)
                for result in results:
                    record = self._record_from_result(result, spec_id, dungeon)
                    if record is not None:
                        records.append(record)

        self._save_cursor(index)
        added = self.sync.merge_external(records, region=region) if records else 0
        if added:
            self.sync.publish()
        return {
            "records": min(self.sync.record_count, MAX_RECORDS),
            "added": int(added),
            "seeds": int(seed_count),
            "slices": int(slices_done),
            "quota": round(self.client.quota_fraction(), 4),
            "region": region,
        }
