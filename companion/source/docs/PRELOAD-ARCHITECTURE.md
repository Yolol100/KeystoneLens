# KeystoneLens preload architecture

## Runtime invariant

The Windows Companion is not a live IPC channel into WoW Lua.

World of Warcraft loads addon files at addon load time. A Companion write to
`KeystoneLensCompanionData/Data.lua` while WoW is already running prepares the
next addon load. KeystoneLens never treats that write as immediately visible in
the current Lua state.

The runtime tooltip source is `_G.KeystoneLensPreloadV4`, already resident in
WoW memory.

## Lookup contract

Applicant lookup key:

`lower(name-realm) | specID | normalized-current-dungeon`

Unit tooltip lookup key:

`lower(name-realm) | normalized-current-dungeon`

The generated tables are direct-key indexes. No tooltip hover scans the full
preload database.

Every lookup fails closed when any of these are wrong or unavailable:

- region;
- active season;
- character/realm;
- specialization for applicants;
- current dungeon;
- metric code;
- percentile range;
- generated/fetched freshness.

A unit index is emitted only when the character+dungeon record is unambiguous
for one specialization. Multi-spec unit records are omitted instead of guessed.

## Current data contract

Dataset version: 4.

Current season: Midnight Season 2.

Persistent Companion fields:

- full character name including realm;
- spec ID;
- canonical dungeon;
- season;
- DPS/HPS metric;
- percentile;
- fetched timestamp.

Generated WoW tuples are compact:

`{"D"|"H", percentile, fetchedAt}`

Credentials are never serialized to the WoW data addon.

## Coverage strategy

The persistent store is capped at 25,000 fresh records.

Coverage grows from two sources:

1. applicants actually observed through the existing QR/screenshot discovery
   transport;
2. bounded WCL `Encounter.characterRankings` discovery slices.

Ranking discovery is identity discovery only. A discovered name/realm is fed
back through KeystoneLens' existing character-specific WCL query. Only the
validated result of that query is eligible for the preload database.

The refresher:

- processes at most four dungeon/spec slices per run;
- samples at most 50 identities per slice;
- reuses WCL batching of at most 10 characters;
- stops discovery at 80% observed hourly quota use;
- retains existing WCL 429 backoff and cache behavior;
- advances a persistent cursor so later refreshes cover different slices;
- refreshes at most once per hour while the authenticated Companion remains open.

This intentionally does not attempt to download every WoW character.

## File safety

Persistent JSON uses temp-file replacement and a last-known-good backup.

Generated `Data.lua` also uses temp-file replacement. A corrupt/missing
persistent primary can recover from the backup; a missing/corrupt WoW dataset
causes no tooltip line until the Companion republishes a valid dataset.

## Cache miss behavior

If a new applicant is absent from the dataset already loaded by WoW:

- current tooltip: no WCL line;
- Companion: may resolve and persist the record;
- current WoW process: does not pretend the file update is live;
- next WoW addon load: record becomes eligible.

There is no per-applicant reload workflow.

## Security and ToS boundary

Not used:

- DLL injection;
- process-memory writes;
- keyboard/clipboard automation;
- external overlay as the WCL tooltip source;
- credentials in addon files.

The QR/screenshot path remains only for applicant discovery/learning.

## External architecture references

The design follows the same broad safe pattern visible in current ecosystem
tools: Raider.IO ships frequent database refresh releases, Umbra ships static
addon data with no addon network calls, and Archon installs/updates tooltip
datasets through its desktop uploader.

No third-party source code is copied into this implementation.
