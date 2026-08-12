# KeystoneLens 0.12.6 — release hardening

0.12.6 keeps the 0.12.5 Season 2/scoring behavior and tightens transport, state continuity, Windows path trust and shutdown behavior without changing the Bridge wire format.

## Fixed

- Partial Blizzard applicant frames now retain missing applicants even when listing context changes; an incomplete frame can no longer silently delete still-pending rows.
- Partial frames without version metadata retain the last confirmed region/default realm instead of falling back to EU or losing realm context.
- Listing title/comment edits no longer invalidate WCL/Raider.IO evidence when dungeon, key and region are unchanged; real enrichment-context changes clear stale queued work immediately.
- Incomplete QR fragments no longer mask a complete APS1 QR later in the same decode batch or in a later crop/full-image decode pass.
- Setup/uninstall resolve user/system locations through Windows known-folder/system APIs instead of trusting `LOCALAPPDATA`, `APPDATA`, `TEMP`, `SystemRoot` or `WINDIR` for destructive path decisions.
- The uninstaller now initializes COM on a locked OS thread for Known Folder resolution and always frees returned shell allocations correctly.
- Companion shutdown now closes WCL/Raider.IO clients before joining enrichment workers so rate-limit waits/retries are signalled to stop as early as possible.
- CPython installer options explicitly keep PATH/associations/shortcuts/debug symbols/tools/compile-all disabled while retaining the required Tkinter and pip components.
- Runtime terminology now accurately says **dedicated per-user CPython runtime**. It is intentionally not described as the Python embeddable distribution.

## Verification

- 58 automated tests pass from the source root before packaging.
- APS1 parser/fragment fuzz smoke: 30,000 randomized CRC-valid payloads reached only controlled success/`APS1Error` outcomes.
- Windows launcher/uninstaller/bootstrap remain subject to `go vet` and x64 PE/resource checks in the build pipeline.
- Source/master/CurseForge package integrity, nested byte parity and deterministic unsigned builds are rechecked by the release pipeline.

## External gates

Authenticode signing with a real publisher identity, native Windows install/update/repair/uninstall acceptance, live WoW Season 2 validation after the regional reset, and actual CurseForge moderation remain external release gates.
