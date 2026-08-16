from __future__ import annotations

from dataclasses import dataclass
import math
import threading
import time
from typing import Any

import requests

from .registries import canonical_dungeon_name

PROFILE_URL = "https://raider.io/api/v1/characters/profile"
PROFILE_TTL_SECONDS = 15 * 60
MAX_PROFILE_CACHE_ENTRIES = 2048
MAX_RAW_PROFILE_CACHE_ENTRIES = 512
MAX_CACHE_FUTURE_SKEW_SECONDS = 5 * 60
REQUEST_TIMEOUT_SECONDS = 8
# Stay comfortably below Raider.IO's documented unauthenticated 200 req/min.
MIN_REQUEST_INTERVAL_SECONDS = 0.36


@dataclass(frozen=True)
class RIOResult:
    name: str
    realm: str
    region: str
    dungeon_name: str
    target_key: int
    score: int = 0
    role_score: int = 0
    role_score_available: bool = False
    best_key: int = 0
    best_dungeon_key: int = 0
    best_dungeon_run_score: float = 0.0
    best_dungeon_score_key: int = 0
    best_dungeon_time_ratio: float = 0.0
    best_dungeon_num_chests: int = 0
    dungeon_count: int = 0
    recent_runs: int = 0
    recent_timed: int = 0
    recent_targetish: int = 0
    recent_dungeon_runs: int = 0
    recent_dungeon_timed: int = 0
    recent_dungeon_targetish: int = 0
    fetched_at: float = 0.0
    not_found: bool = False
    error: str = ""



class RIOClient:
    """Small, rate-conscious Raider.IO runtime enrichment client.

    WoW's Raider.IO addon snapshot remains the local fallback. Runtime HTTP data is
    enrichment only, so a timeout or API error never makes an applicant disappear
    or turns a known player into a zero-score player.
    """

    def __init__(self) -> None:
        self._http = requests.Session()
        self._closed = threading.Event()
        self._http.headers.update({"User-Agent": "KeystoneLens/0.12.7 (Raider.IO attribution: https://raider.io)"})
        self._lock = threading.Lock()
        self._rate_lock = threading.Lock()
        self._last_request_at = 0.0
        self._profiles: dict[tuple[str, str, str, str, int, str], RIOResult] = {}
        # The Raider.IO profile response is character-wide. Dungeon, target key
        # and queued role only affect our local interpretation, so keep the raw
        # response once and derive multiple contexts without repeating HTTP.
        self._raw_profiles: dict[tuple[str, str, str], tuple[float, dict[str, Any] | None, bool]] = {}
        self._blocked_until = 0.0

    def close(self) -> None:
        """Release pooled HTTP resources and prevent any later lookup work."""
        self._closed.set()
        self._http.close()

    @staticmethod
    def _profile_key(region: str, realm: str, name: str, dungeon: str, target: int, role: str) -> tuple[str, str, str, str, int, str]:
        dungeon = canonical_dungeon_name(dungeon)
        return (region.casefold(), realm.casefold(), name.casefold(), dungeon.casefold(), int(target or 0), role.casefold())

    @staticmethod
    def _fresh_at(fetched_at: float, ttl: int, now: float) -> bool:
        if not math.isfinite(fetched_at) or fetched_at <= 0:
            return False
        age = now - fetched_at
        return -MAX_CACHE_FUTURE_SKEW_SECONDS <= age <= ttl

    @classmethod
    def _fresh(cls, fetched_at: float, ttl: int) -> bool:
        return cls._fresh_at(fetched_at, ttl, time.time())

    def _prune_cache_locked(self, now: float) -> None:
        self._profiles = {
            key: value for key, value in self._profiles.items()
            if self._fresh_at(value.fetched_at, PROFILE_TTL_SECONDS, now)
        }
        self._raw_profiles = {
            key: value for key, value in self._raw_profiles.items()
            if self._fresh_at(value[0], PROFILE_TTL_SECONDS, now)
        }
        if len(self._profiles) > MAX_PROFILE_CACHE_ENTRIES:
            newest = sorted(
                self._profiles.items(),
                key=lambda item: item[1].fetched_at,
                reverse=True,
            )[:MAX_PROFILE_CACHE_ENTRIES]
            self._profiles = dict(newest)
        if len(self._raw_profiles) > MAX_RAW_PROFILE_CACHE_ENTRIES:
            newest = sorted(
                self._raw_profiles.items(),
                key=lambda item: item[1][0],
                reverse=True,
            )[:MAX_RAW_PROFILE_CACHE_ENTRIES]
            self._raw_profiles = dict(newest)

    @staticmethod
    def _retry_after(response: requests.Response) -> float:
        try:
            return max(5.0, min(300.0, float(response.headers.get("Retry-After", "30") or 30)))
        except (TypeError, ValueError):
            return 30.0

    def _get(self, url: str, *, params: dict[str, object] | None = None) -> requests.Response:
        if self._closed.is_set():
            raise RuntimeError("Raider.IO client closed")
        if time.monotonic() < self._blocked_until:
            raise RuntimeError("Raider.IO rate limit; waiting for reset")
        # Profile requests are processed asynchronously, but a large applicant pool
        # can still arrive in a burst. Pace requests locally so normal use stays
        # below the public unauthenticated quota even before a 429 is returned.
        with self._rate_lock:
            delay = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - self._last_request_at)
            if delay > 0:
                # Event.wait keeps shutdown responsive during local rate pacing.
                if self._closed.wait(delay):
                    raise RuntimeError("Raider.IO client closed")
            try:
                response = self._http.get(url, params=params or {}, timeout=REQUEST_TIMEOUT_SECONDS)
            except requests.RequestException as exc:
                raise RuntimeError(f"Raider.IO network error: {exc}") from exc
            self._last_request_at = time.monotonic()
        if self._closed.is_set():
            raise RuntimeError("Raider.IO client closed")
        if response.status_code == 429:
            self._blocked_until = time.monotonic() + self._retry_after(response)
        return response

    def fetch_character(self, name: str, realm: str, region: str, dungeon: str, target_key: int, role: str = "") -> RIOResult:
        if self._closed.is_set():
            return RIOResult(name, realm, region, dungeon, target_key, fetched_at=time.time(), error="Raider.IO client closed")
        role = role.casefold().strip()
        key = self._profile_key(region, realm, name, dungeon, target_key, role)
        raw_key = (region.casefold(), realm.casefold(), name.casefold())
        with self._lock:
            self._prune_cache_locked(time.time())
            cached = self._profiles.get(key)
            if cached and self._fresh(cached.fetched_at, PROFILE_TTL_SECONDS):
                return cached
            raw_cached = self._raw_profiles.get(raw_key)
            if raw_cached and self._fresh(raw_cached[0], PROFILE_TTL_SECONDS):
                fetched_at, payload, not_found = raw_cached
                if not_found:
                    result = RIOResult(
                        name, realm, region, dungeon, target_key,
                        fetched_at=fetched_at, not_found=True,
                    )
                else:
                    result = _parse_profile(
                        payload or {}, name, realm, region, dungeon,
                        target_key, fetched_at, role,
                    )
                self._profiles[key] = result
                self._prune_cache_locked(time.time())
                return result

        fields = "mythic_plus_scores_by_season:current,mythic_plus_best_runs,mythic_plus_recent_runs"
        params: dict[str, object] = {
            "region": region.lower(),
            "realm": realm,
            "name": name,
            "fields": fields,
        }
        try:
            response = self._get(PROFILE_URL, params=params)
        except RuntimeError as exc:
            return RIOResult(name, realm, region, dungeon, target_key, fetched_at=time.time(), error=str(exc))

        # Older/alternate API deployments can reject the :current modifier.
        # Fall back once to the legacy public field names rather than disabling RIO.
        if response.status_code == 400:
            params["fields"] = "mythic_plus_scores,mythic_plus_best_runs,mythic_plus_recent_runs"
            try:
                response = self._get(PROFILE_URL, params=params)
            except RuntimeError as exc:
                return RIOResult(name, realm, region, dungeon, target_key, fetched_at=time.time(), error=str(exc))

        if self._closed.is_set():
            return RIOResult(name, realm, region, dungeon, target_key, fetched_at=time.time(), error="Raider.IO client closed")
        now = time.time()
        if response.status_code == 404:
            result = RIOResult(name, realm, region, dungeon, target_key, fetched_at=now, not_found=True)
            with self._lock:
                self._raw_profiles[raw_key] = (now, None, True)
                self._prune_cache_locked(now)
        elif response.status_code != 200:
            result = RIOResult(
                name, realm, region, dungeon, target_key, fetched_at=now,
                error=f"Raider.IO HTTP {response.status_code}",
            )
        else:
            try:
                payload = response.json()
            except ValueError:
                return RIOResult(
                    name, realm, region, dungeon, target_key, fetched_at=now,
                    error="Raider.IO returned invalid JSON",
                )
            # A successful character response must still identify the character.
            # Treat schema drift/empty objects as transient API errors instead of
            # silently caching fabricated zero-score evidence for 15 minutes.
            if not isinstance(payload, dict) or not isinstance(payload.get("name"), str) or not payload.get("name", "").strip():
                return RIOResult(
                    name, realm, region, dungeon, target_key, fetched_at=now,
                    error="Raider.IO returned malformed character data",
                )
            with self._lock:
                self._raw_profiles[raw_key] = (now, payload, False)
                self._prune_cache_locked(now)
            result = _parse_profile(payload, name, realm, region, dungeon, target_key, now, role)

        # Cache successful and explicit not-found responses. Transient errors should
        # be retried on the next snapshot instead of poisoning the cache for 15m.
        if not result.error:
            with self._lock:
                self._profiles[key] = result
                self._prune_cache_locked(now)
        return result


def _num(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return out if math.isfinite(out) else default


def _run_dungeon_name(run: dict[str, Any]) -> str:
    dungeon = run.get("dungeon")
    if isinstance(dungeon, dict):
        return canonical_dungeon_name(str(dungeon.get("name") or ""))
    return canonical_dungeon_name(str(dungeon or ""))


def _run_level(run: dict[str, Any]) -> int:
    return max(0, int(_num(run.get("mythic_level"), 0)))


def _run_timed(run: dict[str, Any]) -> bool:
    if _num(run.get("num_chests"), 0) > 0:
        return True
    clear_ms = _num(run.get("clear_time_ms"), 0)
    timer_ms = _num(run.get("keystone_time_ms"), 0)
    return bool(clear_ms > 0 and timer_ms > 0 and clear_ms <= timer_ms)


def _season_scores(payload: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    rows = payload.get("mythic_plus_scores_by_season")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            scores = row.get("scores")
            if not isinstance(scores, dict):
                continue
            for key, raw in scores.items():
                value = max(0, int(round(_num(raw, 0))))
                if value > 0:
                    out[str(key).casefold()] = value
            if out:
                return out
    scores = payload.get("mythic_plus_scores")
    if isinstance(scores, dict):
        for key, raw in scores.items():
            value = max(0, int(round(_num(raw, 0))))
            if value > 0:
                out[str(key).casefold()] = value
    return out


def _season_role_field_available(payload: dict[str, Any], role_key: str) -> bool:
    if not role_key:
        return False
    rows = payload.get("mythic_plus_scores_by_season")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            scores = row.get("scores")
            if not isinstance(scores, dict):
                continue
            # Match _season_scores(): use the first season row carrying any
            # positive score, but preserve whether this specific role field was
            # explicitly present even when its value is zero.
            if any(max(0, int(round(_num(raw, 0)))) > 0 for raw in scores.values()):
                return role_key in {str(key).casefold() for key in scores}
    scores = payload.get("mythic_plus_scores")
    if isinstance(scores, dict):
        return role_key in {str(key).casefold() for key in scores}
    return False


def _season_score(payload: dict[str, Any], role: str = "") -> tuple[int, int, bool]:
    scores = _season_scores(payload)
    overall = max(0, int(scores.get("all", 0)))
    role_key = "healer" if role == "healer" else "tank" if role == "tank" else "dps" if role == "dps" else ""
    role_score_available = _season_role_field_available(payload, role_key)
    role_score = max(0, int(scores.get(role_key, 0))) if role_key else 0
    return overall, role_score, role_score_available


def _parse_profile(
    payload: dict[str, Any], name: str, realm: str, region: str,
    dungeon: str, target_key: int, now: float, role: str = "",
) -> RIOResult:
    best_runs = payload.get("mythic_plus_best_runs")
    if not isinstance(best_runs, list):
        best_runs = []
    recent_runs = payload.get("mythic_plus_recent_runs")
    if not isinstance(recent_runs, list):
        recent_runs = []

    best_key = 0
    best_dungeon = 0
    best_dungeon_run_score = 0.0
    best_dungeon_score_key = 0
    best_dungeon_time_ratio = 0.0
    best_dungeon_num_chests = 0
    seen_dungeons: set[str] = set()
    wanted = canonical_dungeon_name(dungeon).casefold().strip()

    def consider_same_dungeon(raw: dict[str, Any]) -> None:
        nonlocal best_dungeon, best_dungeon_run_score, best_dungeon_score_key, best_dungeon_time_ratio, best_dungeon_num_chests
        level = _run_level(raw)
        run_score = max(0.0, _num(raw.get("score"), 0.0))
        clear_ms = _num(raw.get("clear_time_ms"), 0.0)
        timer_ms = _num(raw.get("keystone_time_ms"), 0.0)
        ratio = clear_ms / timer_ms if clear_ms > 0 and timer_ms > 0 else 0.0
        chests = max(0, int(_num(raw.get("num_chests"), 0)))

        # Keep the highest key as separate context, but bind score/timing to
        # Raider.IO's highest-scoring known run in this dungeon. Character RIO
        # itself is built from the highest-scoring run per dungeon, not simply
        # the numerically highest key.
        best_dungeon = max(best_dungeon, level)
        candidate = (run_score, level, -ratio if ratio > 0 else -999.0)
        current = (best_dungeon_run_score, best_dungeon_score_key, -best_dungeon_time_ratio if best_dungeon_time_ratio > 0 else -999.0)
        if run_score > 0 and candidate >= current:
            best_dungeon_run_score = run_score
            best_dungeon_score_key = level
            best_dungeon_time_ratio = ratio if math.isfinite(ratio) and ratio > 0 else 0.0
            best_dungeon_num_chests = chests

    for raw in best_runs:
        if not isinstance(raw, dict):
            continue
        level = _run_level(raw)
        best_key = max(best_key, level)
        run_name = _run_dungeon_name(raw)
        if run_name:
            seen_dungeons.add(run_name.casefold())
            if wanted and run_name.casefold() == wanted:
                consider_same_dungeon(raw)

    recent_timed = 0
    recent_targetish = 0
    recent_dungeon_runs = 0
    recent_dungeon_timed = 0
    recent_dungeon_targetish = 0
    floor = max(2, int(target_key or 0) - 2)
    for raw in recent_runs:
        if not isinstance(raw, dict):
            continue
        timed = _run_timed(raw)
        level = _run_level(raw)
        if timed:
            recent_timed += 1
            if level >= floor:
                recent_targetish += 1
        best_key = max(best_key, level)
        run_name = _run_dungeon_name(raw)
        if wanted and run_name.casefold() == wanted:
            recent_dungeon_runs += 1
            if timed:
                recent_dungeon_timed += 1
                if level >= floor:
                    recent_dungeon_targetish += 1
            consider_same_dungeon(raw)

    overall_score, role_score, role_score_available = _season_score(payload, role)
    return RIOResult(
        name=str(payload.get("name") or name),
        realm=realm,
        region=region,
        dungeon_name=dungeon,
        target_key=int(target_key or 0),
        score=overall_score,
        role_score=role_score,
        role_score_available=role_score_available,
        best_key=best_key,
        best_dungeon_key=best_dungeon,
        best_dungeon_run_score=best_dungeon_run_score,
        best_dungeon_score_key=best_dungeon_score_key,
        best_dungeon_time_ratio=best_dungeon_time_ratio,
        best_dungeon_num_chests=best_dungeon_num_chests,
        dungeon_count=len(seen_dungeons),
        recent_runs=len(recent_runs),
        recent_timed=recent_timed,
        recent_targetish=recent_targetish,
        recent_dungeon_runs=recent_dungeon_runs,
        recent_dungeon_timed=recent_dungeon_timed,
        recent_dungeon_targetish=recent_dungeon_targetish,
        fetched_at=now,
    )
