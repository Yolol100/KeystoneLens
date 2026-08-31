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
    ".github/workflows/dependency-review.yml",
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
    "companion/source/app/tests/test_backend_lifecycle.py",
    "companion/source/app/tests/test_config_secret_migration.py",
    "companion/source/app/tests/test_filesystem_failures.py",
    "companion/source/app/tests/test_hardening.py",
    "companion/source/app/tests/test_network_failures.py",
    "companion/source/app/tests/test_observation_only_boundary.py",
    "companion/source/app/tests/test_overlay_click_contract.py",
    "companion/source/app/tests/test_portable_release_contract.py",
    "companion/source/app/tests/test_qr_backend.py",
    "companion/source/app/tests/test_release_contract.py",
    "companion/source/app/tests/test_season2.py",
    "companion/source/app/tests/test_season_transition.py",
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
    r"SendChatMessage|loadstring|RunScript)\s*\("
)
FORBIDDEN_BRIDGE_TOKENS = (
    "COMBAT_LOG_EVENT_UNFILTERED",
    "SecureActionButtonTemplate",
    "SecureHandler",
    "C_UnitAuras.",
)
FORBIDDEN_BRIDGE_POLICY = re.compile(
    r"\b(?:patreon|paypal|donat(?:e|ion|ions)|premium|advertis(?:e|ement|ements|ing)|sponsor(?:ed|ship)?)\b",
    re.I,
)
COMPANION_OBSERVATION_PREFIXES = (
    "companion/source/app/keystonelens_companion/",
    "companion/source/installer/windows/",
    "companion/source/portable/",
)
FORBIDDEN_COMPANION_AUTOMATION_PATTERNS: dict[str, re.Pattern[str]] = {
    "input injection": re.compile(r"\b(?:SendInput|keybd_event|mouse_event)\b"),
    "process memory access": re.compile(r"\b(?:ReadProcessMemory|WriteProcessMemory)\b"),
    "remote process injection": re.compile(r"\b(?:VirtualAllocEx|CreateRemoteThread)\b"),
    "global input hook": re.compile(r"\bSetWindowsHookEx(?:A|W)?\b"),
    "Python input automation dependency": re.compile(r"\b(?:pyautogui|pynput)\b"),
}
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

    transport_path = f"{BRIDGE_ROOT}/Core/Transport.lua"
    for rel in entries:
        source = read_text(rel)
        match = FORBIDDEN_BRIDGE_CALLS.search(source)
        if match:
            fail(f"Bridge must remain recruitment/display-only; forbidden combat/protected call in {rel}: {match.group(0).strip()}")
        for token in FORBIDDEN_BRIDGE_TOKENS:
            if token in source:
                fail(f"Bridge must remain recruitment/display-only; forbidden runtime token in {rel}: {token}")
        policy = FORBIDDEN_BRIDGE_POLICY.search(source)
        if policy:
            fail(f"Bridge violates Blizzard in-game advertising/donation/premium policy in {rel}: {policy.group(0)}")
        if rel != transport_path and re.search(r"\bSendAddonMessage\s*\(", source):
            fail(f"addon messaging is approved only for the guarded LibKeystone shim: {rel}")

    transport = read_text(transport_path)
    addon_send_calls = re.findall(r"C_ChatInfo\.SendAddonMessage\s*\(", transport)
    if len(addon_send_calls) != 1:
        fail(f"guarded LibKeystone addon-message surface drifted: expected 1 send call, got {len(addon_send_calls)}")
    for marker in (
        "local function IsSecretValue(v)",
        "SafeStr = function(v, secretFallback)",
        "C_ChatInfo.InChatMessagingLockdown",
        "CaptureAutoPauseReason",
        "MaybeTriggerScreenshot",
        'channel ~= "PARTY"',
        'IsChatMessagingLockdown()',
        'C_ChatInfo.RegisterAddonMessagePrefix',
        'C_ChatInfo.SendAddonMessage("LibKS", payload, channel)',
    ):
        if marker not in transport:
            fail(f"Bridge secret/lockdown/capture/LibKeystone safety marker missing from Transport.lua: {marker}")

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


def validate_companion_observation_boundary(files: list[str]) -> None:
    for rel in files:
        if not rel.startswith(COMPANION_OBSERVATION_PREFIXES):
            continue
        path = PurePosixPath(rel)
        if path.suffix.lower() in BINARY_SOURCE_SUFFIXES:
            continue
        source = read_text(rel)
        for label, pattern in FORBIDDEN_COMPANION_AUTOMATION_PATTERNS.items():
            match = pattern.search(source)
            if match:
                fail(
                    f"Companion must remain observation/recruitment-only; forbidden {label} "
                    f"surface in {rel}: {match.group(0)}"
                )


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
    validate_companion_observation_boundary(files)

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
        checkout_count = len(re.findall(r"uses:\s*actions/checkout@[0-9a-f]{40}\b", text))
        non_persisting_count = len(re.findall(r"persist-credentials:\s*false\b", text))
        if non_persisting_count != checkout_count:
            fail(
                f"every checkout must set persist-credentials: false: {rel} "
                f"({non_persisting_count}/{checkout_count})"
            )
        if re.search(r"(?:curl|wget)[^\n|]*\|\s*(?:ba)?sh\b", text):
            fail(f"download-to-shell pattern detected: {rel}")
        if re.search(r"runs-on:\s*(?:ubuntu|windows)-latest\b", text):
            fail(f"workflow runner must use an explicit supported OS image, not -latest: {rel}")

    dependency_review = read_text(".github/workflows/dependency-review.yml")
    for marker in (
        "actions/dependency-review-action@a1d282b36b6f3519aa1f3fc636f609c47dddb294",
        "fail-on-severity: moderate",
        "runs-on: ubuntu-24.04",
    ):
        if marker not in dependency_review:
            fail(f"dependency-review workflow contract drifted: {marker}")

    codeql_workflow = read_text(".github/workflows/codeql.yml")
    for marker in (
        "concurrency:",
        "cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
        "queries: security-extended",
    ):
        if marker not in codeql_workflow:
            fail(f"CodeQL workflow hardening contract drifted: {marker}")

    release_workflow = read_text(".github/workflows/rebuild-keystonelens.yml")
    if "git push origin" in release_workflow or "git commit -m" in release_workflow:
        fail("release workflow must publish release assets instead of committing generated binaries to main")
    if "refs/tags/v" not in release_workflow:
        fail("release workflow must have an explicit tag-only public release gate")
    if "KEYSTONELENS_PFX_BASE64" not in release_workflow or "KEYSTONELENS_PFX_PASSWORD" not in release_workflow:
        fail("tag release must fail closed behind the configured signing secrets")
    for marker in (
        "cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
        "sbom-path:",
        "--predicate-type https://cyclonedx.org/bom",
        "KeystoneLens-Portable-${VERSION}-Windows-x64.zip",
    ):
        if marker not in release_workflow:
            fail(f"release workflow missing concurrency/SBOM/portable hardening gate: {marker}")

    validate_match = re.search(r"(?ms)^  validate:\n(.*?)(?=^  portable-windows:\n)", release_workflow)
    if not validate_match:
        fail("release workflow must separate unprivileged validation from portable/tag release jobs")
    validate_block = validate_match.group(1)
    for forbidden in ("id-token: write", "attestations: write", "artifact-metadata: write", "contents: write"):
        if forbidden in validate_block:
            fail(f"ordinary validation job must remain read-only: {forbidden}")

    portable_match = re.search(r"(?ms)^  portable-windows:\n(.*?)(?=^  attest-core:\n)", release_workflow)
    if not portable_match:
        fail("release workflow missing unified portable Windows validation job")
    portable_block = portable_match.group(1)
    for marker in (
        "runs-on: windows-2025",
        "./companion/source/portable/build-portable.ps1",
        "THIRD-PARTY-NOTICES.md",
        "keystonelens-portable-${{ github.sha }}",
    ):
        if marker not in portable_block:
            fail(f"portable Windows release contract drifted: {marker}")
    for forbidden in ("id-token: write", "attestations: write", "artifact-metadata: write", "contents: write"):
        if forbidden in portable_block:
            fail(f"portable validation job must remain read-only: {forbidden}")

    attest_match = re.search(r"(?ms)^  attest-core:\n(.*?)(?=^  sign-windows:\n)", release_workflow)
    if not attest_match:
        fail("release workflow missing isolated tag-only core attestation job")
    attest_block = attest_match.group(1)
    for marker in (
        "if: startsWith(github.ref, 'refs/tags/v')",
        "needs: validate",
        "id-token: write",
        "attestations: write",
        "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6",
    ):
        if marker not in attest_block:
            fail(f"tag-only core attestation contract drifted: {marker}")

    draft_match = re.search(r"(?ms)^  draft-release:\n(.*)$", release_workflow)
    if not draft_match or "- attest-core" not in draft_match.group(1):
        fail("draft release must depend on successful isolated core attestation")
    if "- portable-windows" not in draft_match.group(1):
        fail("draft release must depend on successful portable Windows validation")

    print(
        f"ok - KeystoneLens repository audit passed ({len(files)} tracked files; version {version}; "
        "Bridge/Midnight/Blizzard-policy/Companion+portable-observation/dependency-review/runner/least-privilege/SBOM workflow security enforced)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
