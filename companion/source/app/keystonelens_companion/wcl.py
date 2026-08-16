from __future__ import annotations
from dataclasses import asdict
import json
import math
import statistics
import threading
import time
from pathlib import Path
from typing import Any

import requests

from .config import cache_path
from .constants import DUNGEONS, HEALER_SPECS, SPEC_NAMES
from .models import WCLBracket, WCLResult
from .registries import canonical_dungeon_name, season_for_dungeon, wcl_zone_for_dungeon

OAUTH_URL = "https://www.warcraftlogs.com/oauth/token"
API_URL = "https://www.warcraftlogs.com/api/v2/client"
NEGATIVE_CACHE_TTL_SECONDS = 30 * 60
MAX_CACHE_ENTRIES = 2000
MAX_CACHE_FILE_BYTES = 8 * 1024 * 1024
MAX_CACHE_FUTURE_SKEW_SECONDS = 5 * 60
MAX_WCL_RUN_COUNT = 100_000
MAX_WCL_KEY_LEVEL = 255
MAX_WCL_METRIC_BRACKETS = 16
MAX_REALM_CATALOG_FILE_BYTES = 8 * 1024 * 1024
REALM_CATALOG_TTL_SECONDS = 30 * 24 * 60 * 60
REALM_CATALOG_RETRY_SECONDS = 10 * 60
REALM_CATALOG_VERSION = 1
WCL_CONTEXT_VERSION = "midnight-season-aware-v12:role-aware-ranking-average:parses2w"
WCL_ENCOUNTER_CATALOG_TTL_SECONDS = 24 * 60 * 60
WCL_ENCOUNTER_CATALOG_RETRY_SECONDS = 10 * 60


class WCLError(RuntimeError):
    pass


def _cached_bracket(value: object) -> WCLBracket | None:
    """Validate untrusted on-disk WCL evidence before it reaches scoring."""
    if not isinstance(value, dict):
        return None
    try:
        key_level = int(value["key_level"])
        best = float(value["best_percentile"])
        median = float(value["median_percentile"])
        run_count = int(value["run_count"])
        average = float(value.get("average_percentile", value.get("median_percentile", 0.0)))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not (0 <= key_level <= MAX_WCL_KEY_LEVEL):
        return None
    if not (1 <= run_count <= MAX_WCL_RUN_COUNT):
        return None
    if not all(math.isfinite(v) and 0.0 <= v <= 100.0 for v in (best, median, average)):
        return None
    return WCLBracket(
        key_level=key_level,
        best_percentile=best,
        median_percentile=median,
        run_count=run_count,
        average_percentile=average,
    )


class WCLCache:
    def __init__(self, path: Path | None = None, ttl: int = 43200):
        self.path = path or cache_path()
        self.ttl = ttl
        self._lock = threading.Lock()
        self._save_lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists() and self.path.stat().st_size > MAX_CACHE_FILE_BYTES:
                self._data = {}
                return
            raw = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
            if isinstance(raw, dict):
                self._data = {str(k): v for k, v in raw.items() if isinstance(v, dict)}
        except (OSError, json.JSONDecodeError):
            self._data = {}
        with self._lock:
            changed = self._prune_locked(time.time())
        if changed:
            self._save()

    def _key(self, region: str, realm: str, name: str, spec_id: int, dungeon: str, target_key: int) -> str:
        dungeon = canonical_dungeon_name(dungeon)
        season = season_for_dungeon(dungeon)
        season_key = season.key if season else "unknown-season"
        # encounterRankings(byBracket:true) returns the character's available
        # parses for the whole current dungeon; _reduce_ranks intentionally does
        # not filter by the queued key. Reusing that evidence across a +17 ->
        # +18 re-queue avoids a needless WCL round-trip.
        del target_key
        return "|".join([
            WCL_CONTEXT_VERSION, season_key, region.casefold(), realm.casefold(),
            name.casefold(), str(spec_id), dungeon.casefold(),
        ])

    def _row_ttl(self, row: dict[str, Any]) -> int:
        if bool(row.get("not_found")):
            return min(max(1, int(self.ttl)), NEGATIVE_CACHE_TTL_SECONDS)
        return max(1, int(self.ttl))

    def _prune_locked(self, now: float) -> bool:
        before = len(self._data)
        keep: dict[str, dict[str, Any]] = {}
        for key, row in self._data.items():
            try:
                fetched = float(row.get("fetched_at", 0) or 0)
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(fetched) or fetched <= 0:
                continue
            age = now - fetched
            if not (-MAX_CACHE_FUTURE_SKEW_SECONDS <= age <= self._row_ttl(row)):
                continue
            if row.get("error"):
                continue
            raw_bracket = row.get("bracket")
            raw_metrics = row.get("metric_brackets")
            if raw_bracket is not None and _cached_bracket(raw_bracket) is None:
                continue
            if raw_metrics is None:
                raw_metrics = {}
            if not isinstance(raw_metrics, dict) or len(raw_metrics) > MAX_WCL_METRIC_BRACKETS:
                continue
            metrics_valid = True
            for metric_name, raw_metric_bracket in raw_metrics.items():
                if (
                    not isinstance(metric_name, str)
                    or not metric_name
                    or len(metric_name) > 64
                    or _cached_bracket(raw_metric_bracket) is None
                ):
                    metrics_valid = False
                    break
            if not metrics_valid:
                continue
            is_not_found = bool(row.get("not_found"))
            if is_not_found and (raw_bracket is not None or raw_metrics):
                continue
            if not is_not_found and raw_bracket is None and not raw_metrics:
                continue
            keep[key] = row
        if len(keep) > MAX_CACHE_ENTRIES:
            newest = sorted(
                keep.items(),
                key=lambda item: float(item[1].get("fetched_at", 0) or 0),
                reverse=True,
            )[:MAX_CACHE_ENTRIES]
            keep = dict(newest)
        self._data = keep
        return len(self._data) != before

    def get(self, region: str, realm: str, name: str, spec_id: int, dungeon: str, target_key: int) -> WCLResult | None:
        key = self._key(region, realm, name, spec_id, dungeon, target_key)
        now = time.time()
        should_save = False
        result: WCLResult | None = None
        with self._lock:
            row = self._data.get(key)
            if not isinstance(row, dict):
                return None
            try:
                fetched = float(row.get("fetched_at", 0) or 0)
            except (TypeError, ValueError, OverflowError):
                self._data.pop(key, None)
                should_save = True
                row = None

            if row is not None:
                age = now - fetched
                if (
                    not math.isfinite(fetched)
                    or fetched <= 0
                    or age < -MAX_CACHE_FUTURE_SKEW_SECONDS
                    or age > self._row_ttl(row)
                ):
                    self._data.pop(key, None)
                    should_save = True
                    row = None

            if row is not None:
                raw_bracket = row.get("bracket")
                bracket = _cached_bracket(raw_bracket)
                invalid_evidence = raw_bracket is not None and bracket is None
                metric_brackets: dict[str, WCLBracket] = {}
                raw_metrics = row.get("metric_brackets")
                if isinstance(raw_metrics, dict):
                    if len(raw_metrics) > MAX_WCL_METRIC_BRACKETS:
                        invalid_evidence = True
                    for metric_name, raw_metric_bracket in list(raw_metrics.items())[:MAX_WCL_METRIC_BRACKETS]:
                        if not isinstance(metric_name, str) or not metric_name or len(metric_name) > 64:
                            invalid_evidence = True
                            continue
                        parsed = _cached_bracket(raw_metric_bracket)
                        if parsed is None:
                            invalid_evidence = True
                            continue
                        metric_brackets[metric_name] = parsed
                elif raw_metrics not in (None, {}):
                    invalid_evidence = True
                if invalid_evidence:
                    self._data.pop(key, None)
                    should_save = True
                else:
                    try:
                        stored_spec = int(row.get("spec_id") or spec_id)
                    except (TypeError, ValueError, OverflowError):
                        stored_spec = spec_id
                    result = WCLResult(
                        name=str(row.get("name") or name),
                        realm=str(row.get("realm") or realm),
                        dungeon_name=str(row.get("dungeon_name") or dungeon),
                        spec_id=stored_spec,
                        bracket=bracket,
                        fetched_at=fetched,
                        # Target key is request context, not part of the cached WCL
                        # ranking evidence. Restamp it so engine context checks remain
                        # exact after a re-queue at another key level.
                        target_key=int(target_key or 0),
                        not_found=bool(row.get("not_found")),
                        error=str(row.get("error") or ""),
                        metric_brackets=metric_brackets,
                    )
        if should_save:
            self._save()
        return result

    def put(self, region: str, result: WCLResult) -> None:
        self.put_many(((region, result),))

    def put_many(self, items) -> None:
        """Persist a completed applicant batch with one atomic cache rewrite."""
        pending: list[tuple[str, WCLResult]] = []
        for region, result in items:
            if not isinstance(result, WCLResult):
                continue
            # Only successful evidence and true character-not-found are
            # persisted. Transient/API errors must remain retryable.
            if result.error or (
                result.bracket is None
                and not result.metric_brackets
                and not result.not_found
            ):
                continue
            pending.append((str(region), result))
        if not pending:
            return

        with self._lock:
            for region, result in pending:
                key = self._key(
                    region, result.realm, result.name, result.spec_id,
                    result.dungeon_name, result.target_key,
                )
                payload = asdict(result)
                # Quota is transient UI state, not useful persisted evidence.
                payload.pop("quota_spent", None)
                payload.pop("quota_limit", None)
                payload.pop("quota_reset", None)
                self._data[key] = payload
            self._prune_locked(time.time())
        self._save()

    def count(self) -> int:
        with self._lock:
            changed = self._prune_locked(time.time())
            count = len(self._data)
        if changed:
            self._save()
        return count

    def _save(self) -> None:
        try:
            # Serialise writers so an older snapshot cannot replace a newer one.
            # Snapshotting briefly holds _lock; JSON encoding and filesystem I/O do not.
            with self._save_lock:
                with self._lock:
                    snapshot = dict(self._data)
                payload = json.dumps(
                    snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                )
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(payload, encoding="utf-8")
                tmp.replace(self.path)
        except (OSError, ValueError):
            pass


class WCLClient:
    def __init__(self, client_id: str, client_secret: str, cache: WCLCache):
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.cache = cache
        self._token = ""
        self._token_expires = 0.0
        self._auth_lock = threading.Lock()
        self._http_lock = threading.Lock()
        self._http = requests.Session()
        self._closed = threading.Event()
        self._blocked_until = 0.0
        self.last_quota: tuple[float, float, float] | None = None
        self._realm_lock = threading.Lock()
        self._realm_catalog_path = self.cache.path.with_name("wcl-realms.json")
        self._realm_catalog: dict[str, object] | None = self._load_realm_catalog()
        self._realm_catalog_last_attempt = 0.0
        self._encounter_lock = threading.Lock()
        self._encounter_catalog: dict[int, tuple[float, dict[str, int]]] = {}

    def close(self) -> None:
        """Release HTTP resources and make future network/cache work a no-op."""
        self._closed.set()
        self._token = ""
        self._token_expires = 0.0
        self.client_secret = ""
        self._http.close()

    def _get_token(self) -> str:
        if self._closed.is_set():
            raise WCLError("WCL client closed")
        if self._token and self._token_expires - 60 > time.time():
            return self._token
        with self._auth_lock:
            if self._closed.is_set():
                raise WCLError("WCL client closed")
            if self._token and self._token_expires - 60 > time.time():
                return self._token
            try:
                with self._http_lock:
                    response = self._http.post(
                        OAUTH_URL,
                        data={"grant_type": "client_credentials"},
                        auth=(self.client_id, self.client_secret),
                        timeout=12,
                    )
            except requests.RequestException as exc:
                raise WCLError(f"WCL OAuth network error: {exc}") from exc
            if self._closed.is_set():
                raise WCLError("WCL client closed")
            if response.status_code != 200:
                raise WCLError(f"WCL OAuth HTTP {response.status_code}")
            try:
                data = response.json()
            except ValueError as exc:
                raise WCLError("WCL OAuth returned invalid JSON") from exc
            token = data.get("access_token") if isinstance(data, dict) else None
            if not isinstance(token, str) or not token:
                raise WCLError("WCL OAuth token missing")
            self._token = token
            try:
                expires_in = int(data.get("expires_in", 86400) or 86400)
            except (TypeError, ValueError, OverflowError):
                expires_in = 86400
            self._token_expires = time.time() + max(60, expires_in)
            return token

    def test(self) -> None:
        self._get_token()

    @staticmethod
    def _realm_key(value: object) -> str:
        if not isinstance(value, str):
            return ""
        return "".join(char for char in value.casefold() if char.isalnum())

    def _load_realm_catalog(self) -> dict[str, object] | None:
        try:
            if not self._realm_catalog_path.exists():
                return None
            if self._realm_catalog_path.stat().st_size > MAX_REALM_CATALOG_FILE_BYTES:
                return None
            raw = json.loads(self._realm_catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict) or raw.get("version") != REALM_CATALOG_VERSION:
            return None
        try:
            fetched_at = float(raw.get("fetched_at", 0) or 0)
        except (TypeError, ValueError, OverflowError):
            return None
        age = time.time() - fetched_at
        regions = raw.get("regions")
        if not math.isfinite(fetched_at) or fetched_at <= 0 or age < -300 or age > REALM_CATALOG_TTL_SECONDS:
            return None
        if not isinstance(regions, dict):
            return None
        clean_regions: dict[str, dict[str, str]] = {}
        for region, mapping in regions.items():
            if not isinstance(region, str) or not isinstance(mapping, dict):
                continue
            clean = {str(k): str(v) for k, v in mapping.items() if isinstance(k, str) and k and isinstance(v, str) and v}
            if clean:
                clean_regions[region.casefold()] = clean
        if not clean_regions:
            return None
        return {"version": REALM_CATALOG_VERSION, "fetched_at": fetched_at, "regions": clean_regions}

    def _save_realm_catalog(self, catalog: dict[str, object]) -> None:
        try:
            self._realm_catalog_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._realm_catalog_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            tmp.replace(self._realm_catalog_path)
        except OSError:
            pass

    @staticmethod
    def _catalog_quota(root: dict[str, object]) -> tuple[float, float, float] | None:
        quota = root.get("rateLimitData")
        if not isinstance(quota, dict):
            return None
        try:
            limit = float(quota.get("limitPerHour"))
            spent = float(quota.get("pointsSpentThisHour"))
            reset = float(quota.get("pointsResetIn"))
        except (TypeError, ValueError, OverflowError):
            return None
        if not (math.isfinite(limit) and limit > 0 and math.isfinite(spent) and math.isfinite(reset)):
            return None
        return spent, limit, reset

    def _apply_quota(self, root: dict[str, object]) -> tuple[float, float, float] | None:
        quota = self._catalog_quota(root)
        if quota is None:
            return None
        spent, limit, reset = quota
        self.last_quota = quota
        if spent / limit >= .96:
            self._blocked_until = max(self._blocked_until, time.monotonic() + max(5.0, reset))
        return quota

    def _refresh_realm_catalog(self) -> dict[str, object] | None:
        query = (
            "query KLRealmCatalog {\n"
            "  rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn }\n"
            "  worldData {\n"
            "    regions {\n"
            "      compactName slug\n"
            "      servers(limit:5000) { data { name normalizedName slug } }\n"
            "    }\n"
            "  }\n"
            "}"
        )
        try:
            response = self._post_graphql({"query": query, "variables": {}})
        except WCLError:
            return None
        if response.status_code == 429:
            self._blocked_until = max(self._blocked_until, time.monotonic() + self._retry_after_seconds(response))
            return None
        if response.status_code != 200:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict) or payload.get("errors"):
            return None
        root = payload.get("data")
        if not isinstance(root, dict):
            return None
        quota = self._catalog_quota(root)
        if quota is not None:
            self.last_quota = quota
            spent, limit, reset = quota
            if spent / limit >= .96:
                self._blocked_until = max(self._blocked_until, time.monotonic() + max(5.0, reset))
        world = root.get("worldData")
        region_rows = world.get("regions") if isinstance(world, dict) else None
        if not isinstance(region_rows, list):
            return None
        regions: dict[str, dict[str, str]] = {}
        for region_row in region_rows:
            if not isinstance(region_row, dict):
                continue
            region_names = [region_row.get("compactName"), region_row.get("slug")]
            region_keys = {str(value).casefold() for value in region_names if isinstance(value, str) and value.strip()}
            servers = region_row.get("servers")
            server_rows = servers.get("data") if isinstance(servers, dict) else None
            if not region_keys or not isinstance(server_rows, list):
                continue
            mapping: dict[str, str | None] = {}
            for row in server_rows:
                if not isinstance(row, dict):
                    continue
                slug = row.get("slug")
                if not isinstance(slug, str) or not slug.strip():
                    continue
                slug = slug.strip()
                for raw in (row.get("name"), row.get("normalizedName"), slug):
                    key = self._realm_key(raw)
                    if not key:
                        continue
                    previous = mapping.get(key)
                    if previous is None and key in mapping:
                        continue
                    if previous is not None and previous != slug:
                        mapping[key] = None
                    else:
                        mapping[key] = slug
            clean = {key: slug for key, slug in mapping.items() if isinstance(slug, str) and slug}
            if not clean:
                continue
            for region_key in region_keys:
                regions[region_key] = clean
        if not regions:
            return None
        catalog: dict[str, object] = {
            "version": REALM_CATALOG_VERSION,
            "fetched_at": time.time(),
            "regions": regions,
        }
        self._save_realm_catalog(catalog)
        return catalog

    def _ensure_realm_catalog(self) -> dict[str, object] | None:
        if self._realm_catalog is not None:
            return self._realm_catalog
        now = time.monotonic()
        if now < self._blocked_until:
            return None
        with self._realm_lock:
            if self._realm_catalog is not None:
                return self._realm_catalog
            now = time.monotonic()
            if now < self._blocked_until:
                return None
            if self._realm_catalog_last_attempt and now - self._realm_catalog_last_attempt < REALM_CATALOG_RETRY_SECONDS:
                return None
            self._realm_catalog_last_attempt = now
            self._realm_catalog = self._refresh_realm_catalog()
            return self._realm_catalog

    def _official_realm_slug(
        self,
        region: str,
        realm_display: str,
        fallback_slug: str,
    ) -> str:
        """Resolve a realm slug without making the common path pay for a catalog request.

        Blizzard-style slugs are correct for the overwhelming majority of Retail
        realms. The large WCL world/realm catalog is therefore consulted from
        memory first and fetched only as a recovery step after a character lookup
        returned no data. This keeps first-use applicant batches to one network
        round-trip in the normal case while retaining localized-realm recovery.
        """
        catalog = self._realm_catalog
        if not isinstance(catalog, dict):
            return fallback_slug
        regions = catalog.get("regions")
        mapping = regions.get(region.casefold()) if isinstance(regions, dict) else None
        if not isinstance(mapping, dict):
            return fallback_slug
        for value in (realm_display, fallback_slug):
            key = self._realm_key(value)
            slug = mapping.get(key) if key else None
            if isinstance(slug, str) and slug:
                return slug
        return fallback_slug

    def fetch_batch_current_dungeon(self, jobs: list[tuple[str, str, str, str, int, str, int]]) -> list[WCLResult]:
        """Fetch up to 10 applicants, batching jobs that share region and dungeon."""
        if not jobs:
            return []
        if self._closed.is_set():
            return [
                WCLResult(name, realm, dungeon, spec_id, None, time.time(), target_key=target, error="WCL client closed")
                for name, _slug, realm, _region, spec_id, dungeon, target in jobs
            ]
        if len(jobs) > 10:
            raise ValueError("KeystoneLens batch size is capped at 10")
        results: list[WCLResult | None] = [None] * len(jobs)
        misses: list[tuple[int, tuple[str, str, str, str, int, str, int]]] = []
        for index, job in enumerate(jobs):
            name, _slug, realm, region, spec_id, dungeon, target = job
            cached = self.cache.get(region, realm, name, spec_id, dungeon, target)
            if cached is not None:
                results[index] = cached
            else:
                misses.append((index, job))
        if not misses:
            return [result for result in results if result is not None]

        groups: dict[tuple[str, str], list[tuple[int, tuple[str, str, str, str, int, str, int]]]] = {}
        for item in misses:
            job = item[1]
            groups.setdefault((job[3], job[5]), []).append(item)
        for group in groups.values():
            self._fetch_group(group, results)
        finalized = [
            result if result is not None else WCLResult(
                jobs[index][0], jobs[index][2], jobs[index][5], jobs[index][4], None,
                time.time(), target_key=jobs[index][6], error="WCL batch result missing",
            )
            for index, result in enumerate(results)
        ]
        # Persist all fresh misses in a single atomic rewrite. Rewriting the
        # cache once per applicant was measurable disk overhead on larger queues.
        if not self._closed.is_set():
            self.cache.put_many(
                (jobs[index][3], finalized[index])
                for index, _job in misses
            )
        return finalized

    def _post_graphql(self, body: dict[str, object]):
        if self._closed.is_set():
            raise WCLError("WCL client closed")
        token = self._get_token()
        try:
            with self._http_lock:
                response = self._http.post(
                    API_URL,
                    json=body,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=22,
                )
        except requests.RequestException as exc:
            raise WCLError(f"WCL network error: {exc}") from exc
        if self._closed.is_set():
            raise WCLError("WCL client closed")
        if response.status_code == 401:
            # A token can expire or be invalidated between local expiry checks.
            # Refresh once; never loop on bad credentials.
            self._token = ""
            self._token_expires = 0.0
            token = self._get_token()
            try:
                with self._http_lock:
                    response = self._http.post(
                        API_URL,
                        json=body,
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=22,
                    )
            except requests.RequestException as exc:
                raise WCLError(f"WCL network error: {exc}") from exc
            if self._closed.is_set():
                raise WCLError("WCL client closed")
        return response

    @staticmethod
    def _retry_after_seconds(response) -> float:
        value = response.headers.get("Retry-After") if getattr(response, "headers", None) else None
        try:
            seconds = float(value)
        except (TypeError, ValueError, OverflowError):
            return 300.0
        return max(5.0, min(seconds, 3600.0)) if math.isfinite(seconds) else 300.0

    @staticmethod
    def _encounter_key(name: object) -> str:
        if not isinstance(name, str):
            return ""
        return "".join(ch for ch in name.casefold() if ch.isalnum())

    def _fetch_zone_encounters(self, zone_id: int) -> dict[str, int]:
        now = time.time()
        with self._encounter_lock:
            cached = self._encounter_catalog.get(int(zone_id))
            if cached:
                ttl = WCL_ENCOUNTER_CATALOG_TTL_SECONDS if cached[1] else WCL_ENCOUNTER_CATALOG_RETRY_SECONDS
                if now - cached[0] <= ttl:
                    return dict(cached[1])
        def cache_result(mapping: dict[str, int]) -> dict[str, int]:
            with self._encounter_lock:
                self._encounter_catalog[int(zone_id)] = (time.time(), dict(mapping))
            return mapping

        query = (
            "query KLZoneEncounters($zoneID:Int!) {\n"
            "  worldData { zone(id:$zoneID) { id name encounters { id name } } }\n"
            "}"
        )
        try:
            response = self._post_graphql({"query": query, "variables": {"zoneID": int(zone_id)}})
        except WCLError:
            return cache_result({})
        if response.status_code == 429:
            self._blocked_until = time.monotonic() + self._retry_after_seconds(response)
        if response.status_code != 200:
            return cache_result({})
        try:
            payload = response.json()
        except ValueError:
            return cache_result({})
        root = payload.get("data") if isinstance(payload, dict) else None
        world = root.get("worldData") if isinstance(root, dict) else None
        zone = world.get("zone") if isinstance(world, dict) else None
        if not isinstance(zone, dict):
            return cache_result({})
        try:
            zid = int(zone.get("id") or 0)
        except (TypeError, ValueError, OverflowError):
            return cache_result({})
        if zid != int(zone_id):
            return cache_result({})
        mapping: dict[str, int] = {}
        encounters = zone.get("encounters")
        if isinstance(encounters, list):
            for encounter in encounters:
                if not isinstance(encounter, dict):
                    continue
                key = self._encounter_key(encounter.get("name"))
                try:
                    eid = int(encounter.get("id") or 0)
                except (TypeError, ValueError, OverflowError):
                    eid = 0
                if key and eid > 0:
                    mapping[key] = eid
        return cache_result(mapping)

    def _resolve_encounter_id(self, dungeon: str) -> int | None:
        dungeon = canonical_dungeon_name(dungeon)
        known = DUNGEONS.get(dungeon)
        if known:
            return int(known)
        zone_id = wcl_zone_for_dungeon(dungeon)
        if not zone_id:
            return None
        mapping = self._fetch_zone_encounters(zone_id)
        return mapping.get(self._encounter_key(dungeon))

    def _fetch_group(
        self,
        group,
        results: list[WCLResult | None],
        *,
        resolve_realms: bool = False,
    ) -> None:
        if time.monotonic() < self._blocked_until:
            for index, job in group:
                results[index] = WCLResult(
                    job[0], job[2], job[5], job[4], None, time.time(),
                    target_key=job[6], error="WCL rate limit; waiting for reset",
                )
            return
        region = group[0][1][3]
        dungeon = group[0][1][5]
        encounter = self._resolve_encounter_id(dungeon)
        if not encounter:
            for index, job in group:
                results[index] = WCLResult(
                    job[0], job[2], job[5], job[4], None, time.time(),
                    target_key=job[6], error="WCL dungeon is not available in the current zone catalog yet",
                )
            return

        prepared = []
        for index, job in group:
            name, fallback_slug, realm, _region, spec_id, _dungeon, target = job
            spec_name = SPEC_NAMES.get(spec_id, "")
            if not fallback_slug or not spec_name:
                results[index] = WCLResult(
                    name, realm, dungeon, spec_id, None, time.time(),
                    target_key=target, error="Invalid spec/realm",
                )
                continue
            prepared.append((index, job, spec_name))
        if not prepared:
            return

        # Normal realm slugs are already supplied by the Bridge/companion. Do
        # not block every first WCL batch on the very large WCL realm catalog.
        # A second pass with the official catalog is only used for unresolved
        # characters where a localized realm name may genuinely need mapping.
        if resolve_realms:
            self._ensure_realm_catalog()
            if time.monotonic() < self._blocked_until:
                for index, job, _spec_name in prepared:
                    results[index] = WCLResult(
                        job[0], job[2], dungeon, job[4], None, time.time(),
                        target_key=job[6], error="WCL rate limit; waiting for reset",
                    )
                return

        vars_decl = ["$serverRegion:String!"]
        variables: dict[str, object] = {"serverRegion": region}
        fields = []
        valid = []
        for alias_index, (index, job, spec_name) in enumerate(prepared):
            name, fallback_slug, realm, _region, spec_id, _dungeon, target = job
            slug = self._official_realm_slug(region, realm, fallback_slug)
            nvar = f"n{alias_index}"
            svar = f"s{alias_index}"
            alias = f"c{alias_index}"
            vars_decl += [f"${nvar}:String!", f"${svar}:String!"]
            variables[nvar] = name
            variables[svar] = slug
            role_metric = "hps" if spec_id in HEALER_SPECS else "wdps"
            extra_healer = (
                f"      tankhealing: encounterRankings(encounterID:{encounter}, metric:tankhps, byBracket:true, compare:Parses)\n"
                if spec_id in HEALER_SPECS else ""
            )
            fields.append(
                f"    {alias}: character(name:${nvar}, serverSlug:${svar}, serverRegion:$serverRegion) {{\n"
                "      name\n"
                f"      run: encounterRankings(encounterID:{encounter}, metric:playerscore, byBracket:true, compare:Parses)\n"
                f"      speed: encounterRankings(encounterID:{encounter}, metric:playerspeed, byBracket:true, compare:Parses)\n"
                f"      throughput: encounterRankings(encounterID:{encounter}, metric:{role_metric}, byBracket:true, compare:Parses)\n"
                + extra_healer
                + f"      damage: encounterRankings(encounterID:{encounter}, metric:dps, byBracket:true, compare:Parses)\n"
                + f"      bossdamage: encounterRankings(encounterID:{encounter}, metric:bossdps, byBracket:true, compare:Parses)\n"
                + "    }"
            )
            resolved_job = (name, slug, realm, _region, spec_id, _dungeon, target)
            valid.append((alias, index, resolved_job, spec_name, job))
        query = (
            "query KLB(" + ", ".join(vars_decl) + ") {\n"
            "  rateLimitData { limitPerHour pointsSpentThisHour pointsResetIn }\n"
            "  characterData {\n" + "\n".join(fields) + "\n  }\n}"
        )
        body = {"query": query, "variables": variables}
        try:
            response = self._post_graphql(body)
        except WCLError as exc:
            for _alias, index, job, _spec, _source_job in valid:
                results[index] = WCLResult(
                    job[0], job[2], dungeon, job[4], None, time.time(),
                    target_key=job[6], error=str(exc),
                )
            return
        if response.status_code == 429:
            self._blocked_until = time.monotonic() + self._retry_after_seconds(response)
        if response.status_code != 200:
            error = (
                "WCL rate limit" if response.status_code == 429
                else "WCL login invalid" if response.status_code in (401, 403)
                else f"WCL HTTP {response.status_code}"
            )
            for _alias, index, job, _spec, _source_job in valid:
                results[index] = WCLResult(
                    job[0], job[2], dungeon, job[4], None, time.time(),
                    target_key=job[6], error=error,
                )
            return
        try:
            data = response.json()
        except ValueError:
            data = {}
        graphql_errors = data.get("errors") if isinstance(data, dict) else None
        alias_errors: dict[str, list[str]] = {}
        global_errors: list[str] = []
        if isinstance(graphql_errors, list):
            for item in graphql_errors:
                if not isinstance(item, dict):
                    continue
                message = str(item.get("message") or "GraphQL error")[:180]
                path = item.get("path")
                alias = None
                if isinstance(path, list):
                    for part in path:
                        if isinstance(part, str) and part.startswith("c") and part[1:].isdigit():
                            alias = part
                            break
                if alias:
                    alias_errors.setdefault(alias, []).append(message)
                else:
                    global_errors.append(message)

        root = data.get("data") if isinstance(data, dict) else None
        if not isinstance(root, dict):
            # A single bad character/realm or a query-complexity rejection must
            # not turn the whole applicant batch red. Bisect once recursively so
            # healthy applicants can still resolve; a true global/schema error
            # naturally survives down to the single-character request.
            if len(group) > 1:
                midpoint = max(1, len(group) // 2)
                self._fetch_group(group[:midpoint], results)
                self._fetch_group(group[midpoint:], results)
                return
            detail = global_errors[0] if global_errors else (
                next(iter(alias_errors.values()))[0] if alias_errors else "incomplete response"
            )
            error = f"WCL GraphQL error: {detail}"
            for _alias, index, job, _spec, _source_job in valid:
                results[index] = WCLResult(
                    job[0], job[2], dungeon, job[4], None, time.time(),
                    target_key=job[6], error=error,
                )
            return

        spent = limit = reset = None
        quota = self._apply_quota(root)
        if quota is not None:
            spent, limit, reset = quota
        cdata = root.get("characterData")
        if not isinstance(cdata, dict):
            cdata = {}
        # Only unresolved characters may need WCL's canonical realm catalog.
        # Retry those rows once, and only when the catalog actually changes the
        # slug. Healthy characters from the first batch are never queried again.
        retry_indices: set[int] = set()
        if not resolve_realms:
            unresolved = []
            for alias, index, job, spec_name, source_job in valid:
                if cdata.get(alias) is not None or alias_errors.get(alias) or global_errors:
                    continue
                unresolved.append((alias, index, job, spec_name, source_job))
            if unresolved:
                catalog = self._ensure_realm_catalog()
                if isinstance(catalog, dict) and time.monotonic() >= self._blocked_until:
                    retry_group = []
                    for _alias, index, job, _spec_name, source_job in unresolved:
                        mapped = self._official_realm_slug(region, source_job[2], source_job[1])
                        if mapped and mapped != job[1]:
                            retry_group.append((index, source_job))
                            retry_indices.add(index)
                    if retry_group:
                        self._fetch_group(retry_group, results, resolve_realms=True)

        for alias, index, job, spec_name, _source_job in valid:
            if index in retry_indices:
                continue
            name, _slug, realm, _region, spec_id, _dungeon, target = job
            char = cdata.get(alias)
            local_errors = alias_errors.get(alias, [])
            run = None
            ranks: object = []
            if char is None:
                if local_errors or global_errors:
                    detail = (local_errors or global_errors)[0]
                    result = WCLResult(
                        name, realm, dungeon, spec_id, None, time.time(), target_key=target,
                        error=f"WCL GraphQL error: {detail}",
                        quota_spent=spent, quota_limit=limit, quota_reset=reset,
                    )
                else:
                    result = WCLResult(
                        name, realm, dungeon, spec_id, None, time.time(), target_key=target,
                        not_found=True, quota_spent=spent, quota_limit=limit, quota_reset=reset,
                    )
            elif not isinstance(char, dict):
                result = WCLResult(
                    name, realm, dungeon, spec_id, None, time.time(), target_key=target,
                    error="WCL character data invalid",
                )
            else:
                run = char.get("run")
                ranks = run.get("ranks") if isinstance(run, dict) else []
                bracket = _reduce_ranks(ranks, spec_name)
                role_metric = "hps" if spec_id in HEALER_SPECS else "wdps"
                metric_brackets: dict[str, WCLBracket] = {}
                metric_fields = [
                    ("playerspeed", "speed"),
                    (role_metric, "throughput"),
                    ("dps", "damage"),
                    ("bossdps", "bossdamage"),
                ]
                if spec_id in HEALER_SPECS:
                    metric_fields.append(("tankhps", "tankhealing"))
                for metric_name, field_name in metric_fields:
                    raw_metric = char.get(field_name)
                    metric_ranks = raw_metric.get("ranks") if isinstance(raw_metric, dict) else []
                    metric_bracket = _reduce_ranks(metric_ranks, spec_name)
                    if metric_bracket:
                        metric_brackets[metric_name] = metric_bracket

                # GraphQL can return partial data plus an error for one nested
                # ranking field. Keep a valid playerscore instead of poisoning
                # every applicant in the batch. Only surface the alias error if
                # this character produced no usable score at all.
                error = ""
                if bracket is None and not metric_brackets and local_errors:
                    error = f"WCL GraphQL error: {local_errors[0]}"
                elif bracket is None and not metric_brackets and global_errors:
                    error = f"WCL GraphQL error: {global_errors[0]}"
                result = WCLResult(
                    name, realm, dungeon, spec_id, bracket, time.time(), target_key=target,
                    error=error, quota_spent=spent, quota_limit=limit, quota_reset=reset,
                    metric_brackets=metric_brackets,
                )
            results[index] = result


def _spec_norm(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


def _rank_rows_for_dungeon(ranks: object, spec_name: str) -> list[dict[str, object]]:
    """Return every usable percentile row for this spec in the current dungeon."""
    if not isinstance(ranks, list):
        return []
    wanted = _spec_norm(spec_name)
    rows: list[dict[str, object]] = []
    for row in ranks:
        if not isinstance(row, dict):
            continue
        row_spec = row.get("spec")
        if not isinstance(row_spec, str) or _spec_norm(row_spec) != wanted:
            continue
        percentile = row.get("rankPercent")
        if isinstance(percentile, bool) or not isinstance(percentile, (int, float)):
            continue
        value = float(percentile)
        if math.isfinite(value) and 0 <= value <= 100:
            rows.append(row)
    return rows


def _reduce_ranks(ranks: object, spec_name: str) -> WCLBracket | None:
    # rankPercent is already normalized by WCL for the row's keystone bracket
    # because the query uses byBracket:true. Average every available parse for
    # this spec in this dungeon instead of cherry-picking one key bracket.
    rows = _rank_rows_for_dungeon(ranks, spec_name)
    if not rows:
        return None
    values = [float(row["rankPercent"]) for row in rows]
    return WCLBracket(
        0,  # 0 = whole current dungeon, across available keystone brackets
        max(values),
        float(statistics.median(values)),
        len(values),
        float(statistics.fmean(values)),
    )
