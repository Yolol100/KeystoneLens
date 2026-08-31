from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ROOT.parents[1]


def test_runtime_lock_is_hash_locked_and_pyzbar_is_gone():
    lock = (ROOT / "runtime/requirements-runtime.lock").read_text(encoding="utf-8")
    app_requirements = (ROOT / "app/requirements.txt").read_text(encoding="utf-8")
    builder = (ROOT / "portable/build-portable.ps1").read_text(encoding="utf-8")
    assert "pyzbar" not in (lock + app_requirements + builder).lower()
    assert "zxing-cpp==3.1.1" in lock
    assert "--require-hashes" in builder
    assert "--no-deps" in builder


def test_portable_runtime_contract_is_canonical_and_hash_pinned():
    runtime = json.loads((ROOT / "runtime/windows-x64.json").read_text(encoding="utf-8"))
    assert runtime == {
        "platform": "windows-x64",
        "python_version": "3.13.15",
        "python_url": "https://www.python.org/ftp/python/3.13.15/python-3.13.15-amd64.exe",
        "python_sha256": "edec09c4853aeae9ac36efb8c9f95b6b8e2fee65eee56d9767a8b7c69c574403",
    }


def test_portable_builder_has_no_legacy_installer_dependency_and_removes_build_only_pip():
    source = (ROOT / "portable/build-portable.ps1").read_text(encoding="utf-8")
    assert "runtime\\windows-x64.json" in source
    assert "runtime\\requirements-runtime.lock" in source
    assert "scripts\\make_deterministic_zip.py" in source
    assert "installer\\windows" not in source
    assert "Remove-Item -LiteralPath (Join-Path $Runtime 'Scripts')" in source
    assert "Lib\\site-packages\\pip" in source
    for name in ("KeystoneLens-Setup.exe", "KeystoneLens.exe", "KeystoneLens-Uninstall.exe", "KeystoneLens-WoW-Watcher.exe"):
        assert name in source


def test_portable_launcher_preserves_single_instance_and_runtime_readback():
    source = (ROOT / "portable/portable_launcher.py").read_text(encoding="utf-8")
    assert 'MUTEX_NAME = "KeystoneLens.Companion.Singleton"' in source
    assert "CreateMutexW" in source
    assert 'RUNTIME_CONTRACT = ROOT / "RUNTIME.json"' in source
    assert "expected_python_version" in source
    assert "subprocess" not in source


def test_portable_workflow_builds_twice_and_forbids_custom_executables():
    source = (REPO_ROOT / ".github/workflows/portable-companion.yml").read_text(encoding="utf-8")
    assert "Build twice and prove portable determinism" in source
    assert "Portable build is not deterministic" in source
    assert "runtime\\Scripts\\pip.exe" in source
    for name in ("KeystoneLens-Setup.exe", "KeystoneLens.exe", "KeystoneLens-Uninstall.exe", "KeystoneLens-WoW-Watcher.exe"):
        assert name in source


def test_legacy_installed_executable_stack_is_removed():
    assert not (ROOT / "installer").exists()
    assert not (REPO_ROOT / "executable").exists()


def test_release_workflow_publishes_portable_not_setup():
    source = (REPO_ROOT / ".github/workflows/rebuild-keystonelens.yml").read_text(encoding="utf-8")
    assert "portable-windows:" in source
    assert "Build portable package twice" in source
    assert "KeystoneLens-Portable-$version-Windows-x64.zip" in source
    assert "KeystoneLens-Setup" not in source
    assert "KEYSTONELENS_PFX" not in source
    assert "sign-windows:" not in source
    assert "setup-go" not in source


def test_release_version_is_consistent_in_primary_metadata():
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    for path in (
        ROOT / "app/keystonelens_companion/__init__.py",
        ROOT / "addon/KeystoneLensBridge/KeystoneLensBridge.toc",
        ROOT / "data-addon/KeystoneLensCompanionData/KeystoneLensCompanionData.toc",
    ):
        assert expected in path.read_text(encoding="utf-8"), path


def test_runtime_lock_has_exact_windows_artifact_hashes():
    lock = (ROOT / "runtime/requirements-runtime.lock").read_text(encoding="utf-8")
    expected = {
        "requests==2.34.2": "2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0",
        "Pillow==12.3.0": "1cca606cd25738df4ed873d5ad46bbdb3d83b5cbca291f6b4ff13a4df6b0bbe8",
        "zxing-cpp==3.1.1": "29f98a91148171460b47a942d137ecc90c4b8097636f23cca65263a56bb025d3",
        "charset-normalizer==3.4.9": "fe2c7201c642b7c308f1675355ad7ff7b66acfe3541625efe5a3ad38f29d6115",
        "idna==3.18": "7f952cbe720b688055e3f87de14f5c3e5fdaa8bc3928985c4077ca689de849a2",
        "urllib3==2.7.0": "9fb4c81ebbb1ce9531cce37674bbc6f1360472bc18ca9a553ede278ef7276897",
        "certifi==2026.7.22": "62f22742b58a1a33014a2b6b706588a8d7e2a88ae7bd1a6ebe8c992928483775",
    }
    for package, digest in expected.items():
        assert package in lock
        assert f"--hash=sha256:{digest}" in lock
    assert lock.count("--hash=sha256:") == len(expected)


def test_retail_toc_supports_120007_to_120100_transition():
    toc = (ROOT / "addon/KeystoneLensBridge/KeystoneLensBridge.toc").read_text(encoding="utf-8")
    assert [line.strip() for line in toc.splitlines() if line.startswith("## Interface:")] == ["## Interface: 120007, 120100"]


def test_current_generated_data_toc_is_not_stale():
    source = (ROOT / "app/keystonelens_companion/addon_sync.py").read_text(encoding="utf-8")
    assert '"## Interface: 120007, 120100' in source
    assert "120005" not in source


def test_settings_exposes_user_visible_raider_io_attribution_link():
    from keystonelens_companion import ui
    assert ui.RAIDER_IO_URL == "https://raider.io"
    opened = []
    original = ui.webbrowser.open_new_tab
    try:
        ui.webbrowser.open_new_tab = lambda url: opened.append(url) or True
        assert ui.open_raider_io() is True
    finally:
        ui.webbrowser.open_new_tab = original
    assert opened == ["https://raider.io"]
    source = Path(ui.__file__).read_text(encoding="utf-8")
    assert 'text="Data by Raider.IO • raider.io"' in source


def test_bridge_listing_generation_survives_reload_in_saved_variables():
    state = (ROOT / "addon/KeystoneLensBridge/Core/TransportState.lua").read_text(encoding="utf-8")
    transport = (ROOT / "addon/KeystoneLensBridge/Core/Transport.lua").read_text(encoding="utf-8")
    assert "listingGeneration = 0," in state
    assert "KeystoneLensBridgeDB.listingGeneration" in transport
    assert "listingGeneration = savedListingGeneration" in transport
    assert "KeystoneLensBridgeDB.listingGeneration = listingGeneration" in transport
