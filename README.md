# KeystoneLens 0.12.8

KeystoneLens combines a World of Warcraft Retail Bridge addon with a Windows desktop Companion. The repository keeps source and release engineering on `main`; generated ZIPs, checksums and Windows executables are release outputs rather than tracked source files.

## Repository layout

- `addon/KeystoneLensBridge/` - WoW addon source shipped to CurseForge
- `companion/source/app/` - desktop Companion source and tests
- `companion/source/data-addon/` - generated-data addon template/source
- `companion/source/installer/windows/` - installed Windows bootstrap, launcher, uninstall and signing/build tooling
- `companion/source/portable/` - install-free Windows Companion build and launcher tooling
- `companion/source/docs/` - release, dependency, privacy, security and acceptance documentation
- `companion/source/scripts/` - deterministic release and repository validation scripts
- `companion/source/VERSION` - canonical release identity

See `LICENSE-SCOPE.md` for the licensing boundary. The Bridge has an explicit MIT license; no repository-wide Companion/installer license is implied.

## Release model

Pull requests and `main` pushes run source, dependency, Lua, Python, deterministic packaging, native Windows validation and the portable Windows build. The portable build uses the same canonical Python runtime and hash-locked dependency set as the installed Companion and is verified again after its ZIP is extracted.

Tagged `v<VERSION>` builds additionally require a real Authenticode signing identity for KeystoneLens-produced Windows executables. The draft GitHub Release contains the CurseForge Bridge ZIP, reproducible source ZIP, verified portable Windows ZIP, signed Windows Setup, release evidence, SHA-256 checksums and GitHub artifact attestations. Generated release files are never committed back to `main`.

Current source version: **0.12.8**.

## Public release gate

Source/CI readiness is not the same as public production acceptance. A public tag release requires:

- tag/version parity and deterministic package validation;
- valid SHA-256/RFC 3161 Authenticode signatures on KeystoneLens-produced public Windows executables;
- final clean-Windows installer/repair/uninstall acceptance;
- final clean-Windows portable extract/start and Defender/SmartScreen acceptance;
- final live WoW Retail/Season 2 Bridge, tooltip and screenshot-transport acceptance;
- final CurseForge metadata/version/release-type selection.

The detailed release checklist is in `companion/source/docs/UITGAVE-CHECKLIST.md`.
