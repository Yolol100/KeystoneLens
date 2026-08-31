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
    for marker in (
        "package-ecosystem: github-actions",
        "directory: /companion/source/app",
        "directory: /companion/source/runtime",
    ):
        if marker not in dependabot:
            fail(f"Dependabot coverage missing: {marker}")
    if dependabot.count("interval: weekly") < 3:
        fail("Actions and both Python dependency roots must be reviewed weekly")

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
        fail("Warcraft Logs OAuth endpoint drifted")
    if 'API_URL = "https://www.warcraftlogs.com/api/v2/client"' not in wcl or "/api/v2/user" in wcl:
        fail("Warcraft Logs API boundary drifted")
    rio = source_text("app/keystonelens_companion/rio.py")
    if 'PROFILE_URL = "https://raider.io/api/v1/characters/profile"' not in rio:
        fail("Raider.IO endpoint drifted")
    interval = re.search(r"^MIN_REQUEST_INTERVAL_SECONDS\s*=\s*([0-9.]+)\s*$", rio, re.M)
    if not interval or float(interval.group(1)) < 0.31:
        fail("Raider.IO request pacing is too aggressive")
    if "429" not in rio or "Retry-After" not in rio or "Raider.IO attribution: https://raider.io" not in rio:
        fail("Raider.IO backoff/attribution contract drifted")


def audit_sbom_and_runtime() -> None:
    sbom = json.loads(source_text("docs/SBOM.cdx.json"))
    component = (sbom.get("metadata") or {}).get("component") or {}
    if sbom.get("bomFormat") != "CycloneDX" or component.get("version") != VERSION:
        fail("SBOM identity does not match canonical VERSION")
    runtime = json.loads(source_text("runtime/windows-x64.json"))
    if runtime.get("platform") != "windows-x64" or not str(runtime.get("python_url", "")).startswith("https://"):
        fail("portable runtime source contract is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(runtime.get("python_sha256", ""))):
        fail("portable runtime SHA-256 contract is invalid")
    components = {str(item.get("name", "")).casefold(): item for item in sbom.get("components", []) if isinstance(item, dict)}
    python_component = components.get("cpython")
    if not python_component or python_component.get("version") != runtime.get("python_version"):
        fail("SBOM CPython version does not match portable runtime contract")
    hashes = {str(item.get("content", "")).casefold() for item in python_component.get("hashes", []) if isinstance(item, dict)}
    if runtime["python_sha256"].casefold() not in hashes:
        fail("SBOM CPython hash does not match portable runtime contract")


def audit_portable_distribution() -> None:
    launcher = source_text("portable/portable_launcher.py")
    builder = source_text("portable/build-portable.ps1")
    for marker in ('MUTEX_NAME = "KeystoneLens.Companion.Singleton"', 'CreateMutexW', 'RUNTIME_CONTRACT = ROOT / "RUNTIME.json"'):
        if marker not in launcher:
            fail(f"portable single-instance/runtime marker missing: {marker}")
    for marker in ("runtime\\windows-x64.json", "runtime\\requirements-runtime.lock", "scripts\\make_deterministic_zip.py", "KeystoneLens-Setup.exe"):
        if marker not in builder:
            fail(f"portable builder contract missing: {marker}")
    if "installer\\windows" in builder or "KeystoneLens.exe' -Destination" in builder:
        fail("portable builder depends on the obsolete installed-executable stack")


def audit_libkeystone_wire_contract() -> None:
    transport = repo_text("addon/KeystoneLensBridge/Core/Transport.lua")
    prefix_match = re.search(r'RegisterAddonMessagePrefix\("([^"]+)"\)', transport)
    if not prefix_match or len(prefix_match.group(1).encode("utf-8")) > 16:
        fail("LibKeystone compatibility prefix is invalid")
    for marker in ('channel ~= "PARTY"', "IsChatMessagingLockdown()", 'SendAddonMessage("LibKS", payload, channel)'):
        if marker not in transport:
            fail(f"LibKeystone wire safety marker missing: {marker}")


def main() -> int:
    audit_companion_runtime()
    audit_dependency_governance()
    audit_api_contracts()
    audit_sbom_and_runtime()
    audit_portable_distribution()
    audit_libkeystone_wire_contract()
    print("ok - external Companion, dependency, API, SBOM, portable and addon-wire security gates passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
