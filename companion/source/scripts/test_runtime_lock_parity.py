#!/usr/bin/env python3
"""Fail closed if readable runtime requirements disagree with the Windows wheel lock."""

from pathlib import Path
import re
import unittest

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
DIRECT = RUNTIME / "requirements-runtime.txt"
LOCK = RUNTIME / "requirements-runtime.lock"

PIN = re.compile(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)")
LOCK_PIN = re.compile(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)\s+\\")
HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})")


def parse_requirements(content: str, hashed: bool) -> dict[str, tuple[str, str | None]]:
    lines = content.splitlines()
    pins: dict[str, tuple[str, str | None]] = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("#"):
            continue
        match = (LOCK_PIN if hashed else PIN).fullmatch(line)
        if not match:
            raise ValueError(f"Unrecognized {'lock' if hashed else 'direct'} requirement: {line}")
        name, version = match.groups()
        canonical = name.lower().replace("_", "-")
        if canonical in pins:
            raise ValueError(f"Duplicate pinned package: {name}")
        digest: str | None = None
        if hashed:
            if i >= len(lines):
                raise ValueError(f"Missing SHA-256 for {name}")
            hash_match = HASH.fullmatch(lines[i].strip())
            i += 1
            if not hash_match:
                raise ValueError(f"Missing/invalid SHA-256 for {name}")
            digest = hash_match.group(1)
        pins[canonical] = (version, digest)
    return pins


class RuntimeRequirementsContract(unittest.TestCase):
    def test_direct_requirements_equal_windows_lock_versions(self) -> None:
        direct = parse_requirements(DIRECT.read_text(encoding="utf-8"), hashed=False)
        locked = parse_requirements(LOCK.read_text(encoding="utf-8"), hashed=True)
        self.assertTrue(direct, "Direct runtime requirements must not be empty")
        for name, (version, _) in direct.items():
            self.assertIn(name, locked, f"{name} missing from deterministic Windows lock")
            self.assertEqual(version, locked[name][0], f"{name} runtime/lock version drift")
            self.assertIsNotNone(locked[name][1], f"{name} hash missing from Windows lock")

    def test_reject_missing_hash_and_version_drift(self) -> None:
        with self.assertRaises(ValueError):
            parse_requirements("Pillow==13.0.0 \\\n    --hash=sha256:not-a-digest\n", hashed=True)
        with self.assertRaises(ValueError):
            parse_requirements("Pillow==13.0.0\nPillow==12.3.0\n", hashed=False)
        with self.assertRaises(ValueError):
            parse_requirements("Pillow>=13.0.0\n", hashed=False)


if __name__ == "__main__":
    unittest.main()
