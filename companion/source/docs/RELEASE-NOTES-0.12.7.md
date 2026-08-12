# KeystoneLens 0.12.7 — package consistency, crash-safe update recovery and API validation

0.12.7 contains the generated data-addon consistency fix plus the later maintenance/hardening fixes, without changing the APS1 wire format or scoring contract.

## Fixed

- The Companion-generated `KeystoneLensCompanionData.toc` no longer references `Media\KeystoneLensIcon`, because the runtime generator only installs `Data.lua` and the TOC itself.
- Restores the last valid `.old` application tree when Setup starts after an interrupted atomic directory swap, instead of deleting the only rollback copy.
- Defers stale `.old` cleanup until the replacement tree has passed staged runtime verification.
- Treats Raider.IO HTTP 200 responses with invalid JSON or missing character identity as transient API errors instead of caching fabricated zero-score evidence.
- Refuses ambiguous automatic WoW Retail screenshot-folder selection when more than one known installation exists; the user must choose the intended `_retail_\Screenshots` folder.
- Crash logs include timestamp, fatal severity, component and product version while remaining size-bounded.

## Verification added

- Regression coverage keeps generated TOC metadata limited to files the runtime actually installs.
- Deterministic Raider.IO/WCL failure-matrix tests cover timeout/offline, auth errors, rate limits, common HTTP 5xx responses and TLS-verification hygiene.
- Added a regression gate for the interrupted installer swap window.
- Added atomic config/CompanionData write-failure tests and custom-drive/Unicode/manual WoW path tests.
- Existing APS1, lifecycle, cache-boundary, release-contract and package tests remain required.

## Compatibility

- APS1 wire format and snapshot versions are unchanged.
- Retail interface compatibility remains `120007, 120100`.
- Season 2 dungeon/service mappings and score behavior are unchanged.
- Existing user configuration and generated tooltip-cache schema are unchanged.

Native Windows install/repair/upgrade/uninstall, Authenticode and live WoW client acceptance remain separate target-runtime gates.
