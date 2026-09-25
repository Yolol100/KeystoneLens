from __future__ import annotations

import json
import math
from pathlib import Path
import threading
import time
from typing import Iterable

from .config import local_app_dir
from .metrics import safe_percentile
from .registries import ACTIVE_SEASON_KEY, canonical_dungeon_name, season_for_dungeon

DATASET_VERSION = 4
MAX_DATASET_AGE_SECONDS = 7 * 24 * 60 * 60
MAX_RECORDS = 25000
STORE_PATH = local_app_dir() / "wcl-preload-v4.json"
BACKUP_PATH = local_app_dir() / "wcl-preload-v4.bak.json"

_REGION_IDS = {"US": 1, "KR": 2, "EU": 3, "TW": 4, "CN": 5}


def dungeon_key(name: str) -> str:
    canonical = canonical_dungeon_name(name)
    return "".join(ch for ch in canonical.casefold() if ch.isalnum())


def split_full_name(value: str) -> tuple[str, str]:
    text = str(value or "").strip()
    if "-" not in text:
        return text, ""
    name, realm = text.rsplit("-", 1)
    return name.strip(), realm.strip()


def normalize_full_name(value: str) -> str:
    name, realm = split_full_name(value)
    if not name or not realm:
        return ""
    return f"{name}-{''.join(realm.split())}"


def record_key(full_name: str, spec_id: int, dungeon_name: str) -> str:
    full_name = normalize_full_name(full_name)
    dkey = dungeon_key(dungeon_name)
    try:
        spec_id = int(spec_id)
    except (TypeError, ValueError, OverflowError):
        return ""
    if not full_name or spec_id <= 0 or not dkey:
        return ""
    return f"{full_name.casefold()}|{spec_id}|{dkey}"


def _valid_metric(value: object) -> str:
    metric = str(value or "").upper()
    return metric if metric in {"DPS", "HPS"} else ""


def _clean_record(value: object, *, now: float | None = None) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    now = time.time() if now is None else float(now)
    full_name = normalize_full_name(str(value.get("full_name") or ""))
    dungeon_name = canonical_dungeon_name(str(value.get("dungeon") or ""))
    season = str(value.get("season") or "")
    metric = _valid_metric(value.get("metric"))
    try:
        spec_id = int(value.get("spec_id") or 0)
        percentile = float(value.get("percentile"))
        fetched_at = float(value.get("fetched_at") or 0)
    except (TypeError, ValueError, OverflowError):
        return None
    if (
        not full_name
        or not dungeon_name
        or season != ACTIVE_SEASON_KEY
        or not metric
        or spec_id <= 0
        or not math.isfinite(percentile)
        or percentile < 0
        or percentile > 100
        or not math.isfinite(fetched_at)
        or fetched_at <= 0
        or now - fetched_at > MAX_DATASET_AGE_SECONDS
        or fetched_at - now > 300
    ):
        return None
    if season_for_dungeon(dungeon_name) is None or season_for_dungeon(dungeon_name).key != ACTIVE_SEASON_KEY:
        return None
    return {
        "full_name": full_name,
        "spec_id": spec_id,
        "dungeon": dungeon_name,
        "season": season,
        "metric": metric,
        "percentile": percentile,
        "fetched_at": fetched_at,
    }


class PreloadStore:
    def __init__(self, path: Path | None = None):
        self.path = path or STORE_PATH
        self.backup_path = BACKUP_PATH if path is None else path.with_suffix(".bak.json")
        self._lock = threading.RLock()
        self.region = "EU"
        self.records: dict[str, dict[str, object]] = {}
        self.last_error = ""
        self._load()

    def _read(self, path: Path) -> tuple[str, dict[str, dict[str, object]]] | None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict) or raw.get("version") != DATASET_VERSION:
            return None
        region = str(raw.get("region") or "EU").upper()
        if region not in _REGION_IDS:
            return None
        rows = raw.get("records")
        if not isinstance(rows, dict):
            return None
        now = time.time()
        clean: dict[str, dict[str, object]] = {}
        for value in rows.values():
            record = _clean_record(value, now=now)
            if record is None:
                continue
            key = record_key(
                str(record["full_name"]),
                int(record["spec_id"]),
                str(record["dungeon"]),
            )
            if key:
                clean[key] = record
        return region, clean

    def _load(self) -> None:
        with self._lock:
            loaded = self._read(self.path)
            if loaded is None:
                loaded = self._read(self.backup_path)
            if loaded is not None:
                self.region, self.records = loaded

    def _prune_locked(self) -> None:
        now = time.time()
        clean: dict[str, dict[str, object]] = {}
        for value in self.records.values():
            record = _clean_record(value, now=now)
            if record is None:
                continue
            key = record_key(str(record["full_name"]), int(record["spec_id"]), str(record["dungeon"]))
            if key:
                clean[key] = record
        if len(clean) > MAX_RECORDS:
            newest = sorted(
                clean.items(),
                key=lambda item: float(item[1]["fetched_at"]),
                reverse=True,
            )[:MAX_RECORDS]
            clean = dict(newest)
        self.records = clean

    def merge(self, rows: Iterable[dict[str, object]], *, region: str | None = None) -> int:
        changed = 0
        now = time.time()
        with self._lock:
            if region:
                normalized_region = str(region).upper()
                if normalized_region in _REGION_IDS and normalized_region != self.region:
                    self.region = normalized_region
                    self.records = {}
                    changed += 1
            for raw in rows:
                record = _clean_record(raw, now=now)
                if record is None:
                    continue
                key = record_key(str(record["full_name"]), int(record["spec_id"]), str(record["dungeon"]))
                if not key:
                    continue
                previous = self.records.get(key)
                if previous is None or float(record["fetched_at"]) >= float(previous.get("fetched_at", 0)):
                    if previous != record:
                        self.records[key] = record
                        changed += 1
            self._prune_locked()
        return changed

    def save(self) -> bool:
        with self._lock:
            self._prune_locked()
            payload = {
                "version": DATASET_VERSION,
                "region": self.region,
                "season": ACTIVE_SEASON_KEY,
                "saved_at": int(time.time()),
                "records": self.records,
            }
            try:
                text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(text, encoding="utf-8")
                tmp.replace(self.path)
                backup_tmp = self.backup_path.with_suffix(".tmp")
                backup_tmp.write_text(text, encoding="utf-8")
                backup_tmp.replace(self.backup_path)
                self.last_error = ""
                return True
            except (OSError, ValueError) as exc:
                self.last_error = str(exc)
                return False

    def snapshot(self) -> tuple[str, list[dict[str, object]]]:
        with self._lock:
            self._prune_locked()
            return self.region, list(self.records.values())


def render_lua_dataset(region: str, records: Iterable[dict[str, object]], *, now: float | None = None) -> str:
    generated = int(time.time() if now is None else now)
    region = str(region or "EU").upper()
    region_id = _REGION_IDS.get(region, 0)
    entries: list[str] = []
    unit_candidates: dict[str, list[tuple[int, str, float, int]]] = {}
    for record in records:
        clean = _clean_record(record, now=float(generated))
        if clean is None:
            continue
        full_name = str(clean["full_name"])
        spec_id = int(clean["spec_id"])
        dkey = dungeon_key(str(clean["dungeon"]))
        metric = "H" if clean["metric"] == "HPS" else "D"
        percentile = safe_percentile(clean["percentile"])
        fetched_at = int(float(clean["fetched_at"]))
        if percentile is None:
            continue
        keys = [full_name, full_name.lower()]
        seen: set[str] = set()
        for name_key in keys:
            flat = f"{name_key}|{spec_id}|{dkey}"
            if flat in seen:
                continue
            seen.add(flat)
            escaped = flat.replace("\\", "\\\\").replace('"', '\\"')
            entries.append(f'    ["{escaped}"]={{"{metric}",{percentile:.2f},{fetched_at}}},')
        unit_base = f"{full_name.casefold()}|{dkey}"
        unit_candidates.setdefault(unit_base, []).append((spec_id, metric, float(percentile), fetched_at))
    unit_entries: list[str] = []
    for flat, values in unit_candidates.items():
        unique_specs = {value[0] for value in values}
        if len(unique_specs) != 1:
            continue
        _spec_id, metric, percentile, fetched_at = max(values, key=lambda value: value[3])
        escaped = flat.replace("\\", "\\\\").replace('"', '\\"')
        unit_entries.append(f'    ["{escaped}"]={{"{metric}",{percentile:.2f},{fetched_at}}},')
    body = "\n".join(entries)
    unit_body = "\n".join(unit_entries)
    return (
        "-- Generated by KeystoneLens Companion. Public Warcraft Logs Mythic+ preload data.\n"
        "_G.KeystoneLensTooltipCacheV3 = nil\n"
        "_G.KeystoneLensPreloadV4 = {\n"
        f"  version = {DATASET_VERSION},\n"
        f"  generatedAt = {generated},\n"
        f"  maxAge = {MAX_DATASET_AGE_SECONDS},\n"
        f"  region = {region_id},\n"
        f'  season = "{ACTIVE_SEASON_KEY}",\n'
        "  entries = {\n"
        f"{body}\n"
        "  },\n"
        "  unitEntries = {\n"
        f"{unit_body}\n"
        "  },\n"
        "}\n"
    )
