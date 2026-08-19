#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "companion/source/app/keystonelens_companion"
VERSION = (ROOT / "companion/source/VERSION").read_text(encoding="utf-8").strip()


def fail(message: str) -> None:
    raise SystemExit(f"error - {message}")


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def audit_companion_runtime() -> None:
    forbidden = {
        "shell/process execution": re.compile(r"\b(?:subprocess\b|os\.system\s*\(|os\.popen\s*\(|Popen\s*\(|ShellExecute(?:Ex)?[AW]?\b|CreateProcess[AW]?\b)"),
        "inbound listener/server": re.compile(r"\b(?:HTTPServer|TCPServer|ThreadingTCPServer|socketserver|Flask\s*\(|FastAPI\s*\(|aiohttp\.web\b)|\.listen\s*\(|\.bind\s*\("),
        "TLS verification bypass": re.compile(r"\bverify\s*=\s*False\b|disable_warnings\s*\(|CERT_NONE\b|_create_unverified_context\b"),
        "unsafe archive extraction": re.compile(r"\.extractall\s*\(|\.extract\s*\("),
    }
    for path in sorted(APP_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        for label, pattern in forbidden.items():
            match = pattern.search(source)
            if match:
                fail(f"production Companion introduced {label}: {rel}: {match.group(0)}")
        if "http://" in source:
            fail(f"production Companion contains a plaintext HTTP endpoint: {rel}")


def audit_dependency_governance() -> None:
    dependabot = text(".github/dependabot.yml")
    required = (
        "package-ecosystem: github-actions",
        "directory: /companion/source/app",
        "directory: /companion/source/installer/windows",
    )
    for marker in required:
        if marker not in dependabot:
            fail(f"Dependabot coverage missing: {marker}")
    if dependabot.count("interval: weekly") < 3:
        fail("Actions and both Python dependency roots must be reviewed weekly")

    owners = text(".github/CODEOWNERS")
    for marker in (
        "/.github/CODEOWNERS @Yolol100",
        "/.github/workflows/ @Yolol100",
        "/companion/source/app/keystonelens_companion/ @Yolol100",
        "/companion/source/installer/ @Yolol100",
        "/companion/source/scripts/ @Yolol100",
        "/companion/source/docs/SBOM.cdx.json @Yolol100",
    ):
        if marker not in owners:
            fail(f"critical CODEOWNER boundary missing: {marker}")


def audit_sbom() -> None:
    sbom_path = ROOT / "companion/source/docs/SBOM.cdx.json"
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
    for raw in text("companion/source/app/requirements.txt").splitlines():
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


def audit_signing_contract() -> None:
    sign = text("companion/source/installer/windows/sign-release.ps1")
    verify = text("companion/source/installer/windows/verify-signatures.ps1")
    for marker in ("'/fd','SHA256'", "'/tr',$TimestampUrl", "'/td','SHA256'", "verify /pa /tw /all /v"):
        if marker not in sign:
            fail(f"signing contract missing: {marker}")
    if "verify /pa /tw /all /v" not in verify:
        fail("standalone signature verification must require an RFC3161 timestamp")


def audit_libkeystone_wire_contract() -> None:
    transport = text("addon/KeystoneLensBridge/Core/Transport.lua")
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
    audit_sbom()
    audit_signing_contract()
    audit_libkeystone_wire_contract()
    print("ok - external Companion, dependency, SBOM, signing and addon-wire security gates passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
