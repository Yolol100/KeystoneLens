# KeystoneLens

KeystoneLens is a small Warcraft Logs Mythic+ tooltip for World of Warcraft Retail.

## In game

KeystoneLens adds one compact Warcraft Logs line to the same player tooltip that Raider.IO uses. When Raider.IO is installed, the WCL line is inserted immediately below the Raider.IO M+ score whenever matching cached data exists:

- DPS / tank: `Warcraft Logs M+ — DPS 97%`
- healer: `Warcraft Logs M+ — Healing 94%`

This works for Mythic+ Group Finder applicants and for normal player/unit tooltips while the current hosted Mythic+ listing matches the cached WCL context. Raider.IO remains untouched and optional; without Raider.IO, KeystoneLens still renders the same compact WCL line through its fallback tooltip hooks.

That is all KeystoneLens adds. There is no Blizzard score, custom KeystoneLens score, confidence label, run count or recruitment overlay.

## How it works

1. The WoW bridge captures the current Group Finder applicants.
2. The Windows Companion reads that transport.
3. The Companion queries the official Warcraft Logs API for the current dungeon and specialization.
4. It stores only the relevant role percentile: DPS for DPS/tanks or HPS for healers.
5. The WoW tooltip reads that small local cache after `/reload`.

WoW addons cannot make normal internet requests, so the Companion and transport layer remain necessary.

## Windows portable build

The Companion is required for automatic Warcraft Logs data. The portable Windows build is kept intentionally because it is the simplest zero-install delivery: it bundles the private Python runtime and only the dependencies needed for WCL HTTP requests plus QR/screenshot decoding.

The build verifies the staged package, creates a deterministic ZIP, extracts that exact ZIP again, and verifies the extracted runtime before it is accepted.

## Verification

GitHub Actions checks Python syntax, WoW Lua 5.1 syntax, the minimal architecture contract, Companion lifecycle/window regressions, and an executable Raider.IO tooltip contract that proves ordering, DPS/healing formatting, stale-data rejection, activity/spec rejection, duplicate prevention, LFG fallback, and normal unit-tooltip fallback. On pushes to `main`, it also builds and verifies the Windows portable ZIP and stores the verified ZIP as a short-lived workflow artifact.

## Repository

- `addon/KeystoneLensBridge/` — WoW transport + compact tooltip.
- `companion/source/app/` — minimal Windows Companion + WCL client.
- `companion/source/data-addon/` — generated local WCL tooltip cache template.
- `companion/source/portable/` — portable Windows packaging.

## License

See `LICENSE-SCOPE.md`.
