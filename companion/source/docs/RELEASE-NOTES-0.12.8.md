# KeystoneLens 0.12.8

0.12.8 is a correctness, Season 2 readiness and release-architecture hardening update. The displayed scoring model remains exactly 50% Raider.IO + 50% Warcraft Logs and no automated Group Finder actions are added.

## Runtime correctness

- Tooltip cache schema v2 remains bound to the exact Group Finder activity, target key level and applicant specialization.
- v2 data uses its own global and clears the legacy name-only cache so rollback fails closed.
- Applicant/listing generations prevent delayed prior-queue snapshots/results from repopulating a newer queue.
- Screenshot fragment delivery remains commit-before-delete and supports concurrent incomplete streams.
- Recruitment capture remains bounded by full-party, active-dungeon and listing lifecycle rules.
- Raider.IO and Warcraft Logs enrichment retains bounded request pacing, retry/quota behavior, cache guards and visible source attribution.
- The Season 2 registry/source transition evidence remains the current scoring source boundary.

## Portable Windows Companion

The Windows distribution is now one extract-only portable ZIP. There is no KeystoneLens Setup program, custom KeystoneLens launcher executable, uninstaller executable or WoW watcher executable.

User flow:

1. download `KeystoneLens-Portable-0.12.8-Windows-x64.zip`;
2. extract the entire archive;
3. double-click `START-COMPANION.cmd`.

No administrator install, registry integration, Start-menu installation or separately installed Python is required.

The ZIP intentionally contains an upstream private CPython 3.13.15 runtime. Its official Python.org build input is pinned by URL + SHA-256 in `runtime/windows-x64.json`. All Python packages are installed from an exact hash-locked dependency graph. Build-only pip command shims/package are removed before the artifact is created; `runtime/python.exe` and `runtime/pythonw.exe` remain because they are required interpreter entry points.

The portable launcher preserves the previous single-instance invariant through the named Windows mutex `KeystoneLens.Companion.Singleton`.

## Repository cleanup

- Removed obsolete `companion/source/installer/` bootstrap/launcher/uninstaller/watcher/signing/build source.
- Removed the obsolete root `executable/` documentation surface.
- Moved runtime dependencies to neutral `companion/source/runtime/` ownership.
- Moved deterministic ZIP creation to a generic script rather than importing it from installer code.
- Removed installer-only Go/CodeQL/native Windows lanes while retaining native Windows Python regression coverage.
- Updated dependency audit/Dependabot/CODEOWNERS/release checks to the portable runtime paths.
- Repository audit now fails if the retired installed-executable stack is reintroduced accidentally.

## Release hardening

- Portable CI builds the Windows ZIP twice from the same tree and requires byte-identical SHA-256 output.
- The exact ZIP is re-extracted and its bundled runtime/import graph is verified again.
- The archive contract rejects all retired custom KeystoneLens executables.
- Core Bridge/source release packaging remains deterministic and is re-tested from the extracted source ZIP.
- Tagged draft releases use exact `v<VERSION>` source and include Bridge/source/portable artifacts, SHA-256 checksums and GitHub attestations.
- GitHub Actions remain pinned to immutable full commit SHAs with `persist-credentials: false`.

## External release gates

A green source/CI run is not a claim that every real desktop/client scenario passed. Clean-Windows first-run/AV behavior, live WoW acceptance, authenticated WCL validation, CurseForge metadata, repository-admin settings and Blizzard policy/legal review remain explicit external gates.
