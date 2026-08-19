#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
import unicodedata
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
VERSION_FILE = ROOT / "companion/source/VERSION"
BRIDGE_ROOT = "addon/KeystoneLensBridge"
BRIDGE_TOC = f"{BRIDGE_ROOT}/KeystoneLensBridge.toc"
MAX_TEXT_BYTES = 2 * 1024 * 1024
BINARY_SOURCE_SUFFIXES = {".ico", ".tga", ".png", ".jpg", ".jpeg", ".gif"}
FORBIDDEN_TRACKED_SUFFIXES = {".zip", ".exe", ".pfx", ".p12", ".pem", ".key", ".pyc", ".pyo", ".log", ".tmp", ".bak", ".orig", ".rej"}
FORBIDDEN_PATH_PARTS = {"__pycache__", ".pytest_cache", ".venv", "venv", ".idea", ".vscode", "build", "release"}
REQUIRED_FILES = {
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    ".github/CODEOWNERS",
    ".github/dependabot.yml",
    ".github/workflows/codeql.yml",
    ".github/workflows/dependency-audit-pr.yml",
    ".github/workflows/dependency-audit.yml",
    ".github/workflows/rebuild-keystonelens.yml",
    ".github/workflows/windows-platform.yml",
    "LICENSE-SCOPE.md",
    "README.md",
    "SECURITY.md",
    BRIDGE_TOC,
    "companion/source/VERSION",
    "companion/source/docs/LIVE-WOW-ACCEPTATIE.md",
    "companion/source/docs/OFFICIAL-RELEASE-SOURCES.md",
    "companion/source/docs/UITGAVE-CHECKLIST.md",
    "companion/source/scripts/audit_repository.py",
}
GENERATED_REPOSITORY_PATHS = {
    "SHA256SUMS.txt",
    "companion/source/installer/windows/bootstrap/payload.zip",
}
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b"),
    "OpenAI key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b"),
}
FORBIDDEN_BRIDGE_CALLS = re.compile(
    r"\b(?:CombatLogGetCurrentEventInfo|UnitAura|UnitHealth|UnitHealthMax|UnitPower|UnitPowerMax|"
    r"UnitCastingInfo|UnitChannelInfo|UnitPosition|GetPlayerMapPosition|CastSpellByID|CastSpellByName|"
    r"UseAction|TargetUnit|FocusUnit|SetRaidTarget|SetBinding|SetOverrideBinding|RegisterStateDriver|"
    r"SendAddonMessage|SendChatMessage|loadstring|RunScript)\s*\("
)
FORBIDDEN_BRIDGE_TOKENS = (
    "COMBAT_LOG_EVENT_UNFILTERED",
    "SecureActionButtonTemplate",
    "SecureHandler",
    "C_UnitAuras.",
)
HIGH_RISK_WORKFLOW_TRIGGERS = (
    "pull_request_target:",
    "repository_dispatch:",
    "workflow_run:",
)


def fail(message: str) -> None:
    print(f"error - {message}", file=sys.stderr)
    raise SystemExit(1)


def git_files() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [item.decode("utf-8") for item in raw.split(b"\0") if item]


def read_text(rel: str) -> str:
    data = (ROOT / rel).read_bytes()
    if len(data) > MAX_TEXT_BYTES:
        fail(f"tracked text exceeds {MAX_TEXT_BYTES} bytes: {rel}")
    if b"\0" in data:
        fail(f"unexpected binary/NUL content in text file: {rel}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        fail(f"tracked text must be UTF-8: {rel}")
    if "\r" in text:
        fail(f"tracked text must use LF line endings: {rel}")
    if data and not data.endswith(b"\n"):
        fail(f"tracked text must end with a newline: {rel}")
    return text


def canonical_version() -> str:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        fail(f"invalid canonical VERSION: {version!r}")
    return version


def require_exact_line(rel: str, line: str) -> None:
    if line not in read_text(rel).splitlines():
        fail(f"release identity mismatch in {rel}: missing {line!r}")


def bridge_runtime_entries() -> list[str]:
    entries: list[str] = []
    for raw in read_text(BRIDGE_TOC).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(f"{BRIDGE_ROOT}/{line.replace(chr(92), '/')}")
    return entries


def validate_bridge_runtime(file_set: set[str]) -> None:
    entries = bridge_runtime_entries()
    if not entries or len(entries) != len(set(entries)):
        fail("Bridge TOC runtime inventory is empty or contains duplicates")
    for rel in entries:
        if rel not in file_set:
            fail(f"Bridge TOC runtime file is missing or untracked: {rel}")

    runtime_lua = {
        rel for rel in file_set
        if rel.startswith(BRIDGE_ROOT + "/") and rel.endswith(".lua")
    }
    unlisted = sorted(runtime_lua - set(entries))
    if unlisted:
        fail("Bridge runtime Lua exists outside TOC inventory: " + ", ".join(unlisted))

    for rel in entries:
        source = read_text(rel)
        match = FORBIDDEN_BRIDGE_CALLS.search(source)
        if match:
            fail(f"Bridge must remain recruitment/display-only; forbidden combat/protected/network call in {rel}: {match.group(0).strip()}")
        for token in FORBIDDEN_BRIDGE_TOKENS:
            if token in source:
                fail(f"Bridge must remain recruitment/display-only; forbidden runtime token in {rel}: {token}")

    transport = read_text(f"{BRIDGE_ROOT}/Core/Transport.lua")
    for marker in (
        "local function IsSecretValue(v)",
        "SafeStr = function(v, secretFallback)",
        "C_ChatInfo.InChatMessagingLockdown",
        "CaptureAutoPauseReason",
        "MaybeTriggerScreenshot",
    ):
        if marker not in transport:
            fail(f"Bridge secret/lockdown/capture safety marker missing from Transport.lua: {marker}")

    capture_policy = read_text(f"{BRIDGE_ROOT}/Core/CapturePolicy.lua")
    for marker in (
        'return "dungeon-active"',
        'return "party-full"',
        "return sessionActive and hasRoster",
    ):
        if marker not in capture_policy:
            fail(f"Bridge recruitment auto-pause contract drifted: {marker}")

    screenshot = read_text(f"{BRIDGE_ROOT}/Core/ScreenshotController.lua")
    for marker in (
        "PHASE_WAITING",
        "SCREENSHOT_SUCCEEDED",
        "SCREENSHOT_FAILED",
        "EnsureScreenshotCVars",
        "RestoreScreenshotCVars",
        'SetCVar("screenshotFormat", "png")',
    ):
        if marker not in screenshot:
            fail(f"Bridge serialized screenshot/CVar lease contract drifted: {marker}")


def main() -> int:
    files = git_files()
    file_set = set(files)
    if not files:
        fail("repository contains no tracked files")

    missing = sorted(REQUIRED_FILES - file_set)
    if missing:
        fail("required repository metadata/audit surface is missing: " + ", ".join(missing))

    forbidden_generated = sorted(GENERATED_REPOSITORY_PATHS & file_set)
    if forbidden_generated:
        fail("generated release output must not be tracked: " + ", ".join(forbidden_generated))

    seen: dict[str, str] = {}
    for rel in files:
        if unicodedata.normalize("NFC", rel) != rel:
            fail(f"path is not NFC-normalized: {rel}")
        path = PurePosixPath(rel)
        if path.is_absolute() or ".." in path.parts:
            fail(f"unsafe tracked path: {rel}")
        if any(part in FORBIDDEN_PATH_PARTS for part in path.parts):
            fail(f"generated/local directory must not be tracked: {rel}")
        if path.suffix.lower() in FORBIDDEN_TRACKED_SUFFIXES or rel.endswith("~"):
            fail(f"generated/sensitive file must not be tracked: {rel}")
        key = rel.casefold()
        if key in seen and seen[key] != rel:
            fail(f"case-colliding tracked paths: {seen[key]} / {rel}")
        seen[key] = rel
        if (ROOT / rel).is_symlink():
            fail(f"symlinks are not allowed: {rel}")
        if path.suffix.lower() in BINARY_SOURCE_SUFFIXES:
            continue
        text = read_text(rel)
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                fail(f"possible {label} committed in {rel}")

    validate_bridge_runtime(file_set)

    version = canonical_version()
    require_exact_line("companion/source/app/keystonelens_companion/__init__.py", f'__version__ = "{version}"')
    require_exact_line(BRIDGE_TOC, f"## Version: {version}")
    require_exact_line("companion/source/data-addon/KeystoneLensCompanionData/KeystoneLensCompanionData.toc", f"## Version: {version}")

    sign_source = read_text("companion/source/installer/windows/sign-release.ps1")
    if re.search(r"(?m)^\$Version\s*=\s*'\d+\.\d+\.\d+'\s*$", sign_source):
        fail("sign-release.ps1 must read the canonical VERSION instead of hard-coding a release")
    if "Get-Content -LiteralPath $VersionFile" not in sign_source:
        fail("sign-release.ps1 is not bound to the canonical VERSION file")

    workflow_paths = [rel for rel in files if rel.startswith(".github/workflows/") and rel.endswith((".yml", ".yaml"))]
    for rel in workflow_paths:
        text = read_text(rel)
        if "permissions:" not in text:
            fail(f"workflow must declare permissions explicitly: {rel}")
        for trigger in HIGH_RISK_WORKFLOW_TRIGGERS:
            if trigger in text:
                fail(f"high-risk workflow trigger {trigger[:-1]} is not approved: {rel}")
        if re.search(r"\$\{\{\s*github\.event\.pull_request\.", text):
            fail(f"untrusted pull-request metadata interpolation detected in workflow: {rel}")
        for uses in re.findall(r"^\s*-?\s*uses:\s*([^\s#]+)", text, re.M):
            if uses.startswith(("./", "docker://")):
                continue
            if "@" not in uses or not re.fullmatch(r"[0-9a-f]{40}", uses.rsplit("@", 1)[1]):
                fail(f"workflow action must be pinned to a full commit SHA: {rel}: {uses}")
        if re.search(r"(?:curl|wget)[^\n|]*\|\s*(?:ba)?sh\b", text):
            fail(f"download-to-shell pattern detected: {rel}")

    release_workflow = read_text(".github/workflows/rebuild-keystonelens.yml")
    if "git push origin" in release_workflow or "git commit -m" in release_workflow:
        fail("release workflow must publish release assets instead of committing generated binaries to main")
    if "refs/tags/v" not in release_workflow:
        fail("release workflow must have an explicit tag-only public release gate")
    if "KEYSTONELENS_PFX_BASE64" not in release_workflow or "KEYSTONELENS_PFX_PASSWORD" not in release_workflow:
        fail("tag release must fail closed behind the configured signing secrets")

    print(
        f"ok - KeystoneLens repository audit passed ({len(files)} tracked files; version {version}; "
        "Bridge inventory/Midnight scope/workflow security enforced)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
