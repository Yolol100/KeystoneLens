from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_lock_is_hash_locked_and_pyzbar_is_gone():
    lock = (ROOT / "installer/windows/requirements-runtime.lock").read_text(encoding="utf-8")
    app_requirements = (ROOT / "app/requirements.txt").read_text(encoding="utf-8")
    installer = (ROOT / "installer/windows/bootstrap/installer.ps1").read_text(encoding="utf-8")
    assert "pyzbar" not in lock.lower() + app_requirements.lower() + installer.lower()
    assert "zxing-cpp==3.1.1" in lock
    assert "--require-hashes" in installer
    assert "--no-deps" in installer
    assert "KeystoneLensRuntime" in installer


def test_installer_exposes_real_repair_path_and_dedicated_runtime():
    installer = (ROOT / "installer/windows/bootstrap/installer.ps1").read_text(encoding="utf-8")
    assert "ModifyPath" in installer
    assert "--repair" in installer
    assert "TargetDir=" in installer and "$PythonDir" in installer
    assert "sys.version_info[:3] == (3, 13, 15)" in installer
    assert "python/3.13.15/python-3.13.15-amd64.exe" in installer
    assert "edec09c4853aeae9ac36efb8c9f95b6b8e2fee65eee56d9767a8b7c69c574403" in installer
    assert "python-3.13.15-amd64.exe" in installer
    for option in (
        "AppendPath=0", "CompileAll=0", "Include_debug=0",
        "Include_symbols=0", "Include_tools=0",
    ):
        assert option in installer


def test_release_version_is_consistent_in_primary_metadata():
    expected = "0.12.7"
    paths = [
        ROOT / "app/keystonelens_companion/__init__.py",
        ROOT / "addon/KeystoneLensBridge/KeystoneLensBridge.toc",
        ROOT / "data-addon/KeystoneLensCompanionData/KeystoneLensCompanionData.toc",
    ]
    for path in paths:
        assert expected in path.read_text(encoding="utf-8"), path


def test_runtime_lock_has_exact_windows_artifact_hashes():
    lock = (ROOT / "installer/windows/requirements-runtime.lock").read_text(encoding="utf-8")
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
    interface_lines = [line.strip() for line in toc.splitlines() if line.startswith("## Interface:")]
    assert interface_lines == ["## Interface: 120007, 120100"]


def test_uninstaller_uses_windows_known_folders_for_cleanup():
    uninstaller = (ROOT / "installer/windows/uninstall/main.go").read_text(encoding="utf-8")
    assert 'NewProc("SHGetKnownFolderPath")' in uninstaller
    for guid_prefix in ("0xF1B32785", "0xA77F5D77", "0xB97D20BB", "0xB4BFCC3A"):
        assert guid_prefix in uninstaller
    assert 'filepath.Join(desktop, "KeystoneLens.lnk")' in uninstaller
    assert 'filepath.Join(startup, "KeystoneLens.lnk")' in uninstaller
    assert 'filepath.Join(programs, "KeystoneLens.lnk")' in uninstaller


def test_launcher_isolated_single_instance_and_job_object_contract():
    launcher = (ROOT / "installer/windows/launcher/main.go").read_text(encoding="utf-8")
    assert "KeystoneLens.Companion.Singleton" in launcher
    assert "PYTHONNOUSERSITE=1" in launcher
    assert '"-I", "-c"' in launcher
    assert "jobObjectLimitKillOnJobClose" in launcher
    assert "AssignProcessToJobObject" in launcher
    assert "PYTHONPATH" in launcher and "PYTHONHOME" in launcher


def test_installer_stops_only_its_own_processes_and_uses_https_timestamp():
    installer = (ROOT / "installer/windows/bootstrap/installer.ps1").read_text(encoding="utf-8")
    signer = (ROOT / "installer/windows/sign-release.ps1").read_text(encoding="utf-8")
    assert "Stop-KeystoneLensProcesses" in installer
    assert "taskkill" not in installer.casefold()
    assert "https://timestamp.digicert.com" in signer
    assert "'/fd','SHA256'" in signer
    assert "'/td','SHA256'" in signer


def test_uninstaller_exact_process_matching_and_explicit_data_policy():
    uninstaller = (ROOT / "installer/windows/uninstall/main.go").read_text(encoding="utf-8")
    assert "QueryFullProcessImageNameW" in uninstaller
    assert "--purge-data" in uninstaller
    assert "--keep-data" in uninstaller
    assert "taskkill" not in uninstaller.casefold()


def test_current_generated_data_toc_is_not_stale():
    source = (ROOT / "app/keystonelens_companion/addon_sync.py").read_text(encoding="utf-8")
    assert '"## Interface: 120007, 120100' in source
    assert "120005" not in source


def test_windows_maintenance_is_single_instance_and_resolves_trusted_system_directory():
    bootstrap = (ROOT / "installer/windows/bootstrap/main.go").read_text(encoding="utf-8")
    uninstaller = (ROOT / "installer/windows/uninstall/main.go").read_text(encoding="utf-8")
    for source in (bootstrap, uninstaller):
        assert "KeystoneLens.Maintenance.Singleton" in source
        assert "WindowsPowerShell" in source
        assert 'NewProc("GetSystemDirectoryW")' in source
        assert 'os.Getenv("SystemRoot")' not in source
        assert 'os.Getenv("WINDIR")' not in source
    assert 'exec.Command("powershell.exe"' not in bootstrap
    assert 'exec.Command("powershell.exe"' not in uninstaller


def test_repair_does_not_copy_setup_onto_itself_and_first_install_rolls_back_cleanly():
    installer = (ROOT / "installer/windows/bootstrap/installer.ps1").read_text(encoding="utf-8")
    assert "$sourceFull" in installer and "$repairFull" in installer
    assert "OrdinalIgnoreCase" in installer
    assert "$script:NewAppApplied = $true" in installer
    assert "-not $ExistingState" in installer
    assert "Invoke-DownloadWithProgress" in installer
    assert "'--timeout','30','--retries','3'" in installer


def test_windows_build_runs_go_vet_in_payload_aware_order():
    source = (ROOT / "installer" / "windows" / "build.sh").read_text(encoding="utf-8")
    assert 'go vet "$WIN/launcher/main.go"' in source
    assert 'go vet "$WIN/uninstall/main.go"' in source
    assert 'go vet "$WIN/wowwatcher/main.go"' in source
    copy_pos = source.index('cp "$BUILD/payload.zip" "$WIN/bootstrap/payload.zip"')
    bootstrap_vet_pos = source.index('go vet "$WIN/bootstrap/main.go"')
    bootstrap_build_pos = source.index('go build "${GOFLAGS[@]}" -o "$BUILD/KeystoneLens-Setup.exe"')
    assert copy_pos < bootstrap_vet_pos < bootstrap_build_pos


def test_windows_setup_and_uninstall_use_known_folders_and_refuse_unsafe_paths():
    installer = (ROOT / "installer/windows/bootstrap/installer.ps1").read_text(encoding="utf-8")
    uninstaller = (ROOT / "installer/windows/uninstall/main.go").read_text(encoding="utf-8")
    assert "[System.IO.Path]::IsPathRooted" in installer
    assert "Windows known-folder paths are unavailable or unsafe" in installer
    assert "SpecialFolder]::LocalApplicationData" in installer
    assert "SpecialFolder]::Programs" in installer
    assert "SpecialFolder]::Startup" in installer
    assert "$env:LOCALAPPDATA" not in installer
    assert "$env:APPDATA" not in installer
    assert "$env:TEMP" not in installer
    assert 'knownFolderPath(&folderIDLocalAppData)' in uninstaller
    assert 'NewProc("CoInitializeEx")' in uninstaller
    assert 'NewProc("CoUninitialize")' in uninstaller
    assert 'runtime.LockOSThread()' in uninstaller
    assert 'CoTaskMemFree' in uninstaller
    assert 'expectedRoot := filepath.Join(local, "Programs", "KeystoneLens")' in uninstaller
    assert 'os.Getenv("LOCALAPPDATA")' not in uninstaller
    assert 'os.Getenv("APPDATA")' not in uninstaller
    assert "strings.EqualFold(filepath.Clean(rootAbs), filepath.Clean(expectedAbs))" in uninstaller
    assert "Nothing was removed" in uninstaller


def test_old_python_installer_cache_is_only_pruned_after_atomic_app_swap():
    installer = (ROOT / "installer/windows/bootstrap/installer.ps1").read_text(encoding="utf-8")
    applied = installer.index("$script:NewAppApplied = $true")
    cleanup = installer.index("Get-ChildItem -LiteralPath $RuntimeRoot -Filter 'python-3.13.*-amd64.exe'")
    assert applied < cleanup
    assert "python-3.13.15-amd64.exe" in installer


def test_interrupted_atomic_swap_recovers_last_good_backup_before_new_install_work():
    installer = (ROOT / "installer/windows/bootstrap/installer.ps1").read_text(encoding="utf-8")
    recovery = "if (-not (Test-Path $InstallDir) -and (Test-Path $BackupDir))"
    assert recovery in installer
    assert installer.index(recovery) < installer.index("$ExistingInstall =")
    # Never discard the only prior valid tree during startup. A stale backup may
    # be replaced only after the newly staged runtime has passed verification.
    first_backup_delete = installer.index("Remove-Item -LiteralPath $BackupDir -Recurse -Force")
    staged_verified = installer.index("Staged runtime verification failed.")
    assert staged_verified < first_backup_delete



def test_installer_has_branded_decision_progress_and_completion_flow():
    installer = (ROOT / "installer/windows/bootstrap/installer.ps1").read_text(encoding="utf-8")
    assert 'xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"' in installer
    assert 'Content="Start manually"' in installer
    assert 'Content="Start with Windows"' in installer
    assert 'Content="Start when World of Warcraft Retail starts"' in installer
    assert 'Content="Create desktop shortcut" IsChecked="False"' in installer
    assert 'Content="Launch KeystoneLens after installation" IsChecked="True"' in installer
    assert 'Header="Details"' in installer
    assert 'Content="Cancel"' in installer
    assert 'Content="Install"' in installer
    assert 'Content="Open KeystoneLens"' in installer
    assert 'KeystoneLens is ready' in installer
    assert 'Installation could not be completed' in installer
    assert '$InstallLog = Join-Path $InstallLogDir \'install.log\'' in installer
    assert 'Format-Bytes' in installer
    assert 'ContentLength' in installer
    assert '$ResultFile' in installer


def test_installer_launch_modes_are_mutually_exclusive_and_wow_watcher_is_path_validated():
    installer = (ROOT / "installer/windows/bootstrap/installer.ps1").read_text(encoding="utf-8")
    watcher = (ROOT / "installer/windows/wowwatcher/main.go").read_text(encoding="utf-8")
    assert installer.count('GroupName="LaunchMode"') == 3
    assert "KeystoneLens-WoW-Watcher.lnk" in installer
    assert "KeystoneLens-WoW-Watcher.exe" in installer
    assert "KeystoneLens.WoWWatcher.Singleton" in watcher
    assert "CreateToolhelp32Snapshot" in watcher
    assert "QueryFullProcessImageNameW" in watcher
    assert 'strings.EqualFold(filepath.Base(path), "Wow.exe")' in watcher
    assert 'strings.EqualFold(part, "_retail_")' in watcher
    assert 'filepath.Join(filepath.Dir(exe), "KeystoneLens.exe")' in watcher
    assert 'processRunningAtPath(target)' in watcher
    assert 'cmd.Process.Release()' in watcher
    assert "taskkill" not in watcher.casefold()


def test_uninstaller_and_signing_pipeline_cover_wow_watcher():
    uninstaller = (ROOT / "installer/windows/uninstall/main.go").read_text(encoding="utf-8")
    build = (ROOT / "installer/windows/build.sh").read_text(encoding="utf-8")
    signer = (ROOT / "installer/windows/sign-release.ps1").read_text(encoding="utf-8")
    verifier = (ROOT / "installer/windows/verify-signatures.ps1").read_text(encoding="utf-8")
    assert 'terminateExactExecutable(filepath.Join(root, "KeystoneLens-WoW-Watcher.exe"))' in uninstaller
    assert 'os.Remove(filepath.Join(startup, "KeystoneLens-WoW-Watcher.lnk"))' in uninstaller
    assert 'go build "${GOFLAGS[@]}" -o "$PAYLOAD/KeystoneLens-WoW-Watcher.exe"' in build
    assert 'KeystoneLens WoW Launch Watcher' in build
    assert 'Invoke-Sign $WoWWatcher' in signer
    assert 'KeystoneLens-WoW-Watcher.exe' in verifier


def test_bootstrap_uses_result_marker_to_avoid_duplicate_normal_error_dialogs():
    bootstrap = (ROOT / "installer/windows/bootstrap/main.go").read_text(encoding="utf-8")
    assert 'resultPath := filepath.Join(temp, "result.txt")' in bootstrap
    assert "0xEF, 0xBB, 0xBF" in bootstrap
    assert '"-ResultFile", resultPath' in bootstrap
    assert 'status == "failed"' in bootstrap
    assert 'status == "canceled"' in bootstrap
    assert 'os.Exit(1)' in bootstrap
    assert 'os.Exit(2)' in bootstrap





def test_closing_setup_before_install_is_reported_as_cancellation():
    installer = (ROOT / "installer/windows/bootstrap/installer.ps1").read_text(encoding="utf-8")
    assert "Closing the decision page is a user cancellation, not a successful setup." in installer
    closing = installer.index("$window.add_Closing({")
    canceled = installer.index("$script:InstallCanceled = $true", closing)
    status = installer.index("$status = if ($script:InstallSucceeded)", closing)
    assert closing < canceled < status

def test_installer_xaml_is_well_formed_xml_with_x_namespace():
    installer = (ROOT / "installer/windows/bootstrap/installer.ps1").read_text(encoding="utf-8")
    marker = "[xml]$xaml = @'\n"
    start = installer.index(marker) + len(marker)
    end = installer.index("\n'@\n", start)
    xaml = installer[start:end]
    root = ET.fromstring(xaml)
    assert root.tag.endswith("Window")
    assert 'xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"' in xaml


def test_setup_launches_companion_before_starting_wow_watcher_to_avoid_double_start_race():
    installer = (ROOT / "installer/windows/bootstrap/installer.ps1").read_text(encoding="utf-8")
    success = installer.index("$script:InstallSucceeded = $true")
    launch_after = installer.index("if ($script:LaunchAfterInstall", success)
    watcher_start = installer.index("Start-WoWWatcherIfRequested", success)
    assert launch_after < watcher_start


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
    assert 'cursor="hand2"' in source
    assert 'bind("<Button-1>", lambda _event: open_raider_io())' in source


def test_bridge_listing_generation_survives_reload_in_saved_variables():
    state = (ROOT / "addon/KeystoneLensBridge/Core/TransportState.lua").read_text(encoding="utf-8")
    transport = (ROOT / "addon/KeystoneLensBridge/Core/Transport.lua").read_text(encoding="utf-8")
    assert "listingGeneration = 0," in state
    assert "KeystoneLensBridgeDB.listingGeneration" in transport
    assert "listingGeneration = savedListingGeneration" in transport
    assert "KeystoneLensBridgeDB.listingGeneration = listingGeneration" in transport
