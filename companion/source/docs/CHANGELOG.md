# Changelog

## 0.12.8 — Tooltip-context correctness and release integrity

- Bound cached KL tooltip scores to the exact Group Finder activity, target key level and applicant specialization.
- Isolated schema-v2 tooltip data in `KeystoneLensTooltipCacheV2` and clear the legacy name-only global so rollback to an older Bridge fails closed.
- Promoted the corrected build to a unique `0.12.8` release identity instead of rebuilding changed bytes under `0.12.7`.
- Added canonical `companion/source/VERSION` validation across Companion, Bridge, generated data addon, Windows PE metadata, installer source archive and release filenames.
- Bound the Raider.IO HTTP User-Agent to the canonical Companion version so runtime requests cannot report stale release identity.
- Confirmed the official Midnight Season 2 dungeon rotation in the season registry and retain Warcraft Logs zone 56 as the Season 2 source pending first-live validation.
- Run release CI against the same exact production runtime dependency versions as the shipped Windows runtime.
- Build the release twice and require deterministic SHA-256 output before publication.
- Add version-matched release notes/audit evidence, repository security/code-ownership metadata and main-build artifact provenance attestations.
- Keep Authenticode signing, clean-Windows acceptance and live WoW Retail Season 2 acceptance as explicit external release gates.

Full pre-0.12.8 history is retained in `HISTORY.md`. Version-specific release notes remain in `RELEASE-NOTES-<VERSION>.md`.
