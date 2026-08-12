# KeystoneLens 0.12.2 release notes

## Companion
- KL score range filtering from 0 to 100 with a compact dual-handle control; default visibility remains 84–100 until the user deliberately changes the range.
- Class and Role filters can be combined with the score range.
- Settings now controls visibility of Role, Class, Spec, Raider.IO and Warcraft Logs columns.
- Class/Role filters automatically disappear when their corresponding column is hidden.
- Hidden Raider.IO/WCL columns do not alter the underlying 50/50 KL score.
- Added Reset filters, active-filter count, result count, clearer empty states and automatic table reflow.
- Display preferences persist without restarting network/watcher services.

## Reliability
- Fixed the APS1 v12/v13 applicant parser to consume the single `application_member_count` byte exactly as emitted by the Bridge; non-empty current snapshots no longer shift the Blizzard fallback fields.
- QR/screenshot input, fragment streams, decode-failure bookkeeping and pending-delete bookkeeping now have explicit resource bounds.
- Raider.IO/WCL shutdown now prevents late post-close cache/state writes after in-flight requests.
- Crash-log size is bounded.
- Screenshot directory scans now tolerate files disappearing during a polling pass.
- Runtime reconfiguration cleanly stops the previous watcher before applying a new setup.
- Removed obsolete code that hid Blizzard's screenshot status.
- Score-slider keyboard navigation no longer traps Tab focus.

## Windows setup
- Setup/Repair/Uninstall share a maintenance mutex so destructive operations cannot overlap.
- Launcher uses a per-user single-instance mutex, isolated Python startup and a kill-on-close Windows Job Object.
- Installer/uninstaller stop only KeystoneLens processes resolved to the installed path and invoke required Windows system tools from System32.
- Fixed Repair self-copy handling and cleanup of a failed first install after the staged application was applied.
- Replaced the old `pyzbar` decoder with `zxing-cpp 3.1.1`, which has a current Windows x64 ABI3 wheel suitable for CPython 3.13.
- CPython now installs into a KeystoneLens-dedicated per-user runtime namespace instead of a generic Python program directory.
- The complete runtime dependency graph is version-pinned and wheel-hash-locked; pip runs isolated against the explicit PyPI HTTPS index.
- Installed Apps now exposes a real Repair/Modify path; update/repair preserves the existing Desktop/autostart choices.
- Uninstall now resolves the Windows Desktop Known Folder so a shortcut on a redirected/OneDrive Desktop is removed correctly.
- Setup, launcher and uninstaller now carry deterministic icon, VERSIONINFO and DPI-aware/asInvoker manifest resources.
- Added a small x64 bootstrap Setup.exe.
- Branded progress flow: prepare, download, verify, install, configure, ready.
- Official Python runtime download is SHA-256 checked before installation.
- Dependencies install into an application-local package directory.
- Updates are staged and verified before swapping the installed app, with rollback of the previous app when possible.
- Start Menu registration and Installed Apps uninstall entry.
- Finish options: Start KeystoneLens, Desktop shortcut, Start with Windows (opt-in).
- `/S`, `/silent` or `--silent` starts silent setup; the uninstaller supports the same silent switches.
- Silent setup now returns a failure exit code correctly; installer update rollback also covers the narrow pre-swap failure window.
- Added a deterministic Windows build script so identical sources reproduce the same bootstrap payload/build output in the current toolchain.

## WoW / CurseForge
- CurseForge upload archive contains only `KeystoneLensBridge/` and its addon files.
- Companion executable is intentionally excluded from the CurseForge addon ZIP.
- Capture pauses when recruitment is no longer active according to the in-game lifecycle policy (including full normal party and party dungeon state).
- Closing the external Companion cannot be signalled live back into a running WoW addon with the current one-way screenshot transport; this remains a documented runtime limitation.

## Release package
- Master release includes a deterministic source snapshot for audit/rebuild/signing workflows.
- The nested CurseForge ZIP remains clean and contains no Windows executable.
