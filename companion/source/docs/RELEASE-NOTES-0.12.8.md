# KeystoneLens 0.12.8

0.12.8 is a correctness, Season 2 readiness and production-release hardening update. It does not add user-facing settings or scoring features.

## Runtime fixes

- Tooltip cache schema v2 remains bound to the exact Group Finder activity, target key level and applicant specialization.
- Schema v2 uses `KeystoneLensTooltipCacheV2` and explicitly clears the legacy `KeystoneLensTooltipCache` global. An older Bridge therefore fails closed instead of interpreting new v2 data with former name-only cache logic after a rollback.
- Raider.IO runtime requests derive their User-Agent version from the canonical Companion `__version__`.
- The Midnight Season 2 registry matches Blizzard's eight-dungeon rotation and was re-verified on the EU launch date, 2026-08-19. Warcraft Logs zone 56 is retained for Season 2.
- Week-one WCL behavior intentionally remains Season-1 carry-over. At the launch-day review the public Warcraft Logs zone 56 surface was still labelled `Mythic+ Season 2 (PTR)`, so KeystoneLens does not promote date alone into proof that current Season-2 ranking evidence is production-ready. Carry-over evidence is source-stamped, never written into the normal Season-2 dungeon cache and becomes invalid automatically at the week-two cutover.
- Raider.IO's addon source changed its internal previous-score decoder from 12 to 13 bits on launch day. KeystoneLens does not consume those encoded bit positions; its reviewed local Bridge contract still reads Raider.IO's public profile table and the Companion uses the Raider.IO HTTP API. No score-parser change is required from that upstream implementation fix.
- The Bridge remains explicitly recruitment/display-only. Its repository audit now rejects new combat-log, aura, health/power, cast, position, protected-action, target/focus, raid-marker and chat-automation surfaces from the tracked WoW runtime.
- The existing LibKeystone compatibility message is intentionally narrow: one fixed `LibKS` send surface, `PARTY` only, grouped only and blocked during Chat Messaging Lockdown. The audit rejects addon-message expansion outside that reviewed shim.
- The tracked Bridge runtime must match the TOC inventory exactly; unlisted runtime Lua or missing TOC files fail the release audit.
- Existing secret-value guards, dungeon/party-full auto-pause boundaries and the serialized screenshot/CVar lease are now permanent audited contracts rather than convention-only behavior.
- Blizzard's Patch 12.1 Group Finder fixes do not weaken those fail-closed guards; transient/secret/partial LFG reads remain treated as untrusted even if the upstream UI refresh bug is fixed.

## Release/product hardening

- `companion/source/VERSION` is the canonical Companion, Bridge, data-addon, Windows metadata and artifact version source.
- `sign-release.ps1` now reads that canonical version instead of carrying a stale hard-coded release number.
- Generated ZIPs, checksums and Windows executables are no longer stored on `main`; tagged builds publish them as release assets.
- Repository hygiene now has explicit `.gitignore`, `.gitattributes`, `.editorconfig`, release-output/secret checks and GitHub Actions dependency maintenance.
- A repository audit rejects generated binaries, local build/cache output, common secret/key patterns, version drift, mutable/unpinned Actions and workflows that try to commit release artifacts back to `main`.
- The audit also protects its own critical verification surface, rejects high-risk Actions triggers and direct untrusted pull-request metadata interpolation, and requires every checkout to set `persist-credentials: false`.
- CI release validation uses the same exact production dependency versions as the Windows runtime lock, compiles Lua, runs the full Python suite and proves deterministic packaging with two builds.
- CodeQL, native Windows validation and both dependency-audit workflows run independently of the primary release build where their path filters apply.
- Public tag releases require `v<VERSION>` parity and fail closed unless the real publisher signing secrets are configured.
- Windows public-release builds sign and RFC 3161 timestamp the three payload executables first, rebuild Setup with that signed payload, sign Setup and verify every signature.
- Final tagged assets receive SHA-256 checksums and GitHub artifact attestations; the workflow creates a draft GitHub Release rather than publishing before live acceptance.
- `LICENSE-SCOPE.md` documents the existing Bridge/third-party license boundary without inventing a repository-wide Companion/installer license.

## Release gates still external

- Native clean-Windows install/repair/uninstall and SmartScreen/AV behavior remain runtime acceptance gates.
- A real publisher signing identity must be securely configured before the tag workflow can produce a public Windows release.
- Live World of Warcraft Midnight Season 2 Group Finder/screenshot/tooltip validation remains a live-client acceptance gate. The expanded matrix now covers secret LFG fields, active-dungeon and party-full pause behavior, screenshot success/failure and CVar restoration, representative resolutions/UI scales, Raider.IO/no-data behavior, Companion Data co-load, Season transitions and a repeated-capture soak.
- Warcraft Logs Season 2 must be rechecked against first-live production parses/zone state before current-season WCL evidence is treated as the normal source.
- The draft GitHub Release and CurseForge file should be published as Release only after those live gates pass; until then use preview/Beta distribution where appropriate.
- Repository branch protection/rulesets and GitHub-native secret scanning/push protection remain owner/admin settings and are tracked separately; source CI cannot prove those settings are enabled.
