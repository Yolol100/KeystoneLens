from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from keystonelens_companion import __version__, rio, wcl


class Response:
    def __init__(self, status_code: int, payload=None, headers=None, json_error: Exception | None = None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


def test_rio_user_agent_follows_canonical_companion_version():
    client = rio.RIOClient()
    try:
        assert client._http.headers["User-Agent"].startswith(f"KeystoneLens/{__version__} ")
        assert "Raider.IO attribution" in client._http.headers["User-Agent"]
    finally:
        client.close()


@pytest.mark.parametrize("status", [400, 401, 403, 409, 429, 500, 502, 503])
def test_rio_http_failure_matrix_is_explicit_and_not_cached(status):
    client = rio.RIOClient()
    try:
        client._last_request_at = 0.0
        client._http.get = Mock(return_value=Response(status, {}, {"Retry-After": "7"}))
        result = client.fetch_character("Applicant", "Realm", "EU", "Altar of Fangs", 10, "dps")
        assert result.error == f"Raider.IO HTTP {status}"
        assert client._profiles == {}
        assert client._raw_profiles == {}
        if status == 429:
            assert client._blocked_until > 0
    finally:
        client.close()


def test_rio_timeout_is_retryable_and_not_cached():
    client = rio.RIOClient()
    try:
        client._last_request_at = 0.0
        client._http.get = Mock(side_effect=requests.Timeout("timeout"))
        result = client.fetch_character("Applicant", "Realm", "EU", "Altar of Fangs", 10, "dps")
        assert "network error" in result.error.casefold()
        assert client._profiles == {}
        assert client._raw_profiles == {}
    finally:
        client.close()


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 502, 503])
def test_wcl_oauth_failure_matrix_is_explicit(tmp_path, status):
    client = wcl.WCLClient("client", "secret", wcl.WCLCache(tmp_path / "wcl.json"))
    try:
        client._http.post = Mock(return_value=Response(status, {}))
        with pytest.raises(wcl.WCLError, match=str(status)):
            client.test()
    finally:
        client.close()


def test_wcl_oauth_invalid_json_is_explicit(tmp_path):
    client = wcl.WCLClient("client", "secret", wcl.WCLCache(tmp_path / "wcl.json"))
    try:
        client._http.post = Mock(return_value=Response(200, json_error=ValueError("bad")))
        with pytest.raises(wcl.WCLError, match="invalid JSON"):
            client.test()
    finally:
        client.close()


@pytest.mark.parametrize("status, expected", [
    (400, "WCL HTTP 400"),
    (401, "WCL login invalid"),
    (403, "WCL login invalid"),
    (404, "WCL HTTP 404"),
    (409, "WCL HTTP 409"),
    (429, "WCL rate limit"),
    (500, "WCL HTTP 500"),
    (502, "WCL HTTP 502"),
    (503, "WCL HTTP 503"),
])
def test_wcl_graphql_failure_matrix_does_not_persist_error(tmp_path, status, expected):
    cache = wcl.WCLCache(tmp_path / "wcl.json")
    client = wcl.WCLClient("client", "secret", cache)
    try:
        client._resolve_encounter_id = Mock(return_value=123)
        client._post_graphql = Mock(return_value=Response(status, {}, {"Retry-After": "7"}))
        jobs = [("Applicant", "realm", "Realm", "EU", 71, "Altar of Fangs", 10)]
        result = client.fetch_batch_current_dungeon(jobs)[0]
        assert result.error == expected
        assert cache.count() == 0
    finally:
        client.close()


def test_rio_404_is_explicit_not_found_and_cacheable():
    client = rio.RIOClient()
    try:
        client._last_request_at = 0.0
        client._http.get = Mock(return_value=Response(404, {}))
        result = client.fetch_character("Applicant", "Realm", "EU", "Altar of Fangs", 10, "dps")
        assert result.not_found is True
        assert result.error == ""
        assert len(client._profiles) == 1
        assert len(client._raw_profiles) == 1
    finally:
        client.close()


def test_wcl_graphql_invalid_200_json_is_explicit_and_not_cached(tmp_path):
    cache = wcl.WCLCache(tmp_path / "wcl.json")
    client = wcl.WCLClient("client", "secret", cache)
    try:
        client._resolve_encounter_id = Mock(return_value=123)
        client._post_graphql = Mock(return_value=Response(200, json_error=ValueError("bad")))
        jobs = [("Applicant", "realm", "Realm", "EU", 71, "Altar of Fangs", 10)]
        result = client.fetch_batch_current_dungeon(jobs)[0]
        assert "GraphQL error" in result.error
        assert cache.count() == 0
    finally:
        client.close()


def test_network_sources_do_not_disable_tls_verification():
    root = Path(__file__).resolve().parents[2] / "app" / "keystonelens_companion"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "verify=False" not in source
    assert ".verify = False" not in source
