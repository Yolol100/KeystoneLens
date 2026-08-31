# Third-party notices — KeystoneLens Companion 0.12.8

KeystoneLens Companion uses the following third-party runtime components from their official distributions:

- CPython 3.13.15 — Python Software Foundation License Version 2.
- Requests 2.34.2 — Apache-2.0.
- Pillow 12.3.0 — MIT-CMU.
- zxing-cpp 3.1.1 — Apache-2.0.
- charset-normalizer 3.4.9 — MIT.
- idna 3.18 — BSD-3-Clause.
- urllib3 2.7.0 — MIT.
- certifi 2026.7.22 — MPL-2.0.

The official CPython Windows x64 build input is pinned by URL and SHA-256 in `runtime/windows-x64.json`. Python package versions and accepted Windows wheel hashes are locked in `runtime/requirements-runtime.lock`.

The install-free portable ZIP carries this notice. Normal package metadata and upstream license information remain alongside the runtime packages where required; pip-generated console scripts, `RECORD` files and bytecode caches that are not needed for KeystoneLens execution are removed before the deterministic archive is created.
