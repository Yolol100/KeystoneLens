# KeystoneLens 0.12.8

0.12.8 is a correctness, Season 2 readiness and release-integrity update. It does not add user-facing settings or scoring features.

## Fixes

- Tooltip cache schema v2 remains bound to the exact Group Finder activity, target key level and applicant specialization.
- Schema v2 now uses `KeystoneLensTooltipCacheV2` and explicitly clears the legacy `KeystoneLensTooltipCache` global. An older Bridge therefore fails closed instead of interpreting new v2 data with the former name-only cache logic after a rollback.
- Raider.IO runtime requests derive their User-Agent version from the canonical Companion `__version__`, removing the stale `0.12.7` network identity from the 0.12.8 build.
- The Midnight Season 2 registry matches Blizzard's eight-dungeon rotation. Warcraft Logs zone 56 is retained for Season 2; because Warcraft Logs still labels it PTR before the European Mythic+ unlock, the first live Season 2 data remains an acceptance gate rather than guessed production evidence.
- Release identity is no longer reused after source changes. Companion, Bridge, Windows PE metadata, setup UI build, ZIP names and generated data-addon metadata are validated against the canonical `companion/source/VERSION` value.
- The distributed source archive receives the canonical installer version before verification, so a source rebuild and the shipped binary agree on product version.
- CI release validation uses the same exact production dependency versions as the Windows runtime lock when running the Python regression suite.

## Release gates still external

- Native clean-Windows install/repair/uninstall and SmartScreen behavior remain runtime acceptance gates.
- Authenticode signing requires the real publisher certificate; unsigned public Windows binaries are not a production-trust GO.
- Live World of Warcraft Midnight Season 2 Group Finder/screenshot/tooltip validation remains a live-client acceptance gate after Mythic+ opens in Europe.
- Warcraft Logs zone 56 must be rechecked once live Season 2 parses replace the pre-season PTR state.
