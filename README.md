# KeystoneLens 0.12.8

KeystoneLens combines a World of Warcraft Retail Bridge addon with a portable Windows desktop Companion. `main` contains source and release engineering only; generated ZIPs and other build outputs are published as CI/release artifacts rather than committed binaries.

## Repository layout

- `addon/KeystoneLensBridge/` - WoW addon source shipped to CurseForge
- `companion/source/app/` - desktop Companion source and tests
- `companion/source/data-addon/` - generated-data addon template/source
- `companion/source/portable/` - install-free Windows launcher and portable packaging
- `companion/source/runtime/windows/` - canonical Windows Python runtime manifest and hash-locked package graph
- `companion/source/docs/` - release, dependency, privacy, security and acceptance documentation
- `companion/source/scripts/` - deterministic source/CurseForge release and repository validation scripts
- `companion/source/VERSION` - canonical release identity

See `LICENSE-SCOPE.md` for the licensing boundary. The Bridge has an explicit MIT license; no repository-wide Companion license is implied.

## Windows Companion model

The supported Windows distribution is `KeystoneLens-Portable-<VERSION>-Windows-x64.zip`.

Users extract the complete ZIP and start `START-COMPANION.cmd`. No KeystoneLens Setup executable, Windows installation, registry registration, Start-menu registration, administrator rights or separately installed Python are required. The ZIP contains its own private CPython runtime and hash-locked dependencies.

The portable launcher preserves the single-instance guard, verifies the bundled runtime before startup and writes a visible diagnostic log for nonzero startup failures. CI builds and re-extracts the ZIP on `windows-2025`, then verifies the extracted runtime and rejects legacy KeystoneLens installer/launcher/uninstaller/watcher executables.

## Release model

Pull requests and `main` pushes run source, dependency, Lua, Python, deterministic packaging, native Windows and portable-package validation. A `v<VERSION>` tag stages the exact verified source ZIP, CurseForge Bridge ZIP and portable Windows ZIP, generates SHA-256 checksums and GitHub artifact attestations, and creates a draft GitHub Release.

Current source version: **0.12.8**.

## Public release gate

Source/CI readiness is not the same as public production acceptance. Publication still requires:

- tag/version parity;
- deterministic package validation;
- final clean-Windows portable extraction/start/restart/single-instance acceptance;
- final live WoW Retail/Season 2 Bridge, tooltip and screenshot-transport acceptance;
- final CurseForge metadata/version/release-type selection.

The detailed release checklist is in `companion/source/docs/UITGAVE-CHECKLIST.md`.
