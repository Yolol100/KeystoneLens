# KeystoneLens 0.12.7 — package consistency, crash-safe update recovery and API validation

0.12.7 contains the generated data-addon consistency fix plus the later maintenance/hardening fixes, without changing the APS1 wire format or scoring contract.

## Fixed

- The Companion-generated `KeystoneLensCompanionData.toc` no longer references `Media\KeystoneLensIcon`, because the runtime generator only installs `Data.lua` and the TOC itself.
- Restores the last valid `.old` application tree when Setup starts after an interrupted atomic directory swap, instead of deleting the only rollback copy.
- Defers stale `.old` cleanup until the replacement tree has passed staged runtime verification.
- Treats Raider.IO HTTP 200 responses with invalid JSON or missing character identity as transient API errors instead of caching fabricated zero-score evidence.
- Refuses ambiguous automatic WoW Retail screenshot-folder selection when more than one known installation exists; the user must choose the intended `_retail_\Screenshots` folder.
- Crash logs include timestamp, fatal severity, component and product version while remaining size-bounded.
- A stale but valid snapshot that the engine rejects can no longer cause the screenshot watcher to clear newer pending fragment files.
- Screenshots temporarily blocked by Windows sharing/lock violations remain retryable instead of being permanently retired after three polls; permanent access-denied errors remain bounded.
- Setup launches the Companion before activating the optional WoW watcher, avoiding a redundant double-start race when WoW is already running.
- Settings now exposes a fixed, visible HTTPS attribution link to Raider.IO for public API data.
- Generated tooltip sync failures are visible in the Companion status instead of being silently masked by the normal runtime status.
- First-use `KeystoneLensCompanionData` publication commits `Data.lua` before publishing its TOC, and no-op sync heals missing/corrupt TOC metadata.
- Completing one QR fragment stream no longer deletes restart-recovery screenshots belonging to another incomplete stream.
- The Bridge listing-generation ring persists across `/reload`, so a Companion left running across the reload accepts the fresh listing generation instead of misclassifying it as stale.

## Verification added

- Regression coverage keeps generated TOC metadata limited to files the runtime actually installs.
- Deterministic Raider.IO/WCL failure-matrix tests cover timeout/offline, auth errors, rate limits, common HTTP 5xx responses and TLS-verification hygiene.
- Added a regression gate for the interrupted installer swap window.
- Added atomic config/CompanionData write-failure tests and custom-drive/Unicode/manual WoW path tests.
- Existing APS1, lifecycle, cache-boundary, release-contract and package tests remain required.
- Added stale-generation watcher/fragment preservation, transient lock versus permanent ACL handling, installer launch-order and Raider.IO attribution regressions.
- Expanded the controlled regression suite to 115 tests.
- Kept the prior 100,000-case APS1 adversarial verification and added an independent 50,000-random-input pass, 10,000 out-of-order/duplicate fragmentstream roundtrips and 1,103 truncation boundaries without unexpected productroute exceptions.

## Installer experience hardening

- Setup now uses a clear decision → progress → completion flow in the existing KeystoneLens dark palette.
- Fresh installs choose exactly one launch mode: manual, with Windows, or when a path-validated WoW Retail `Wow.exe` starts.
- Added a lightweight `KeystoneLens-WoW-Watcher.exe` that only accepts `Wow.exe` processes whose full executable path contains the `_retail_` directory. It does not read game memory, inject code or automate gameplay.
- Desktop shortcut creation is optional and defaults off; the Start menu entry remains automatic.
- Runtime download progress now reports real transferred bytes when Content-Length is available, while installation phases share one 0–100 progress bar.
- Added an expandable Details view and a bounded `%LOCALAPPDATA%\KeystoneLens\install.log` containing installation steps and dependency names without credentials.
- Cancel remains available during safe preparation/download/dependency phases and is disabled only for the verified atomic commit phase.
- Normal installer failures are shown in the branded setup flow; the Go bootstrap only falls back to an emergency MessageBox when the PowerShell UI could not report a result.
- The signing and uninstall pipelines now include the WoW launch watcher, and the watcher avoids relaunching the exact installed Companion when it is already running.
- Closing the initial Setup decision screen is reported as cancellation rather than success.
- The embedded PowerShell script is written with a UTF-8 BOM so Windows PowerShell 5.1 renders branded Unicode text deterministically.

## Compatibility

- APS1 wire format and snapshot versions are unchanged.
- Retail interface compatibility remains `120007, 120100`.
- Season 2 dungeon/service mappings and score behavior are unchanged.
- Existing user configuration and generated tooltip-cache schema are unchanged.

Native Windows install/repair/upgrade/uninstall, Authenticode and live WoW client acceptance remain separate target-runtime gates.
