# Companion runtime dependencies — 0.12.8

KeystoneLens Setup uses CPython **3.13.15 x64** in a dedicated per-user KeystoneLens runtime directory. The official python.org installer is downloaded over HTTPS and must match SHA-256:

`edec09c4853aeae9ac36efb8c9f95b6b8e2fee65eee56d9767a8b7c69c574403`

The Windows package install uses `--only-binary=:all: --require-hashes --no-deps` against `installer/windows/requirements-runtime.lock`. The complete runtime graph is explicit:

| Package | Version | Purpose | License |
|---|---:|---|---|
| requests | 2.34.2 | HTTP clients | Apache-2.0 |
| Pillow | 12.3.0 | screenshot/image handling | MIT-CMU |
| zxing-cpp | 3.1.1 | QR decoding | Apache-2.0 |
| charset-normalizer | 3.4.9 | Requests dependency | MIT |
| idna | 3.18 | Requests dependency | BSD-3-Clause |
| urllib3 | 2.7.0 | Requests dependency | MIT |
| certifi | 2026.7.22 | CA bundle | MPL-2.0 |

For the compiled packages, the lock targets the normal CPython 3.13 Windows x64 wheel (`Pillow`, `charset-normalizer`) or the compatible Windows x64 ABI3 wheel (`zxing-cpp`). The remaining wheels are platform-independent. Any package file whose SHA-256 is not listed in the lock is rejected by pip.

`docs/SBOM.cdx.json` contains the same runtime inventory in machine-readable CycloneDX form.
