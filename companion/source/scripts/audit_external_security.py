#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SOURCE_ROOT.parents[1]
APP_ROOT = SOURCE_ROOT / "app/keystonelens_companion"
VERSION = (SOURCE_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def fail(message: str) -> None:
    raise SystemExit(f"error - {message}")


def source_text(rel: str) -> str:
    return (SOURCE_ROOT / rel).read_text(encoding="utf-8")


def repo_text(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def audit_companion_runtime() -> None:
    forbidden = {
        "shell/process execution": re.compile(r"\b(?:subprocess\b|os\.system\s*\(|os\.popen\s*\(|Popen\s*\(|ShellExecute(?:Ex)?[AW]?\b|CreateProcess[AW]?\b)"),
        "inbound listener/server": re.compile(r"\b(?:HTTPServer|TCPServer|ThreadingTCPServer|socketserver|Flask\s*\(|FastAPI\s*\(|aiohttp\.web\b|socket\.(?:socket|create_server)\s*\()|\.listen\s*\("),
        "TLS verification bypass": re.compile(r"\bverify\s*=\s*False\b|disable_warnings\s*\(|CERT_NONE\b|_create_unverified_context\b"),
        "unsafe archive extraction": re.compile(r"\.extractall\s*\(|\.extract\s*\("),
        "unsafe deserialization/dynamic execution": re.compile(r"\b(?:pickle\.(?:load|loads)|marshal\.loads|yaml\.load\s*\(|eval\s*\(|exec\s*\()"),
    }
    for path in sorted(APP_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        rel = path.relative_to(SOURCE_ROOT).as_posix()
        for label, pattern in forbidden.items():
            match = pattern.search(source)
            if match:
                fail(f"production Companion introduced {label}: {rel}: {match.group(0)}")
        if "http://" in source:
            fail(f"production Companion contains a plaintext HTTP endpoint: {rel}")


def audit_dependency_governance() -> None:
    if not (REPO_ROOT / ".github").is_dir():
        return
    dependabot = repo_text(".github/dependabot.yml")
    for marker in ("package-ecosystem: github-actions", "directory: /companion/source/app"):
        if marker not in dependabot:
            fail(f"Dependabot coverage missing: {marker}")
    if dependabot.count("interval: weekly") < 2:
        fail("Actions and Companion Python dependencies must be reviewed weekly")

    owners = repo_text(".github/CODEOWNERS")
    for marker in (
        "/.github/CODEOWNERS @Yolol100",
        "/.github/workflows/ @Yolol100",
        "/companion/source/app/keystonelens_companion/ @Yolol100",
        "/companion/source/portable/ @Yolol100",
        "/companion/source/runtime/ @Yolol100",
        "/companion/source/scripts/ @Yolol100",
        "/companion/source/docs/SBOM.cdx.json @Yolol100",
    ):
        if marker not in owners:
            fail(f"critical CODEOWNER boundary missing: {marker}")

    dependency_review = repo_text(".github/workflows/dependency-review.yml")
    if "actions/dependency-review-action@a1d282b36b6f3519aa1f3fc636f609c47dddb294" not in dependency_review:
        fail("Dependency Review Action must remain pinned to the reviewed v5.0.0 commit")
    if "fail-on-severity: moderate" not in dependency_review:
        fail("Dependency Review must block newly introduced moderate-or-higher vulnerabilities")


def audit_api_contracts() -> None:
    wcl = source_text("app/keystonelens_companion/wcl.py")
    if 'OAUTH_URL = "https://www.warcraftlogs.com/oauth/token"' not in wcl:
        fail("Warcraft Logs OAuth endpoint drifted from the reviewed HTTPS token endpoint")
    if 'API_URL = "https://www.warcraftlogs.com/api/v2/client"' not in wcl:
        fail("Warcraft Logs enrichment must remain on the public client-credentials API")
    if "/api/v2/user" in wcl:
        fail("Warcraft Logs private user API requires explicit user authorization and is not approved")

    rio = source_text("app/keystonelens_companion/rio.py")
    if 'PROFILE_URL = "https://raider.io/api/v1/characters/profile"' not in rio:
        fail("Raider.IO runtime enrichment must remain on the documented HTTPS API endpoint")
    interval = re.search(r"^MIN_REQUEST_INTERVAL_SECONDS\s*=\s*([0-9.]+)\s*$", rio, re.M)
    if not interval or float(interval.group(1)) < 0.31:
        fail("Raider.IO request pacing no longer stays below the documented unauthenticated 200 req/min limit")
    if "429" not in rio or "Retry-After" not in rio:
        fail("Raider.IO 429/backoff handling is missing")
    if "Raider.IO attribution: https://raider.io" not in rio:
        fail("Raider.IO attribution marker is missing from the public-facing client identity")


def audit_sbom() -> None:
    sbom_path = SOURCE_ROOT / "docs/SBOM.cdx.json"
    if not sbom_path.is_file():
        fail("CycloneDX SBOM is missing")
    try:
        sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"SBOM is invalid JSON: {exc}")
    if sbom.get("bomFormat") != "CycloneDX" or str(sbom.get("specVersion", "")) < "1.5":
        fail("SBOM must remain CycloneDX 1.5+")
    component = (sbom.get("metadata") or {}).get("component") or {}
    if component.get("name") != "KeystoneLens Companion" or component.get("version") != VERSION:
        fail("SBOM application identity does not match canonical VERSION")

    requirements = {}
    for raw in source_text("app/requirements.txt").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            fail(f"direct runtime dependency is not exactly pinned: {line}")
        name, version = line.split("==", 1)
        requirements[name.casefold()] = version
    components = {
        str(item.get("name", "")).casefold(): str(item.get("version", ""))
        for item in sbom.get("components", [])
        if isinstance(item, dict)
    }
    for name, version in requirements.items():
        if components.get(name) != version:
            fail(f"SBOM direct dependency mismatch: {name}=={version}")


def audit_portable_distribution_contract() -> None:
    manifest_path = SOURCE_ROOT / "runtime/windows/python-runtime.json"
    lock_path = SOURCE_ROOT / "runtime/windows/requirements-runtime.lock"
    if not manifest_path.is_file() or not lock_path.is_file():
        fail("portable runtime manifest/lock is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("platform") != "windows-x64":
        fail("portable runtime platform must remain windows-x64")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(manifest.get("version", ""))):
        fail("portable runtime version is invalid")
    if not str(manifest.get("url", "")).startswith("https://www.python.org/"):
        fail("portable runtime must come from python.org over HTTPS")
    if not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("sha256", ""))):
        fail("portable runtime SHA-256 is invalid")

    lock = lock_path.read_text(encoding="utf-8")
    if lock.count("--hash=sha256:") < 1:
        fail("portable runtime dependency lock is not hash pinned")

    builder = source_text("portable/build-portable.ps1")
    launcher = source_text("portable/portable_launcher.py")
    for marker in ("--require-hashes", "--no-deps", "--only-binary=:all:"):
        if marker not in builder:
            fail(f"portable builder dependency hardening drifted: {marker}")
    if "KeystoneLens.Companion.Singleton" not in launcher or "CreateMutexW" not in launcher:
        fail("portable launcher lost the single-instance contract")
    if "show_startup_error" not in launcher or "except SystemExit as exc" not in launcher:
        fail("portable launcher lost visible startup failure handling")
    if (SOURCE_ROOT / "installer").exists():
        fail("legacy installer source is present in portable-only source")


def audit_libkeystone_wire_contract() -> None:
    transport = source_text("addon/KeystoneLensBridge/Core/Transport.lua")
    prefix_match = re.search(r'RegisterAddonMessagePrefix\("([^"]+)"\)', transport)
    if not prefix_match:
        fail("LibKeystone compatibility prefix is not a fixed literal")
    if len(prefix_match.group(1).encode("utf-8")) > 16:
        fail("LibKeystone addon-message prefix exceeds WoW's 16-byte ceiling")
    for marker in (
        'channel ~= "PARTY"',
        "IsChatMessagingLockdown()",
        'SendAddonMessage("LibKS", payload, channel)',
        'string.format("%d,%d,%d", keyLevel, challengeMapID, playerRating)',
    ):
        if marker not in transport:
            fail(f"LibKeystone wire safety marker missing: {marker}")


def main() -> int:
    audit_companion_runtime()
    audit_dependency_governance()
    audit_api_contracts()
    audit_sbom()
    audit_portable_distribution_contract()
    audit_libkeystone_wire_contract()
    print("ok - external Companion, dependency, API, SBOM, portable-distribution and addon-wire security gates passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
