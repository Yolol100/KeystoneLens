# KeystoneLens 0.12.8

KeystoneLens combines a World of Warcraft Retail Bridge addon with a Windows desktop Companion. The repository now keeps **source and release engineering** on `main`; generated ZIPs, checksums and Windows executables are release outputs rather than tracked source files.

## Repository layout

- `addon/KeystoneLensBridge/` - WoW addon source shipped to CurseForge
- `companion/source/app/` - desktop Companion source and tests
- `companion/source/data-addon/` - generated-data addon template/source
- `companion/source/installer/windows/` - Windows bootstrap, launcher, uninstall and signing/build tooling
- `companion/source/docs/` - release, dependency, privacy, security and acceptance documentation
- `companion/source/scripts/` - deterministic release and repository validation scripts
- `companion/source/VERSION` - canonical release identity

See `LICENSE-SCOPE.md` for the licensing boundary. The Bridge has an explicit MIT license; no repository-wide Companion/installer license is implied.

## Release model

Pull requests and `main` pushes run source, dependency, Lua, Python, deterministic packaging and native Windows validation. Tagged `v<VERSION>` builds additionally require a real Authenticode signing identity before a public Windows release can be created.

Release artifacts are published through GitHub Releases and the Bridge ZIP is the CurseForge upload artifact. The release workflow produces SHA-256 checksums and GitHub artifact attestations from the exact tagged source. It does not commit generated binaries back to `main`.

Current source version: **0.12.8**.

## Public release gate

Source/CI readiness is not the same as public production acceptance. A public tag release requires:

- tag/version parity;
- deterministic package validation;
- valid SHA-256/RFC 3161 Authenticode signatures on all public Windows executables;
- final clean-Windows installer/repair/uninstall acceptance;
- final live WoW Retail/Season 2 Bridge, tooltip and screenshot-transport acceptance;
- final CurseForge metadata/version/release-type selection.

The detailed release checklist is in `companion/source/docs/UITGAVE-CHECKLIST.md`.
