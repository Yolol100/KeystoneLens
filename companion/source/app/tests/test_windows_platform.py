from __future__ import annotations

import json
import os

import pytest

from keystonelens_companion import config as config_module
from keystonelens_companion.config import Config


pytestmark = pytest.mark.skipif(os.name != "nt", reason="native Windows contract")


def test_dpapi_secret_round_trip_is_not_plaintext() -> None:
    secret = "wcl-secret-native-windows-check"
    protected = config_module._protect_secret(secret)

    assert protected.startswith("dpapi:v1:")
    assert secret not in protected
    assert config_module._unprotect_secret(protected) == secret


def test_config_persists_wcl_secret_only_as_dpapi(tmp_path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "config_path", lambda: path)

    original = Config(
        client_id="client-id",
        client_secret="super-secret-value",
        screenshots_path=r"C:\Games\World of Warcraft\_retail_\Screenshots",
    )
    config_module.save_config(original)

    raw_text = path.read_text(encoding="utf-8")
    raw = json.loads(raw_text)
    assert "client_secret" not in raw
    assert "super-secret-value" not in raw_text
    assert raw["client_secret_protected"].startswith("dpapi:v1:")

    loaded = config_module.load_config()
    assert loaded.client_id == original.client_id
    assert loaded.client_secret == original.client_secret
    assert loaded.screenshots_path == original.screenshots_path


def test_corrupt_dpapi_blob_fails_closed(tmp_path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "config_path", lambda: path)
    path.write_text(
        json.dumps(
            {
                "client_id": "client-id",
                "client_secret_protected": "dpapi:v1:not-valid-base64!",
                "screenshots_path": r"C:\Screenshots",
            }
        ),
        encoding="utf-8",
    )

    loaded = config_module.load_config()
    assert loaded.client_id == "client-id"
    assert loaded.client_secret == ""
    assert loaded.screenshots_path == r"C:\Screenshots"
