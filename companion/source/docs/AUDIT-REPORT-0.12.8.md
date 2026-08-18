# KeystoneLens 0.12.8 post-audit report

## Verdict

**SOURCE / BUILD / RELEASE PIPELINE: PASS WITH EXTERNAL LIVE + SIGNING IDENTITY GATES**

This report supersedes the 0.12.7 audit for the 0.12.8 source and future tagged release artifacts. Historical audit files remain documentation only and are not release binaries.

## Runtime correctness verified by source contracts

- Tooltip data is schema v2 and includes `activityID`, `keyLevel` and `specID` for every published score.
- The Bridge requires the current active Group Finder activity/key plus applicant specialization to match before showing cached KeystoneLens lines.
- Generated v2 data uses `_G.KeystoneLensTooltipCacheV2` and clears `_G.KeystoneLensTooltipCache`, so rollback to a name-only Bridge fails closed.
- Invalid, incomplete or unreadable listing/spec context remains fail-closed.
- Raider.IO runtime HTTP identity follows the canonical Companion version.
- The Season 2 dungeon registry and score-source contracts remain covered by regression tests; first-live WCL/runtime observations are still external evidence.

## Repository/product hardening

- `main` contains source, documentation and release engineering only. Generated `.zip`, `.exe`, root checksum manifests, build/release directories and local caches are explicitly excluded and audited.
- Repository text/binary handling is normalized through `.gitattributes` and `.editorconfig`; local output and signing material are ignored by `.gitignore`.
- `LICENSE-SCOPE.md` states the actual licensing boundary instead of implying a blanket repository license.
- GitHub Actions are required by the repository audit to use immutable full commit SHA pins. Dependabot maintains GitHub Actions dependency updates.
- The release workflow no longer commits generated assets back to `main`, removing the previous unsigned artifact-bot commit from the forward release design.

## Release integrity

- Canonical release identity is `0.12.8` in `companion/source/VERSION`.
- Companion, Bridge, Companion Data and Windows metadata are checked against the canonical version.
- `sign-release.ps1` reads the canonical version and rejects ambiguous/missing signing identities or non-HTTPS timestamp URLs.
- Release output is built twice and must have identical SHA-256 manifests before staging.
- A public tag must be exactly `v<VERSION>`.
- Tagged core assets receive GitHub artifact attestations; final release assets receive SHA-256 checksums and final provenance attestations.
- GitHub Release creation is draft-only so live acceptance cannot be bypassed by a successful build.

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
- Complete live WoW Retail Group Finder tooltip, screenshot transport and Bridge/Data co-load acceptance after the Season 2 unlock.
- Recheck Warcraft Logs against live Season 2 parses.
- Publish the draft GitHub Release and CurseForge file only after those gates pass.
- Enable branch protection/rulesets with required checks on `main` in repository settings when administration tooling is available.

No new user-facing features or settings are introduced by this hardening round.
