# KeystoneLens 0.12.8

0.12.8 is a correctness, Season 2 readiness and production-release hardening update. It does not add user-facing settings or change the fixed scoring formula; it does add evidence transparency to the existing in-game tooltip.

## Runtime fixes

- Tooltip cache schema v2 remains bound to the exact Group Finder activity, target key level and applicant specialization.
- Schema v2 uses `KeystoneLensTooltipCacheV2` and explicitly clears the legacy `KeystoneLensTooltipCache` global. An older Bridge therefore fails closed instead of interpreting new v2 data with former name-only cache logic after a rollback.
- Raider.IO runtime requests derive their User-Agent version from the canonical Companion `__version__`.
- The Midnight Season 2 registry matches Blizzard's eight-dungeon rotation and was re-verified on the EU launch date, 2026-08-19. Warcraft Logs zone 56 is retained for Season 2.
- Launch-day WCL behavior initially used source-stamped Season-1 carry-over because current Season-2 production evidence was not yet independently visible. On 2026-08-20 public Warcraft Logs character/ranking surfaces were rechecked and showed live `Mythic+ Season 2` scores/ranks. KeystoneLens now keeps the week-one transition context for Raider.IO previous-score display but stops forcing Season-1 WCL from that verified date onward; current Season-2 WCL becomes the scoring source and stale Season-1 WCL results fail the existing source-season assignment guard.
- Raider.IO's addon source changed its internal previous-score decoder from 12 to 13 bits on launch day. KeystoneLens does not consume those encoded bit positions; its reviewed local Bridge contract still reads Raider.IO's public profile table and the Companion uses the Raider.IO HTTP API. No score-parser change is required from that upstream implementation fix.
- The Bridge remains explicitly recruitment/display-only. Its repository audit now rejects new combat-log, aura, health/power, cast, position, protected-action, target/focus, raid-marker and chat-automation surfaces from the tracked WoW runtime.
- The existing LibKeystone compatibility message is intentionally narrow: one fixed `LibKS` send surface, `PARTY` only, grouped only and blocked during Chat Messaging Lockdown. The audit rejects addon-message expansion outside that reviewed shim.
- The tracked Bridge runtime must match the TOC inventory exactly; unlisted runtime Lua or missing TOC files fail the release audit.
- Existing secret-value guards, dungeon/party-full auto-pause boundaries and the serialized screenshot/CVar lease are now permanent audited contracts rather than convention-only behavior.
- Blizzard's Patch 12.1 Group Finder fixes do not weaken those fail-closed guards; transient/secret/partial LFG reads remain treated as untrusted even if the upstream UI refresh bug is fixed.
- The 2026-08-20 rule expansion explicitly keeps Raider.IO request pacing below the public unauthenticated API limit, respects HTTP `Retry-After`, and keeps Warcraft Logs OAuth expiry, GraphQL `rateLimitData` and retry behavior inside bounded failure paths; these behaviors already existed and were reclassified as release controls rather than changed at runtime.

## Evidence transparency and WoW AddOns metadata

- The displayed KL Score remains exactly 50% Raider.IO and 50% Warcraft Logs. No third scoring pillar or hidden weighting was added.
- The generated tooltip cache exports the existing `high` / `medium` / `low` score confidence and the Bridge displays that confidence plus a human-readable evidence age below the KL Score.
- When both Raider.IO and Warcraft Logs contribute online evidence, `fetchedAt` uses the oldest positive contributing source timestamp. The existing maximum-age gate therefore cannot be made to look fresher by only one source being refreshed.
- `KeystoneLensBridge` and `KeystoneLensCompanionData` share `## Group: KeystoneLensBridge`, matching WoW's group contract for related addons.
- The published Bridge TOC, the dynamically generated Companion Data TOC and the checked-in Companion Data source TOC carry the same localized `Dungeons & Raids` category metadata.
- The Bridge remains observation-only: these changes do not add automated applicant acceptance/decline, hidden Group Finder actions, input injection or process-memory access.

## Release/product hardening

- `companion/source/VERSION` is the canonical Companion, Bridge, data-addon, Windows metadata and artifact version source.
- `sign-release.ps1` now reads that canonical version instead of carrying a stale hard-coded release number.
- Generated ZIPs, checksums and Windows executables are no longer stored on `main`; tagged builds publish them as release assets.
- Repository hygiene now has explicit `.gitignore`, `.gitattributes`, `.editorconfig`, release-output/secret checks and GitHub Actions dependency maintenance.
- A repository audit rejects generated binaries, local build/cache output, common secret/key patterns, version drift, mutable/unpinned Actions and workflows that try to commit release artifacts back to `main`.
- The audit also protects its own critical verification surface, rejects high-risk Actions triggers and direct untrusted pull-request metadata interpolation, and requires every checkout to set `persist-credentials: false`.
- GitHub-hosted CI runner images are explicit (`ubuntu-24.04` and `windows-2025`) rather than `-latest`, reducing unreviewed environment drift during future runner migrations.
- Dependabot now covers GitHub Actions and both production Python dependency roots on a weekly cadence. A separate PR Dependency Review workflow is full-SHA pinned and becomes a blocking `moderate`-severity vulnerability-diff gate when GitHub Dependency Graph is enabled; until that repository feature is enabled, the workflow reports the missing admin prerequisite while the existing `pip-audit` jobs remain blocking for the resulting requirement sets and exact Windows runtime lock.
- The production Companion has a package-portable external-security gate that rejects shell/process spawning, inbound listeners/servers, TLS-verification bypasses, unsafe archive extraction, unsafe deserialization/dynamic execution and plaintext HTTP endpoints.
- Warcraft Logs enrichment is machine-bound to the HTTPS OAuth token endpoint plus the public `/api/v2/client` client-credentials API; the private `/api/v2/user` surface is rejected until a deliberate user-authorization feature exists.
- Raider.IO enrichment is machine-bound to the documented HTTPS profile API, conservative unauthenticated request pacing, explicit 429/`Retry-After` behavior and visible attribution/client identity.
- The checked-in CycloneDX SBOM must remain parseable, match canonical `VERSION` and contain every direct exact-pinned Python runtime dependency at the same version.
- CI release validation uses the same exact production dependency versions as the Windows runtime lock, compiles Lua, runs the full Python suite and proves deterministic packaging with two builds.
- CodeQL, native Windows validation, dependency review and both dependency-audit workflows run independently of the primary release build where their path filters apply.
- The WoW Bridge is also checked against Blizzard's published UI Add-On policy boundary for in-game advertising, premium, sponsorship and donation-solicitation behavior.
- Public tag releases require `v<VERSION>` parity and fail closed unless the real publisher signing secrets are configured.
- Windows public-release builds sign and RFC 3161 timestamp the three payload executables first, rebuild Setup with that signed payload, sign Setup and require `signtool verify /pa /tw /all /v` plus valid PowerShell Authenticode status and an actual timestamp certificate for the final binaries.
- Final tagged assets receive SHA-256 checksums and GitHub artifact attestations. In addition, the existing CycloneDX 1.5 SBOM is bound to the final source ZIP and signed Windows installer with a dedicated `https://cyclonedx.org/bom` SBOM attestation, and both SLSA provenance and CycloneDX predicate are verified before a draft release can be created.
- `LICENSE-SCOPE.md` documents the existing Bridge/third-party license boundary without inventing a repository-wide Companion/installer license.

## Release gates still external

- Native clean-Windows install/repair/uninstall and SmartScreen/AV behavior remain runtime acceptance gates. The acceptance scope also includes Unicode/long paths, permission failures, locked files, low disk space and reparse-point/symlink edge cases.
- A real publisher signing identity must be securely configured before the tag workflow can produce a public Windows release.
- Live World of Warcraft Midnight Season 2 Group Finder/screenshot/tooltip validation remains a live-client acceptance gate. The expanded matrix covers secret LFG fields, active-dungeon and party-full pause behavior, screenshot success/failure and CVar restoration, representative resolutions/UI scales, Raider.IO/no-data behavior, Companion Data co-load, Season transitions and a repeated-capture soak.
- Public Warcraft Logs Season-2 availability is source-verified and used by the runtime from 2026-08-20, but an authenticated first-live `/api/v2/client` parse matrix with the real release credentials remains a separate target-runtime acceptance gate.
- CurseForge project metadata is an explicit owner/distribution gate: Retail game-version/flavor, Beta versus Release channel, dependency relations, distribution toggle and project license scope must match the tested artifact and evidence state.
- GitHub Dependency Graph was found disabled during the new Dependency Review run on 2026-08-20; enabling it is an explicit repository-admin prerequisite for the vulnerability-diff action to become blocking.
- The draft GitHub Release and CurseForge file should be published as Release only after the live gates pass; until then use preview/Beta distribution where appropriate.
- Repository branch protection/rulesets and GitHub-native secret scanning/push protection remain owner/admin settings and are tracked separately; source CI cannot prove those settings are enabled.
- The external Windows Companion remains subject to an explicit Blizzard EULA/policy review. Observation-only source evidence reduces technical automation risk but does not substitute for Blizzard authorization.
