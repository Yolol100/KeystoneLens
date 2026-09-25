# KeystoneLens

KeystoneLens is a small Warcraft Logs Mythic+ tooltip for World of Warcraft Retail.

## In game

Hover a player in your Mythic+ Group Finder applicant list:

- DPS / tank: `Warcraft Logs M+ — DPS 97%`
- healer: `Warcraft Logs M+ — Healing 94%`

That is all the tooltip shows. There is no Raider.IO score, Blizzard score, custom KeystoneLens score, confidence label, run count or recruitment overlay.

## How it works

1. The WoW bridge captures the current Group Finder applicants.
2. The Windows Companion reads that transport.
3. The Companion queries the official Warcraft Logs API for the current dungeon and specialization.
4. It stores only the relevant role percentile: DPS for DPS/tanks or HPS for healers.
5. The WoW tooltip reads that small local cache after `/reload`.

WoW addons cannot make normal internet requests, so the Companion and transport layer remain necessary.

## Repository

- `addon/KeystoneLensBridge/` — WoW transport + compact tooltip.
- `companion/source/app/` — minimal Windows Companion + WCL client.
- `companion/source/data-addon/` — generated local WCL tooltip cache template.
- `companion/source/portable/` — portable Windows packaging.

## License

See `LICENSE-SCOPE.md`.
