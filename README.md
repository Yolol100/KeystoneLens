# KeystoneLens

KeystoneLens is a small Warcraft Logs Mythic+ tooltip for World of Warcraft Retail.

## In game

KeystoneLens adds one compact Warcraft Logs line to the same player tooltip that Raider.IO uses. When Raider.IO is installed, the line sits directly below the current Raider.IO M+ score:

- DPS / tank: `Warcraft Logs M+ — DPS 97%`
- healer: `Warcraft Logs M+ — Healing 94%`

For Mythic+ Group Finder applicants this updates live. A newly arrived applicant does **not** require `/reload`.

Raider.IO remains untouched and optional. KeystoneLens does not add a Blizzard score, custom KeystoneLens score, confidence label, run count, ranking window, or recruitment overlay.

## How the live update works

WoW addons cannot receive arbitrary HTTP responses while the game is running, so KeystoneLens keeps a strict split:

1. The WoW bridge detects the current Group Finder applicants.
2. The Companion receives that state through KeystoneLens' QR/screenshot transport.
3. The Companion queries the official Warcraft Logs API in the background for DPS or HPS.
4. When you hover an applicant, the addon immediately reserves the `Warcraft Logs M+` row under Raider.IO and sends only that applicant identity plus normalized tooltip geometry through the existing transport.
5. The Companion paints only the right-hand value (`DPS 97%` / `Healing 94%`) into that reserved row with a transparent, mouse-through, no-activate Windows overlay.
6. When the WCL request finishes, the value appears without reloading WoW.

The overlay is display-only. It does not send keyboard/mouse input to WoW and does not inject code into the game process.

The generated `KeystoneLensCompanionData/Data.lua` remains as a warm-start/fallback cache for later sessions and normal unit tooltips. It is no longer required for live Group Finder updates.

## Safety and correctness

Live values are bound to:

- applicant ID + member index
- character name
- specialization
- current hosted Mythic+ activity
- hover generation
- exact reserved tooltip geometry

Stale hover generations, removed applicants, activity changes, spec mismatches and cross-realm collisions fail closed instead of showing another player's value.

The live Windows overlay is visible only while World of Warcraft is the foreground application and automatically hides when the cursor leaves the applicant row.

## Windows portable build

The Companion is required for automatic Warcraft Logs data. The portable Windows build is the zero-install delivery: it bundles the private Python runtime and only the dependencies needed for WCL HTTP requests plus QR/screenshot decoding.

The build verifies the staged package, creates a deterministic ZIP, extracts that exact ZIP again, and verifies the extracted runtime before it is accepted.

## Verification

GitHub Actions checks:

- Python source compilation
- WoW Lua 5.1 compilation
- Raider.IO tooltip ordering and fallback behavior
- the no-reload blank-row/live-hover contract
- APS1 v14 live-hover transport decoding and stale-generation handling
- live overlay metric/geometry/fail-closed behavior
- minimal architecture constraints
- Companion shutdown behavior
- Companion window restore behavior
- Windows portable/Tk/overlay runtime creation
- the complete Windows ZIP package

## Repository

- `addon/KeystoneLensBridge/` — WoW transport + compact Raider.IO/WCL tooltip integration.
- `companion/source/app/` — Windows Companion, WCL client and live display bridge.
- `companion/source/data-addon/` — generated warm-start WCL cache.
- `companion/source/portable/` — portable Windows packaging.

## License

See `LICENSE-SCOPE.md`.
