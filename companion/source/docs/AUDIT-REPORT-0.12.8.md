# KeystoneLens 0.12.8 post-audit report

## Verdict

**SOURCE / BUILD / RELEASE PIPELINE: PASS WITH EXTERNAL LIVE + SIGNING IDENTITY + REPOSITORY-ADMIN + POLICY REVIEW GATES**

This report describes the current 0.12.8 source. It does not claim live WoW, signed-Windows, repository-admin or Blizzard-policy acceptance that source inspection cannot prove.

## Runtime correctness verified by source contracts

- The displayed KL Score is exactly 50% Raider.IO plus 50% Warcraft Logs. Missing WCL evidence contributes 0 to the WCL half; no third scoring pillar is used.
- Tooltip cache schema v2 includes `activityID`, `keyLevel` and `specID` for every published score and the Bridge requires the current active Group Finder activity/key plus applicant specialization to match before showing cached KeystoneLens lines.
- Generated v2 data uses `_G.KeystoneLensTooltipCacheV2` and clears `_G.KeystoneLensTooltipCache`, so rollback to a name-only Bridge fails closed.
- The generated cache exports the existing `high` / `medium` / `low` confidence value and the Bridge displays confidence plus human-readable evidence age below the KL Score.
- When both Raider.IO and Warcraft Logs contribute online evidence, the cache uses the oldest positive contributing source timestamp for `fetchedAt`. The existing maximum-age rejection therefore evaluates the least-fresh contributing evidence rather than the newest source.
- Invalid, incomplete, secret or unreadable listing/spec context remains fail-closed.
- Raider.IO runtime HTTP identity follows the canonical Companion version.
- `MIDNIGHT_SEASON_2_WCL_PRODUCTION_VERIFIED_ON` is 2026-08-20 in the current registry. From that date the current Season-2 WCL source is selected rather than forcing Season-1 carry-over for a Season-2 dungeon.

## WoW addon metadata and ownership

- `KeystoneLensBridge` and `KeystoneLensCompanionData` both declare `## Group: KeystoneLensBridge`, satisfying WoW's shared-group requirement for related addons.
- The published Bridge TOC, the dynamically generated Companion Data TOC and the checked-in Companion Data source TOC carry the same `Dungeons & Raids` category plus the maintained localized category metadata.
- The Bridge remains recruitment/display-only. No automated applicant acceptance/decline, hidden Group Finder actions, input injection or process-memory access is introduced by the evidence/metadata changes.
- `KeystoneLensBridge.toc` remains the exact tracked Bridge runtime inventory; missing TOC entries and additional unlisted runtime Lua are release-audit failures.

## Midnight / external-process safety boundary

- The Bridge is machine-constrained to recruitment/display and local screenshot transport. Repository validation rejects new combat-log, aura, health/power, cast, position, protected-action, targeting/focus, raid-marker, binding/state-driver and ordinary chat-automation surfaces from the tracked WoW runtime.
- Secret-value safety markers in Group Finder transport remain required by the audit.
- Active-dungeon and party-full capture pause contracts remain required so recruitment screenshots cannot silently continue into an active run or full group.
- Screenshot success/failure state, temporary PNG CVar leasing and restoration remain explicit audited contracts.
- The sole reviewed addon-message surface is the LibKeystone compatibility shim: fixed `LibKS` prefix, `PARTY` only, grouped only and blocked by Chat Messaging Lockdown. Additional addon-message call sites fail the audit.
- The production Companion is separately constrained against input injection, process-memory access, remote-process injection, global input hooks, unsafe external execution, inbound listeners/servers, TLS-verification bypasses, unsafe archive extraction, unsafe deserialization/dynamic execution and plaintext HTTP endpoints.

## Repository and release integrity

- `companion/source/VERSION` is the canonical release identity and current value is `0.12.8`; Companion, Bridge, Companion Data and Windows metadata are checked against it.
- During the 2026-08-21 re-audit, no `v0.12.8` or `0.12.8` Git ref was present, so these source corrections are not mutating an existing version tag.
- The primary release workflow validates repository hygiene, canonical version parity, Lua syntax, the QR reliability baseline, the full Python regression suite and a double deterministic release build.
- The extracted source ZIP is tested again, so tests that accidentally depend on the full Git checkout are detected by the release build.
- GitHub Actions are required by the repository audit to use immutable full commit SHA pins and checkout steps use `persist-credentials: false`.
- Release output is generated rather than committed back to `main`.
- Public tag releases require exact `v<VERSION>` parity. Tagged Windows release jobs require the configured publisher signing identity, sign and timestamp the payload and Setup, and verify the resulting signatures before release staging.
- Final tagged assets use SHA-256 checksums and GitHub attestations; release creation is draft-only.
- `LICENSE-SCOPE.md` documents the existing Bridge/third-party licensing boundary without implying a repository-wide Companion/installer license.

## Validation evidence still external

The source and CI gates cannot prove the following and this report does not mark them as passed:

- clean-Windows install/repair/uninstall, SmartScreen/AV behavior, Unicode/long paths, permission failures, locked files, low disk space and reparse-point/symlink cases on the signed build;
- the real publisher signing identity, because it is an external secret;
- live WoW Retail Group Finder context churn, secret values, active-dungeon/full-party pausing, screenshot/CVar recovery, UI scales/resolutions, Companion Data co-load, tooltip rendering and repeated-capture soak;
- authenticated first-live Warcraft Logs `/api/v2/client` parsing with real release credentials;
- CurseForge project metadata and distribution-channel settings;
- branch protection/rulesets, secret scanning, push protection and other repository-admin settings;
- formal Blizzard authorization for the external Companion. Observation-only implementation constraints are not a substitute for Blizzard policy/EULA approval.

## Re-audit result

The 2026-08-21 factual re-audit corrected two source-structure problems from the comparable-addon round: duplicate AddOns grouping metadata paths are now kept consistent, and the release documentation now describes the actually present confidence/freshness UI rather than claiming there were no user-facing changes. No scoring weights or automated Group Finder actions were added by this correction.
