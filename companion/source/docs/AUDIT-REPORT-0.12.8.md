# KeystoneLens 0.12.8 post-audit report

## Verdict

**SOURCE/CI: PASS WITH EXTERNAL RUNTIME GATES**

This report supersedes the 0.12.7 audit for the 0.12.8 artifacts. The 0.12.7 report remains historical evidence for the original 0.12.7 build and must not be used to describe 0.12.8.

## Correctness changes verified by source contracts

- Tooltip data is schema v2 and includes `activityID`, `keyLevel` and `specID` for every published score.
- The Bridge accepts only schema v2 and requires the current active Group Finder activity/key plus the applicant specialization to match before showing cached KeystoneLens lines.
- Generated v2 data uses `_G.KeystoneLensTooltipCacheV2` and clears `_G.KeystoneLensTooltipCache`. This closes the downgrade path where an older name-only Bridge could otherwise consume a new v2 entry.
- Invalid, incomplete or unreadable listing/spec context remains fail-closed.

## Release-integrity changes

- Canonical release identity is `0.12.8` in `companion/source/VERSION`.
- Companion and Bridge version metadata are checked against the canonical version before Windows or release packaging proceeds.
- Windows PE resources and the embedded Setup script receive the canonical version during the deterministic build.
- The source ZIP is normalized to the same installer version and is reopened and checked after packaging.
- Release notes and this audit report are selected by the canonical version, preventing an older audit from being silently republished as current evidence.
- Release output is built twice and must have identical SHA-256 manifests before it can be staged for publication.

## CI/runtime dependency parity

The release-validation workflow derives the Linux test installation from the exact package versions in the Windows runtime lock (hash lines removed only because the lock contains Windows-wheel hashes). This keeps functional tests on the same dependency versions that the shipped Windows runtime uses. The separate dependency-audit workflow continues to audit the production requirements and exact runtime package set.

## Remaining external gates

- A live WoW Retail client is required for final Group Finder tooltip, screenshot transport and co-load acceptance.
- A native clean Windows machine is required for final installer/repair/uninstall, taskbar, DPI and SmartScreen acceptance.
- Authenticode signing requires the actual publisher certificate and timestamping service. Until signed, the Windows executable remains a release-trust blocker for a public production claim.
- GitHub branch protection/rulesets are repository settings and are not established by source code. Required checks should be enforced on `main` in repository settings.

No new user-facing features or settings are introduced by 0.12.8.
