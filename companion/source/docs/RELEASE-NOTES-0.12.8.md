# KeystoneLens 0.12.8

0.12.8 is a correctness, Season 2 readiness and production-release hardening update. It does not add user-facing settings or scoring features.

## Runtime fixes

- Tooltip cache schema v2 remains bound to the exact Group Finder activity, target key level and applicant specialization.
- Schema v2 uses `KeystoneLensTooltipCacheV2` and explicitly clears the legacy `KeystoneLensTooltipCache` global. An older Bridge therefore fails closed instead of interpreting new v2 data with former name-only cache logic after a rollback.
- Raider.IO runtime requests derive their User-Agent version from the canonical Companion `__version__`.
- The Midnight Season 2 registry matches Blizzard's eight-dungeon rotation. Warcraft Logs zone 56 is retained for Season 2; first-live parse verification remains an acceptance gate.

## Release/product hardening

- `companion/source/VERSION` is the canonical Companion, Bridge, data-addon, Windows metadata and artifact version source.
- `sign-release.ps1` now reads that canonical version instead of carrying a stale hard-coded release number.
- Generated ZIPs, checksums and Windows executables are no longer stored on `main`; tagged builds publish them as release assets.
- Repository hygiene now has explicit `.gitignore`, `.gitattributes`, `.editorconfig`, release-output/secret checks and GitHub Actions dependency maintenance.
- A repository audit rejects generated binaries, local build/cache output, common secret/key patterns, version drift, mutable/unpinned Actions and workflows that try to commit release artifacts back to `main`.
- CI release validation uses the same exact production dependency versions as the Windows runtime lock, compiles Lua, runs the full Python suite and proves deterministic packaging with two builds.
- Public tag releases require `v<VERSION>` parity and fail closed unless the real publisher signing secrets are configured.
- Windows public-release builds sign and RFC 3161 timestamp the three payload executables first, rebuild Setup with that signed payload, sign Setup and verify every signature.
- Final tagged assets receive SHA-256 checksums and GitHub artifact attestations; the workflow creates a draft GitHub Release rather than publishing before live acceptance.
- `LICENSE-SCOPE.md` documents the existing Bridge/third-party license boundary without inventing a repository-wide Companion/installer license.

## Release gates still external

- Native clean-Windows install/repair/uninstall and SmartScreen/AV behavior remain runtime acceptance gates.
- A real publisher signing identity must be securely configured before the tag workflow can produce a public Windows release.
- Live World of Warcraft Midnight Season 2 Group Finder/screenshot/tooltip validation remains a live-client acceptance gate.
- Warcraft Logs Season 2 must be rechecked against first-live parses before full production acceptance.
- The draft GitHub Release and CurseForge file should be published as Release only after those live gates pass; until then use preview/Beta distribution where appropriate.
