# KeystoneLens

KeystoneLens is a compact Warcraft Logs Mythic+ tooltip for World of Warcraft Retail.

## What it shows

When you hover a player in your Mythic+ Group Finder applicant list, KeystoneLens adds one line:

- DPS/Tank: Warcraft Logs M+ — DPS 97%
- Healer: Warcraft Logs M+ — Healing 94%

The percentage is the player's Warcraft Logs ranking percentile for the current dungeon and specialization.

The tooltip does not show Raider.IO score, Blizzard Mythic+ score, a custom KeystoneLens score, confidence labels, source breakdowns, run counts or cache/debug text.

## Why a Companion is still needed

WoW addons cannot make normal internet requests. The existing Bridge transport identifies the current Group Finder applicants. The Windows Companion queries the official Warcraft Logs API and writes a small local data addon that the tooltip can read after /reload.

The transport layer remains because it is required for automatic data transfer; the visible tooltip and stored tooltip data are intentionally minimal.

## Repository structure

- addon/KeystoneLensBridge/ — WoW bridge and compact tooltip
- companion/source/app/ — Companion runtime and Warcraft Logs client
- companion/source/data-addon/ — generated local tooltip cache template
- companion/source/portable/ — portable Windows packaging

## Warcraft Logs metric

KeystoneLens uses DPS for DPS/tank specializations and HPS for healer specializations. Only that role metric is needed for the tooltip.

## License

See LICENSE-SCOPE.md and the notice files included with the project.
