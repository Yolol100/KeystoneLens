# KeystoneLens

KeystoneLens is a small Warcraft Logs Mythic+ tooltip for World of Warcraft Retail, with a live Windows applicant board.

## In game

KeystoneLens adds one compact Warcraft Logs line to the same tooltip that Raider.IO uses:

- DPS / tank: `Warcraft Logs M+ — DPS 97%`
- healer: `Warcraft Logs M+ — Healing 94%`

When matching preload data exists, the line is inserted immediately below the current Raider.IO M+ score. Raider.IO itself is not modified. Without Raider.IO, the same compact WCL line can still render through KeystoneLens' fallback tooltip hooks.

There is no KeystoneLens score, Blizzard score, confidence label, run-count block or recruitment overlay.

## Live Windows applicant board

The Companion also shows the current Group Finder applicants as a simple live table:

- **Speler** — character + realm;
- **Warcraft Logs** — `DPS 97%` for DPS/tank or `Healing 94%` for healers;
- **Rank** — display-only tier derived directly from that WCL percentile.

Rows with valid WCL data are sorted highest percentile first. Loading, missing and error states stay below valid rows so the list remains readable while lookups are still running.

Rank is not a separate KeystoneLens score. It is only a compact band for the WCL percentile: `S >=95`, `A >=85`, `B >=75`, `C >=50`, `D >=25`, `E >=10`, otherwise `F`.

The existing screenshot/QR discovery path supplies the current applicant identities. The Windows Companion then queries Warcraft Logs directly for those players. Live applicant evidence older than one hour is refreshed from WCL, subject to the existing quota/backoff rules. This means a player can appear immediately in the Windows list without waiting for an in-game addon reload.

## No per-applicant reload

WoW does not live-reload addon files written by an external process. KeystoneLens therefore does not use Companion → Data.lua as fake live IPC.

The normal path is:

1. The Windows Companion maintains a persistent local WCL preload database.
2. Before WoW loads addons, the generated `KeystoneLensCompanionData/Data.lua` is already available.
3. WoW loads that database into Lua memory.
4. A new Group Finder applicant appears.
5. KeystoneLens builds a normalized name + realm + spec + dungeon key.
6. The WCL record is read directly from the in-memory Lua table in O(1).
7. The WCL line appears immediately under Raider.IO.

If an applicant is not in the loaded dataset, KeystoneLens shows no WCL line for that applicant. The Companion can learn the character and publish it for the next WoW start. It never claims that a file written during the current WoW session became live in Lua.

## Preload coverage

The Companion uses the configured WoW region (EU/US/KR/TW/CN) so preload quota is spent only on the region you actually need. Changing region clears incompatible local preload records before a new regional dataset is built.

The Companion grows coverage in two ways:

- applicants discovered through the existing addon-safe QR/screenshot transport;
- small, quota-bounded Warcraft Logs ranking-discovery slices, followed by the same validated per-character WCL query used for applicants.

Ranking data is used only to discover character identities. Tooltip percentiles are written only after the character-specific WCL query succeeds. Refresh is incremental, cached, atomic and capped at 25,000 current-season records. WCL quota use stops early at the configured safety threshold. Discovery now cycles across up to five ranking pages instead of repeating page 1 forever, and the observed hourly quota snapshot expires after the provider reset window.

The dataset stores only the fields required for tooltip lookup: character/realm, spec, current-season dungeon, DPS or healing percentile and timestamp. Credentials remain in the Companion configuration and are never written into WoW addon files.

## Failure behavior

KeystoneLens fails closed:

- no record → no WCL line;
- wrong realm/spec/dungeon/region/season → no WCL line;
- stale or malformed record → no WCL line;
- WCL/API/Companion unavailable → the last valid preload remains usable;
- interrupted writes use atomic replacement and a last-known-good persistent backup.

The QR/screenshot transport remains useful for applicant discovery and future preload learning. It is not the runtime tooltip data source.

## Windows portable build

The portable Windows build bundles a private Python runtime and the dependencies needed for WCL HTTP requests plus QR/screenshot decoding. The build verifies the staged portable package and the complete downloadable ZIP after extraction.

For best coverage, start the Companion before World of Warcraft. Data learned while WoW is already running is prepared for the next WoW start; it does not require a per-applicant reload workflow.

## Verification

GitHub Actions checks:

- Python syntax;
- WoW Lua 5.1 syntax;
- preload persistence/integrity/backup/atomic-write contracts;
- preload refresh, quota and offline contracts;
- a 25,000-record load/memory/O(1)-lookup performance contract;
- Raider.IO tooltip ordering and fallback behavior;
- DPS, healer and tank handling;
- stale, malformed, wrong-region/season/spec/dungeon and cross-realm rejection;
- recycled rows and 30+ rapid applicant identities;
- live Windows applicant sorting/ranking and rendering;
- one-hour live applicant cache freshness;
- Companion shutdown and window restore;
- portable Windows build;
- complete ZIP contents after extraction;
- `git diff --check`.

## Repository

- `addon/KeystoneLensBridge/` — WoW transport + compact in-memory tooltip lookup.
- `companion/source/app/` — Windows Companion, WCL client and persistent preload database.
- `companion/source/data-addon/` — generated WoW preload data addon template.
- `companion/source/portable/` — portable Windows packaging.

## License

See `LICENSE-SCOPE.md`.
