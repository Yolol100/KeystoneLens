# Changelog

## 0.12.8 — Tooltip-context correctness and production release hardening

- Bound cached KL tooltip scores to the exact Group Finder activity, target key level and applicant specialization.
- Isolated schema-v2 tooltip data in `KeystoneLensTooltipCacheV2` and clear the legacy name-only global so rollback to an older Bridge fails closed.
- Promoted the corrected build to a unique `0.12.8` release identity instead of rebuilding changed bytes under `0.12.7`.
- Added canonical `companion/source/VERSION` validation across Companion, Bridge, generated data addon, Windows PE metadata, signing and release filenames.
- Bound the Raider.IO HTTP User-Agent to the canonical Companion version.
- Confirmed the Midnight Season 2 dungeon rotation in the season registry and retain Warcraft Logs zone 56 pending first-live validation.
- Run release CI against the same exact production runtime dependency versions as the shipped Windows runtime.
- Build release payloads twice and require deterministic SHA-256 output.
- Removed generated ZIP/EXE/checksum artifacts from `main`; tagged builds now create release assets instead of bot commits to the source branch.
- Added repository hygiene enforcement, GitHub Actions dependency maintenance, explicit license-scope documentation and structured bug-report metadata.
- Require `v<VERSION>` parity, immutable Action SHA pins, release provenance attestations and SHA-256 checksums.
- Made public Windows tag releases fail closed behind a real Authenticode signing identity; payload binaries are signed before Setup is rebuilt and signed.
- Create GitHub Releases as drafts so live WoW and clean-Windows acceptance remain explicit final publication gates.

Full pre-0.12.8 history is retained in `HISTORY.md`. Version-specific release notes remain in `RELEASE-NOTES-<VERSION>.md`.
