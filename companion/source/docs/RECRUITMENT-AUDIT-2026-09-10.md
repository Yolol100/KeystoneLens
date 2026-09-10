# KeystoneLens recruitment audit matrix — 2026-09-10

This matrix supplements `TESTSCENARIOS.md` for the applicant-list features added in 0.12.8. The explicit product contract is: searchable applicants, class/spec/role filtering, sortable visible columns, optional strict one-row-per-known-spec presentation, persisted preferences, and fail-visible provider errors.

## Current external contracts checked

- Raider.IO Developer API 0.62.5: use the published character profile endpoint; treat HTTP 429 as rate limiting; honor `Retry-After`; public-facing applications using API data must link back to `raider.io`.
  - Source: https://raider.io/api
- Warcraft Logs v2: OAuth 2.0; public `/api/v2/client` uses client credentials; v2 is GraphQL.
  - Source: https://www.warcraftlogs.com/api/docs
- World of Warcraft retail: KeystoneLensBridge currently declares interface `120100` for the live Midnight 12.1 line. Midnight 12.1.5 is still PTR as of this audit and must not be treated as the live interface until Blizzard ships it.
  - Source: https://news.blizzard.com/en-us/article/24298589/blizzcon-2026-midnight-12-1-5-and-more-in-this-weeks-wow-weekly

External facts are time-sensitive. Re-check these sources before a future release.

## Automated recruitment scenarios

| ID | Scenario | Expected result |
| --- | --- | --- |
| R-01 | Role = TANK / HEALER / DPS | Only matching completed applicants remain. |
| R-02 | Class filter | Only matching class remains. |
| R-03 | Spec filter | Only matching known spec remains. |
| R-04 | Combined class + spec + role + search | Filters intersect; no filter silently overrides another. |
| R-05 | Search by player name | Case-insensitive match. |
| R-06 | Search by class name | Case-insensitive match. |
| R-07 | Search by spec name | Case-insensitive match. |
| R-08 | Search by role | Case-insensitive match. |
| R-09 | Search whitespace/control input | Collapsed to one line; bounded to 80 characters. |
| R-10 | Sort `score` ascending/descending | Correct order. |
| R-11 | Sort `role` ascending/descending | Correct order. |
| R-12 | Sort `player` ascending/descending | Correct order. |
| R-13 | Sort `class` ascending/descending | Correct order. |
| R-14 | Sort `spec` ascending/descending | Correct order. |
| R-15 | Sort `rio` ascending/descending | Uses the existing effective Raider.IO value; correct order. |
| R-16 | Sort `wcl` ascending/descending | Correct order; missing WCL values remain last both ways. |
| R-17 | Equal sort values | Stable source order is preserved. |
| R-18 | Invalid sort key | Falls back to the default score sort. |
| R-19 | Unique specs OFF | No deduplication is applied. |
| R-20 | Unique specs ON | Exactly the first sorted applicant per known spec remains. |
| R-21 | Same spec with a provider-error row | Still at most one row for that known spec; active sort chooses the representative. |
| R-22 | Unknown spec IDs in unique mode | Rows remain visible; unknown values are not guessed/grouped. |
| R-23 | Provider error below score floor | Error row stays visible so an outage is not disguised as no applicants. |
| R-24 | Pending enrichment | Row is not presented as a final sortable result. |
| R-25 | Config valid values | Spec/search/unique/sort preferences normalize correctly. |
| R-26 | Config malformed values | Unsafe/unknown values fail closed to documented defaults. |
| R-27 | Config payload | All recruitment preferences survive serialization. |
| R-28 | UI-to-App persistence bridge | UI config and App-owned config update before existing debounced atomic save. |
| R-29 | Spec/class mapping drift | Every supported spec has exactly one known class mapping. |
| R-30 | Sort header accessibility | Sort headers use focusable buttons and expose both direction states. |

## Existing provider/network scenarios that remain mandatory

- Raider.IO: timeout, HTTP 500, malformed error body, HTTP 429, numeric `Retry-After`, HTTP-date `Retry-After`, shared block window, unsupported region, invalid JSON/payload.
- Warcraft Logs: OAuth failure, timeout, malformed JSON, GraphQL errors, missing data, transport 429, quota exhaustion/low budget, schema/data absence, cache/freshness behavior and fallback encounter resolution.
- Missing provider data must remain distinguishable from a real zero score and from a provider error.
- Client shutdown/close paths must remain deterministic and must not continue network work after closure.

These are covered by the repository's existing network, WCL, RIO, lifecycle and regression suites and must remain green together with R-01..R-30.

## Security and release gates

- No client secret in source, logs, package or persisted plaintext config.
- TLS verification remains enabled for live providers.
- Network calls remain bounded by timeouts, retries and rate-limit backoff.
- Production requirements remain pinned; portable runtime remains hash-locked.
- `pip-audit --strict` remains a release/dependency gate.
- CodeQL remains green.
- Lua/Python compile preflights remain green.
- Deterministic release ZIP and independent portable Windows builds remain byte-identical where the existing workflow requires it.
- Repository hygiene, release identity, package contract and artifact verification remain green.

## Manual target-runtime acceptance before calling the product runtime-perfect

These require an actual current WoW + Windows GUI runtime and are not replaceable by mocks or CI:

1. Open the applicant overlay with a real Mythic+ listing and real applicants.
2. Verify search, class, spec and each role filter visually with live rows.
3. Click and keyboard-focus every visible sortable header; verify arrow/direction and row order.
4. Toggle Unique specs and verify no known spec appears twice on-screen.
5. Restart Companion and verify search/spec/unique/sort preferences are restored.
6. Simulate/observe unavailable WCL or Raider.IO and confirm the error is visible without freezing the UI.
7. Open Settings and verify the visible Raider.IO attribution link opens `https://raider.io`.
8. Verify layout at supported Windows scaling/display configurations and with columns hidden/shown.
9. Verify KeystoneLensBridge loads without an outdated-interface block on the current live retail client.

A repository/CI score may be 10/10 only for the controlled evidence layer. A full target-runtime 10/10 additionally requires the manual acceptance above on the current live client.
