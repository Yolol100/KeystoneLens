from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import keystonelens_companion.config as config


class ConfigSecretMigrationScenarios(unittest.TestCase):
    def _path(self, root: str) -> Path:
        return Path(root) / "config.json"

    def _write(self, path: Path, data: dict[str, object]) -> None:
        path.write_text(json.dumps(data), encoding="utf-8")

    def _load_disk(self, path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_plaintext_legacy_secret_is_migrated_to_dpapi_on_windows(self):
        with tempfile.TemporaryDirectory() as root:
            path = self._path(root)
            self._write(path, {
                "client_id": "client-id",
                "client_secret": "legacy-secret",
                "screenshots_path": r"C:\\WoW\\_retail_\\Screenshots",
            })
            with (
                patch.object(config, "config_path", return_value=path),
                patch.object(config.os, "name", "nt"),
                patch.object(config, "_protect_secret", return_value="dpapi:v1:protected"),
            ):
                cfg = config.load_config()

            self.assertEqual(cfg.client_secret, "legacy-secret")
            disk = self._load_disk(path)
            self.assertNotIn("client_secret", disk)
            self.assertEqual(disk["client_secret_protected"], "dpapi:v1:protected")

    def test_dpapi_value_wins_and_duplicate_plaintext_is_removed(self):
        with tempfile.TemporaryDirectory() as root:
            path = self._path(root)
            self._write(path, {
                "client_id": "client-id",
                "client_secret": "stale-plaintext",
                "client_secret_protected": "dpapi:v1:old",
            })
            with (
                patch.object(config, "config_path", return_value=path),
                patch.object(config.os, "name", "nt"),
                patch.object(config, "_unprotect_secret", return_value="trusted-secret"),
                patch.object(config, "_protect_secret", return_value="dpapi:v1:refreshed"),
            ):
                cfg = config.load_config()

            self.assertEqual(cfg.client_secret, "trusted-secret")
            disk = self._load_disk(path)
            self.assertNotIn("client_secret", disk)
            self.assertEqual(disk["client_secret_protected"], "dpapi:v1:refreshed")

    def test_corrupt_dpapi_never_falls_back_to_plaintext(self):
        with tempfile.TemporaryDirectory() as root:
            path = self._path(root)
            self._write(path, {
                "client_id": "client-id",
                "client_secret": "must-not-be-used",
                "client_secret_protected": "dpapi:v1:broken",
            })
            with (
                patch.object(config, "config_path", return_value=path),
                patch.object(config.os, "name", "nt"),
                patch.object(config, "_unprotect_secret", side_effect=ValueError("bad blob")),
            ):
                cfg = config.load_config()

            self.assertEqual(cfg.client_secret, "")
            disk = self._load_disk(path)
            self.assertNotIn("client_secret", disk)
            self.assertNotIn("client_secret_protected", disk)

    def test_failed_dpapi_protection_scrubs_plaintext_and_disables_wcl(self):
        with tempfile.TemporaryDirectory() as root:
            path = self._path(root)
            self._write(path, {
                "client_id": "client-id",
                "client_secret": "legacy-secret",
            })
            with (
                patch.object(config, "config_path", return_value=path),
                patch.object(config.os, "name", "nt"),
                patch.object(config, "_protect_secret", side_effect=OSError("DPAPI unavailable")),
            ):
                cfg = config.load_config()

            self.assertEqual(cfg.client_secret, "")
            self.assertFalse(cfg.wcl_configured)
            disk = self._load_disk(path)
            self.assertNotIn("client_secret", disk)
            self.assertNotIn("client_secret_protected", disk)

    def test_non_windows_plaintext_is_scrubbed_and_not_activated(self):
        with tempfile.TemporaryDirectory() as root:
            path = self._path(root)
            self._write(path, {
                "client_id": "client-id",
                "client_secret": "legacy-secret",
            })
            with (
                patch.object(config, "config_path", return_value=path),
                patch.object(config.os, "name", "posix"),
            ):
                cfg = config.load_config()

            self.assertEqual(cfg.client_secret, "")
            self.assertNotIn("client_secret", self._load_disk(path))

    def test_protected_only_config_is_read_without_rewrite(self):
        with tempfile.TemporaryDirectory() as root:
            path = self._path(root)
            original = {
                "client_id": "client-id",
                "client_secret_protected": "dpapi:v1:existing",
                "score_min": 84,
            }
            self._write(path, original)
            with (
                patch.object(config, "config_path", return_value=path),
                patch.object(config.os, "name", "nt"),
                patch.object(config, "_unprotect_secret", return_value="secret") as unprotect,
                patch.object(config, "_protect_secret") as protect,
            ):
                cfg = config.load_config()

            self.assertEqual(cfg.client_secret, "secret")
            unprotect.assert_called_once_with("dpapi:v1:existing")
            protect.assert_not_called()
            self.assertEqual(self._load_disk(path), original)

    def test_read_only_migration_failure_never_activates_plaintext_secret(self):
        with tempfile.TemporaryDirectory() as root:
            path = self._path(root)
            self._write(path, {
                "client_id": "client-id",
                "client_secret": "legacy-secret",
            })
            real_atomic_write = config._atomic_write_config
            calls = 0

            def fail_writes(target: Path, data: dict[str, object]) -> None:
                nonlocal calls
                calls += 1
                raise OSError("read-only config")

            with (
                patch.object(config, "config_path", return_value=path),
                patch.object(config.os, "name", "nt"),
                patch.object(config, "_protect_secret", return_value="dpapi:v1:new"),
                patch.object(config, "_atomic_write_config", side_effect=fail_writes),
            ):
                cfg = config.load_config()

            self.assertGreaterEqual(calls, 2)
            self.assertEqual(cfg.client_secret, "")
            # A genuinely read-only file cannot be repaired in-process, but the
            # application must still refuse to use its plaintext credential.
            self.assertEqual(self._load_disk(path)["client_secret"], "legacy-secret")
            self.assertIsNotNone(real_atomic_write)


if __name__ == "__main__":
    unittest.main()
