# KeystoneLens 0.12.8 post-audit report

## Verdict

**SOURCE / BUILD / RELEASE PIPELINE: PASS WITH EXTERNAL LIVE + SIGNING IDENTITY + REPOSITORY-ADMIN GATES**

This report supersedes the 0.12.7 audit for the 0.12.8 source and future tagged release artifacts. Historical audit files remain documentation only and are not release binaries.

## Runtime correctness verified by source contracts

- Tooltip data is schema v2 and includes `activityID`, `keyLevel` and `specID` for every published score.
- The Bridge requires the current active Group Finder activity/key plus applicant specialization to match before showing cached KeystoneLens lines.
- Generated v2 data uses `_G.KeystoneLensTooltipCacheV2` and clears `_G.KeystoneLensTooltipCache`, so rollback to a name-only Bridge fails closed.
- Invalid, incomplete, secret or unreadable listing/spec context remains fail-closed.
- Raider.IO runtime HTTP identity follows the canonical Companion version.
- The Season 2 dungeon registry and score-source contracts remain covered by regression tests; first-live WCL/runtime observations are still external evidence.

## 2026-08-19 Season 2 launch-day source review

- Blizzard's EU Season 2 opening was rechecked on the launch date. The registry still matches the official eight-dungeon Mythic+ rotation and its `verified_date` is now 2026-08-19.
- The existing exact EU phase boundary remains regression-tested around the weekly reset instant. Week one continues to use source-stamped Season-1 WCL carry-over and week two invalidates that evidence before switching to the current Season-2 source.
- Warcraft Logs public zone 56 still presented as `Mythic+ Season 2 (PTR)` during this review. KeystoneLens therefore does not treat the calendar alone as proof that current-season WCL ranking evidence is production-ready. The conservative carry-over route remains in place until the source itself is live-verified.
- Raider.IO addon source fixed its internal `PreviousScore` and `WarbandPreviousScore` decoder width from 12 to 13 bits on 2026-08-19. KeystoneLens does not decode that binary database format. The Bridge consumes Raider.IO's public profile object and the Companion uses the HTTP API, so no parser/runtime change is required for that implementation-level fix.
- Blizzard's 12.1 Group Finder overlap/refresh fixes do not relax KeystoneLens' partial/secret read protections. Last-known-good applicant state is still preserved when LFG context is unreadable, and context/source identities remain mandatory before online enrichment can be assigned.
- No repository code depends on `ManifestInterfaceData`, so the 12.1 change that stops publishing new UI texture filenames through that database has no direct KeystoneLens compatibility impact.

## WoW Bridge / Midnight boundary

- `KeystoneLensBridge.toc` is machine-checked as the exact tracked runtime inventory. Missing TOC entries and additional unlisted runtime Lua fail the repository audit.
- The Bridge is machine-constrained to recruitment/display and local screenshot transport. New combat-log, aura, health/power, cast, position, protected-action, targeting/focus, raid-marker, binding/state-driver and ordinary chat-automation surfaces are rejected.
- Secret-value safety markers in Group Finder transport remain required by the audit.
- Active-dungeon and party-full capture pause contracts remain required so recruitment screenshots cannot silently continue into an active run/full group.
- Screenshot success/failure state, temporary PNG CVar leasing and restoration remain explicit audited contracts.
- The sole reviewed addon-message surface is the LibKeystone compatibility shim: fixed `LibKS` prefix, `PARTY` only, grouped only and blocked by Chat Messaging Lockdown. Additional addon-message call sites fail the audit.

## Repository/product hardening

- `main` contains source, documentation and release engineering only. Generated `.zip`, `.exe`, root checksum manifests, build/release directories and local caches are explicitly excluded and audited.
- Repository text/binary handling is normalized through `.gitattributes` and `.editorconfig`; local output and signing material are ignored by `.gitignore`.
- `LICENSE-SCOPE.md` states the actual licensing boundary instead of implying a blanket repository license.
- GitHub Actions are required by the repository audit to use immutable full commit SHA pins. Dependabot maintains GitHub Actions dependency updates.
- High-risk `pull_request_target`, `repository_dispatch` and `workflow_run` triggers plus direct pull-request metadata interpolation are rejected by the repository audit.
- Every `actions/checkout` call is required to set `persist-credentials: false`; the release jobs use explicit GitHub tokens/secrets only for the operations that need them.
- Critical workflow files, the Bridge TOC, live acceptance matrix and audit script itself are required files, preventing later changes from silently deleting the verification layer.
- The release workflow does not commit generated assets back to `main`, removing the previous unsigned artifact-bot commit from the forward release design.

## Release integrity

- Canonical release identity is `0.12.8` in `companion/source/VERSION`; no public `v0.12.8` tag existed at the launch-day review, so the verified source/evidence update does not mutate an immutable published release.
- Companion, Bridge, Companion Data and Windows metadata are checked against the canonical version.
- `sign-release.ps1` reads the canonical version and rejects ambiguous/missing signing identities or non-HTTPS timestamp URLs.
- Release output is built twice and must have identical SHA-256 manifests before staging.
- A public tag must be exactly `v<VERSION>`.
- Tagged core assets receive GitHub artifact attestations; final release assets receive SHA-256 checksums and final provenance attestations.
- GitHub Release creation is draft-only so live acceptance cannot be bypassed by a successful build.
- The 2026-08-19 hardening head passed the primary Build and stage release workflow, native Windows platform validation, CodeQL, PR dependency audit and scheduled-style dependency audit before merge. This launch-day evidence update must pass the same affected source/release gates again before merge.

## Windows trust gate

- Public Windows tag releases fail closed unless the real publisher PFX/password secrets are available to the ephemeral Windows runner.
- Payload binaries are signed before embedding; Setup is rebuilt and signed afterwards.
- Signing uses SHA-256 Authenticode with RFC 3161/SHA-256 timestamping and verifies the four binaries through SignTool and PowerShell Authenticode status.
- The signing identity itself is an external secret and is not present in source control.

## CI/runtime dependency parity

The release-validation workflow derives Linux functional test dependencies from the exact Windows production runtime lock. Native Windows CI installs the same exact hashed runtime package set. The scheduled dependency-audit workflow continues to audit both declared application requirements and the exact runtime package set.

## Remaining external gates

- Configure the real publisher signing identity securely before creating a public Windows tag release.
- Complete clean-Windows install/repair/uninstall, taskbar/DPI and SmartScreen/AV acceptance on the signed build.
- Complete the expanded live WoW Retail matrix: Group Finder context churn, secret values, dungeon/full-party auto-pause, serialized screenshot/CVar recovery, representative resolutions/UI scales, Raider.IO/no-data behavior, Companion Data co-load, WCL failure/context boundaries and repeated-capture soak.
- Recheck Warcraft Logs against live Season 2 production parses/source state before treating current Season-2 WCL evidence as the normal scoring source.
- Publish the draft GitHub Release and CurseForge file only after those gates pass.
- Enable branch protection/rulesets with required checks on `main` and verify GitHub-native secret scanning/push protection. These owner/admin actions are tracked in issue #17 and are not implied by source-only CI.

No new user-facing features or settings are introduced by this hardening round.
