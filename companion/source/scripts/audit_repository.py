#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = ROOT / "companion/source"
VERSION_FILE = SOURCE_ROOT / "VERSION"
BRIDGE_ROOT = "addon/KeystoneLensBridge"
BRIDGE_TOC = f"{BRIDGE_ROOT}/KeystoneLensBridge.toc"
MAX_TEXT_BYTES = 2 * 1024 * 1024
BINARY_SOURCE_SUFFIXES = {".ico", ".tga", ".png", ".jpg", ".jpeg", ".gif"}
FORBIDDEN_TRACKED_SUFFIXES = {".zip", ".exe", ".pfx", ".p12", ".pem", ".key", ".pyc", ".pyo", ".log", ".tmp", ".bak", ".orig", ".rej"}
FORBIDDEN_PATH_PARTS = {"__pycache__", ".pytest_cache", ".venv", "venv", ".idea", ".vscode", "build", "release"}
FORBIDDEN_LEGACY_PREFIXES = ("companion/source/installer/", "executable/")
REQUIRED_FILES = {
    ".editorconfig", ".gitattributes", ".gitignore", ".github/CODEOWNERS", ".github/dependabot.yml",
    ".github/workflows/codeql.yml", ".github/workflows/dependency-audit-pr.yml",
    ".github/workflows/dependency-audit.yml", ".github/workflows/dependency-review.yml",
    ".github/workflows/portable-companion.yml", ".github/workflows/rebuild-keystonelens.yml",
    ".github/workflows/windows-platform.yml", "LICENSE-SCOPE.md", "README.md", "SECURITY.md", BRIDGE_TOC,
    "companion/source/VERSION", "companion/source/runtime/windows-x64.json",
    "companion/source/runtime/requirements-runtime.txt", "companion/source/runtime/requirements-runtime.lock",
    "companion/source/portable/START-COMPANION.cmd", "companion/source/portable/portable_launcher.py",
    "companion/source/portable/build-portable.ps1", "companion/source/scripts/make_deterministic_zip.py",
    "companion/source/docs/LIVE-WOW-ACCEPTATIE.md", "companion/source/docs/OFFICIAL-RELEASE-SOURCES.md",
    "companion/source/docs/UITGAVE-CHECKLIST.md", "companion/source/scripts/audit_repository.py",
    "companion/source/app/tests/test_backend_lifecycle.py", "companion/source/app/tests/test_config_secret_migration.py",
    "companion/source/app/tests/test_filesystem_failures.py", "companion/source/app/tests/test_hardening.py",
    "companion/source/app/tests/test_network_failures.py", "companion/source/app/tests/test_observation_only_boundary.py",
    "companion/source/app/tests/test_qr_backend.py", "companion/source/app/tests/test_release_contract.py",
    "companion/source/app/tests/test_season2.py", "companion/source/app/tests/test_season_transition.py",
}
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b"),
    "OpenAI key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b"),
}
FORBIDDEN_BRIDGE_CALLS = re.compile(r"\b(?:CombatLogGetCurrentEventInfo|UnitAura|UnitHealth|UnitHealthMax|UnitPower|UnitPowerMax|UnitCastingInfo|UnitChannelInfo|UnitPosition|GetPlayerMapPosition|CastSpellByID|CastSpellByName|UseAction|TargetUnit|FocusUnit|SetRaidTarget|SetBinding|SetOverrideBinding|RegisterStateDriver|SendChatMessage|loadstring|RunScript)\s*\(")
FORBIDDEN_BRIDGE_TOKENS = ("COMBAT_LOG_EVENT_UNFILTERED", "SecureActionButtonTemplate", "SecureHandler", "C_UnitAuras.")
FORBIDDEN_BRIDGE_POLICY = re.compile(r"\b(?:patreon|paypal|donat(?:e|ion|ions)|premium|advertis(?:e|ement|ements|ing)|sponsor(?:ed|ship)?)\b", re.I)
FORBIDDEN_COMPANION_AUTOMATION_PATTERNS = {
    "input injection": re.compile(r"\b(?:SendInput|keybd_event|mouse_event)\b"),
    "process memory access": re.compile(r"\b(?:ReadProcessMemory|WriteProcessMemory)\b"),
    "remote process injection": re.compile(r"\b(?:VirtualAllocEx|CreateRemoteThread)\b"),
    "global input hook": re.compile(r"\bSetWindowsHookEx(?:A|W)?\b"),
    "Python input automation dependency": re.compile(r"\b(?:pyautogui|pynput)\b"),
}
HIGH_RISK_WORKFLOW_TRIGGERS = ("pull_request_target:", "repository_dispatch:", "workflow_run:")


def fail(message: str) -> None:
    print(f"error - {message}", file=sys.stderr)
    raise SystemExit(1)


def git_files() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [item.decode("utf-8") for item in raw.split(b"\0") if item]


def read_text(rel: str) -> str:
    data = (ROOT / rel).read_bytes()
    if len(data) > MAX_TEXT_BYTES or b"\0" in data:
        fail(f"unexpected/non-text tracked content: {rel}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        fail(f"tracked text must be UTF-8: {rel}")
    if "\r" in text or (data and not data.endswith(b"\n")):
        fail(f"tracked text must use LF and end with newline: {rel}")
    return text


def canonical_version() -> str:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        fail(f"invalid canonical VERSION: {version!r}")
    return version


def bridge_runtime_entries() -> list[str]:
    entries = []
    for raw in read_text(BRIDGE_TOC).splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            entries.append(f"{BRIDGE_ROOT}/{line.replace(chr(92), '/')}")
    return entries


def validate_bridge_runtime(file_set: set[str]) -> None:
    entries = bridge_runtime_entries()
    if not entries or len(entries) != len(set(entries)):
        fail("Bridge TOC runtime inventory is empty or duplicated")
    for rel in entries:
        if rel not in file_set:
            fail(f"Bridge TOC runtime file is missing: {rel}")
    runtime_lua = {rel for rel in file_set if rel.startswith(BRIDGE_ROOT + "/") and rel.endswith(".lua")}
    unlisted = sorted(runtime_lua - set(entries))
    if unlisted:
        fail("Bridge runtime Lua exists outside TOC inventory: " + ", ".join(unlisted))
    transport_path = f"{BRIDGE_ROOT}/Core/Transport.lua"
    for rel in entries:
        source = read_text(rel)
        match = FORBIDDEN_BRIDGE_CALLS.search(source)
        if match:
            fail(f"Bridge forbidden combat/protected call in {rel}: {match.group(0).strip()}")
        for token in FORBIDDEN_BRIDGE_TOKENS:
            if token in source:
                fail(f"Bridge forbidden runtime token in {rel}: {token}")
        policy = FORBIDDEN_BRIDGE_POLICY.search(source)
        if policy:
            fail(f"Bridge violates in-game policy in {rel}: {policy.group(0)}")
        if rel != transport_path and re.search(r"\bSendAddonMessage\s*\(", source):
            fail(f"addon messaging is approved only in {transport_path}")
    transport = read_text(transport_path)
    if len(re.findall(r"C_ChatInfo\.SendAddonMessage\s*\(", transport)) != 1:
        fail("guarded LibKeystone addon-message surface drifted")
    for marker in ("local function IsSecretValue(v)", "SafeStr = function(v, secretFallback)", "C_ChatInfo.InChatMessagingLockdown", "CaptureAutoPauseReason", "MaybeTriggerScreenshot", 'channel ~= "PARTY"', 'C_ChatInfo.RegisterAddonMessagePrefix', 'C_ChatInfo.SendAddonMessage("LibKS", payload, channel)'):
        if marker not in transport:
            fail(f"Bridge safety marker missing: {marker}")
    capture = read_text(f"{BRIDGE_ROOT}/Core/CapturePolicy.lua")
    for marker in ('return "dungeon-active"', 'return "party-full"', "return sessionActive and hasRoster"):
        if marker not in capture:
            fail(f"Bridge capture boundary drifted: {marker}")
    screenshot = read_text(f"{BRIDGE_ROOT}/Core/ScreenshotController.lua")
    for marker in ("PHASE_WAITING", "SCREENSHOT_SUCCEEDED", "SCREENSHOT_FAILED", "EnsureScreenshotCVars", "RestoreScreenshotCVars", 'SetCVar("screenshotFormat", "png")'):
        if marker not in screenshot:
            fail(f"Bridge screenshot contract drifted: {marker}")


def validate_runtime_contract() -> None:
    try:
        runtime = json.loads(read_text("companion/source/runtime/windows-x64.json"))
        sbom = json.loads(read_text("companion/source/docs/SBOM.cdx.json"))
    except json.JSONDecodeError as exc:
        fail(f"runtime/SBOM JSON invalid: {exc}")
    if runtime.get("platform") != "windows-x64":
        fail("runtime contract platform must be windows-x64")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(runtime.get("python_version", ""))):
        fail("runtime contract Python version invalid")
    if not str(runtime.get("python_url", "")).startswith("https://www.python.org/"):
        fail("runtime contract must use the official Python HTTPS host")
    if not re.fullmatch(r"[0-9a-f]{64}", str(runtime.get("python_sha256", ""))):
        fail("runtime contract SHA-256 invalid")
    components = {str(c.get("name", "")).casefold(): c for c in sbom.get("components", []) if isinstance(c, dict)}
    cpython = components.get("cpython")
    if not cpython or cpython.get("version") != runtime["python_version"]:
        fail("SBOM CPython version differs from runtime contract")
    if runtime["python_sha256"] not in {str(h.get("content", "")).casefold() for h in cpython.get("hashes", []) if isinstance(h, dict)}:
        fail("SBOM CPython hash differs from runtime contract")

    lock = read_text("companion/source/runtime/requirements-runtime.lock")
    app = read_text("companion/source/app/requirements.txt")
    for line in app.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line not in lock:
            fail(f"direct app requirement missing from exact runtime lock: {line}")


def validate_portable_contract() -> None:
    builder = read_text("companion/source/portable/build-portable.ps1")
    launcher = read_text("companion/source/portable/portable_launcher.py")
    workflow = read_text(".github/workflows/portable-companion.yml")
    for marker in ("runtime\\windows-x64.json", "runtime\\requirements-runtime.lock", "scripts\\make_deterministic_zip.py", "Remove-Item -LiteralPath (Join-Path $Runtime 'Scripts')"):
        if marker not in builder:
            fail(f"portable builder contract missing: {marker}")
    if "installer\\windows" in builder:
        fail("portable builder must not depend on the legacy installer tree")
    for marker in ('MUTEX_NAME = "KeystoneLens.Companion.Singleton"', "CreateMutexW", 'RUNTIME_CONTRACT = ROOT / "RUNTIME.json"'):
        if marker not in launcher:
            fail(f"portable launcher contract missing: {marker}")
    for marker in ("Build twice and prove portable determinism", "Portable build is not deterministic", "KeystoneLens-Setup.exe", "runtime\\Scripts\\pip.exe"):
        if marker not in workflow:
            fail(f"portable workflow gate missing: {marker}")


def validate_workflows(files: list[str]) -> None:
    workflow_paths = [rel for rel in files if rel.startswith(".github/workflows/") and rel.endswith((".yml", ".yaml"))]
    for rel in workflow_paths:
        text = read_text(rel)
        if "permissions:" not in text:
            fail(f"workflow must declare permissions: {rel}")
        for trigger in HIGH_RISK_WORKFLOW_TRIGGERS:
            if trigger in text:
                fail(f"high-risk workflow trigger {trigger[:-1]}: {rel}")
        if re.search(r"\$\{\{\s*github\.event\.pull_request\.", text):
            fail(f"untrusted pull-request metadata interpolation: {rel}")
        for uses in re.findall(r"^\s*-?\s*uses:\s*([^\s#]+)", text, re.M):
            if uses.startswith(("./", "docker://")):
                continue
            if "@" not in uses or not re.fullmatch(r"[0-9a-f]{40}", uses.rsplit("@", 1)[1]):
                fail(f"workflow action must be full-SHA pinned: {rel}: {uses}")
        if len(re.findall(r"persist-credentials:\s*false\b", text)) != len(re.findall(r"uses:\s*actions/checkout@[0-9a-f]{40}\b", text)):
            fail(f"every checkout must disable persisted credentials: {rel}")
        if re.search(r"(?:curl|wget)[^\n|]*\|\s*(?:ba)?sh\b", text):
            fail(f"download-to-shell pattern detected: {rel}")
        if re.search(r"runs-on:\s*(?:ubuntu|windows)-latest\b", text):
            fail(f"workflow runner must not use -latest: {rel}")

    dependency_review = read_text(".github/workflows/dependency-review.yml")
    for marker in ("actions/dependency-review-action@a1d282b36b6f3519aa1f3fc636f609c47dddb294", "fail-on-severity: moderate", "runs-on: ubuntu-24.04"):
        if marker not in dependency_review:
            fail(f"dependency-review contract drifted: {marker}")
    codeql = read_text(".github/workflows/codeql.yml")
    for marker in ("concurrency:", "cancel-in-progress: ${{ github.event_name == 'pull_request' }}", "queries: security-extended", "languages: python"):
        if marker not in codeql:
            fail(f"CodeQL contract drifted: {marker}")
    if "language: go" in codeql or "setup-go" in codeql:
        fail("CodeQL must not retain obsolete installer-only Go analysis")

    release = read_text(".github/workflows/rebuild-keystonelens.yml")
    for forbidden in ("KEYSTONELENS_PFX", "sign-windows:", "setup-go", "companion/source/installer/"):
        if forbidden in release:
            fail(f"portable-only release workflow retained legacy installer surface: {forbidden}")
    for marker in ("refs/tags/v", "portable-windows:", "Build portable package twice", "KeystoneLens-Portable-$version-Windows-x64.zip", "KeystoneLens-Setup.exe", "sbom-path:", "--predicate-type https://cyclonedx.org/bom", "--draft"):
        if marker not in release:
            fail(f"portable-only release workflow missing: {marker}")
    validate_match = re.search(r"(?ms)^  validate:\n(.*?)(?=^  portable-windows:\n)", release)
    if not validate_match:
        fail("release workflow must separate unprivileged validation from portable tag build")
    for forbidden in ("id-token: write", "attestations: write", "artifact-metadata: write", "contents: write"):
        if forbidden in validate_match.group(1):
            fail(f"ordinary validation must remain read-only: {forbidden}")


def main() -> int:
    files = git_files(); file_set = set(files)
    missing = sorted(REQUIRED_FILES - file_set)
    if missing:
        fail("required repository surface missing: " + ", ".join(missing))
    legacy = sorted(rel for rel in files if rel.startswith(FORBIDDEN_LEGACY_PREFIXES))
    if legacy:
        fail("obsolete installed-executable source remains tracked: " + ", ".join(legacy))

    seen = {}
    for rel in files:
        if unicodedata.normalize("NFC", rel) != rel:
            fail(f"path is not NFC-normalized: {rel}")
        path = PurePosixPath(rel)
        if path.is_absolute() or ".." in path.parts or any(part in FORBIDDEN_PATH_PARTS for part in path.parts):
            fail(f"unsafe/generated tracked path: {rel}")
        if path.suffix.lower() in FORBIDDEN_TRACKED_SUFFIXES or rel.endswith("~"):
            fail(f"generated/sensitive file must not be tracked: {rel}")
        key = rel.casefold()
        if key in seen and seen[key] != rel:
            fail(f"case-colliding paths: {seen[key]} / {rel}")
        seen[key] = rel
        if (ROOT / rel).is_symlink():
            fail(f"symlinks are not allowed: {rel}")
        if path.suffix.lower() not in BINARY_SOURCE_SUFFIXES:
            text = read_text(rel)
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    fail(f"possible {label} committed in {rel}")
            if rel.startswith(("companion/source/app/keystonelens_companion/", "companion/source/portable/")):
                for label, pattern in FORBIDDEN_COMPANION_AUTOMATION_PATTERNS.items():
                    if pattern.search(text):
                        fail(f"Companion forbidden {label} surface in {rel}")

    validate_bridge_runtime(file_set)
    validate_runtime_contract()
    validate_portable_contract()
    validate_workflows(files)

    version = canonical_version()
    for rel, line in (
        ("companion/source/app/keystonelens_companion/__init__.py", f'__version__ = "{version}"'),
        (BRIDGE_TOC, f"## Version: {version}"),
        ("companion/source/data-addon/KeystoneLensCompanionData/KeystoneLensCompanionData.toc", f"## Version: {version}"),
    ):
        if line not in read_text(rel).splitlines():
            fail(f"release identity mismatch in {rel}: {line}")

    print(f"ok - KeystoneLens repository audit passed ({len(files)} tracked files; version {version}; portable-only Windows distribution enforced)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
