from __future__ import annotations

from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2]
AUDIT = SOURCE_ROOT / "scripts/audit_repository.py"

# These are the executable/text runtime surfaces delivered by the portable product.
PRODUCTION_ROOTS = [
    SOURCE_ROOT / "app/keystonelens_companion",
    SOURCE_ROOT / "portable",
]

TEXT_SUFFIXES = {".py", ".ps1", ".cmd", ".sh", ".lua", ".toml", ".json", ".txt"}
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


def test_legitimate_windows_secret_and_single_instance_apis_remain_allowed():
    config = (SOURCE_ROOT / "app/keystonelens_companion/config.py").read_text(encoding="utf-8")
    launcher = (SOURCE_ROOT / "portable/portable_launcher.py").read_text(encoding="utf-8")
    assert "CryptProtectData" in config and "CryptUnprotectData" in config
    assert "CreateMutexW" in launcher
    assert 'MUTEX_NAME = "KeystoneLens.Companion.Singleton"' in launcher
