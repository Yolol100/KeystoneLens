from __future__ import annotations

from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2]
AUDIT = SOURCE_ROOT / "scripts/audit_repository.py"

# These roots exist both in the repository and in the verified source archive.
PRODUCTION_ROOTS = [
    SOURCE_ROOT / "app/keystonelens_companion",
    SOURCE_ROOT / "installer/windows",
]

# The repository also contains a top-level executable source tree. Include it when
# this test runs from a full checkout, but do not require it from the intentionally
# scoped source release archive.
REPO_ROOT = SOURCE_ROOT.parents[1]
REPO_EXECUTABLE = REPO_ROOT / "executable"
if REPO_EXECUTABLE.exists():
    PRODUCTION_ROOTS.append(REPO_EXECUTABLE)

TEXT_SUFFIXES = {".py", ".go", ".ps1", ".sh", ".lua", ".toml", ".json", ".txt"}
FORBIDDEN_TOKENS = (
    "SendInput",
    "keybd_event",
    "mouse_event",
    "ReadProcessMemory",
    "WriteProcessMemory",
    "VirtualAllocEx",
    "CreateRemoteThread",
    "SetWindowsHookEx",
    "pyautogui",
    "pynput",
)


def _production_sources():
    for root in PRODUCTION_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.casefold() in TEXT_SUFFIXES:
                yield path


def test_observation_only_boundary_is_machine_enforced():
    source = AUDIT.read_text(encoding="utf-8")
    assert "validate_companion_observation_boundary(files)" in source
    for token in FORBIDDEN_TOKENS:
        assert token in source, f"repository audit no longer guards {token}"


def test_production_companion_has_no_input_or_process_memory_automation():
    checked = 0
    for path in _production_sources():
        checked += 1
        source = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_TOKENS:
            assert token not in source, f"forbidden automation/process surface {token} in {path}"
    assert checked > 0, "observation-only scan did not inspect production source"


def test_legitimate_windows_observation_and_secret_apis_remain_allowed():
    config = (SOURCE_ROOT / "app/keystonelens_companion/config.py").read_text(encoding="utf-8")
    watcher = (SOURCE_ROOT / "installer/windows/wowwatcher/main.go").read_text(encoding="utf-8")
    assert "CryptProtectData" in config and "CryptUnprotectData" in config
    assert "QueryFullProcessImageNameW" in watcher
    assert "CreateToolhelp32Snapshot" in watcher
