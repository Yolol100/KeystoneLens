# Companion runtime dependencies — 0.12.8

The portable Windows build stages CPython **3.13.15 x64** into the ZIP. The official python.org installer is build input only and must match the SHA-256 recorded in `runtime/windows-x64.json`:

`edec09c4853aeae9ac36efb8c9f95b6b8e2fee65eee56d9767a8b7c69c574403`

Runtime packages are installed with `--only-binary=:all: --require-hashes --no-deps` from `runtime/requirements-runtime.lock`:

| Package | Version | Purpose | License |
|---|---:|---|---|
| requests | 2.34.2 | HTTP clients | Apache-2.0 |
| Pillow | 12.3.0 | screenshot/image handling | MIT-CMU |
| zxing-cpp | 3.1.1 | QR decoding | Apache-2.0 |
| charset-normalizer | 3.4.9 | Requests dependency | MIT |
| idna | 3.18 | Requests dependency | BSD-3-Clause |
| urllib3 | 2.7.0 | Requests dependency | MIT |
| certifi | 2026.7.22 | CA bundle | MPL-2.0 |

The builder needs pip only while assembling `packages/`. Before the ZIP is created it removes the runtime `Scripts` directory and installed pip package metadata, so package-management command executables are not part of the delivered runtime. `python.exe` and `pythonw.exe` remain because they are the required upstream interpreter/runtime entry points used by `START-COMPANION.cmd`.

`docs/SBOM.cdx.json` records the same CPython source hash and runtime dependency inventory in CycloneDX form.
