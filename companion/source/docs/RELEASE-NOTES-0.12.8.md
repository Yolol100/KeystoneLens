# KeystoneLens 0.12.8

0.12.8 is a correctness and release-integrity update. It does not add user-facing settings or scoring features.

## Fixes

- Tooltip cache schema v2 remains bound to the exact Group Finder activity, target key level and applicant specialization.
- Schema v2 now uses `KeystoneLensTooltipCacheV2` and explicitly clears the legacy `KeystoneLensTooltipCache` global. An older Bridge therefore fails closed instead of interpreting new v2 data with the former name-only cache logic after a rollback.
- Release identity is no longer reused after source changes. Companion, Bridge, Windows PE metadata, setup UI build, ZIP names and generated data-addon metadata are validated against the canonical `companion/source/VERSION` value.
- The distributed source archive receives the canonical installer version before verification, so a source rebuild and the shipped binary agree on product version.
- CI release validation is updated to use the same exact production dependency versions as the Windows runtime lock when running the Python regression suite.

## Release gates still external

- Native clean-Windows install/repair/uninstall and SmartScreen behavior remain runtime acceptance gates.
- Authenticode signing requires the real publisher certificate; unsigned public Windows binaries are not a production-trust GO.
- Live World of Warcraft Midnight Season 2 validation remains a live-client acceptance gate.
