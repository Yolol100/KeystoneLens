# Contributing to KeystoneLens

KeystoneLens contains a WoW addon and a portable Windows desktop Companion. Changes should preserve release determinism, fail-closed data handling and the separation between source and generated artifacts.

## Source and release rules

- `companion/source/VERSION` is the canonical product version.
- Do not commit generated ZIPs/EXEs, build/release directories, checksums, caches, logs, screenshots, credentials, PFX files or private keys.
- The installed-executable stack was retired. Do not reintroduce `companion/source/installer/`, root `executable/`, `KeystoneLens-Setup.exe` or custom `KeystoneLens.exe` launchers without an explicit architecture decision.
- Keep `addon/KeystoneLensBridge/` authoritative; release validation syncs its source into the Companion source tree for tests/packages.
- Runtime changes must update `companion/source/runtime/windows-x64.json`, the hash-locked runtime requirements and SBOM evidence together where applicable.
- Portable changes must keep the exact extract-only contract, single-instance guard, runtime readback and deterministic double-build gate.

## Validation before a pull request

```bash
python3 companion/source/scripts/audit_repository.py
python3 companion/source/scripts/audit_external_security.py
cd companion/source
python -m pytest -q
python -m compileall -q app/keystonelens_companion
bash scripts/BUILD-RELEASE.sh
```

Portable/runtime changes must also pass `Portable KeystoneLens Companion` and `Windows platform validation`. Dependency changes must pass both dependency-audit lanes. Python source is scanned by CodeQL.

Do not claim live WoW, Warcraft Logs, SmartScreen/AV or clean-Windows acceptance unless it was actually performed.
