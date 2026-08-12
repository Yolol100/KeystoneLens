# KeystoneLens 0.12.5 — release hardening

0.12.5 keeps the 0.12.4 Season 2 compatibility behavior and hardens malformed transport input, external-data caches, numerical score validation and Windows install/uninstall safety.

## Changes
- Rejects truncated/malformed APS1 QR transport data without uncontrolled indexing errors.
- Rejects non-finite score evidence so corrupted `NaN`/`Inf` data cannot become a high KL contribution.
- Bounds Raider.IO profile caches by TTL and entry count and rejects future-dated cache timestamps.
- Validates Warcraft Logs cache evidence before it can reach scoring.
- Refuses uninstall when the uninstaller is not running from the expected KeystoneLens per-user install directory.
- Validates Windows profile/temp paths before setup changes state.
- Updates the dedicated runtime to CPython 3.13.15 x64 with the official python.org SHA-256 pinned in Setup/SBOM.
- Retains 12.0.7/12.1.0 TOC transition compatibility and the Midnight Season 2 dungeon/WCL registry from 0.12.4.

## External release gates
- Authenticode signing still requires the publisher certificate/private key.
- Native Windows install/update/repair/uninstall acceptance remains required.
- Live Season 2 WoW/WCL validation remains a post-reset runtime gate.
- CurseForge approval can only be confirmed after its actual processor/moderation review.
