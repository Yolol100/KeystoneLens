#!/usr/bin/env python3
"""Controlled-runtime checks for live Warcraft Logs provider readiness."""
from __future__ import annotations

from pathlib import Path
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "companion" / "source" / "app"
sys.path.insert(0, str(APP_ROOT))

requests_stub = types.ModuleType("requests")
requests_stub.RequestException = RuntimeError
requests_stub.Session = object
sys.modules.setdefault("requests", requests_stub)

from keystonelens_companion.wcl import WCLError, WCLClient  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, payload=None, *, json_error=False, headers=None):
        self.status_code = int(status_code)
        self._payload = payload
        self._json_error = bool(json_error)
        self.headers = dict(headers or {})

    def json(self):
        if self._json_error:
            raise ValueError("bad json")
        return self._payload


class ReadinessClient(WCLClient):
    def __init__(self, response):
        self.response = response
        self.last_body = None
        self.last_quota = None
        self._last_quota_observed_at = 0.0
        self._blocked_until = 0.0

    def _post_graphql(self, body):
        self.last_body = body
        return self.response


def expect_error(client, expected: str):
    try:
        client.test()
    except WCLError as exc:
        assert expected in str(exc), (expected, str(exc))
    else:
        raise AssertionError(f"expected WCLError containing {expected!r}")


def test_success_requires_real_graphql_quota():
    client = ReadinessClient(FakeResponse(payload={
        "data": {
            "rateLimitData": {
                "limitPerHour": 3600,
                "pointsSpentThisHour": 12.5,
                "pointsResetIn": 1234,
            }
        }
    }))
    quota = client.test()
    assert quota == (12.5, 3600.0, 1234.0)
    assert client.last_quota == quota
    assert client._last_quota_observed_at > 0
    query = str(client.last_body.get("query") or "")
    assert "KLProviderReadiness" in query
    assert "rateLimitData" in query
    assert "characterData" not in query


def test_http_auth_failure_is_not_connected():
    expect_error(ReadinessClient(FakeResponse(status_code=401, payload={})), "WCL API HTTP 401")


def test_rate_limit_sets_backoff_and_is_not_connected():
    client = ReadinessClient(FakeResponse(
        status_code=429,
        payload={},
        headers={"Retry-After": "60"},
    ))
    before = time.monotonic()
    expect_error(client, "WCL API rate limit")
    assert client._blocked_until >= before + 55


def test_invalid_json_is_not_connected():
    expect_error(ReadinessClient(FakeResponse(json_error=True)), "invalid JSON")


def test_graphql_error_is_not_connected():
    expect_error(ReadinessClient(FakeResponse(payload={
        "data": None,
        "errors": [{"message": "schema unavailable"}],
    })), "WCL GraphQL error: schema unavailable")


def test_missing_quota_is_not_connected():
    expect_error(ReadinessClient(FakeResponse(payload={"data": {}})), "missing rateLimitData")


if __name__ == "__main__":
    test_success_requires_real_graphql_quota()
    test_http_auth_failure_is_not_connected()
    test_rate_limit_sets_backoff_and_is_not_connected()
    test_invalid_json_is_not_connected()
    test_graphql_error_is_not_connected()
    test_missing_quota_is_not_connected()
    print("KeystoneLens WCL provider readiness contract passed.")
